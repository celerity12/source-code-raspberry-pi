#!/usr/bin/env python3
"""
Pi-hole Analytics - Device Resolver

Identifies devices by querying Pi-hole's network table (MAC + hostname + vendor)
instead of relying on a static IP→name map that breaks every time DHCP reassigns.

Resolution priority (highest to lowest):
  1. MAC-based custom name  — client_macs in config (stable across IP changes)
  2. Hostname pattern match — client_hostnames in config ("johns-iphone" → "John's iPhone")
  3. IP-based custom name   — clients in config (legacy, still supported)
  4. Auto-detected type     — inferred from hostname keywords + hardware vendor string
  5. Raw hostname           — as broadcast by the device via mDNS / DHCP
  6. Raw IP                 — last resort
"""

import logging
import requests
import sqlite3
from datetime import datetime
from urllib.parse import quote

log = logging.getLogger(__name__)


# ── Auto-detection: hostname keywords → device type label ────────────────────
# Each entry is ([keywords_to_match], "Human Label").
# Keywords are matched as substrings (case-insensitive) inside the hostname.
# Checked in order; first match wins.

HOSTNAME_TYPE_PATTERNS = [
    # Apple devices
    (["iphone"],                        "iPhone"),
    (["ipad"],                          "iPad"),
    (["macbook"],                       "MacBook"),
    (["imac"],                          "iMac"),
    (["mac-mini", "macmini"],           "Mac Mini"),
    (["appletv", "apple-tv"],           "Apple TV"),
    (["homepod"],                       "HomePod"),
    (["applewatch"],                    "Apple Watch"),
    # Google / Android
    (["pixel"],                         "Google Pixel"),
    (["galaxy", "samsung"],             "Samsung Phone"),
    (["android"],                       "Android Device"),
    (["chromecast"],                    "Chromecast"),
    (["nest-hub", "nest-mini"],         "Google Nest"),
    # Amazon
    (["echo-", "alexa"],                "Amazon Echo"),
    (["fire-tv", "firetv", "firestick"],"Fire TV"),
    (["kindle"],                        "Kindle"),
    (["ring"],                          "Ring Device"),
    # Gaming
    (["playstation", "ps4", "ps5"],     "PlayStation"),
    (["xbox"],                          "Xbox"),
    (["switch", "nintendo"],            "Nintendo Switch"),
    (["steam-deck"],                    "Steam Deck"),
    # Streaming / Smart TV
    (["roku"],                          "Roku"),
    (["bravia"],                        "Sony Bravia TV"),
    (["tizen"],                         "Samsung TV"),
    (["webos"],                         "LG TV"),
    (["vizio"],                         "Vizio TV"),
    (["smarttv", "smart-tv"],           "Smart TV"),
    # Network gear
    (["router", "gateway"],             "Router"),
    (["unifi", "ubiquiti"],             "Ubiquiti AP"),
    (["access-point", "accesspoint"],   "Access Point"),
    # Smart home
    (["philips-hue", "-hue-"],          "Philips Hue"),
    (["kasa", "smartplug", "tp-plug"],  "Smart Plug"),
    (["thermostat"],                    "Thermostat"),
    (["wemo"],                          "Wemo Device"),
    # Computers (raspberry before nas so "raspberrypi-nas" → Raspberry Pi)
    (["raspberry", "rpi"],              "Raspberry Pi"),
    (["macpro", "mac-pro"],             "Mac Pro"),
    (["ubuntu", "debian"],              "Linux PC"),
    (["desktop", "workstation"],        "Desktop PC"),
    (["laptop"],                        "Laptop"),
    # Storage / other
    (["synology", "nas"],               "NAS"),
    (["printer", "print"],              "Printer"),
    (["camera", "cam"],                 "Camera"),
    (["tablet"],                        "Tablet"),
    (["watch"],                         "Smartwatch"),
    (["speaker"],                       "Smart Speaker"),
]

# Hardware vendor string → device type hint (Pi-hole's hwVendor field)
# Checked only when hostname patterns produce no result.
VENDOR_TYPE_HINTS = [
    ("apple",       "Apple Device"),
    ("samsung",     "Samsung Device"),
    ("amazon",      "Amazon Device"),
    ("google",      "Google Device"),
    ("microsoft",   "Windows PC"),
    ("nintendo",    "Nintendo Device"),
    ("sony",        "Sony Device"),
    ("espressif",   "IoT Device"),       # ESP8266 / ESP32 microcontrollers
    ("tuya",        "Smart Home Device"),
    ("raspberry",   "Raspberry Pi"),
    ("tp-link",     "TP-Link Device"),
    ("ubiquiti",    "Ubiquiti Device"),
    ("netgear",     "Netgear Device"),
    ("synology",    "Synology NAS"),
    ("roku",        "Roku"),
    ("vizio",       "Vizio TV"),
    ("lgelectronics", "LG Device"),
    ("echostar",    "Dish / EchoStar"),
    ("philips",     "Philips Device"),
    ("amazon",      "Amazon Device"),
    ("intel",       "Intel Device"),
    ("murata",      "IoT Device"),       # common Wi-Fi module used in IoT gear
]


