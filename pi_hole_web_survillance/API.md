# Pi-hole Analytics — REST API Reference

All endpoints are served by the Flask dashboard at `http://YOUR_PI_IP:8080`.

Most endpoints require an active session (browser login or the `password` cookie).  
Endpoints marked **🔓 Public** do not require auth — they are safe to call from the MCP server.  
Endpoints marked **🔐 Auth** require a valid session cookie.

---

## Authentication

```
POST /login
Content-Type: application/x-www-form-urlencoded
Body: password=YOUR_DASHBOARD_PASSWORD
```

The server sets a session cookie on success. All subsequent requests must include it.  
The MCP connector (`connectors/pihole_client.py`) handles this automatically via `requests.Session`.

---

## Common query parameters

| Parameter | Type | Description |
|---|---|---|
| `date` | `YYYY-MM-DD` | Target date (default: today) |
| `end_date` | `YYYY-MM-DD` | End of date range (inclusive) |
| `start_ts` | Unix timestamp | Range start (alternative to date) |
| `end_ts` | Unix timestamp | Range end (alternative to date) |

---

## Overview

### `GET /api/stats` 🔐
All-in-one network snapshot — single call for LLM/MCP consumption.

**Query params:** `date`, `end_date`

**Returns:**
```json
{
  "date": "2025-01-01",
  "summary": { "total_queries": 16000, "blocked_queries": 800, "active_clients": 8, "unique_domains": 2100 },
  "categories": [{ "category": "streaming", "queries": 3000, "unique_domains": 45 }],
  "blocked": { "blocked": 800, "allowed": 15200 },
  "top_domains": [{ "domain": "netflix.com", "queries": 2500 }],
  "trend_7d": [{ "date": "2024-12-26", "total": 14000, "blocked": 700 }]
}
```

---

### `GET /api/summary` 🔓
Network totals for a date or date range.

**Query params:** `date`, `end_date`, `start_ts`, `end_ts`

**Returns:** `{ total_queries, blocked_queries, unique_domains, active_clients }`

---

### `GET /api/compare` 🔓
Compare today's stats vs yesterday.

**Query params:** `date`, `start_ts`, `end_ts`

**Returns:** `{ today: {...}, yesterday: {...}, delta: {...} }`

---

### `GET /api/trend` 🔓
Daily query totals over N days.

**Query params:** `days` (1–365, default 7), `client` (IP, optional)

**Returns:** `[{ date, total, blocked }]`

---

### `GET /api/health` 🔐
System health — disk, RAM, CPU, temperature, Pi-hole service status.

**Returns:**
```json
{
  "disk_percent": 42,
  "ram_percent": 38,
  "cpu_percent": 12,
  "temperature": 51.2,
  "pihole_blocking": true
}
```

---

## Devices

### `GET /api/devices` 🔓
Active devices enriched with MAC, hostname, and device type. Excludes devices listed in `excluded_devices` config.

**Query params:** `date`, `end_date`

**Returns:** `[{ client_ip, client_name, mac, hostname, device_type, custom_name, total_queries, blocked_queries, unique_domains }]`

---

### `GET /api/device_registry` 🔐
All known devices from the MAC registry — survives IP changes.

**Returns:** `[{ mac, last_ip, hostname, device_type, custom_name, last_seen }]`

---

### `GET /api/device_detail` 🔐
Deep summary + category breakdown for one device.

**Query params:** `ip`* (required), `date`

**Returns:** `{ summary: {...}, categories: [{category, queries, unique_domains}] }`

---

### `GET /api/device_hourly` 🔐
Hourly query counts for one device.

**Query params:** `ip`* (required), `date`

**Returns:** `[{ hour: 0..23, queries, blocked }]`

---

### `GET /api/device_hourly_categories` 🔐
Hourly query counts broken down by category for one device.

**Query params:** `ip`* (required), `date`

**Returns:** `[{ hour, category, queries }]`

---

### `GET /api/device_domains` 🔐
All domains accessed by one device.

**Query params:** `ip`* (required), `date`, `limit` (1–500, default 200)

**Returns:** `[{ domain, category, queries, blocked }]`

---

### `GET /api/device_flagged_category` 🔐
Domains in a flagged category accessed by one device — used for alert drill-down.

**Query params:** `ip`* (required), `category`* (required), `date`

**Returns:** `[{ domain, queries, blocked }]`

---

### `GET /api/date_range` 🔐
Per-device summary over an arbitrary date range.

**Query params:** `start_date`* (required), `end_date`* (required)

**Returns:** `[{ client_ip, client_name, total_queries, blocked_queries, unique_domains }]`

---

### `GET /api/all_clients_hourly` 🔐
Hourly query counts for every active client — useful for heatmap views.

**Query params:** `date`

**Returns:** `{ "192.168.1.10": [0, 0, 12, ...], ... }` (24 values per client, one per hour)

