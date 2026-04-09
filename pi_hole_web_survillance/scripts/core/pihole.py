"""
Pi-hole block/unblock helper.

Pure HTTP — no Flask dependencies. Tries Pi-hole v6 API first, falls back to v5.
"""
import requests
from urllib.parse import quote


def pihole_block(domain: str, block: bool, cfg: dict) -> bool:
    """Add (block=True) or remove (block=False) a domain from Pi-hole's deny list.

    Args:
        domain: Domain name to block or unblock.
        block:  True to block, False to unblock.
        cfg:    Full config dict (reads cfg['pihole'] keys).

    Returns:
        True on success, False if all attempts failed.
    """
    host     = cfg['pihole']['host']
    token    = cfg['pihole'].get('api_token', '')
    password = cfg['pihole'].get('password', '')

    # ── Try v6 with each credential ──────────────────────────────────────────
    for cred in filter(None, [password, token]):
        try:
            auth_resp = requests.post(
                f"{host}/api/auth", json={"password": cred}, timeout=8
            )
            if auth_resp.status_code == 200:
                sid = auth_resp.json().get("session", {}).get("sid", "")
                if sid:
                    hdrs = {"X-FTL-SID": sid}
                    if block:
                        r = requests.post(
                            f"{host}/api/domains/deny/exact",
                            json={"domain": domain, "comment": "blocked via dashboard"},
                            headers=hdrs, timeout=8,
                        )
                    else:
                        r = requests.delete(
                            f"{host}/api/domains/deny/exact/{domain}",
                            headers=hdrs, timeout=8,
                        )
                    if r.status_code in (200, 201, 204):
                        return True
        except Exception:
            pass

    # ── Fallback: Pi-hole v5 API ──────────────────────────────────────────────
    try:
        action = 'add' if block else 'sub'
        base   = host + cfg['pihole'].get('api_path', '/admin/api.php')
        r = requests.get(
            f"{base}?list=black&{action}={quote(domain, safe='')}&auth={quote(token, safe='')}",
            timeout=8,
        )
        return r.status_code == 200
    except Exception:
        pass

    return False