def detect_device_type(hostname: str, vendor: str = "") -> str:
    """
    Infer a human-readable device type from hostname and/or hardware vendor.
    Returns an empty string when nothing matches (caller falls through to hostname/IP).
    """
    h = (hostname or "").lower()
    v = (vendor   or "").lower()

    if h:
        for keywords, label in HOSTNAME_TYPE_PATTERNS:
            if any(kw in h for kw in keywords):
                return label

    if v:
        for kw, label in VENDOR_TYPE_HINTS:
            if kw in v:
                return label

    return ""


def _is_pihole_v6(cfg: dict) -> bool:
    """Return True if the Pi-hole instance exposes the v6 REST API.
    v6 serves /api/info/version with any HTTP response (200 or 401).
    v5 returns 404 or does not route that path at all.
    """
    try:
        r = requests.get(f"{cfg['pihole']['host']}/api/info/version", timeout=5)
        return r.status_code in (200, 401)
    except Exception:
        return False


def _get_v6_sid(cfg: dict) -> str:
    """Authenticate with Pi-hole v6 and return a session ID.
    Tries password first (v6 uses the web password), then api_token as fallback."""
    base = cfg["pihole"]["host"]
    for cred in filter(None, [
        cfg["pihole"].get("password", ""),
        cfg["pihole"].get("api_token", ""),
    ]):
        resp = requests.post(f"{base}/api/auth", json={"password": cred}, timeout=10)
        if resp.ok:
            sid = resp.json().get("session", {}).get("sid", "")
            if sid:
                return sid
    raise ValueError("Pi-hole v6 auth returned no session ID — check password/api_token in config")