---

### `GET /api/clients` 🔓
Client comparison — today vs yesterday per device.

**Query params:** `date`, `start_ts`, `end_ts`

**Returns:** `[{ client, today_queries, yesterday_queries, delta }]`

---

## Categories

### `GET /api/categories` 🔓
Category breakdown for a date.

**Query params:** `date`, `end_date`, `start_ts`, `end_ts`, `client` (IP)

**Returns:** `[{ category, queries, unique_domains }]`

---

### `GET /api/category_detail` 🔓
Top domains for a specific category — used by the dashboard drill-down modal.

**Query params:** `category`* (required), `date`, `end_date`, `client` (IP), `limit` (1–100, default 20)

**Returns:** `[{ domain, queries, blocked }]`

---

### `GET /api/top_by_category` 🔐
Top domains for a category, optionally filtered by device IP.

**Query params:** `category`* (required), `date`, `end_date`, `ip`, `limit` (1–100, default 10)

**Returns:** `[{ domain, queries, blocked }]`

---

### `GET /api/categorization_stats` 🔐
How many domains were categorized vs uncategorized.

**Query params:** `date`

**Returns:** `{ categorized: 900, uncategorized: 100, total: 1000, pct_categorized: 90.0 }`

---

### `GET /api/uncategorized_domains` 🔐
Domains that could not be matched to any category (category = `other`).

**Query params:** `date`, `limit` (1–200, default 20)

**Returns:** `[{ domain, queries }]`

---

### `GET /api/client_category_usage` 🔐
Category breakdown for one client or all clients.

**Query params:** `date`, `ip` (optional — omit for all clients)

**Returns:** `{ "192.168.1.10": { "streaming": { queries, domains }, ... }, ... }`

---

## Security & Alerts

### `GET /api/alerts` 🔓
Security alerts for a date — adult content, VPN/proxy, crypto, excessive usage.

**Query params:** `date`, `start_ts`, `end_ts`

**Returns:**
```json
{
  "critical": [{
    "category": "adult",
    "level": "critical",
    "icon": "🔞",
    "title": "Adult Content",
    "short": "42 requests detected",
    "queries": 42,
    "devices": "John's iPhone",
    "top_domains": ["example.com (42)"]
  }],
  "warnings": [{ "category": "streaming", "level": "warning", ... }]
}
```

---

### `GET /api/excessive_usage` 🔐
Clients exceeding usage thresholds for social media, streaming, or gaming.

**Query params:** `date`, `threshold_minutes` (default 60)

**Returns:** `[{ client_ip, client_name, category, queries, domains }]`

---

## Blocking

### `GET /api/blocked_top` 🔐
Top domains blocked by Pi-hole for a date.

**Query params:** `date`, `end_date`, `start_ts`, `end_ts`

**Returns:** `[{ domain, count }]`

---

### `GET /api/blocked_summary` 🔐
Blocked vs allowed query counts.

**Query params:** `date`, `end_date`

**Returns:** `{ blocked, allowed, total, pct_blocked }`

---

### `GET /api/blocking` 🔓
Pi-hole blocking effectiveness summary (alias for blocked_summary with time range support).

**Query params:** `date`, `end_date`, `start_ts`, `end_ts`

**Returns:** `{ blocked, allowed, total, pct_blocked }`

---

### `GET /api/blocked_domains` 🔐
List all domains manually blocked via the dashboard.

**Returns:** `[{ domain, category, blocked_at }]`

---

### `GET /api/manually_blocked` 🔐
Alias for `/api/blocked_domains` — used by MCP tools.

**Returns:** `[{ domain, category, blocked_at }]`

---

### `POST /api/block_domain` 🔐
Block a domain via Pi-hole and record it in the local database.

**Body (JSON):** `{ "domain": "ads.example.com", "category": "ads_tracking" }`

**Returns:** `{ status, domain, pihole_ok, message }`

---

### `POST /api/unblock_domain` 🔐
Unblock a domain.

**Body (JSON):** `{ "domain": "ads.example.com" }`

**Returns:** `{ status, domain, pihole_ok, message }`

---

## Search & Query Log

### `GET /api/search` 🔐
Search domains by keyword across a date.

**Query params:** `q`* (required), `date`, `limit` (1–200, default 50)

**Returns:** `{ query, date, results: [{ domain, category, client, client_ip, queries, blocked }] }`

---

### `GET /api/query_log` 🔐
Raw DNS query log with optional filters.

**Query params:** `date`, `ip`, `category`, `domain`, `blocked` (`1` = blocked only), `limit` (1–500, default 100)

**Returns:** `[{ timestamp, domain, client, client_ip, category, status, query_type }]`

---

### `GET /api/new_domains` 🔓
Domains seen for the first time today.

**Query params:** `date`, `end_date`, `start_ts`, `end_ts`

