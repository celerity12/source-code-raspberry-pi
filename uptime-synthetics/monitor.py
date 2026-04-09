#!/usr/bin/env python3
"""
up_synthetics — Pi-hole Stack Health Monitor
Checks all services running on the Raspberry Pi and sends
a daily summary + immediate alerts via Telegram and Email.

Services checked:
  - Pi-hole DNS (port 53)
  - Pi-hole Admin UI (port 80)
  - Analytics Dashboard (port 8080)
  - MCP Telegram Bot (systemd: pihole-mcp-watch)
  - Samba NAS (port 445)
  - Tailscale VPN
  - All pihole-analytics systemd timers
  - Disk / RAM / CPU / temperature
"""

import os
import sys
import socket
import subprocess
import smtplib
import logging
import requests
import yaml
from datetime import datetime
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "monitor.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("up_synthetics")

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log.error(f"Config not found: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ── Check helpers ─────────────────────────────────────────────────────────────

def check_port(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    """Return (ok, message) for a TCP port check."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"port {port} reachable"
    except OSError as e:
        return False, f"port {port} unreachable: {e}"


def check_http(url: str, timeout: float = 8.0, expect_status: int = None) -> tuple[bool, str]:
    """Return (ok, message) for an HTTP reachability check."""
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        if expect_status and r.status_code != expect_status:
            return False, f"HTTP {r.status_code} (expected {expect_status})"
        if r.status_code >= 500:
            return False, f"HTTP {r.status_code} server error"
        return True, f"HTTP {r.status_code} OK"
    except requests.exceptions.ConnectionError:
        return False, "connection refused"
    except requests.exceptions.Timeout:
        return False, "timed out"
    except Exception as e:
        return False, str(e)


def check_systemd(service: str) -> tuple[bool, str]:
    """Return (ok, message) for a systemd service/timer active state."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5
        )
        state = result.stdout.strip()
        if state == "active":
            return True, "active"
        return False, f"state: {state}"
    except Exception as e:
        return False, f"error: {e}"


def check_tailscale() -> tuple[bool, str]:
    """Check if Tailscale is up and has a peer connection."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=8
        )
        if result.returncode != 0:
            return False, "tailscale not running"
        import json
        data = json.loads(result.stdout)
        backend = data.get("BackendState", "")
        if backend == "Running":
            peers = len(data.get("Peer", {}))
            return True, f"running, {peers} peer(s)"
        return False, f"backend state: {backend}"
    except FileNotFoundError:
        return False, "tailscale not installed"
    except Exception as e:
        return False, str(e)


def check_disk(path: str = "/", warn_pct: int = 80, crit_pct: int = 90) -> tuple[bool, str, str]:
    """Return (ok, message, level) for disk usage."""
    try:
        result = subprocess.run(
            ["df", "-h", path], capture_output=True, text=True
        )
        lines = result.stdout.strip().split("\n")
        pct_str = lines[1].split()[4].replace("%", "")
        pct = int(pct_str)
        msg = f"{pct}% used"
        if pct >= crit_pct:
            return False, msg, "critical"
        if pct >= warn_pct:
            return True, msg, "warning"
        return True, msg, "ok"
    except Exception as e:
        return False, str(e), "critical"


def check_ram(warn_pct: int = 80, crit_pct: int = 90) -> tuple[bool, str, str]:
    """Return (ok, message, level) for RAM usage."""
    try:
        result = subprocess.run(["free", "-m"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")
        parts = lines[1].split()
        total, used = int(parts[1]), int(parts[2])
        pct = round(used / total * 100)
        msg = f"{pct}% used ({used}/{total} MB)"
        if pct >= crit_pct:
            return False, msg, "critical"
        if pct >= warn_pct:
            return True, msg, "warning"
        return True, msg, "ok"
    except Exception as e:
        return False, str(e), "critical"


def check_cpu_temp() -> tuple[bool, str, str]:
    """Return (ok, message, level) for CPU temperature."""
    try:
        result = subprocess.run(
            ["cat", "/sys/class/thermal/thermal_zone0/temp"],
            capture_output=True, text=True
        )
        temp = int(result.stdout.strip()) / 1000
        msg = f"{temp:.1f}°C"
        if temp >= 80:
            return False, msg, "critical"
        if temp >= 70:
            return True, msg, "warning"
        return True, msg, "ok"
    except Exception as e:
        return False, str(e), "critical"


def check_nas_mount(mount: str = "/mnt/nas") -> tuple[bool, str]:
    """Check if NAS drive is mounted."""
    try:
        result = subprocess.run(
            ["mountpoint", "-q", mount],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            # Check free space on NAS
            df = subprocess.run(["df", "-h", mount], capture_output=True, text=True)
            avail = df.stdout.strip().split("\n")[1].split()[3]
            return True, f"mounted, {avail} free"
        return False, f"{mount} not mounted"
    except Exception as e:
        return False, str(e)


# ── Run all checks ────────────────────────────────────────────────────────────

def run_all_checks(cfg: dict) -> list[dict]:
    """Run every check and return a list of result dicts."""
    pi_host = cfg.get("pi_host", "localhost")
    dashboard_url = cfg.get("dashboard_url", f"http://{pi_host}:8080")
    pihole_url = cfg.get("pihole_url", f"http://{pi_host}/admin")
    nas_mount = cfg.get("nas_mount", "/mnt/nas")

    results = []

    def add(name: str, category: str, ok: bool, msg: str, level: str = None):
        if level is None:
            level = "ok" if ok else "critical"
        results.append({
            "name": name,
            "category": category,
            "ok": ok,
            "msg": msg,
            "level": level,
        })

    # ── Pi-hole ───────────────────────────────────────────────
    ok, msg = check_port(pi_host, 53)
    add("Pi-hole DNS", "Pi-hole", ok, msg)

    ok, msg = check_http(pihole_url)
    add("Pi-hole Admin UI", "Pi-hole", ok, msg)

    # ── Analytics Dashboard ───────────────────────────────────
    ok, msg = check_http(dashboard_url)
    add("Analytics Dashboard (HTTP)", "Analytics", ok, msg)

    ok, msg = check_systemd("pihole-analytics-dashboard")
    add("Analytics Dashboard (systemd)", "Analytics", ok, msg)

    # ── Analytics timers ──────────────────────────────────────
    for timer in [
        "pihole-analytics-fetch.timer",
        "pihole-analytics-daily.timer",
        "pihole-analytics-weekly.timer",
        "pihole-analytics-monthly.timer",
        "pihole-analytics-download.timer",
        "pihole-analytics-sysupdate.timer",
    ]:
        ok, msg = check_systemd(timer)
        add(timer, "Timers", ok, msg)

    # ── MCP Telegram Bot ──────────────────────────────────────
    ok, msg = check_systemd("pihole-mcp-watch")
    add("MCP Telegram Bot (systemd)", "MCP Bot", ok, msg)

    # ── NAS ───────────────────────────────────────────────────
    ok, msg = check_port(pi_host, 445)
    add("Samba NAS (port 445)", "NAS", ok, msg)

    ok, msg = check_systemd("smbd")
    add("Samba smbd (systemd)", "NAS", ok, msg)

    ok, msg = check_nas_mount(nas_mount)
    add(f"NAS drive ({nas_mount})", "NAS", ok, msg)

    # ── Tailscale ─────────────────────────────────────────────
    ok, msg = check_tailscale()
    add("Tailscale VPN", "Network", ok, msg)

    # ── System resources ──────────────────────────────────────
    ok, msg, level = check_disk("/")
    add("Root disk (/)", "System", ok, msg, level)

    ok, msg, level = check_disk(nas_mount)
    add(f"NAS disk ({nas_mount})", "System", ok, msg, level)

    ok, msg, level = check_ram()
    add("RAM usage", "System", ok, msg, level)

    ok, msg, level = check_cpu_temp()
    add("CPU temperature", "System", ok, msg, level)

    return results


# ── Reporting ─────────────────────────────────────────────────────────────────

def build_telegram_message(results: list[dict], mode: str = "daily") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    failures = [r for r in results if not r["ok"]]
    warnings = [r for r in results if r["ok"] and r["level"] == "warning"]
    ok_count = sum(1 for r in results if r["ok"] and r["level"] == "ok")

    if mode == "alert":
        header = f"🚨 <b>SERVICE DOWN ALERT — {now}</b>\n"
    else:
        if failures:
            header = f"🔴 <b>Daily Health Report — {now}</b>\n"
        elif warnings:
            header = f"🟡 <b>Daily Health Report — {now}</b>\n"
        else:
            header = f"✅ <b>Daily Health Report — {now}</b>\n"

    summary = (
        f"\n📊 <b>Summary:</b> "
        f"{ok_count} OK  |  {len(warnings)} warnings  |  {len(failures)} failures\n"
    )

    # Group by category
    categories: dict[str, list] = {}
    for r in results:
        categories.setdefault(r["category"], []).append(r)

    body_lines = []
    for cat, items in categories.items():
        cat_ok = all(i["ok"] for i in items)
        cat_icon = "✅" if cat_ok else "❌"
        body_lines.append(f"\n{cat_icon} <b>{cat}</b>")
        for item in items:
            icon = "✅" if item["ok"] else ("⚠️" if item["level"] == "warning" else "❌")
            body_lines.append(f"  {icon} {item['name']}: <i>{item['msg']}</i>")

    return header + summary + "\n".join(body_lines)


def build_email_html(results: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    failures = [r for r in results if not r["ok"]]
    warnings = [r for r in results if r["ok"] and r["level"] == "warning"]
    ok_count = sum(1 for r in results if r["ok"] and r["level"] == "ok")
    total = len(results)

    status_color = "#cf222e" if failures else ("#b45309" if warnings else "#1a7f37")
    status_text = "ISSUES DETECTED" if failures else ("WARNINGS" if warnings else "ALL SYSTEMS OK")

    rows = ""
    current_cat = ""
    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            rows += f"""
            <tr>
              <td colspan="3" style="background:#f6f8fa;padding:8px 12px;
                  font-weight:bold;font-size:13px;color:#57606a;
                  border-top:2px solid #d0d7de;">{current_cat}</td>
            </tr>"""
        icon = "✅" if r["ok"] and r["level"] == "ok" else ("⚠️" if r["level"] == "warning" else "❌")
        row_bg = "#fff0f0" if not r["ok"] else ("#fffbeb" if r["level"] == "warning" else "#ffffff")
        rows += f"""
            <tr style="background:{row_bg}">
              <td style="padding:7px 12px;font-size:14px;">{icon}</td>
              <td style="padding:7px 12px;font-size:14px;">{r['name']}</td>
              <td style="padding:7px 12px;font-size:13px;color:#57606a;">{r['msg']}</td>
            </tr>"""

    alert_banner = ""
    if failures:
        items_html = "".join(f"<li>{r['name']}: {r['msg']}</li>" for r in failures)
        alert_banner = f"""
        <div style="background:#fff0f0;border:1px solid #fca5a5;border-left:4px solid #cf222e;
                    border-radius:6px;padding:12px 16px;margin-bottom:20px;">
          <strong style="color:#b91c1c;">Services Down ({len(failures)})</strong>
          <ul style="margin:8px 0 0 16px;color:#7f1d1d;font-size:14px;">{items_html}</ul>
        </div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f6f8fa;
             color:#1f2328;padding:16px;font-size:15px;">
  <div style="max-width:680px;margin:0 auto;">

    <div style="background:linear-gradient(135deg,#0969da,#0550ae);color:#fff;
                padding:20px 18px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0 0 4px;font-size:22px;">Pi-hole Stack — Health Report</h1>
      <p style="margin:0;opacity:.85;font-size:14px;">{now}</p>
    </div>

    <div style="background:#fff;padding:20px;border:1px solid #d0d7de;border-top:none;">

      <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;">
        <div style="flex:1;min-width:130px;background:#f6f8fa;border:1px solid #d0d7de;
                    border-radius:8px;padding:14px;text-align:center;">
          <div style="font-size:28px;font-weight:bold;color:#1a7f37;">{ok_count}</div>
          <div style="font-size:13px;color:#57606a;">Passing</div>
        </div>
        <div style="flex:1;min-width:130px;background:#f6f8fa;border:1px solid #d0d7de;
                    border-radius:8px;padding:14px;text-align:center;">
          <div style="font-size:28px;font-weight:bold;color:#b45309;">{len(warnings)}</div>
          <div style="font-size:13px;color:#57606a;">Warnings</div>
        </div>
        <div style="flex:1;min-width:130px;background:#f6f8fa;border:1px solid #d0d7de;
                    border-radius:8px;padding:14px;text-align:center;">
          <div style="font-size:28px;font-weight:bold;color:#cf222e;">{len(failures)}</div>
          <div style="font-size:13px;color:#57606a;">Failures</div>
        </div>
        <div style="flex:1;min-width:130px;background:{status_color};
                    border-radius:8px;padding:14px;text-align:center;">
          <div style="font-size:13px;font-weight:bold;color:#fff;">{status_text}</div>
          <div style="font-size:12px;color:rgba(255,255,255,.8);">{total} checks total</div>
        </div>
      </div>

      {alert_banner}

      <table style="width:100%;border-collapse:collapse;border:1px solid #d0d7de;
                    border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#f6f8fa;">
            <th style="padding:10px 12px;text-align:left;font-size:13px;
                       color:#57606a;border-bottom:2px solid #d0d7de;width:40px;"></th>
            <th style="padding:10px 12px;text-align:left;font-size:13px;
                       color:#57606a;border-bottom:2px solid #d0d7de;">Service</th>
            <th style="padding:10px 12px;text-align:left;font-size:13px;
                       color:#57606a;border-bottom:2px solid #d0d7de;">Status</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>

      <p style="margin-top:20px;font-size:12px;color:#8c959f;text-align:center;">
        Generated by up_synthetics · Raspberry Pi Health Monitor
      </p>
    </div>
  </div>
</body></html>"""


# ── Notification senders ──────────────────────────────────────────────────────

def send_telegram(cfg: dict, message: str):
    token = cfg["telegram"]["bot_token"]
    chat_id = cfg["telegram"]["chat_id"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        log.info("Telegram notification sent.")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")


def send_email(cfg: dict, subject: str, html_body: str):
    ec = cfg["email"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = ec["sender_email"]
    msg["To"] = ", ".join(ec["recipient_emails"])
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(ec["smtp_server"], ec["smtp_port"]) as s:
            s.ehlo()
            s.starttls()
            s.login(ec["sender_email"], ec["sender_password"])
            s.sendmail(ec["sender_email"], ec["recipient_emails"], msg.as_string())
        log.info(f"Email sent to {ec['recipient_emails']}")
    except Exception as e:
        log.error(f"Email send failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pi-hole Stack Uptime Monitor")
    parser.add_argument(
        "--mode",
        choices=["daily", "alert-only"],
        default="daily",
        help="daily = always send report; alert-only = only notify if something is down",
    )
    args = parser.parse_args()

    log.info("=== up_synthetics starting ===")
    cfg = load_config()
    results = run_all_checks(cfg)

    failures = [r for r in results if not r["ok"]]
    warnings = [r for r in results if r["ok"] and r["level"] == "warning"]

    has_issues = bool(failures or warnings)
    now_str = datetime.now().strftime("%Y-%m-%d")

    if args.mode == "alert-only" and not failures:
        log.info("No failures detected — skipping notification (alert-only mode).")
        return

    # Telegram
    tg_mode = "alert" if failures else "daily"
    tg_msg = build_telegram_message(results, mode=tg_mode)
    send_telegram(cfg, tg_msg)

    # Email
    if failures:
        subject = f"[Pi-hole] 🚨 Services Down — {now_str}"
    elif warnings:
        subject = f"[Pi-hole] ⚠️ Health Warnings — {now_str}"
    else:
        subject = f"[Pi-hole] ✅ All Systems OK — {now_str}"

    html = build_email_html(results)
    send_email(cfg, subject, html)

    log.info(f"Done. {len(failures)} failures, {len(warnings)} warnings, "
             f"{len(results) - len(failures) - len(warnings)} passing.")


if __name__ == "__main__":
    main()