def _fetch_network_devices_v6(cfg: dict) -> dict:
    """Fetch network devices from Pi-hole v6 REST API."""
    base = cfg["pihole"]["host"]
    try:
        sid = _get_v6_sid(cfg)
    except Exception as e:
        log.warning(f"Could not authenticate with Pi-hole v6: {e}")
        return {}

    try:
        resp = requests.get(f"{base}/api/network/devices",
                            headers={"X-FTL-SID": sid}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning(f"Could not fetch Pi-hole v6 network devices: {e}")
        return {}

    result = {}
    for device in data.get("devices", []):
        mac    = (device.get("hwaddr")    or "").upper().strip()
        vendor = (device.get("macVendor") or "").strip()
        ips    = device.get("ips", [])
        hostname = (ips[0].get("name") or "").strip() if ips else ""

        for ip_entry in ips:
            ip = (ip_entry.get("ip") or "").strip()
            if ip:
                result[ip] = {"mac": mac, "hostname": hostname, "vendor": vendor}

    log.info(f"Pi-hole v6 network devices loaded: {len(result)} entries")
    return result


def fetch_network_devices(cfg: dict) -> dict:
    """
    Query Pi-hole for per-device MAC, hostname, and hardware vendor.
    Supports Pi-hole v5 (/admin/api.php) and v6 (/api/network/devices).

    Returns {ip: {"mac": ..., "hostname": ..., "vendor": ...}}
    Returns {} gracefully on any error — callers must handle empty registry.
    """
    if _is_pihole_v6(cfg):
        return _fetch_network_devices_v6(cfg)

    # ── Pi-hole v5 path ───────────────────────────────────────────────────────
    base  = cfg["pihole"]["host"] + cfg["pihole"].get("api_path", "/admin/api.php")
    token = cfg["pihole"]["api_token"]

    try:
        resp = requests.get(f"{base}?network&auth={quote(token, safe='')}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning(f"Could not fetch Pi-hole network table: {e}")
        return {}

    result = {}
    for entry in data.get("network", []):
        ips      = entry.get("ip")   or []
        names    = entry.get("name") or []
        mac      = (entry.get("macaddr")  or "").upper().strip()
        vendor   = (entry.get("hwVendor") or "").strip()
        hostname = names[0].strip() if names else ""

        for ip in ips:
            ip = (ip or "").strip()
            if ip:
                result[ip] = {"mac": mac, "hostname": hostname, "vendor": vendor}

    log.info(f"Pi-hole network table loaded: {len(result)} device-IP entries")
    return result


def refresh_device_registry(conn, cfg: dict):
    """
    Pull the current Pi-hole network table and upsert into the device_registry
    table.  Called once per fetch run before processing query rows.
    last_ip / hostname / device_type are always updated.
    custom_name is set from client_macs config when provided; never cleared once set.
    """
    devices = fetch_network_devices(cfg)
    if not devices:
        return

    # Build normalised MAC->name lookup from config for fast access
    client_macs = cfg.get("client_macs") or {}
    mac_names   = {k.lower(): v for k, v in client_macs.items()}

    now = datetime.now().isoformat()
    for ip, info in devices.items():
        mac         = info["mac"] or ip    # use IP as surrogate key if MAC absent
        device_type = detect_device_type(info["hostname"], info["vendor"])
        # Resolve custom_name from config client_macs (empty string = no override)
        custom_name = mac_names.get(mac.lower(), "") if mac else ""

        conn.execute("""
            INSERT INTO device_registry (mac, last_ip, hostname, device_type, custom_name, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                last_ip     = excluded.last_ip,
                hostname    = excluded.hostname,
                device_type = excluded.device_type,
                last_seen   = excluded.last_seen,
                custom_name = CASE
                    WHEN excluded.custom_name != "" THEN excluded.custom_name
                    ELSE device_registry.custom_name
                END
        """, (mac, ip, info["hostname"], device_type, custom_name, now))

    # Second pass: ensure every client_macs entry exists in device_registry
    # even if Pi-hole has never reported that MAC in its network table.
    for mac_raw, name in client_macs.items():
        mac_norm = mac_raw.upper()
        conn.execute("""
            INSERT INTO device_registry (mac, last_ip, hostname, device_type, custom_name, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                custom_name = excluded.custom_name
        """, (mac_norm, "", "", "", name, now))

    conn.commit()

    # Backfill client_name in queries/daily_summary for any named device
    # whose IP is now known — catches rows stored before config names were added.
    conn.executescript("""
        UPDATE queries
        SET client_name = (
            SELECT custom_name FROM device_registry
            WHERE last_ip = queries.client_ip AND custom_name != '' AND last_ip != ''
        )
        WHERE client_ip IN (
            SELECT last_ip FROM device_registry WHERE custom_name != '' AND last_ip != ''
        )
          AND client_name != (
            SELECT custom_name FROM device_registry
            WHERE last_ip = queries.client_ip AND custom_name != '' AND last_ip != ''
          );

        UPDATE daily_summary
        SET client_name = (
            SELECT custom_name FROM device_registry
            WHERE last_ip = daily_summary.client_ip AND custom_name != '' AND last_ip != ''
        )
        WHERE client_ip IN (
            SELECT last_ip FROM device_registry WHERE custom_name != '' AND last_ip != ''
        );
    """)
    conn.commit()
    log.info(f"Device registry refreshed: {len(devices)} entries, {len(client_macs)} config MACs")


def build_registry_map(conn) -> dict:
    """
    Load device_registry into an {ip: {...}} dict for O(1) per-query lookup.
    Called once per fetch run; result is passed down to store_queries.
    """
    rows = conn.execute(
        "SELECT last_ip, mac, hostname, device_type, custom_name "
        "FROM device_registry"
    ).fetchall()

    return {
        row["last_ip"]: {
            "mac":         (row["mac"]         or ""),
            "hostname":    (row["hostname"]     or ""),
            "device_type": (row["device_type"]  or ""),
            "custom_name": (row["custom_name"]  or ""),
        }
        for row in rows
    }


def resolve_client(client_ip: str, cfg: dict, registry: dict) -> str:
    """
    Return the best human-readable name for a client IP address.

    Args:
        client_ip: The raw IP from the Pi-hole query row.
        cfg:       Loaded config dict (may contain client_macs, client_hostnames, clients).
        registry:  Pre-loaded device registry dict from build_registry_map().

    Priority order:
        1  MAC-based custom name  (client_macs in config)
        2  Hostname pattern match (client_hostnames in config)
        3  IP-based custom name   (clients in config — legacy)
        4  Auto-detected type + hostname
        5  Raw hostname
        6  Raw IP
    """
    device   = registry.get(client_ip, {})
    mac      = device.get("mac",         "").upper()
    hostname = device.get("hostname",    "").lower()
    dtype    = device.get("device_type", "")

    # 1 — MAC-based name (survives DHCP reassignment)
    # cfg values may be None when config.yaml has "client_macs:" with no entries
    if mac:
        client_macs = cfg.get("client_macs") or {}
        for key in (mac, mac.lower()):
            if key in client_macs:
                return client_macs[key]

    # 2 — Hostname pattern (e.g. "johns-iphone" → "John's iPhone")
    if hostname:
        for pattern, name in (cfg.get("client_hostnames") or {}).items():
            if pattern.lower() in hostname:
                return name

    # 3 — Legacy IP-based name (backward-compatible with old config)
    if client_ip in (cfg.get("clients") or {}):
        return cfg["clients"][client_ip]

    # 4 — Auto-detected device type
    if dtype and hostname:
        return f"{hostname} ({dtype})"
    if dtype:
        return dtype

    # 5 — Raw hostname (at least human-readable)
    if hostname:
        return hostname

    # 6 — Raw IP (last resort)
    return client_ip