**Returns:** `[{ domain, category, client, queries }]`

---

### `GET /api/domains` 🔓
Top queried domains for a date.

**Query params:** `date`, `end_date`, `limit` (1–100, default 15), `client` (IP)

**Returns:** `[{ domain, category, queries, blocked }]`

---

### `GET /api/hourly` 🔓
Hourly query counts — all clients combined, or one specific client.

**Query params:** `date`, `end_date`, `client` (IP), `start_ts`, `end_ts`

**Returns:** `[{ hour: 0..23, queries, blocked }]`

---

## AI Summary (Gemini)

> Requires `gemini.api_key` to be configured in `config.yaml`.

### `GET /api/ai_summary_stored` 🔐
Return the best stored AI summary without calling Gemini.

**Query params:** `period` (`daily` | `weekly` | `monthly`, default `daily`)

**Returns:** `{ summary, period, start, end, model, generated_at, run_type }` — or `204 No Content` if none stored.

---

### `GET /api/ai_eta` 🔐
Return estimated time for AI summary generation (for UI countdown).

**Query params:** `period`, `start_ts`, `end_ts`

**Returns:** `{ num_devices, num_calls, delay_s, eta_seconds, rpm }`

---

### `POST /api/ai_summary` 🔐
Generate an AI summary on-demand via Gemini, store it, and return it.

**Body (JSON):** `{ "period": "daily" }` — or `{ "start_ts": 1234567890, "end_ts": 1234567890 }`

**Returns:**
- `{ source: "live", summary, period, start, end, model, generated_at }` — fresh result
- `{ source: "cached", summary, cache_notice, ... }` — quota hit, served from cache
- `429` — quota hit and no cache available
- `400` — API key not configured

---

### `POST /api/send_report` 🔓
Trigger an HTML email report in a background thread.

**Body (JSON):** `{ "period": "daily" }` — `daily` | `weekly` | `monthly`

**Returns:** `{ status: "queued", message }` — report is emailed asynchronously.

---

## Endpoint summary

| Method | Path | Auth | MCP tool |
|---|---|---|---|
| GET | `/api/stats` | 🔐 | `pihole_stats` |
| GET | `/api/summary` | 🔓 | `pihole_summary` |
| GET | `/api/compare` | 🔓 | — |
| GET | `/api/trend` | 🔓 | — |
| GET | `/api/health` | 🔐 | `pihole_health` |
| GET | `/api/alerts` | 🔓 | `pihole_alerts` |
| GET | `/api/excessive_usage` | 🔐 | `pihole_excessive_usage` |
| GET | `/api/devices` | 🔓 | `pihole_devices` |
| GET | `/api/device_registry` | 🔐 | `pihole_device_registry` |
| GET | `/api/device_detail` | 🔐 | `pihole_device_detail` |
| GET | `/api/device_hourly` | 🔐 | — |
| GET | `/api/device_hourly_categories` | 🔐 | — |
| GET | `/api/device_domains` | 🔐 | `pihole_device_domains` |
| GET | `/api/device_flagged_category` | 🔐 | — |
| GET | `/api/date_range` | 🔐 | `pihole_date_range` |
| GET | `/api/all_clients_hourly` | 🔐 | — |
| GET | `/api/clients` | 🔓 | — |
| GET | `/api/categories` | 🔓 | `pihole_categories` |
| GET | `/api/category_detail` | 🔓 | — |
| GET | `/api/top_by_category` | 🔐 | `pihole_top_by_category` |
| GET | `/api/categorization_stats` | 🔐 | — |
| GET | `/api/uncategorized_domains` | 🔐 | `pihole_uncategorized_domains` |
| GET | `/api/client_category_usage` | 🔐 | `pihole_client_category_usage` |
| GET | `/api/blocked_top` | 🔐 | `pihole_blocked_top` |
| GET | `/api/blocked_summary` | 🔐 | `pihole_blocked_summary` |
| GET | `/api/blocking` | 🔓 | — |
| GET | `/api/blocked_domains` | 🔐 | — |
| GET | `/api/manually_blocked` | 🔐 | `pihole_manually_blocked` |
| POST | `/api/block_domain` | 🔐 | `pihole_block_domain` |
| POST | `/api/unblock_domain` | 🔐 | `pihole_unblock_domain` |
| GET | `/api/search` | 🔐 | `pihole_search` |
| GET | `/api/query_log` | 🔐 | `pihole_query_log` |
| GET | `/api/new_domains` | 🔓 | `pihole_new_domains` |
| GET | `/api/domains` | 🔓 | — |
| GET | `/api/hourly` | 🔓 | — |
| GET | `/api/ai_summary_stored` | 🔐 | — |
| GET | `/api/ai_eta` | 🔐 | — |
| POST | `/api/ai_summary` | 🔐 | — |
| POST | `/api/send_report` | 🔓 | `pihole_send_report` |
