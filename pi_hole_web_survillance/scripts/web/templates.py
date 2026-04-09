"""
HTML template strings for the Pi-hole dashboard.
Extracted from dashboard.py for maintainability.
"""

LOGIN_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pi-hole Dashboard — Login</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#f6f8fa;font-family:'Segoe UI',system-ui,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh}
  .box{background:#fff;border:1px solid #d0d7de;border-radius:12px;
       padding:32px 28px;width:100%;max-width:360px;box-shadow:0 4px 16px rgba(0,0,0,.08)}
  h1{font-size:18px;color:#0969da;margin-bottom:6px;text-align:center}
  .sub{font-size:14px;color:#3d444d;text-align:center;margin-bottom:24px}
  label{font-size:13px;color:#1f2328;font-weight:500;display:block;margin-bottom:6px}
  input[type=password]{width:100%;padding:10px 12px;border:1px solid #d0d7de;
    border-radius:6px;font-size:14px;outline:none;transition:border-color .15s}
  input[type=password]:focus{border-color:#0969da;box-shadow:0 0 0 3px #dbeafe}
  .btn{width:100%;margin-top:14px;padding:11px;background:#0969da;color:#fff;
       border:none;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;
       transition:background .15s}
  .btn:hover{background:#1a7dc8}
  .err{color:#b91c1c;font-size:14px;text-align:center;margin-top:10px;
       background:#fff5f5;border:1px solid #fca5a5;border-radius:6px;padding:8px}
</style>
</head>
<body>
<div class="box">
  <h1>🛡️ Pi-hole Analytics</h1>
  <div class="sub">Home Network Monitor — Sign in to continue</div>
  <form method="POST">
    <label for="pw">Password</label>
    <input type="password" id="pw" name="password" placeholder="Enter password"
           autofocus autocomplete="current-password">
    <button class="btn" type="submit">Sign In</button>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
  </form>
</div>
</body></html>"""

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pi-hole Home Network Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:#f6f8fa; --card:#ffffff; --card2:#f6f8fa;
    --border:#d0d7de; --border2:#e8ecf0;
    --accent:#0969da; --accent2:#8250df;
    --text:#1f2328; --text2:#0d1117; --muted:#3d444d;
    --green:#1a7f37; --red:#cf222e; --yellow:#9a6700;
    --orange:#bc4c00; --purple:#8250df;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif; min-height:100vh; font-size:15px; line-height:1.5; }

  /* ── Header ─────────────────────────────────────────────────────────── */
  header {
    background:#ffffff; padding:12px 20px;
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;
    border-bottom:1px solid var(--border); position:sticky; top:0; z-index:200;
    box-shadow:0 1px 4px rgba(0,0,0,.08);
  }
  .header-left h1 { font-size:17px; color:var(--accent); font-weight:600; }
  .header-left .sub { font-size:14px; color:var(--muted); margin-top:2px; }
  .header-right { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .date-nav { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
  .date-nav select { font-size:13px; padding:5px 10px; border-radius:6px; border:1px solid var(--border); background:var(--card); color:var(--text); cursor:pointer; }
  .btn { background:#f6f8fa; border:1px solid var(--border); color:var(--text);
         padding:6px 14px; border-radius:6px; cursor:pointer; font-size:13px;
         transition:all .15s; white-space:nowrap; }
  .btn:hover { border-color:var(--accent); color:var(--accent); background:#dbeafe; }
  .btn-primary { background:#0969da; border-color:#0969da; color:#fff; }
  .btn-primary:hover { background:#1a7dc8; border-color:#1a7dc8; color:#fff; }
  .btn-danger { background:#cf222e; border-color:#cf222e; color:#fff; }
  input[type=date] { background:#f6f8fa; border:1px solid var(--border); color:var(--text);
                     padding:6px 10px; border-radius:6px; font-size:13px; }

  /* ── Alert Banner ───────────────────────────────────────────────────── */
  #alert-banner { display:none; }
  .alert-banner { background:#fff0f0; border-bottom:2px solid var(--red); padding:10px 20px; }
  .alert-banner .alerts-inner { max-width:1400px; margin:0 auto; display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
  .alert-item { display:flex; align-items:center; gap:6px; background:#ffe0e0; border:1px solid #ffb3b3;
                border-radius:6px; padding:6px 12px; font-size:14px; color:#b91c1c; }
  .alert-item strong { color:#991b1b; }
  .alert-banner .banner-label { font-weight:600; color:var(--red); font-size:13px; margin-right:4px; }

  /* ── Main ───────────────────────────────────────────────────────────── */
  main { padding:16px 20px; max-width:1400px; margin:0 auto; }

  /* ── Stat Cards ─────────────────────────────────────────────────────── */
  .stat-row { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px; }
  .stat-card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px;
               position:relative; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .stat-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
  .stat-card.blue::before   { background:var(--accent); }
  .stat-card.red::before    { background:var(--red); }
  .stat-card.yellow::before { background:var(--yellow); }
  .stat-card.green::before  { background:var(--green); }
  .stat-val { font-size:28px; font-weight:700; color:var(--text2); line-height:1; }
  .stat-lbl { font-size:14px; color:var(--text); margin-top:5px; text-transform:uppercase; letter-spacing:.5px; font-weight:500; }
  .stat-sub { font-size:14px; color:var(--muted); margin-top:6px; }
  .stat-chg { font-size:14px; margin-top:4px; }
  .chg-up   { color:var(--red); }
  .chg-down { color:var(--green); }
  .chg-same { color:var(--muted); }

  /* ── Plain English Summary ──────────────────────────────────────────── */
  .summary-box { background:#f0f7ff; border:1px solid #c9dff7; border-radius:10px;
                 padding:16px 20px; margin-bottom:16px; border-left:3px solid var(--accent); }
  .summary-box h2 { font-size:15px; color:var(--accent); margin-bottom:8px; font-weight:600; }
  .summary-box p { font-size:14px; color:var(--text); line-height:1.7; }
  .summary-box .highlight { color:var(--text2); font-weight:600; }

  /* ── Grid Layouts ───────────────────────────────────────────────────── */
  .grid-2   { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }
  .grid-3   { display:grid; grid-template-columns:2fr 1fr; gap:12px; margin-bottom:16px; }
  .grid-wide{ display:grid; grid-template-columns:3fr 2fr; gap:12px; margin-bottom:16px; }

  /* ── Panels ─────────────────────────────────────────────────────────── */
  .panel { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px;
           box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .panel-title { font-size:13px; color:var(--text); text-transform:uppercase; letter-spacing:.5px;
                 margin-bottom:12px; display:flex; align-items:center; gap:6px; font-weight:600; }
  .panel-title .pill { font-size:13px; background:var(--bg); border:1px solid var(--border);
                       border-radius:10px; padding:2px 8px; color:var(--muted); }
  .chart-wrap { position:relative; height:200px; }

  /* ── Needs Attention Cards ──────────────────────────────────────────── */
  .attention-section { margin-bottom:16px; }
  .attention-section .section-heading { font-size:13px; font-weight:600; color:var(--red);
    display:flex; align-items:center; gap:6px; margin-bottom:10px; }
  .attention-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:10px; }
  .attention-card { background:#fff5f5; border:1px solid #fecaca; border-radius:8px; padding:14px;
                    display:flex; flex-direction:column; gap:8px; }
  .attention-card.warn { background:#fffbeb; border-color:#fde68a; }
  .attention-card .ac-header { display:flex; justify-content:space-between; align-items:flex-start; }
  .attention-card .ac-title { font-size:14px; font-weight:600; color:var(--text2); }
  .attention-card .ac-badge { font-size:13px; padding:2px 8px; border-radius:10px; font-weight:600; }
  .badge-alert { background:#fee2e2; color:#b91c1c; border:1px solid #fca5a5; }
  .badge-warn  { background:#fef3c7; color:#92400e; border:1px solid #fcd34d; }
  .attention-card .ac-count { font-size:22px; font-weight:700; color:var(--red); }
  .attention-card.warn .ac-count { color:var(--yellow); }
  .attention-card .ac-desc { font-size:14px; color:var(--muted); }
  .attention-card .ac-devices { font-size:14px; color:var(--text); }
  .attention-card .ac-btn { align-self:flex-start; margin-top:4px; }

  /* ── Category Table ─────────────────────────────────────────────────── */
  table { width:100%; border-collapse:collapse; }
  th { font-size:14px; color:var(--text); text-transform:uppercase; letter-spacing:.4px;
       padding:9px 10px; border-bottom:1px solid var(--border2); text-align:left; font-weight:600; }
  td { padding:9px 10px; border-bottom:1px solid var(--border2); vertical-align:middle; font-size:14px; }
  tr:last-child td { border-bottom:none; }
  tr.clickable:hover td { background:#f6f8fa; cursor:pointer; }
  td.mono { font-family:monospace; font-size:13px; }

  .cat-badge { display:inline-flex; align-items:center; gap:5px; padding:3px 10px;
               border-radius:12px; font-size:13px; font-weight:500; }
  .status-badge { display:inline-block; padding:2px 8px; border-radius:10px;
                  font-size:12px; font-weight:600; }
  .s-alert  { background:#fee2e2; color:#b91c1c; border:1px solid #fca5a5; }
  .s-warn   { background:#fef3c7; color:#92400e; border:1px solid #fcd34d; }
  .s-normal { background:#dcfce7; color:#15803d; border:1px solid #86efac; }

  .bar-wrap { background:var(--border2); border-radius:3px; height:6px; display:inline-block;
              vertical-align:middle; min-width:60px; max-width:120px; width:100%; }
  .bar-fill { height:6px; border-radius:3px; }

  /* ── Device Cards ───────────────────────────────────────────────────── */
  .section-heading-light { font-size:14px; font-weight:600; color:var(--text2);
    display:flex; align-items:center; gap:6px; margin-bottom:10px; }
  .device-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:12px; margin-bottom:16px; }
  .device-card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px;
                 box-shadow:0 1px 3px rgba(0,0,0,.06); cursor:pointer; transition:box-shadow .15s,border-color .15s; }
  .device-card:hover { box-shadow:0 3px 10px rgba(0,0,0,.12); border-color:var(--accent); }
  .device-card.flagged { border-left:3px solid var(--red); }
  .dc-header { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
  .device-avatar { width:44px; height:44px; border-radius:50%;
                   background:linear-gradient(135deg,var(--accent),var(--accent2));
                   display:flex; align-items:center; justify-content:center; font-size:20px; flex-shrink:0; }
  .dc-name { font-size:14px; font-weight:600; color:var(--text2); }
  .dc-ip   { font-size:14px; color:var(--muted); font-family:monospace; }
  .dc-stats { display:flex; gap:16px; margin-bottom:10px; }
  .dc-stat .val { font-size:18px; font-weight:700; color:var(--accent); }
  .dc-stat .lbl { font-size:13px; color:var(--muted); text-transform:uppercase; }
  .dc-bar-bg { background:var(--border2); border-radius:3px; height:4px; margin-bottom:10px; }
  .dc-bar-fg { height:4px; border-radius:3px; background:linear-gradient(90deg,var(--accent),var(--accent2)); }
  .dc-cats { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px; }
  .dc-flags { display:flex; flex-direction:column; gap:5px; margin-top:6px; }
  .dc-flag { background:#fff5f5; border:1px solid #fecaca; border-radius:6px; padding:8px 10px; font-size:13px; }
  .dc-flag.warn { background:#fffbeb; border-color:#fde68a; }
  .dc-flag .flag-title { font-weight:600; color:#b91c1c; margin-bottom:4px; }
  .dc-flag.warn .flag-title { color:#92400e; }
  .dc-flag .flag-links { display:flex; flex-wrap:wrap; gap:4px; }
  .dc-flag .flag-links a { color:var(--accent); text-decoration:none; font-size:12px; font-family:monospace;
                            background:#f0f7ff; border:1px solid #c9dff7; border-radius:4px; padding:2px 6px; }
  .dc-flag .flag-links a:hover { background:#dbeafe; text-decoration:underline; }

  /* ── Risky Category Cards ───────────────────────────────────────────── */
  .risky-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:12px; margin-bottom:16px; }
  .risky-card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px;
                box-shadow:0 1px 3px rgba(0,0,0,.06); display:flex; flex-direction:column; gap:8px; }
  .risky-card.rc-alert-card { border-color:#fca5a5; background:#fff8f8; }
  .risky-card.rc-warn-card  { border-color:#fde68a; background:#fffdf0; }
  .risky-card.rc-clean-card { border-color:#86efac; background:#f8fff8; }
  .rc-top { display:flex; justify-content:space-between; align-items:flex-start; }
  .rc-icon { font-size:30px; line-height:1; }
  .rc-title { font-size:14px; font-weight:600; color:var(--text2); margin-top:4px; }
  .rc-badge { font-size:12px; padding:3px 9px; border-radius:10px; font-weight:600; align-self:flex-start; }
  .rc-badge-alert { background:#fee2e2; color:#b91c1c; border:1px solid #fca5a5; }
  .rc-badge-warn  { background:#fef3c7; color:#92400e; border:1px solid #fcd34d; }
  .rc-badge-clean { background:#dcfce7; color:#15803d; border:1px solid #86efac; }
  .rc-badge-info  { background:#dbeafe; color:#1d4ed8; border:1px solid #93c5fd; }
  .rc-count { font-size:24px; font-weight:700; }
  .risky-card.rc-alert-card .rc-count { color:var(--red); }
  .risky-card.rc-warn-card  .rc-count { color:var(--yellow); }
  .risky-card.rc-clean-card .rc-count { color:var(--green); }
  .rc-desc    { font-size:14px; color:var(--muted); line-height:1.5; }
  .rc-devices { font-size:14px; color:var(--text); }
  .rc-sites   { display:flex; flex-direction:column; gap:4px; margin-top:4px; }
  .rc-site    { display:flex; align-items:center; justify-content:space-between;
                background:var(--bg); border:1px solid var(--border2); border-radius:6px;
                padding:5px 8px; gap:8px; }
  .rc-site-left { display:flex; flex-direction:column; gap:1px; min-width:0; flex:1; }
  .rc-site a  { color:var(--accent); text-decoration:none; font-family:monospace;
                font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .rc-site a:hover { text-decoration:underline; }
  .rc-site .rc-cnt { color:var(--muted); font-size:12px; }

  /* ── Pi-hole Protection Box ─────────────────────────────────────────── */
  .protection-box { background:#f0fff4; border:1px solid #86efac; border-radius:10px;
                    padding:16px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .protection-box h2 { font-size:15px; color:var(--green); margin-bottom:10px; font-weight:600; }
  .protection-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:12px; }
  .ps-box { background:#ffffff; border:1px solid #c3e6cb; border-radius:6px; padding:10px; text-align:center; }
  .ps-box .ps-val { font-size:20px; font-weight:700; color:var(--green); }
  .ps-box .ps-lbl { font-size:13px; color:var(--muted); margin-top:2px; text-transform:uppercase; }
  .protection-box .explain { font-size:13px; color:var(--muted); line-height:1.6; }
  .protection-box .explain strong { color:var(--text); }

  /* ── New Domains ────────────────────────────────────────────────────── */
  .new-domain-row { display:flex; align-items:center; gap:10px; padding:8px 0;
                    border-bottom:1px solid var(--border2); }
  .new-domain-row:last-child { border-bottom:none; }
  .nd-dot { width:6px; height:6px; border-radius:50%; background:var(--yellow); flex-shrink:0; }
  .nd-domain { font-family:monospace; font-size:13px; color:var(--text2); flex:1; min-width:0;
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .nd-meta { font-size:14px; color:var(--muted); text-align:right; flex-shrink:0; }

  /* ── Modal ──────────────────────────────────────────────────────────── */
  .modal-backdrop { display:none; position:fixed; inset:0; background:#00000040; z-index:500;
                    align-items:center; justify-content:center; padding:20px; }
  .modal-backdrop.open { display:flex; }
  .modal { background:#ffffff; border:1px solid var(--border); border-radius:12px;
           padding:24px; max-width:640px; width:100%; max-height:80vh; overflow-y:auto;
           position:relative; box-shadow:0 8px 24px rgba(0,0,0,.12); }
  .modal-close { position:absolute; top:14px; right:16px; background:none; border:none;
                 color:var(--muted); cursor:pointer; font-size:18px; }
  .modal-close:hover { color:var(--text); }
  .modal h2 { font-size:16px; color:var(--text2); margin-bottom:16px; }
  .modal-row { display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; }
  .period-btn { flex:1; min-width:100px; text-align:center; padding:10px; background:var(--bg);
                border:1px solid var(--border); border-radius:8px; cursor:pointer;
                color:var(--text); transition:all .15s; }
  .period-btn:hover, .period-btn.active { background:#0969da; border-color:#0969da; color:#fff; }
  .period-btn .pb-icon { font-size:20px; display:block; margin-bottom:4px; }
  .period-btn .pb-lbl  { font-size:14px; font-weight:500; }
  .period-btn .pb-desc { font-size:12px; color:#3d444d; margin-top:2px; }
  .modal-status { margin-top:12px; padding:10px; border-radius:6px; font-size:13px; display:none; }
  .modal-status.success { background:#dcfce7; border:1px solid #86efac; color:#15803d; }
  .modal-status.error   { background:#fee2e2; border:1px solid #fca5a5; color:#b91c1c; }
  .modal-status.sending { background:#dbeafe; border:1px solid #93c5fd; color:#1d4ed8; }

  /* ── Category Detail Modal ──────────────────────────────────────────── */
  #cat-modal h2 { display:flex; align-items:center; gap:8px; }

  /* ── Misc ───────────────────────────────────────────────────────────── */
  .loader { text-align:center; padding:30px; color:var(--muted); font-size:13px; }
  .pulse  { animation:pulse 1.5s ease infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .empty  { text-align:center; padding:24px; color:var(--muted); font-size:13px; font-style:italic; opacity:.8; }

  /* ── Collapsible panels ─────────────────────────────────────────────────── */
  .collapsible { cursor:pointer; user-select:none; }
  .collapsible:hover { background:var(--bg); border-radius:6px; }
  .collapse-arrow { margin-left:auto; font-size:13px; color:var(--muted);
                    transition:transform .2s; display:inline-block; }
  .panel.collapsed .panel-body { display:none; }
  .panel.collapsed .collapse-arrow { transform:rotate(-90deg); }
  .panel-title.collapsible { padding:4px 6px; margin:-4px -6px; border-radius:6px; }
  .mb16   { margin-bottom:16px; }
  .info-box { background:#f0f7ff; border:1px solid #c9dff7; border-radius:8px; padding:12px 14px; font-size:14px; color:#1e3a5f; line-height:1.6; }
  .info-box strong { color:var(--text2); }

  /* ── Block button ───────────────────────────────────────────────────── */
  .btn-block { background:transparent; border:1px solid #fca5a5; color:#b91c1c;
               padding:2px 6px; border-radius:4px; cursor:pointer; font-size:14px;
               transition:all .15s; white-space:nowrap; line-height:1; flex-shrink:0; }
  .btn-block:hover { background:#fee2e2; }
  .btn-block.blocked { background:#dcfce7; border-color:#86efac; color:#15803d; }
  .btn-block.busy { opacity:.4; pointer-events:none; }
  .btn-ignore { background:transparent; border:1px solid #d1d5db; color:#9ca3af;
                padding:2px 6px; border-radius:4px; cursor:pointer; font-size:11px;
                transition:all .15s; white-space:nowrap; line-height:1; flex-shrink:0; }
  .btn-ignore:hover { border-color:#f59e0b; color:#b45309; background:#fffbeb; }
  .btn-ignore.ignored { border-color:#6b7280; color:#6b7280; background:#f3f4f6; }
  .btn-ignore.busy { opacity:.4; pointer-events:none; }

  /* ── Blocked domains section ────────────────────────────────────────── */
  .blocked-section { margin-bottom:16px; }
  .blocked-row { display:flex; align-items:center; gap:10px; padding:8px 10px;
                 border-bottom:1px solid var(--border2); background:#fff8f8; }
  .blocked-row:last-child { border-bottom:none; }
  .blocked-domain { font-family:monospace; font-size:14px; color:#b91c1c;
                    text-decoration:line-through; flex:1; }
  .blocked-cat { font-size:12px; color:var(--muted); }
  .blocked-date { font-size:12px; color:var(--muted); }
  .btn-unblock { background:#f0fff4; border:1px solid #86efac; color:#15803d;
                 padding:3px 10px; border-radius:4px; cursor:pointer; font-size:13px;
                 font-weight:600; transition:all .15s; }
  .btn-unblock:hover { background:#dcfce7; }

  @media(max-width:900px) {
    .stat-row { grid-template-columns:repeat(2,1fr); }
    .grid-2,.grid-3,.grid-wide { grid-template-columns:1fr; }
    .protection-stats { grid-template-columns:repeat(2,1fr); }
    .device-grid,.risky-grid { grid-template-columns:1fr; }
  }
  @media(max-width:480px) {
    .stat-row { grid-template-columns:1fr 1fr; }
    .attention-grid { grid-template-columns:1fr; }
  }
</style>
</head>
<body>

<!-- ── Header ─────────────────────────────────────────────────────────────── -->
<header>
  <div class="header-left">
    <h1>🛡️ Pi-hole Home Network Monitor</h1>
    <div class="sub">Raspberry Pi · <span id="live-time"></span> · <span id="live-date"></span></div>
  </div>
  <div class="header-right">
    <div class="date-nav">
      <button class="btn" onclick="changeDate(-1)" id="btn-prev">‹ Prev</button>
      <input type="datetime-local" id="start-datetime" disabled>
      <span style="margin:0 4px">to</span>
      <input type="datetime-local" id="end-datetime" disabled>
      <button class="btn" onclick="changeDate(1)" id="btn-next">Next ›</button>
    </div>
    <a href="/logout" class="btn" style="color:var(--muted)" title="Sign out">⎋ Sign Out</a>
  </div>
</header>

<!-- ── Alert Banner ───────────────────────────────────────────────────────── -->
<div id="alert-banner"></div>

<!-- ── Main ──────────────────────────────────────────────────────────────── -->
<main>

  <!-- Stat Cards -->
  <div class="stat-row" id="stat-row">
    <div class="stat-card blue"><div class="stat-val pulse">…</div><div class="stat-lbl">Total Requests</div></div>
    <div class="stat-card red"><div class="stat-val pulse">…</div><div class="stat-lbl">Blocked by Pi-hole</div></div>
    <div class="stat-card yellow"><div class="stat-val pulse">…</div><div class="stat-lbl">Need Attention</div></div>
    <div class="stat-card green"><div class="stat-val pulse">…</div><div class="stat-lbl">Active Devices</div></div>
  </div>

  <!-- Plain English Summary -->
  <div class="summary-box" id="summary-box">
    <h2>📋 What's Happening on Your Network</h2>
    <p id="summary-text" style="color:var(--muted)">Loading summary…</p>
  </div>

  <!-- AI Summary Panel -->
  <div id="ai-panel" style="margin-bottom:16px">
    <div class="panel" id="panel-ai">
      <div class="panel-title collapsible" onclick="togglePanel('panel-ai')" style="justify-content:space-between">
        <span>🤖 Intelligent Network Monitor Summary</span>
        <div style="display:flex;gap:8px;align-items:center" onclick="event.stopPropagation()">
          <button id="ai-run-btn" class="btn" onclick="generateAISummary()" style="font-size:12px;padding:2px 12px">▶ Run</button>
          <span class="collapse-arrow">▼</span>
        </div>
      </div>
      <div class="panel-body" id="ai-body">
        <div id="ai-content" style="color:var(--muted);font-size:13px;padding:12px 0">
          Click <strong>Run</strong> to get an AI analysis of your network activity.
        </div>
      </div>
    </div>
  </div>

  <!-- Needs Attention -->
  <div class="attention-section" id="attention-section" style="display:none">
    <div class="section-heading">⚠️ Needs Attention</div>
    <div class="attention-grid" id="attention-grid"></div>
  </div>

  <!-- Risky Category Cards -->
  <div class="panel mb16" id="panel-risky">
    <div class="panel-title collapsible" onclick="togglePanel('panel-risky')">
      🚨 Categories That Need Your Attention
      <span class="collapse-arrow">▼</span>
    </div>
    <div class="panel-body">
      <div class="risky-grid" id="risky-grid"><div class="loader">Loading…</div></div>
    </div>
  </div>

  <!-- Device Cards -->
  <div class="panel mb16" id="panel-devices">
    <div class="panel-title collapsible" onclick="togglePanel('panel-devices')">
      📱 Your Devices
      <span style="font-size:13px;font-weight:400;color:var(--muted);margin-left:4px">(click a card to filter by device)</span>
      <span class="collapse-arrow">▼</span>
    </div>
    <div class="panel-body" style="padding-top:12px">
      <div class="device-grid" id="device-grid"><div class="loader">Loading devices…</div></div>
    </div>
  </div>

  <!-- Per-Device Time Series Chart -->
  <div class="panel mb16" id="panel-timeseries">
    <div class="panel-title collapsible" onclick="togglePanel('panel-timeseries')">
      📈 Hourly Activity by Device
      <span class="collapse-arrow">▼</span>
    </div>
    <div class="panel-body" style="padding-top:12px">
      <div style="height:260px"><canvas id="timeseries-chart"></canvas></div>
    </div>
  </div>

  <!-- Hourly Bar + Category Breakdown -->
  <div class="grid-wide mb16">
    <div class="panel" id="panel-hourly">
      <div class="panel-title collapsible" onclick="togglePanel('panel-hourly')">
        📊 Hourly Traffic Total
        <span class="collapse-arrow">▼</span>
      </div>
      <div class="panel-body" style="padding-top:12px">
        <div class="chart-wrap"><canvas id="hourly-chart"></canvas></div>
      </div>
    </div>
    <div class="panel" id="panel-catmix">
      <div class="panel-title collapsible" onclick="togglePanel('panel-catmix')">
        📊 Traffic Mix <span class="pill" id="cat-pill"></span>
        <span class="collapse-arrow">▼</span>
      </div>
      <div class="panel-body" style="padding-top:12px">
        <div class="chart-wrap"><canvas id="cat-chart"></canvas></div>
      </div>
    </div>
  </div>

  <!-- Full Category Table -->
  <div class="panel mb16" id="panel-categories">
    <div class="panel-title collapsible" onclick="togglePanel('panel-categories')">
      📂 What Category Was Browsed
      <span class="collapse-arrow">▼</span>
    </div>
    <div class="panel-body" style="padding-top:12px">
      <div class="info-box mb16" id="filter-banner" style="display:none;">Filtering by selected device.</div>
      <table id="cat-table">
        <thead>
          <tr>
            <th>Category</th><th>Requests</th><th>% of Traffic</th>
            <th>Unique Sites</th><th>Traffic</th><th>Status</th>
          </tr>
        </thead>
        <tbody><tr><td colspan="6" class="loader">Loading…</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- Pi-hole Protection -->
  <div class="panel mb16" id="panel-protection" style="background:#f0fff4;border-color:#86efac">
    <div class="panel-title collapsible" onclick="togglePanel('panel-protection')" style="color:var(--green)">
      🛡️ Pi-hole Protection
      <span class="collapse-arrow">▼</span>
    </div>
    <div class="panel-body" style="padding-top:12px" id="protection-box">
      <div class="protection-stats" id="protection-stats">
        <div class="ps-box"><div class="ps-val">…</div><div class="ps-lbl">Total Requests</div></div>
        <div class="ps-box"><div class="ps-val">…</div><div class="ps-lbl">Blocked</div></div>
        <div class="ps-box"><div class="ps-val">…</div><div class="ps-lbl">Block Rate</div></div>
      </div>
      <div class="explain" id="protection-explain">Loading protection summary…</div>
    </div>
  </div>

  <!-- Top Blocked Domains -->
  <div class="panel mb16" id="panel-blocked-top">
    <div class="panel-title collapsible" onclick="togglePanel('panel-blocked-top')">
      🚫 Top Blocked Domains <span class="pill" id="blocked-top-count"></span>
      <span class="collapse-arrow">▼</span>
    </div>
    <div class="panel-body" style="padding-top:12px" id="blocked-top-content"><div class="loader">Loading…</div></div>
  </div>

  <!-- New Domains + 7-Day Trend -->
  <div class="grid-2 mb16">
    <div class="panel" id="panel-newdomains">
      <div class="panel-title collapsible" onclick="togglePanel('panel-newdomains')">
        🆕 New Sites Today
        <span class="collapse-arrow">▼</span>
      </div>
      <div class="panel-body" style="padding-top:12px">
        <div id="new-domains-list"><div class="loader">Loading…</div></div>
      </div>
    </div>
    <div class="panel" id="panel-trend">
      <div class="panel-title collapsible" onclick="togglePanel('panel-trend')">
        📅 7-Day Trend
        <span class="collapse-arrow">▼</span>
      </div>
      <div class="panel-body" style="padding-top:12px">
        <div class="chart-wrap"><canvas id="trend-chart"></canvas></div>
      </div>
    </div>
  </div>

  <!-- Health Panel -->
  <div class="panel mb16" id="panel-health">
    <div class="panel-title collapsible" onclick="togglePanel('panel-health')" style="justify-content:space-between">
      <span style="display:flex;align-items:center;gap:6px;flex:1">
        🏥 System Health
        <span class="collapse-arrow">▼</span>
      </span>
      <button class="btn" onclick="event.stopPropagation();loadHealth()" style="text-transform:none;letter-spacing:0;font-size:13px">↺ Refresh</button>
    </div>
    <div class="panel-body" style="padding-top:12px">
      <div id="health-content"><div class="loader">Loading…</div></div>
    </div>
  </div>

  <!-- Info Box -->
  <div class="info-box mb16">
    ℹ️ <strong>How to read this dashboard:</strong>
    Each "request" is a DNS lookup — your devices make these whenever they load a website or app.
    <strong>Pi-hole</strong> intercepts ads, trackers and malicious lookups before they reach your network.
    <span style="color:#f87171">🚨 Alert</span> = content you should review.
    <span style="color:#fcd34d">⚠️ Watch</span> = usage is higher than expected.
    <span style="color:#86efac">✅ Normal</span> = all good.
    Click any category row above to see which specific sites were visited.
    Click a device card to filter categories and top domains by that client.
    <h2>📧 Send Email Report</h2>
    <p style="font-size:14px;color:var(--muted);margin-bottom:16px;">
      Choose the report type to generate and send to your configured email address.
      The report includes everything shown here plus detailed analysis.
    </p>
    <div class="modal-row">
      <div class="period-btn active" onclick="selectPeriod('daily', this)">
        <span class="pb-icon">📅</span>
        <div class="pb-lbl">Daily</div>
        <div class="pb-desc">Today's full summary</div>
      </div>
      <div class="period-btn" onclick="selectPeriod('weekly', this)">
        <span class="pb-icon">📆</span>
        <div class="pb-lbl">Weekly</div>
        <div class="pb-desc">Last 7 days + trends</div>
      </div>
      <div class="period-btn" onclick="selectPeriod('monthly', this)">
        <span class="pb-icon">🗓️</span>
        <div class="pb-lbl">Monthly</div>
        <div class="pb-desc">30-day overview</div>
      </div>
    </div>
    <button class="btn btn-primary" style="width:100%;padding:12px;font-size:14px" onclick="sendReport()">
      📤 Send Report Now
    </button>
    <div class="modal-status" id="report-status"></div>
  </div>
</div>

</main>

<!-- ── Blocked Domains ───────────────────────────────────────────────────── -->
<div style="max-width:1400px;margin:0 auto;padding:0 20px 20px">
  <div class="panel blocked-section collapsed" id="blocked-section" style="display:none">
    <div class="panel-title collapsible" onclick="togglePanel('blocked-section')" style="color:var(--red)">
      🚫 Blocked Sites
      <span style="font-weight:400;font-size:13px;color:var(--muted);margin-left:4px">Manually blocked domains</span>
      <span class="collapse-arrow" style="color:var(--red)">▼</span>
    </div>
    <div class="panel-body" style="padding-top:12px">
      <div id="blocked-list"></div>
    </div>
  </div>
</div>

<!-- ── Category Detail Modal ──────────────────────────────────────────────── -->
<div class="modal-backdrop" id="cat-modal">
  <div class="modal">
    <button class="modal-close" onclick="closeCatModal()">✕</button>
    <h2 id="cat-modal-title">Category Details</h2>
    <div id="cat-modal-body"><div class="loader">Loading…</div></div>
  </div>
</div>

<script>
// ── Constants ────────────────────────────────────────────────────────────────
const CAT_COLORS = {
  streaming:'#e50914',social_media:'#1877f2',gaming:'#6441a5',
  educational:'#27ae60',news:'#2980b9',shopping:'#ff9900',
  tech:'#00b4d8',adult:'#e74c3c',ads_tracking:'#95a5a6',
  smart_home:'#f39c12',other:'#7f8c8d',music:'#1db954',
  vpn_proxy:'#8b5cf6',crypto:'#f59e0b',sports:'#10b981',
  finance:'#06b6d4',health:'#84cc16',travel:'#f97316',
  food:'#ef4444',productivity:'#6366f1',government:'#64748b'
};
const CAT_ICONS = {
  streaming:'🎬',social_media:'📱',gaming:'🎮',educational:'📚',
  news:'📰',shopping:'🛒',tech:'💻',adult:'🔞',ads_tracking:'📊',
  smart_home:'🏠',other:'🌐',music:'🎵',vpn_proxy:'🔒',
  crypto:'₿',sports:'⚽',finance:'💰',health:'❤️',travel:'✈️',
  food:'🍔',productivity:'💼',government:'🏛️'
};
// Categories always flagged as alert if any queries
const ALERT_CATS  = new Set(['adult','vpn_proxy','crypto']);
// Categories flagged as warning if above threshold queries
const WATCH_CATS  = {social_media:900, gaming:1500, streaming:3000};
const DAY_START_HOUR = {{ day_start_hour|default(5) }};
const DEVICE_ICONS= ['💻','📱','🖥️','🎮','📺','🏠','⌚','🖨️'];

function localDateStr(d){ const dt=d||new Date(); return dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0'); }
function localDateTimeStr(d){ const dt=d||new Date(); return dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0')+'T'+String(dt.getHours()).padStart(2,'0')+':'+String(dt.getMinutes()).padStart(2,'0'); }
let currentDate    = localDateStr();
let currentEndDate = null;   // null = single-day mode
let currentStartTS = null;  // timestamp for custom time ranges
let currentEndTS   = null;  // timestamp for custom time ranges
let currentTimeWindow = '24h-from-5am';
let selectedPeriod = 'daily';
let selectedClient = null;
let selectedClientName = null;
let hourlyChart, catChart, trendChart, timeseriesChart;

function clearAISummary(){
  const box = document.getElementById('ai-content');
  if(box) box.innerHTML = '';
}

function detectPeriodFromDateRange(){
  // First check timestamp-based ranges
  if(currentStartTS && currentEndTS){
    const now = new Date();
    const anchor = new Date(now);
    anchor.setHours(DAY_START_HOUR, 0, 0, 0);
    if(now.getHours() < DAY_START_HOUR) {
      anchor.setDate(anchor.getDate() - 1);
    }
    
    // Check if matches 24h-from-5am (last 24h ending at 5 AM today)
    const endTime24h = new Date(anchor);
    const startTime24h = new Date(endTime24h);
    startTime24h.setDate(startTime24h.getDate() - 1);
    const expectedStart24h = Math.floor(startTime24h.getTime() / 1000);
    const expectedEnd24h = Math.floor(endTime24h.getTime() / 1000);
    
    if(currentStartTS === expectedStart24h && currentEndTS === expectedEnd24h){
      return 'daily';
    }
    
    // Check if matches 7days
    const endTime7d = new Date(anchor);
    const startTime7d = new Date(endTime7d);
    startTime7d.setDate(startTime7d.getDate() - 7);
    const expectedStart7d = Math.floor(startTime7d.getTime() / 1000);
    const expectedEnd7d = Math.floor(endTime7d.getTime() / 1000);
    
    if(currentStartTS === expectedStart7d && currentEndTS === expectedEnd7d){
      return 'weekly';
    }
    
    // Check if matches 30days
    const endTime30d = new Date(anchor);
    const startTime30d = new Date(endTime30d);
    startTime30d.setDate(startTime30d.getDate() - 30);
    const expectedStart30d = Math.floor(startTime30d.getTime() / 1000);
    const expectedEnd30d = Math.floor(endTime30d.getTime() / 1000);
    
    if(currentStartTS === expectedStart30d && currentEndTS === expectedEnd30d){
      return 'monthly';
    }
  }
  
  // Check date-based ranges
  if(currentDate && currentEndDate){
    const now = new Date();
    const today = localDateStr(now);
    
    // Check if it's a single day that is today
    if(currentDate === currentEndDate && currentDate === today){
      return 'daily';
    }
    
    // Check if it's a 7-day range ending today
    const startDate = new Date(currentDate + 'T00:00:00');
    const endDate = new Date(currentEndDate + 'T23:59:59');
    const todayDate = new Date(today + 'T23:59:59');
    const sevenDaysAgo = new Date(todayDate);
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 6); // 7 days including today
    
    if(startDate.getTime() === sevenDaysAgo.getTime() && endDate.getTime() >= todayDate.getTime()){
      return 'weekly';
    }
    
    // Check if it's a 30-day range ending today
    const thirtyDaysAgo = new Date(todayDate);
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 29); // 30 days including today
    
    if(startDate.getTime() === thirtyDaysAgo.getTime() && endDate.getTime() >= todayDate.getTime()){
      return 'monthly';
    }
  }
  
  // Check single date mode - if currentDate is today, return daily
  if(!currentEndDate && currentDate){
    const today = localDateStr(new Date());
    if(currentDate === today){
      return 'daily';
    }
  }
  
  return null;
}

function syncAISummaryForTimeWindow(){
  const mapping = {
    today: 'daily',
    '24h-from-5am': 'daily',
    '7days': 'weekly',
    '30days': 'monthly'
  };
  let period = mapping[currentTimeWindow] || detectPeriodFromDateRange();

  if(!period){
    clearAISummary();
    return;
  }

  loadStoredAISummary();
}

// ── Utilities ────────────────────────────────────────────────────────────────
function fmt(n){ return n==null?'—':Number(n).toLocaleString(); }
function fmtPct(v){ return v==null?'—':v.toFixed(1)+'%'; }

function arrow(v){
  if(v==null) return '';
  if(v>0) return `<span class="chg-up">▲ ${Math.abs(v).toFixed(1)}%</span>`;
  if(v<0) return `<span class="chg-down">▼ ${Math.abs(v).toFixed(1)}%</span>`;
  return `<span class="chg-same">—</span>`;
}
function pct(a,b){ return b ? +((a-b)/b*100).toFixed(1) : null; }

function catBadge(cat){
  const c = CAT_COLORS[cat]||'#7f8c8d';
  const i = CAT_ICONS[cat]||'🌐';
  const label = cat.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase());
  return `<span class="cat-badge" style="background:${c}25;color:${c};border:1px solid ${c}50">${i} ${label}</span>`;
}

function getStatus(cat, queries){
  if(ALERT_CATS.has(cat) && queries>0)
    return {cls:'s-alert', label:'🚨 Alert'};
  if(WATCH_CATS[cat] && queries >= WATCH_CATS[cat])
    return {cls:'s-warn', label:'⚠️ High'};
  return {cls:'s-normal', label:'✅ Normal'};
}

function miniBar(val, max, color){
  const pctVal = max ? Math.min(100,(val/max*100)).toFixed(0) : 0;
  return `<div class="bar-wrap"><div class="bar-fill" style="width:${pctVal}%;background:${color||'#58a6ff'}"></div></div>`;
}

// ── Time window helpers ───────────────────────────────────────────────────────
function applyTimeWindow(win){
  currentTimeWindow = win;
  const now = new Date();
  const anchor = new Date(now);
  anchor.setHours(DAY_START_HOUR, 0, 0, 0);
  if(now.getHours() < DAY_START_HOUR) {
    anchor.setDate(anchor.getDate() - 1);
  }

  if(win === 'today'){
    const startTime = new Date(anchor);
    const endTime = new Date(anchor);
    endTime.setDate(endTime.getDate() + 1);

    currentStartTS = Math.floor(startTime.getTime() / 1000);
    currentEndTS = Math.floor(endTime.getTime() / 1000);
    currentDate = localDateStr(startTime);
    currentEndDate = localDateStr(endTime);
    updateDateTimeInputs();
    document.getElementById('btn-prev').disabled = false;
    document.getElementById('btn-next').disabled = false;
  } else if(win === 'yesterday'){
    const endTime = new Date(anchor);
    const startTime = new Date(endTime);
    startTime.setDate(startTime.getDate() - 1);

    currentStartTS = Math.floor(startTime.getTime() / 1000);
    currentEndTS = Math.floor(endTime.getTime() / 1000);
    currentDate = localDateStr(startTime);
    currentEndDate = localDateStr(endTime);
    updateDateTimeInputs();
    document.getElementById('btn-prev').disabled = false;
    document.getElementById('btn-next').disabled = false;
  } else if(win === '7days'){
    const endTime = new Date(anchor);
    const startTime = new Date(endTime);
    startTime.setDate(startTime.getDate() - 7);

    currentStartTS = Math.floor(startTime.getTime() / 1000);
    currentEndTS = Math.floor(endTime.getTime() / 1000);
    currentDate = localDateStr(startTime);
    currentEndDate = localDateStr(endTime);
    updateDateTimeInputs();
    document.getElementById('btn-prev').disabled = true;
    document.getElementById('btn-next').disabled = true;
  } else if(win === '30days'){
    const endTime = new Date(anchor);
    const startTime = new Date(endTime);
    startTime.setDate(startTime.getDate() - 30);

    currentStartTS = Math.floor(startTime.getTime() / 1000);
    currentEndTS = Math.floor(endTime.getTime() / 1000);
    currentDate = localDateStr(startTime);
    currentEndDate = localDateStr(endTime);
    updateDateTimeInputs();
    document.getElementById('btn-prev').disabled = true;
    document.getElementById('btn-next').disabled = true;
  } else if(win === '24h-from-5am'){
    // Last 24 hours ending at 5 AM today
    const endTime = new Date(anchor);
    const startTime = new Date(endTime);
    startTime.setDate(startTime.getDate() - 1);

    currentStartTS = Math.floor(startTime.getTime() / 1000);
    currentEndTS = Math.floor(endTime.getTime() / 1000);
    currentDate = localDateStr(startTime);
    currentEndDate = localDateStr(endTime);
    updateDateTimeInputs();
    document.getElementById('btn-prev').disabled = false;
    document.getElementById('btn-next').disabled = false;
  }
  _loadAll();
  syncAISummaryForTimeWindow();
}

function updateDateTimeInputs(){
  const startInput = document.getElementById('start-datetime');
  const endInput = document.getElementById('end-datetime');
  
  if(currentStartTS && currentEndTS){
    const startDate = new Date(currentStartTS * 1000);
    const endDate = new Date(currentEndTS * 1000);
    startInput.value = localDateTimeStr(startDate);
    endInput.value = localDateTimeStr(endDate);
  } else if(currentEndDate){
    // Date range
    startInput.value = currentDate + 'T00:00';
    endInput.value = currentEndDate + 'T23:59';
  } else {
    // Single date
    startInput.value = currentDate + 'T00:00';
    endInput.value = currentDate + 'T23:59';
  }
}

function applyDateTimeRange(loadData = true){
  const startInput = document.getElementById('start-datetime');
  const endInput = document.getElementById('end-datetime');
  
  console.log('applyDateTimeRange called with loadData:', loadData);
  console.log('startInput.value:', startInput.value);
  console.log('endInput.value:', endInput.value);
  
  if(startInput.value && endInput.value){
    const startDate = new Date(startInput.value);
    const endDate = new Date(endInput.value);
    currentStartTS = Math.floor(startDate.getTime() / 1000);
    currentEndTS = Math.floor(endDate.getTime() / 1000);
    currentDate = localDateStr(startDate);
    currentEndDate = localDateStr(endDate);
    currentTimeWindow = 'custom';
    clearAISummary();
    
    console.log('Timestamps set:', currentStartTS, currentEndTS);
    console.log('Dates set:', currentDate, currentEndDate);
    
    if(loadData){
      _loadAll();
      syncAISummaryForTimeWindow();
    }
  } else {
    console.log('Input values missing, not setting timestamps');
  }
}

function applyDatePicker(date){
  currentEndDate = null;
  currentStartTS = null;
  currentEndTS = null;
  currentTimeWindow = 'custom';
  currentDate = date;
  updateDateTimeInputs();
  clearAISummary();
  _loadAll();
  syncAISummaryForTimeWindow();
}

function dateQS(){
  // Build query-string fragment for date/end_date or start_ts/end_ts
  console.log('dateQS called, currentStartTS:', currentStartTS, 'currentEndTS:', currentEndTS, 'currentEndDate:', currentEndDate, 'currentDate:', currentDate);
  if(currentStartTS && currentEndTS){
    const qs = `start_ts=${currentStartTS}&end_ts=${currentEndTS}`;
    console.log('Returning timestamp QS:', qs);
    return qs;
  } else if(currentEndDate){
    const qs = `date=${currentDate}&end_date=${currentEndDate}`;
    console.log('Returning date range QS:', qs);
    return qs;
  } else {
    const qs = `date=${currentDate}`;
    console.log('Returning single date QS:', qs);
    return qs;
  }
}

// ── Load All ─────────────────────────────────────────────────────────────────
async function _loadAll(){
  await Promise.all([
    loadSummary(), loadAlerts(), loadCategories(),
    loadDeviceCards(), loadRiskyCategoryCards(), loadHourly(),
    loadTimeSeries(), loadProtection(), loadNewDomains(), loadTrend(),
    loadBlockedTop(), loadHealth()
  ]);
  loadBlockedDomains();
}

function refreshAll(){ 
  console.log('refreshAll called');
  // Ensure date/time inputs are applied before refreshing
  applyDateTimeRange(false);
  _loadAll();
  syncAISummaryForTimeWindow();
}

function changeDate(delta){
  currentTimeWindow = 'custom';
  if(currentStartTS && currentEndTS){
    // For custom time ranges, shift by 24 hours
    const shiftMs = delta * 24 * 60 * 60 * 1000; // 24 hours in milliseconds
    currentStartTS += shiftMs / 1000;
    currentEndTS += shiftMs / 1000;
    updateDateTimeInputs();
  } else if(currentEndDate && currentDate !== currentEndDate){
    // For date ranges, shift by the range length
    const start = new Date(currentDate + 'T00:00:00');
    const end = new Date(currentEndDate + 'T23:59:59');
    const rangeDays = Math.ceil((end - start) / (24 * 60 * 60 * 1000)) + 1;
    start.setDate(start.getDate() + delta * rangeDays);
    end.setDate(end.getDate() + delta * rangeDays);
    currentDate = localDateStr(start);
    currentEndDate = localDateStr(end);
    currentStartTS = null;
    currentEndTS = null;
    updateDateTimeInputs();
  } else {
    // For single dates, shift by days
    const [y,m,day] = currentDate.split('-').map(Number);
    const d = new Date(y, m-1, day+delta);
    currentEndDate = null;
    currentStartTS = null;
    currentEndTS = null;
    currentDate = localDateStr(d);
    updateDateTimeInputs();
  }
  _loadAll();
  syncAISummaryForTimeWindow();
}

function applyClientFilter(clientIp, clientName){
  selectedClient = decodeURIComponent(clientIp);
  selectedClientName = decodeURIComponent(clientName);
  updateFilterBanner();
  loadCategories();
  loadDomains();
  loadHourly();
}

function clearClientFilter(){
  selectedClient = null;
  selectedClientName = null;
  updateFilterBanner();
  loadCategories();
  loadDomains();
  loadHourly();
}

function updateFilterBanner(){
  const banner = document.getElementById('filter-banner');
  if(selectedClient){
    banner.style.display = 'block';
    banner.innerHTML = `Filtering by <strong>${selectedClientName||selectedClient}</strong>. ` +
      `<button class="btn" style="font-size:13px;padding:4px 10px" onclick="clearClientFilter()">Clear filter</button>`;
  } else {
    banner.style.display = 'none';
    banner.innerHTML = '';
  }
}

function currentClientQuery(){
  return selectedClient ? `&client=${encodeURIComponent(selectedClient)}` : '';
}

// ── Summary Cards + Plain English ────────────────────────────────────────────
async function loadSummary(){
  try {
  const [ns, comp] = await Promise.all([
    fetch(`/api/summary?${dateQS()}`).then(r=>r.json()),
    fetch(`/api/compare?${dateQS()}`).then(r=>r.json())
  ]);
  const tq = ns.total_queries||0;
  const bq = ns.blocked_queries||0;
  const ud = ns.unique_domains||0;
  const ac = ns.active_clients||0;
  const bp = tq ? (bq/tq*100).toFixed(1) : 0;
  const ytq= comp.yesterday?.avg_q||0;
  const yud= comp.yesterday?.avg_d||0;

  // Fetch categories for attention count
  const cats = await fetch(`/api/categories?${dateQS()}`).then(r=>r.json());
  let attentionCount = 0;
  let attentionRequests = 0;
  let topCat = null, topCatQ = 0;
  let totalQ = cats.reduce((s,c)=>s+(c.queries||0),0)||1;
  const concernRows = [];
  for(const c of cats){
    const q = c.queries||0;
    const isAlert = ALERT_CATS.has(c.category) && q > 0;
    const isWatch = WATCH_CATS[c.category] && q >= WATCH_CATS[c.category];
    if(isAlert || isWatch){
      attentionCount++;
      attentionRequests += q;
      concernRows.push({ category: c.category, queries: q, level: isAlert ? 'alert' : 'warning' });
    }
    if(q>topCatQ){ topCatQ=q; topCat=c.category; }
  }

  document.getElementById('stat-row').innerHTML = `
    <div class="stat-card blue">
      <div class="stat-val">${fmt(tq)}</div>
      <div class="stat-lbl">Total Requests Today</div>
      <div class="stat-chg">${arrow(pct(tq,ytq))} vs yesterday</div>
      <div class="stat-sub">DNS lookups by all devices</div>
    </div>
    <div class="stat-card red">
      <div class="stat-val" style="color:#f85149">${fmt(bq)}</div>
      <div class="stat-lbl">Blocked by Pi-hole</div>
      <div class="stat-sub">${bp}% of traffic stopped</div>
    </div>
    <div class="stat-card yellow">
      <div class="stat-val" style="color:${attentionCount>0?'#d29922':'#3fb950'}">${attentionCount}</div>
      <div class="stat-lbl">Categories Need Attention</div>
      <div class="stat-sub">${attentionCount>0?`${fmt(attentionRequests)} requests flagged`:'All categories normal'}</div>
    </div>
    <div class="stat-card green">
      <div class="stat-val" style="color:#3fb950">${fmt(ac)}</div>
      <div class="stat-lbl">Active Devices Today</div>
      <div class="stat-chg">${arrow(pct(ud,yud))} unique sites vs yesterday</div>
    </div>`;

  // Plain English Summary
  const topCatLabel = topCat ? topCat.replace(/_/g,' ') : 'unknown';
  const topCatPct   = topCat ? ((topCatQ/totalQ)*100).toFixed(0) : 0;
  const concernLabels = concernRows.slice(0,3)
    .map(c => `${c.category.replace(/_/g,' ')} (${fmt(c.queries)})`)
    .join(', ');
  const compareTxt  = ytq>0
    ? (tq > ytq ? `That's <span class="highlight">more than yesterday</span> (${fmt(ytq)} requests).`
                : `That's <span class="highlight">less than yesterday</span> (${fmt(ytq)} requests).`)
    : '';
  const attentionTxt = concernRows.length > 0
    ? `<span class="highlight" style="color:#d29922">⚠️ ${concernRows.length} categor${concernRows.length===1?'y':'ies'} need your attention</span> — ${fmt(attentionRequests)} requests were flagged today. ${concernLabels ? `Top flagged categories: ${concernLabels}.` : ''}`
    : `<span class="highlight" style="color:#3fb950">✅ All categories look normal</span>.`;

  document.getElementById('summary-text').innerHTML =
    `Today your network made <span class="highlight">${fmt(tq)} DNS requests</span> from <span class="highlight">${ac} device${ac!==1?'s':''}</span>.
     Pi-hole blocked <span class="highlight">${fmt(bq)} (${bp}%)</span> of those — stopping ads, trackers and unwanted traffic before it reaches your devices. ${compareTxt}
     The most activity was <span class="highlight">${topCatLabel} (${topCatPct}% of traffic)</span>. ${attentionTxt}`;
  } catch(err) {
    document.getElementById('summary-text').innerHTML = '<span style="color:var(--red)">Failed to load summary</span>';
  }
}

// ── Alerts Banner ─────────────────────────────────────────────────────────────
async function loadAlerts(){
  try {
  const data = await fetch(`/api/alerts?${dateQS()}`).then(r=>r.json());
  const banner = document.getElementById('alert-banner');
  const section = document.getElementById('attention-section');
  const grid = document.getElementById('attention-grid');

  const allAlerts = [...(data.critical||[]), ...(data.warnings||[])];
  if(allAlerts.length === 0){
    banner.style.display = 'none';
    section.style.display = 'none';
    return;
  }

  // Top banner
  banner.style.display = 'block';
  const bannerItems = allAlerts.slice(0,4).map(a =>
    `<div class="alert-item">
      <span>${a.icon}</span>
      <span><strong>${a.title}:</strong> ${a.short}</span>
    </div>`).join('');
  banner.innerHTML = `
    <div class="alert-banner">
      <div class="alerts-inner">
        <span class="banner-label">⚠️ Attention Required</span>
        ${bannerItems}
      </div>
    </div>`;

  // Attention cards
  section.style.display = 'block';
  grid.innerHTML = allAlerts.map(a => {
    const topSites = a.top_domains && a.top_domains.length
      ? `<div class="ac-desc" style="color:var(--text);margin-top:8px;"><strong>Top sites:</strong> ${a.top_domains.join(', ')}</div>`
      : '';
    return `
    <div class="attention-card ${a.level==='warning'?'warn':''}">
      <div class="ac-header">
        <div class="ac-title">${a.icon} ${a.title}</div>
        <span class="ac-badge ${a.level==='warning'?'badge-warn':'badge-alert'}">${a.level==='warning'?'⚠️ Watch':'🚨 Alert'}</span>
      </div>
      <div class="ac-count">${fmt(a.queries)} requests</div>
      <div class="ac-desc">${a.description}</div>
      ${topSites}
      <div class="ac-devices">📱 ${a.devices||'Unknown device'}</div>
      <button class="btn ac-btn" style="font-size:13px;padding:4px 10px"
        onclick="showCategoryDetail('${a.category}','${a.title}')">🔍 See Sites</button>
    </div>`;
  }).join('');
  } catch(err) { console.error('alerts:', err); }
}

// ── Categories Table ─────────────────────────────────────────────────────────
async function loadCategories(){
  try {
  const rows = await fetch(`/api/categories?${dateQS()}${currentClientQuery()}`).then(r=>r.json());
  const total = rows.reduce((s,r)=>s+(r.queries||0),0)||1;
  const maxQ  = Math.max(...rows.map(r=>r.queries||0),1);
  document.getElementById('cat-pill').textContent = `${rows.length} categories`;

  // Donut chart
  const labels = rows.slice(0,8).map(r=>(CAT_ICONS[r.category]||'')+ ' '+r.category.replace(/_/g,' '));
  const values = rows.slice(0,8).map(r=>r.queries||0);
  const colors = rows.slice(0,8).map(r=>CAT_COLORS[r.category]||'#7f8c8d');
  if(catChart) catChart.destroy();
  catChart = new Chart(document.getElementById('cat-chart'),{
    type:'doughnut',
    data:{ labels, datasets:[{ data:values, backgroundColor:colors, borderWidth:2, borderColor:'#ffffff' }] },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ position:'right', labels:{ color:'#1f2328', font:{size:10}, padding:6, boxWidth:10 } } }
    }
  });

  // Category table (sorted: alerts first, then by queries)
  const sorted = [...rows].sort((a,b)=>{
    const aAlert = ALERT_CATS.has(a.category)&&a.queries>0 ? 2
      : (WATCH_CATS[a.category]&&a.queries>=WATCH_CATS[a.category] ? 1 : 0);
    const bAlert = ALERT_CATS.has(b.category)&&b.queries>0 ? 2
      : (WATCH_CATS[b.category]&&b.queries>=WATCH_CATS[b.category] ? 1 : 0);
    return bAlert - aAlert || b.queries - a.queries;
  });

  const tbody = sorted.map(r=>{
    const q = r.queries||0;
    const p = ((q/total)*100).toFixed(1);
    const color = CAT_COLORS[r.category]||'#7f8c8d';
    const status = getStatus(r.category, q);
    return `
    <tr class="clickable" onclick="showCategoryDetail('${r.category}','${r.category.replace(/_/g,' ')}')" title="Click to see top sites">
      <td>${catBadge(r.category)}</td>
      <td>${fmt(q)}</td>
      <td>${p}%</td>
      <td>${fmt(r.unique_domains)}</td>
      <td style="min-width:100px">${miniBar(q,maxQ,color)}</td>
      <td><span class="status-badge ${status.cls}">${status.label}</span></td>
    </tr>`;
  }).join('');
  document.querySelector('#cat-table tbody').innerHTML = tbody || '<tr><td colspan="6" class="empty">No category data</td></tr>';
  } catch(err) {
    document.querySelector('#cat-table tbody').innerHTML = `<tr><td colspan="6" style="color:var(--red);padding:12px">Failed to load categories: ${err.message}</td></tr>`;
  }
}

// ── Device Cards ─────────────────────────────────────────────────────────────
// Server-side filtering (config.yaml `excluded_devices`) is the source of truth.
async function loadDeviceCards(){
  try {
  const all = await fetch(`/api/devices?${dateQS()}`).then(r=>r.json());
  // Hide cards with zero queries — nothing to show
  const filtered = all.filter(r => (r.today_q || 0) > 0);
  if(!filtered.length){
    document.getElementById('device-grid').innerHTML='<div class="empty">No personal devices found today</div>';
    return;
  }
  const maxQ = Math.max(...filtered.map(r=>r.today_q||0),1);
  const ALERT_SET = new Set(['adult','vpn_proxy','crypto']);
  const WATCH_MAP = {social_media:900,gaming:1500,streaming:3000};

  // Fetch per-device category breakdown in parallel
  const catData = await Promise.all(
    filtered.map(r=>fetch(`/api/categories?${dateQS()}&client=${encodeURIComponent(r.client_ip)}`).then(x=>x.json()))
  );

  const html = filtered.map((r,i)=>{
    const cats   = catData[i]||[];
    const barPct = maxQ ? Math.min(100,Math.round((r.today_q/maxQ)*100)) : 0;
    const totalCatQ = cats.reduce((s,c)=>s+(c.queries||0),0)||1;
    const topCats   = cats.filter(c=>c.queries>0).slice(0,4);
    const alertFlags= cats.filter(c=>ALERT_SET.has(c.category)&&c.queries>0);
    const warnFlags = cats.filter(c=>WATCH_MAP[c.category]&&c.queries>=WATCH_MAP[c.category]&&!alertFlags.find(a=>a.category===c.category));
    const isFlagged = alertFlags.length>0;

    const topCatsHtml = topCats.map(c=>{
      const cp = Math.round((c.queries/totalCatQ)*100);
      const col= CAT_COLORS[c.category]||'#888';
      return `<span class="cat-badge" style="background:${col}18;color:${col};border:1px solid ${col}40;font-size:12px">${CAT_ICONS[c.category]||'🌐'} ${c.category.replace(/_/g,' ')} ${cp}%</span>`;
    }).join('');

    const flagsHtml = [...alertFlags.map(c=>`
      <div class="dc-flag" id="dcf-${r.client_ip.replace(/\./g,'-')}-${c.category}">
        <div class="flag-title">🚨 ${c.category.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase())}: ${fmt(c.queries)} requests</div>
        <div class="flag-links"><span style="color:var(--muted);font-size:12px">Loading sites…</span></div>
      </div>`),
    ...warnFlags.map(c=>`
      <div class="dc-flag warn" id="dcf-${r.client_ip.replace(/\./g,'-')}-${c.category}">
        <div class="flag-title">⚠️ High ${c.category.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase())}: ${fmt(c.queries)} requests</div>
        <div class="flag-links"><span style="color:var(--muted);font-size:12px">Loading sites…</span></div>
      </div>`)
    ].join('');

    const chgHtml = r.yesterday_q
      ? (r.today_q>=r.yesterday_q
          ? `<span class="chg-up">▲ ${Math.abs(pct(r.today_q,r.yesterday_q)).toFixed(0)}%</span>`
          : `<span class="chg-down">▼ ${Math.abs(pct(r.today_q,r.yesterday_q)).toFixed(0)}%</span>`)
      : '<span class="chg-same">—</span>';

    const viewDetailsBtn = (alertFlags.length||warnFlags.length)
      ? `<a href="/device?ip=${encodeURIComponent(r.client_ip)}&date=${currentDate}"
            onclick="event.stopPropagation()"
            style="display:inline-flex;align-items:center;gap:4px;margin-top:8px;
                   padding:5px 12px;background:#fff0f0;border:1px solid #fca5a5;
                   border-radius:6px;font-size:13px;font-weight:600;color:#b91c1c;
                   text-decoration:none;transition:all .15s"
            onmouseover="this.style.background='#fee2e2'"
            onmouseout="this.style.background='#fff0f0'">
            🔍 View Full Details
         </a>`
      : `<a href="/device?ip=${encodeURIComponent(r.client_ip)}&date=${currentDate}"
            onclick="event.stopPropagation()"
            style="display:inline-flex;align-items:center;gap:4px;margin-top:8px;
                   padding:5px 12px;background:#f0f7ff;border:1px solid #c9dff7;
                   border-radius:6px;font-size:13px;color:var(--accent);
                   text-decoration:none;transition:all .15s"
            onmouseover="this.style.background='#dbeafe'"
            onmouseout="this.style.background='#f0f7ff'">
            🔍 View Details
         </a>`;

    return `
    <div class="device-card ${isFlagged?'flagged':''}"
         onclick="applyClientFilter('${encodeURIComponent(r.client_ip)}','${encodeURIComponent(r.client_name||r.client_ip)}')">
      <div class="dc-header">
        <div class="device-avatar">${DEVICE_ICONS[i%DEVICE_ICONS.length]}</div>
        <div style="min-width:0;flex:1">
          <div class="dc-name">${r.client_name||r.client_ip}</div>
          ${r.device_type?`<div style="font-size:13px;color:var(--accent);font-weight:500">${r.device_type}</div>`:''}
          <div class="dc-ip">${r.client_ip}${r.hostname&&r.hostname!==r.client_name?` · ${r.hostname}`:''}</div>
          ${r.mac?`<div style="font-size:12px;color:var(--muted);font-family:monospace">${r.mac}</div>`:''}
        </div>
      </div>
      <div class="dc-stats">
        <div class="dc-stat"><div class="val">${fmt(r.today_q)}</div><div class="lbl">Requests</div></div>
        <div class="dc-stat"><div class="val">${fmt(r.today_d)}</div><div class="lbl">Sites</div></div>
        <div class="dc-stat"><div class="val" style="font-size:13px">${chgHtml}</div><div class="lbl">vs Yesterday</div></div>
      </div>
      <div class="dc-bar-bg"><div class="dc-bar-fg" style="width:${barPct}%"></div></div>
      <div class="dc-cats">${topCatsHtml||'<span style="color:var(--muted);font-size:13px">No data yet</span>'}</div>
      ${(alertFlags.length||warnFlags.length)?`<div class="dc-flags">${flagsHtml}</div>`:''}
      ${viewDetailsBtn}
    </div>`;
  }).join('');

  document.getElementById('device-grid').innerHTML = html;

  // Load top sites for each flagged device/category asynchronously
  for(const [i,r] of filtered.entries()){
    const cats = catData[i]||[];
    const ALERT_SET2 = new Set(['adult','vpn_proxy','crypto']);
    const WATCH_MAP2 = {social_media:900,gaming:1500,streaming:3000};
    const flagged = [
      ...cats.filter(c=>ALERT_SET2.has(c.category)&&c.queries>0),
      ...cats.filter(c=>WATCH_MAP2[c.category]&&c.queries>=WATCH_MAP2[c.category])
    ];
    for(const fc of flagged){
      const elId = `dcf-${r.client_ip.replace(/\./g,'-')}-${fc.category}`;
      const container = document.getElementById(elId);
      if(!container) continue;
      const linksDiv = container.querySelector('.flag-links');
      if(!linksDiv) continue;
      try{
        const sites = await fetch(`/api/category_detail?${dateQS()}&category=${encodeURIComponent(fc.category)}&client=${encodeURIComponent(r.client_ip)}&limit=5`).then(x=>x.json());
        linksDiv.innerHTML = sites.length
          ? sites.map(s=>`<a href="https://${s.domain}" target="_blank" rel="noopener noreferrer" title="${fmt(s.queries)} requests">${s.domain} (${fmt(s.queries)})</a>`).join('')
          : '<span style="color:var(--muted);font-size:12px">No specific sites found</span>';
      }catch(e){ linksDiv.innerHTML=''; }
    }
  }
  } catch(err) {
    document.getElementById('device-grid').innerHTML = `<div class="empty" style="color:var(--red)">Failed to load device data: ${err.message}</div>`;
  }
}

// ── Risky Category Cards ──────────────────────────────────────────────────────
async function loadRiskyCategoryCards(){
  try {
  const RISK_CATS = [
    {cat:'adult',       icon:'🔞',title:'Adult Content',      level:'alert',desc:'Explicit/adult websites — should not be accessible to children.'},
    {cat:'vpn_proxy',   icon:'🔒',title:'VPN / Proxy',        level:'alert',desc:'VPN or proxy services can bypass filters and parental controls.'},
    {cat:'crypto',      icon:'₿', title:'Crypto / Blockchain',level:'alert',desc:'Cryptocurrency activity — watch for scams or unsupervised spending.'},
    {cat:'social_media',icon:'📱',title:'Social Media',       level:'watch',desc:'Social platforms — monitor screen time, especially for children.',threshold:900},
    {cat:'gaming',      icon:'🎮',title:'Gaming',             level:'watch',desc:'Online gaming — check for excessive hours or in-app purchases.',threshold:1500},
    {cat:'streaming',   icon:'🎬',title:'Video Streaming',    level:'watch',desc:'Streaming services — high usage may mean extended screen time.',threshold:3000},
  ];

  const [cats, alertsData, blockedList] = await Promise.all([
    fetch(`/api/categories?${dateQS()}`).then(r=>r.json()),
    fetch(`/api/alerts?${dateQS()}`).then(r=>r.json()),
    fetch('/api/blocked_domains').then(r=>r.json()).catch(()=>[])
  ]);
  const blockedSet = new Set(blockedList.map(b=>b.domain));
  const catMap={};
  cats.forEach(c=>catMap[c.category]=c);

  const siteResults = await Promise.all(
    RISK_CATS.map(rc=>{
      const row=catMap[rc.cat];
      return (row&&row.queries>0)
        ? fetch(`/api/category_detail?${dateQS()}&category=${encodeURIComponent(rc.cat)}&limit=6`).then(r=>r.json())
        : Promise.resolve([]);
    })
  );

  const allAlerts=[...(alertsData.critical||[]),...(alertsData.warnings||[])];

  const html = RISK_CATS.map((rc,i)=>{
    const row    = catMap[rc.cat]||{queries:0,unique_domains:0};
    const q      = row.queries||0;
    const sites  = siteResults[i]||[];
    const aInfo  = allAlerts.find(a=>a.category===rc.cat);
    const devTxt = aInfo?aInfo.devices:'';

    // Badge logic:
    //   alert-level cats (adult/vpn/crypto): any query = 🚨 Alert, zero = ✅ Clear
    //   watch-level cats (social/gaming/streaming):
    //     above threshold = ⚠️ Watch, any queries but below = ℹ️ Active, zero = ✅ Clear
    let cardCls, bdgCls, bdgTxt;
    if(rc.level==='alert'){
      if(q>0){ cardCls='rc-alert-card'; bdgCls='rc-badge-alert'; bdgTxt='🚨 Alert'; }
      else    { cardCls='rc-clean-card'; bdgCls='rc-badge-clean'; bdgTxt='✅ Clear'; }
    } else {
      if(q>0 && rc.threshold && q>=rc.threshold){ cardCls='rc-warn-card';  bdgCls='rc-badge-warn';  bdgTxt='⚠️ High Usage'; }
      else if(q>0)                              { cardCls='rc-clean-card'; bdgCls='rc-badge-info';  bdgTxt='ℹ️ Active'; }
      else                                      { cardCls='rc-clean-card'; bdgCls='rc-badge-clean'; bdgTxt='✅ Clear'; }
    }

    let sitesHtml='';
    if(sites.length){
      sitesHtml=`<div class="rc-sites">${sites.map(s=>{
        const isBlocked = blockedSet.has(s.domain);
        return `<div class="rc-site">
          <div class="rc-site-left">
            <a href="https://${s.domain}" target="_blank" rel="noopener noreferrer">${s.domain}</a>
            <span class="rc-cnt">${fmt(s.queries)} requests</span>
          </div>
          <button class="btn-block ${isBlocked?'blocked':''}"
            title="${isBlocked?'Blocked — click to unblock':'Block this domain'}"
            onclick="${isBlocked?`unblockDomain('${s.domain}',this)`:`blockDomain('${s.domain}','${rc.cat}',this)`}">
            ${isBlocked?'✅':'🚫'}
          </button>
        </div>`;
      }).join('')}</div>`;
    } else if(q===0){
      sitesHtml=`<div style="font-size:13px;color:var(--green)">✅ None accessed today — all clear</div>`;
    }

    const uniqueTxt = row.unique_domains>0 ? `<span style="font-size:13px;color:var(--muted)">${fmt(row.unique_domains)} unique sites</span>` : '';

    return `
    <div class="risky-card ${cardCls}">
      <div class="rc-top">
        <div><div class="rc-icon">${rc.icon}</div><div class="rc-title">${rc.title}</div></div>
        <span class="rc-badge ${bdgCls}">${bdgTxt}</span>
      </div>
      ${q>0
        ? `<div class="rc-count">${fmt(q)} requests ${uniqueTxt}</div>
           <div class="rc-desc">${rc.desc}${rc.threshold&&q<rc.threshold?' Below watch threshold of '+fmt(rc.threshold)+'.':''}</div>
           ${devTxt?`<div class="rc-devices">📱 <strong>Devices:</strong> ${devTxt}</div>`:''}
           ${sitesHtml}
           <button class="btn" style="font-size:13px;padding:4px 10px;margin-top:2px" onclick="event.stopPropagation();showCategoryDetail('${rc.cat}','${rc.title}')">🔍 See All Sites</button>`
        : `<div style="font-size:13px;color:var(--muted);font-style:italic;margin-top:4px">No activity today</div>`
      }
    </div>`;
  }).join('');

  document.getElementById('risky-grid').innerHTML=html;
  } catch(err) {
    document.getElementById('risky-grid').innerHTML=
      `<div class="empty" style="color:var(--red)">Could not load category cards: ${err.message}</div>`;
    console.error('loadRiskyCategoryCards error:', err);
  }
}

// ── Per-Device Time Series ────────────────────────────────────────────────────
const TS_COLORS = ['#58a6ff','#f78166','#3fb950','#d2a8ff','#ffa657','#39d353','#ff7b72','#79c0ff','#56d364','#e3b341'];
const SKIP_TS   = ['amazon','samsung','pihole','localhost','127.0.0.'];

async function loadTimeSeries(){
  try {
  const data = await fetch(`/api/hourly?${dateQS()}`).then(r=>r.json());
  const hours = Array.from({length:24},(_,i)=>String(i).padStart(2,'0'));

  // data is {ip: {client_name, hours:[{hour,queries}]}}
  const clients = Object.entries(data).filter(([ip,v])=>{
    const n=(v.client_name||ip).toLowerCase();
    return !SKIP_TS.some(s=>n.includes(s)||ip.includes(s));
  });

  // Sort by total queries desc, take top 6
  clients.sort((a,b)=>{
    const ta=(b[1].hours||[]).reduce((s,h)=>s+h.queries,0);
    const tb=(a[1].hours||[]).reduce((s,h)=>s+h.queries,0);
    return ta-tb;
  });
  const top = clients.slice(0,6);

  const datasets = top.map(([ip,v],i)=>{
    const hmap={};
    (v.hours||[]).forEach(h=>{ hmap[h.hour]=(hmap[h.hour]||0)+h.queries; });
    return {
      label: v.client_name||ip,
      data: hours.map(h=>hmap[h]||0),
      borderColor: TS_COLORS[i%TS_COLORS.length],
      backgroundColor: TS_COLORS[i%TS_COLORS.length]+'22',
      borderWidth:2, pointRadius:2, pointHoverRadius:5,
      tension:.35, fill:false
    };
  });

  if(timeseriesChart) timeseriesChart.destroy();
  timeseriesChart = new Chart(document.getElementById('timeseries-chart'),{
    type:'line',
    data:{ labels:hours.map(h=>h+':00'), datasets },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{ mode:'index', intersect:false },
      plugins:{
        legend:{ position:'bottom', labels:{ color:'#1f2328', font:{size:11}, boxWidth:12, padding:12 } },
        tooltip:{ callbacks:{ label:ctx=>`${ctx.dataset.label}: ${fmt(ctx.raw)}` } }
      },
      scales:{
        x:{ ticks:{color:'#656d76',font:{size:10}, maxTicksLimit:12}, grid:{color:'#e8ecf0'} },
        y:{ ticks:{color:'#656d76',font:{size:10}}, grid:{color:'#e8ecf0'}, beginAtZero:true }
      }
    }
  });
  } catch(err) { console.error('timeseries:', err); }
}

// ── Hourly Chart ─────────────────────────────────────────────────────────────
async function loadHourly(){
  try {
  const data = await fetch(`/api/hourly?${dateQS()}${currentClientQuery()}`).then(r=>r.json());
  const hours = Array.from({length:24},(_,i)=>String(i).padStart(2,'0'));
  const queryMap = {};
  if(Array.isArray(data)){
    data.forEach(h=>{ queryMap[h.hour]=(queryMap[h.hour]||0)+h.queries; });
  } else {
    Object.values(data).forEach(client=>{
      (client.hours||[]).forEach(h=>{queryMap[h.hour]=(queryMap[h.hour]||0)+h.queries;});
    });
  }
  const values = hours.map(h=>queryMap[h]||0);
  const maxVal = Math.max(...values,1);
  const peakHour = hours[values.indexOf(maxVal)];

  if(hourlyChart) hourlyChart.destroy();
  hourlyChart = new Chart(document.getElementById('hourly-chart'),{
    type:'bar',
    data:{
      labels:hours.map(h=>h+':00'),
      datasets:[{
        label:'Requests',
        data:values,
        backgroundColor: values.map(v => v===maxVal ? '#58a6ff80' : '#58a6ff20'),
        borderColor: values.map(v => v===maxVal ? '#58a6ff' : '#58a6ff60'),
        borderWidth:1, borderRadius:3,
      }]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{display:false},
        tooltip:{ callbacks:{ label:ctx=>`${fmt(ctx.raw)} requests` } }
      },
      scales:{
        x:{ ticks:{color:'#656d76',maxRotation:0,font:{size:9}}, grid:{color:'#e8ecf0'} },
        y:{ ticks:{color:'#656d76',font:{size:10}}, grid:{color:'#e8ecf0'} }
      }
    }
  });
  } catch(err) { console.error('hourly:', err); }
}

// ── Protection Summary ────────────────────────────────────────────────────────
async function loadProtection(){
  try {
  const data = await fetch(`/api/blocking?${dateQS()}`).then(r=>r.json());
  const total   = data.total_queries||0;
  const blocked = data.blocked_queries||0;
  const bp      = total ? (blocked/total*100).toFixed(1) : 0;
  const allowed = total - blocked;

  document.getElementById('protection-stats').innerHTML = `
    <div class="ps-box">
      <div class="ps-val">${fmt(total)}</div>
      <div class="ps-lbl">Total Requests</div>
    </div>
    <div class="ps-box">
      <div class="ps-val">${fmt(blocked)}</div>
      <div class="ps-lbl">Blocked (${bp}%)</div>
    </div>
    <div class="ps-box">
      <div class="ps-val">${fmt(allowed)}</div>
      <div class="ps-lbl">Passed Through</div>
    </div>`;

  const quality = bp > 20 ? 'excellent' : bp > 10 ? 'good' : 'moderate';
  const tip = bp > 20
    ? 'Your Pi-hole is working very hard — this is a well-protected network.'
    : bp > 10
      ? 'Pi-hole is providing solid protection against ads and trackers.'
      : 'Consider reviewing your blocklists to improve protection.';

  document.getElementById('protection-explain').innerHTML =
    `<strong>Pi-hole acts like a bouncer for your network.</strong>
     Out of ${fmt(total)} requests today, it turned away <strong>${fmt(blocked)} (${bp}%)</strong> that were
     ads, trackers, telemetry, or unwanted services — before they ever reached your devices.
     <strong>${fmt(allowed)} requests passed through</strong> to the internet.
     Protection quality: <strong>${quality}</strong>. ${tip}`;
  } catch(err) {
    document.getElementById('protection-explain').innerHTML = `<div class="empty" style="color:var(--red)">Failed to load protection data: ${err.message}</div>`;
  }
}

// ── New Domains ───────────────────────────────────────────────────────────────
async function loadNewDomains(){
  try {
  const rows = await fetch(`/api/new_domains?${dateQS()}`).then(r=>r.json());
  if(!rows.length){
    document.getElementById('new-domains-list').innerHTML = '<div class="empty">No new sites seen today</div>';
    return;
  }
  const html = rows.slice(0,12).map(r=>`
    <div class="new-domain-row">
      <div class="nd-dot"></div>
      <div class="nd-domain" title="${r.domain}">${r.domain}</div>
      <div class="nd-meta">${catBadge(r.category)}<br>${fmt(r.queries)} req</div>
      ${_ignoreBtn(r.domain)}
    </div>`).join('');
  document.getElementById('new-domains-list').innerHTML = html;
  } catch(err) {
    document.getElementById('new-domains-list').innerHTML = `<div class="empty" style="color:var(--red)">Failed to load: ${err.message}</div>`;
  }
}

// ── Trend Chart ───────────────────────────────────────────────────────────────
async function loadTrend(){
  try {
  const rows = await fetch('/api/trend?days=7').then(r=>r.json());
  if(trendChart) trendChart.destroy();
  trendChart = new Chart(document.getElementById('trend-chart'),{
    type:'line',
    data:{
      labels:rows.map(r=>{ const d=new Date(r.date); return d.toLocaleDateString('en',{weekday:'short',month:'short',day:'numeric'}); }),
      datasets:[
        { label:'Total', data:rows.map(r=>r.total_queries||0),
          borderColor:'#58a6ff', backgroundColor:'#58a6ff15',
          fill:true, tension:.4, pointRadius:4, pointBackgroundColor:'#58a6ff' },
        { label:'Blocked', data:rows.map(r=>r.blocked_queries||0),
          borderColor:'#f85149', backgroundColor:'#f8514915',
          fill:true, tension:.4, pointRadius:4, pointBackgroundColor:'#f85149' }
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ labels:{ color:'#1f2328', font:{size:11} } },
               tooltip:{ callbacks:{ label:ctx=>`${ctx.dataset.label}: ${fmt(ctx.raw)}` } } },
      scales:{
        x:{ ticks:{color:'#656d76',font:{size:10}}, grid:{color:'#e8ecf0'} },
        y:{ ticks:{color:'#656d76'}, grid:{color:'#e8ecf0'} }
      }
    }
  });
  } catch(err) { console.error('trend:', err); }
}

// ── Blocked Top Domains ───────────────────────────────────────────────────────
async function loadBlockedTop(){
  try {
    const rows = await fetch(`/api/blocked_top?${dateQS()}`).then(r=>r.json());
    document.getElementById('blocked-top-count').textContent = rows.length ? `${rows.length} domains` : '';
    if(!rows.length){
      document.getElementById('blocked-top-content').innerHTML = '<div class="empty">No blocked domains found for this date</div>';
      return;
    }
    const tbody = rows.map(r=>{
      const cat = r.category || 'other';
      const color = CAT_COLORS[cat]||'#7f8c8d';
      const icon  = CAT_ICONS[cat]||'🌐';
      const label = cat.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase());
      const badge = `<span class="cat-badge" style="background:${color}25;color:${color};border:1px solid ${color}50">${icon} ${label}</span>`;
      return `<tr>
        <td class="mono">${r.domain}</td>
        <td>${badge}</td>
        <td style="color:var(--red);font-weight:600">${fmt(r.blocked_count)}</td>
        <td>${fmt(r.device_count)}</td>
        <td>${_ignoreBtn(r.domain)}</td>
      </tr>`;
    }).join('');
    document.getElementById('blocked-top-content').innerHTML = `
      <table>
        <thead><tr><th>Domain</th><th>Category</th><th>Times Blocked</th><th>Devices</th></tr></thead>
        <tbody>${tbody}</tbody>
      </table>`;
  } catch(err) {
    document.getElementById('blocked-top-content').innerHTML = `<div class="empty" style="color:var(--red)">Failed to load blocked domains: ${err.message}</div>`;
  }
}

// ── Health Panel ──────────────────────────────────────────────────────────────
let healthLoaded = false;

function toggleHealth() {
  const panel = document.getElementById('health-panel');
  const btn   = document.getElementById('health-btn');
  const shown = panel.style.display !== 'none';
  panel.style.display = shown ? 'none' : '';
  btn.textContent = shown ? '🏥 Health' : '✕ Health';
  if (!shown && !healthLoaded) loadHealth();
}

async function loadHealth() {
  const el = document.getElementById('health-content');
  el.innerHTML = '<div class="loader pulse">Loading…</div>';
  try {
    const data = await fetch('/api/health').then(r => r.json());
    const sys  = data.system  || {};
    const db   = data.db      || {};
    const svcs = data.services|| [];
    const ph   = data.pihole  || {};
    const errs = data.recent_errors || [];

    function pill(txt, col) {
      const bg = {green:'#dcfce7',red:'#fee2e2',yellow:'#fef3c7',gray:'#f3f4f6'}[col]||'#f3f4f6';
      const fg = {green:'#15803d',red:'#b91c1c',yellow:'#854d0e',gray:'#374151'}[col]||'#374151';
      const bd = {green:'#86efac',red:'#fca5a5',yellow:'#fcd34d',gray:'#e5e7eb'}[col]||'#e5e7eb';
      return `<span style="background:${bg};border:1px solid ${bd};color:${fg};border-radius:10px;padding:2px 8px;font-size:12px;font-weight:600">${txt}</span>`;
    }
    function row(label, value) {
      return `<tr><td style="padding:4px 10px 4px 0;font-size:14px;color:var(--muted);width:50%">${label}</td><td style="padding:4px 0;font-size:14px;font-weight:500">${value}</td></tr>`;
    }
    function card(title, rows) {
      return `<div class="panel" style="margin-bottom:0"><div style="font-size:14px;font-weight:600;color:var(--accent);margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border2)">${title}</div><table style="width:100%;border-collapse:collapse">${rows}</table></div>`;
    }

    // Pi-hole card
    const phRows = ph.reachable
      ? row('Status',   ph.blocking ? pill('✅ Blocking ON','green') : pill('⛔ Blocking OFF','red'))
        + row('Gravity', ph.gravity_count_h ? ph.gravity_count_h+' domains' : '—')
        + row('Version', ph.version||'—')
        + row('Upstream DNS', ph.upstream_dns||'—')
        + row('FTL', ph.ftl_running ? pill('Running','green') : pill('Unknown','gray'))
      : row('Status', pill('⚠️ Unreachable','red')) + row('Error', (ph.error||'').slice(0,60));

    // System card
    const dp = sys.disk_pct||0, mp = sys.mem_pct||0, cp = sys.cpu_load_pct||0;
    const temp = sys.cpu_temp_c;
    const tempStr = temp != null ? pill(temp + '°C', temp>75?'red':temp>60?'yellow':'green') : '—';
    const sysRows = row('Disk', pill(dp+'%', dp>90?'red':dp>75?'yellow':'green') + ` (${sys.disk_used_h||'—'} used · ${sys.disk_free_h||'—'} free)`)
      + row('RAM', pill(mp+'%', mp>90?'red':mp>75?'yellow':'green') + ` (${sys.mem_used_h||'—'} / ${sys.mem_total_h||'—'})`)
      + row('CPU Load', pill(cp+'%', cp>90?'red':cp>50?'yellow':'green') + ` (${sys.cpu_load1||0} · ${sys.cpu_load5||0} · ${sys.cpu_load15||0})`)
      + row('Uptime', sys.uptime_str||'—')
      + row('Temp', tempStr);

    // DB card
    const stale = db.last_fetch_stale;
    const dbRows = row('DB Size', db.db_size_h||'—')
      + row('Total Records', (db.total_queries||0).toLocaleString())
      + row('Days Tracked', (db.total_days||0)+' days')
      + row('Today Queries', (db.today_queries||0).toLocaleString())
      + row('Last Fetch', (db.last_fetch_time||'—') + ' ' + (stale ? pill(db.last_fetch_ago||'stale','red') : pill(db.last_fetch_ago||'—','green')))
      + row('Logs Total', db.logs_total_h||'—')
      + row('Data Gaps (7d)', db.data_gaps&&db.data_gaps.length ? db.data_gaps.join(', ') : pill('None','green'));

    // Services card
    const svcRows = svcs.map(s => {
      const a = s.active;
      const res = s.result || '';
      // oneshot services (fetch.service) are "inactive" after a successful run — show as OK
      const isOneshotOk = a === 'inactive' && (res === 'success' || res === '');
      const p = a==='active'     ? pill('✅ Active','green')
              : a==='failed'     ? pill('❌ Failed','red')
              : isOneshotOk      ? pill('✅ Completed','green')
              : a==='inactive'   ? pill('⏸ Inactive','yellow')
              : pill(a,'gray');
      const trig = s.last_trigger ? ` <span style="font-size:12px;color:var(--muted)">· last: ${s.last_trigger}</span>` : '';
      return row(s.label, p + trig);
    }).join('');

    // Error log section
    const errHtml = errs.length
      ? `<div style="margin-top:12px;background:#fff5f5;border:1px solid #fca5a5;border-left:3px solid var(--red);border-radius:6px;padding:10px 12px">
           <div style="font-size:13px;font-weight:600;color:var(--red);margin-bottom:6px">⚠️ Recent Errors (${errs.length})</div>
           ${errs.slice(-5).map(e=>`<div style="font-size:12px;font-family:monospace;color:var(--red);padding:2px 0"><span style="color:var(--muted)">[${e.file}]</span> ${e.line.slice(0,120)}</div>`).join('')}
         </div>` : '';

    el.innerHTML = `
      ${errHtml}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div style="display:flex;flex-direction:column;gap:12px">${card('🛡️ Pi-hole Status', phRows)}${card('📊 Analytics DB', dbRows)}</div>
        <div style="display:flex;flex-direction:column;gap:12px">${card('💻 System Resources', sysRows)}${card('⚙️ Services', svcRows)}</div>
      </div>
      <div style="font-size:13px;color:var(--muted);margin-top:8px;text-align:right">Collected at ${data.collected_at||''}</div>`;
    healthLoaded = true;
  } catch(err) {
    el.innerHTML = `<div class="empty" style="color:var(--red)">Failed to load health data: ${err.message}</div>`;
  }
}

// ── Category Detail Modal ─────────────────────────────────────────────────────
async function showCategoryDetail(cat, label){
  document.getElementById('cat-modal').classList.add('open');
  const icon = CAT_ICONS[cat]||'🌐';
  const color= CAT_COLORS[cat]||'#7f8c8d';
  document.getElementById('cat-modal-title').innerHTML =
    `<span style="color:${color}">${icon}</span> ${label.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase())} — Top Sites Today`;
  document.getElementById('cat-modal-body').innerHTML = '<div class="loader">Loading…</div>';

  const clientQuery = selectedClient ? `&client=${encodeURIComponent(selectedClient)}` : '';
  const rows = await fetch(`/api/category_detail?${dateQS()}&category=${encodeURIComponent(cat)}${clientQuery}`).then(r=>r.json());
  if(!rows.length){
    document.getElementById('cat-modal-body').innerHTML = '<div class="empty">No data for this category today</div>';
    return;
  }
  const maxQ = Math.max(...rows.map(r=>r.queries||0),1);
  const tbody = rows.map(r=>`
    <tr>
      <td class="mono">${r.domain}</td>
      <td>${fmt(r.queries)}</td>
      <td style="min-width:80px">${miniBar(r.queries,maxQ,color)}</td>
      <td style="font-size:13px;color:var(--muted)">${r.client_name||''}</td>
      <td style="display:flex;gap:4px;align-items:center">
        <button class="btn-block" onclick="blockDomain('${r.domain}','${cat}',this)" title="Block domain">🚫</button>
        ${_ignoreBtn(r.domain)}
      </td>
    </tr>`).join('');
  document.getElementById('cat-modal-body').innerHTML = `
    <table>
      <thead><tr><th>Domain / Site</th><th>Requests</th><th>Traffic</th><th>First Seen By</th><th></th></tr></thead>
      <tbody>${tbody}</tbody>
    </table>
    <p style="font-size:13px;color:var(--muted);margin-top:12px">
      Showing top ${rows.length} sites. Click "Send Report" for the full email report.
    </p>`;
}
function closeCatModal(){
  document.getElementById('cat-modal').classList.remove('open');
}

// ── Report Modal ──────────────────────────────────────────────────────────────
function openReportModal(){ document.getElementById('report-modal').classList.add('open'); }
function closeReportModal(){ document.getElementById('report-modal').classList.remove('open'); }
function selectPeriod(p, el){
  selectedPeriod = p;
  document.querySelectorAll('.period-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
}

async function sendReport(){
  const statusEl = document.getElementById('report-status');
  statusEl.style.display='block';
  statusEl.className='modal-status sending';
  statusEl.textContent=`⏳ Sending ${selectedPeriod} report… this may take 30 seconds.`;

  try {
    const res = await fetch('/api/send_report', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({period: selectedPeriod})
    });
    const data = await res.json();
    if(data.status==='queued'){
      statusEl.className='modal-status success';
      statusEl.textContent=`✅ ${data.message} Check your inbox in about 30 seconds.`;
    } else {
      statusEl.className='modal-status error';
      statusEl.textContent=`❌ ${data.message||'Failed to send report'}`;
    }
  } catch(e) {
    statusEl.className='modal-status error';
    statusEl.textContent='❌ Could not reach the server. Is the dashboard running?';
  }
}

// ── Ignore / Unignore Domain ─────────────────────────────────────────────────
async function ignoreDomain(domain, btn){
  if(btn.classList.contains('busy')) return;
  const isIgnored = btn.classList.contains('ignored');
  btn.classList.add('busy');
  try {
    const res = await fetch('/api/ignore_domain', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({domain, action: isIgnored ? 'unignore' : 'ignore'})
    });
    const data = await res.json();
    if(data.status === 'ignored'){
      btn.textContent='Hidden';
      btn.classList.add('ignored');
      btn.title='Hidden from dashboard & reports. Click to show again.';
      btn.onclick = ()=>ignoreDomain(domain, btn);
      // Fade out the row so the user sees it disappear
      const row = btn.closest('tr') || btn.closest('.new-domain-row');
      if(row){ row.style.transition='opacity .4s'; row.style.opacity='0.25'; }
    } else if(data.status === 'unignored'){
      btn.textContent='Ignore';
      btn.classList.remove('ignored');
      btn.title='Hide this domain from dashboard & reports';
      btn.onclick = ()=>ignoreDomain(domain, btn);
      const row = btn.closest('tr') || btn.closest('.new-domain-row');
      if(row){ row.style.opacity='1'; }
    }
  } catch(e) {
    btn.textContent='Error';
    setTimeout(()=>{ btn.textContent='Ignore'; }, 2000);
  }
  btn.classList.remove('busy');
}

// Pre-load ignored set so buttons reflect state on render
let _ignoredSet = new Set();
(async ()=>{
  try {
    const rows = await fetch('/api/ignored_domains').then(r=>r.json());
    _ignoredSet = new Set(rows.map(r=>r.domain));
  } catch(_){}
})();
function _ignoreBtn(domain){
  const isIgn = _ignoredSet.has(domain);
  return `<button class="btn-ignore${isIgn?' ignored':''}" onclick="ignoreDomain('${domain}',this)"
    title="${isIgn?'Hidden from dashboard &amp; reports. Click to show again.':'Hide from dashboard &amp; reports'}"
    >${isIgn?'Hidden':'Ignore'}</button>`;
}

// ── Block / Unblock Domain ───────────────────────────────────────────────────
async function blockDomain(domain, category, btn){
  if(btn.classList.contains('busy')) return;
  btn.classList.add('busy');
  try {
    const res = await fetch('/api/block_domain', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({domain, category})
    });
    const data = await res.json();
    if(data.status==='blocked'){
      btn.textContent='✅ Blocked';
      btn.classList.add('blocked');
      btn.onclick = ()=>unblockDomain(domain, btn);
      btn.title = data.pihole_ok ? 'Blocked in Pi-hole. Click to unblock.' : 'Saved locally (Pi-hole API unreachable). Click to unblock.';
      loadBlockedDomains();
    } else {
      btn.textContent='❌ Failed';
      setTimeout(()=>{ btn.textContent='🚫'; btn.classList.remove('busy'); }, 2000);
    }
  } catch(e) {
    btn.textContent='❌ Error';
    setTimeout(()=>{ btn.textContent='🚫'; btn.classList.remove('busy'); }, 2000);
  }
  btn.classList.remove('busy');
}

async function unblockDomain(domain, btn){
  if(!btn) return;
  btn.classList.add('busy');
  try {
    const res = await fetch('/api/unblock_domain', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({domain})
    });
    const data = await res.json();
    if(data.status==='unblocked'){
      btn.textContent='🚫';
      btn.classList.remove('blocked');
      btn.onclick = null;
      loadBlockedDomains();
      loadRiskyCategoryCards();
    }
  } catch(e) {}
  btn.classList.remove('busy');
}

async function loadBlockedDomains(){
  try {
    const rows = await fetch('/api/blocked_domains').then(r=>r.json());
    const section = document.getElementById('blocked-section');
    const list    = document.getElementById('blocked-list');
    if(!rows.length){ section.style.display='none'; return; }
    // Show the panel but keep it collapsed — user expands manually
    section.style.display='block';
    if(!section.classList.contains('collapsed')) section.classList.add('collapsed');
    list.innerHTML = rows.map(r=>`
      <div class="blocked-row">
        <span class="blocked-domain mono">🚫 ${r.domain}</span>
        <span class="blocked-cat">${r.category||''}</span>
        <span style="font-size:13px;color:var(--muted)">${r.blocked_at?r.blocked_at.slice(0,10):''}</span>
        <button class="btn-unblock" onclick="unblockFromPanel('${r.domain}',this)">✅ Unblock</button>
      </div>`).join('');
  } catch(e) {}
}

async function unblockFromPanel(domain, btn){
  btn.textContent='…'; btn.disabled=true;
  try {
    await fetch('/api/unblock_domain',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({domain})
    });
  } catch(e){}
  loadBlockedDomains();
  loadRiskyCategoryCards();
}

// Close modals on backdrop click
document.querySelectorAll('.modal-backdrop').forEach(m=>{
  m.addEventListener('click', e => { if(e.target===m){ m.classList.remove('open'); } });
});

// ── Live Clock ────────────────────────────────────────────────────────────────
function updateClock(){
  const now = new Date();
  document.getElementById('live-time').textContent = now.toLocaleTimeString();
  document.getElementById('live-date').textContent  = now.toLocaleDateString('en',{weekday:'long',month:'long',day:'numeric'});
}
setInterval(updateClock, 1000);
updateClock();

// ── AI Summary ───────────────────────────────────────────────────────────────
function _inline(text){
  // Inline markdown: **bold**, `code`, then escape HTML (pre-escaped caller handles &<>)
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="background:var(--border);border-radius:3px;padding:1px 4px;font-size:14px">$1</code>');
}

function _mdToHtml(raw){
  // Escape HTML first
  const text = raw.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const lines = text.split('\n');
  const out   = [];
  let inList = false, inDeviceCard = false;

  const closeList = () => { if(inList){ out.push('</ul>'); inList=false; } };
  const closeCard = () => { if(inDeviceCard){ out.push('</div>'); inDeviceCard=false; } };

  // Section heading colours
  const SECTION_ICONS = {
    'executive': '📊', 'summary': '📊',
    'device': '📱', 'devices': '📱',
    'alert': '⚠️', 'concern': '⚠️', 'risk': '⚠️',
    'education': '🎓', 'school': '🎓',
    'block': '🛡️', 'protect': '🛡️',
    'recommendation': '💡', 'suggest': '💡',
    'trend': '📈', 'pattern': '📈',
  };
  const sectionIcon = (title) => {
    const low = title.toLowerCase();
    for(const [k,v] of Object.entries(SECTION_ICONS)) if(low.includes(k)) return v;
    return '🔹';
  };

  for(let i=0; i<lines.length; i++){
    const line = lines[i];
    const trim = line.trim();

    // Numbered section headings like "1. Executive Summary" or "## Section"
    if(/^\d+\.\s+\S/.test(trim) && trim.length < 60){
      closeList(); closeCard();
      const title = trim.replace(/^\d+\.\s+/, '');
      const icon  = sectionIcon(title);
      out.push(`<div style="display:flex;align-items:center;gap:8px;margin:20px 0 8px;padding-bottom:6px;border-bottom:2px solid var(--border)">
        <span style="font-size:16px">${icon}</span>
        <h3 style="margin:0;font-size:14px;font-weight:700;color:var(--text);text-transform:uppercase;letter-spacing:.5px">${_inline(title)}</h3>
      </div>`);
      continue;
    }
    if(/^#{1,3} /.test(trim)){
      closeList(); closeCard();
      const level = trim.match(/^(#{1,3})/)[1].length;
      const title = trim.replace(/^#{1,3} /,'');
      const icon  = sectionIcon(title);
      if(level===1){
        out.push(`<div style="display:flex;align-items:center;gap:8px;margin:20px 0 8px;padding-bottom:6px;border-bottom:2px solid var(--border)">
          <span style="font-size:16px">${icon}</span>
          <h3 style="margin:0;font-size:14px;font-weight:700;color:var(--text);text-transform:uppercase;letter-spacing:.5px">${_inline(title)}</h3>
        </div>`);
      } else if(level===2){
        // Device card header — e.g. "## Samsung Device (192.168.68.114)"
        closeCard();
        const isAlert = /adult|vpn|crypto|concern/i.test(title);
        const borderColor = isAlert ? '#ef4444' : 'var(--border)';
        const bgColor     = isAlert ? '#fff1f2' : 'var(--card)';
        out.push(`<div style="background:${bgColor};border:1px solid ${borderColor};border-radius:8px;padding:12px 14px;margin:8px 0">`);
        out.push(`<div style="font-weight:600;font-size:13px;color:var(--text);margin-bottom:6px">${isAlert?'⚠️ ':''} ${_inline(title)}</div>`);
        inDeviceCard = true;
      } else {
        out.push(`<div style="font-weight:600;font-size:14px;color:var(--accent);margin:10px 0 4px;text-transform:uppercase;letter-spacing:.4px">${_inline(title)}</div>`);
      }
      continue;
    }

    // Bullet points
    if(/^[-*•]\s/.test(trim)){
      if(!inList){ out.push('<ul style="margin:4px 0 8px 16px;padding:0;list-style:disc">'); inList=true; }
      const content = trim.replace(/^[-*•]\s/,'');
      // Detect sub-labels like "* Usage:", "* Peak Activity:", "* Concerns:"
      const labelMatch = content.match(/^\*\*?([^:*]+):\*?\*?\s*(.*)/);
      if(labelMatch){
        const label  = labelMatch[1].trim();
        const rest   = labelMatch[2];
        const labelColor = label.toLowerCase().includes('concern') || label.toLowerCase().includes('alert')
          ? '#dc2626' : 'var(--accent)';
        out.push(`<li style="margin:3px 0;font-size:13px;list-style:none;padding-left:0">
          <span style="font-weight:600;color:${labelColor}">${label}:</span> ${_inline(rest)}
        </li>`);
      } else {
        // ALERT keyword highlight
        const alertLine = /ALERT|⚠|adult|blocked/i.test(content);
        const style = alertLine
          ? 'color:#dc2626;font-weight:500'
          : 'color:var(--text)';
        out.push(`<li style="margin:3px 0;font-size:13px;${style}">${_inline(content)}</li>`);
      }
      continue;
    }

    // Empty line
    if(trim === ''){
      closeList();
      out.push('<div style="height:4px"></div>');
      continue;
    }

    // Horizontal rule
    if(/^[-=]{3,}$/.test(trim)){
      closeList(); closeCard();
      out.push('<hr style="border:none;border-top:1px solid var(--border);margin:12px 0">');
      continue;
    }

    // Regular paragraph — highlight ALERT lines
    closeList();
    const isAlertLine = /\bALERT\b|⚠️/.test(trim);
    if(isAlertLine){
      out.push(`<p style="margin:4px 0;font-size:13px;color:#dc2626;font-weight:600;background:#fff1f2;padding:5px 8px;border-radius:5px;border-left:3px solid #ef4444">${_inline(trim)}</p>`);
    } else {
      out.push(`<p style="margin:4px 0;font-size:13px;color:var(--text);line-height:1.6">${_inline(trim)}</p>`);
    }
  }

  closeList();
  closeCard();
  return out.join('\n');
}

async function generateAISummary(){
  const period = detectPeriodFromDateRange() || 'daily';
  const box    = document.getElementById('ai-content');
  const runBtn = document.getElementById('ai-run-btn');
  if(runBtn){ runBtn.disabled = true; runBtn.textContent = '⏳ Running…'; }

  // ── Step 1: fetch ETA so we can show a meaningful countdown ───────────────
  let etaParams = `period=${period}`;
  if(currentStartTS && currentEndTS){
    etaParams += `&start_ts=${currentStartTS}&end_ts=${currentEndTS}`;
  }
  let etaInfo = {num_calls:1, num_devices:0, eta_seconds:10, delay_s:7, rpm:10};
  try {
    const etaResp = await fetch(`/api/ai_eta?${etaParams}`);
    if(etaResp.ok) etaInfo = await etaResp.json();
  } catch(_){}

  const totalCalls = etaInfo.num_calls   || 1;
  const numDev     = etaInfo.num_devices || 0;
  const etaSec     = etaInfo.eta_seconds || 10;
  const rpm        = etaInfo.rpm         || 10;
  const delaySec   = etaInfo.delay_s     || 7;

  // ── Step 2: start live countdown while the API call runs ──────────────────
  let remaining = etaSec;
  let callsDone = 0;

  function progressLabel(){
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
    const callLabel = callsDone === 0
      ? `Analyzing network overview…`
      : `Analyzing device ${callsDone} of ${numDev}…`;
    return `
      <div style="display:flex;flex-direction:column;gap:10px;padding:16px 20px;
                  background:var(--bg);border-radius:8px;border:1px solid var(--border)">
        <div style="display:flex;align-items:center;gap:10px">
          <div class="pulse" style="width:10px;height:10px;border-radius:50%;
               background:var(--accent);flex-shrink:0"></div>
          <div style="font-size:14px;font-weight:600;color:var(--text2)">${callLabel}</div>
        </div>
        <div style="font-size:13px;color:var(--muted)">
          Making <strong style="color:var(--text)">${totalCalls} Gemini calls</strong>
          (1 network overview + ${numDev} devices) ·
          <strong style="color:var(--text)">${rpm} calls/min</strong> rate limit ·
          ${delaySec}s between calls
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <div style="flex:1;background:var(--border2);border-radius:4px;height:6px">
            <div style="width:${Math.round((1-remaining/Math.max(etaSec,1))*100)}%;
                        height:6px;border-radius:4px;background:var(--accent);
                        transition:width 1s linear"></div>
          </div>
          <div style="font-size:13px;font-weight:600;color:var(--accent);white-space:nowrap">
            ETA ~${timeStr}
          </div>
        </div>
      </div>`;
  }

  box.innerHTML = progressLabel();

  const countdownTimer = setInterval(() => {
    remaining = Math.max(0, remaining - 1);
    // Advance "call done" marker roughly every delay_s seconds
    callsDone = Math.min(numDev, Math.floor((etaSec - remaining) / Math.max(delaySec, 1)));
    box.innerHTML = progressLabel();
  }, 1000);

  try {
    const requestBody = {period};
    if(currentStartTS && currentEndTS){
      requestBody.start_ts = currentStartTS;
      requestBody.end_ts = currentEndTS;
    }
    const resp = await fetch('/api/ai_summary', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(requestBody)
    });
    clearInterval(countdownTimer);
    const data = await resp.json();

    // ── Error states ──────────────────────────────────────────────────────────
    if(data.error){
      const is429  = resp.status === 429;
      const is400  = resp.status === 400;
      const icon   = is429 ? '🚫' : is400 ? '⚙️' : '⚠️';
      const bg     = is429 ? '#fff1f2' : '#fffbeb';
      const border = is429 ? '#fecaca' : '#fcd34d';
      const color  = is429 ? '#b91c1c' : '#92400e';
      box.innerHTML = `
        <div style="color:${color};padding:10px 12px;background:${bg};border-radius:6px;border:1px solid ${border};font-size:13px">
          ${icon} ${data.error}
        </div>`;
      return;
    }

    // ── Success (live or cached fallback) ─────────────────────────────────────
    const label     = {daily:'Today (24h)',weekly:'Last 7 Days',monthly:'Last 30 Days'}[period]||period;
    const dateRange = data.start===data.end ? data.start : `${data.start} – ${data.end}`;
    const genAt     = data.generated_at ? new Date(data.generated_at+' UTC').toLocaleString() : 'just now';
    const model     = data.model || 'Gemini';
    const isLive    = data.source === 'live';

    const cacheNotice = data.cache_notice
      ? `<div style="color:#92400e;padding:6px 10px;background:#fffbeb;border-radius:5px;border:1px solid #fcd34d;font-size:14px;margin-bottom:10px">
           ⚠️ ${data.cache_notice}
         </div>`
      : '';

    box.innerHTML = `
      ${cacheNotice}
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;
                  padding:8px 12px;background:var(--bg);border-radius:6px;margin-bottom:12px;font-size:13px;color:var(--muted)">
        <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
          <span style="color:${isLive?'#22c55e':'#f59e0b'};font-weight:600">${isLive?'🟢 Live':'📦 Cached'}</span>
          <span>${model}</span>
          <span>📅 ${dateRange}</span>
          <span>🕐 ${genAt}</span>
        </div>
        <button class="btn" onclick="generateAISummary()" style="font-size:12px;padding:2px 10px">▶ Run</button>
      </div>
      <div style="max-height:520px;overflow-y:auto;padding-right:4px">${_mdToHtml(data.summary)}</div>`;

  } catch(e) {
    clearInterval(countdownTimer);
    box.innerHTML = `<div style="color:#b91c1c;padding:8px">⚠️ Network error: ${e.message}</div>`;
  }
  btn.disabled = false;
  btn.textContent = '▶ Run';
  if(runBtn){ runBtn.disabled = false; runBtn.textContent = '▶ Run'; }
}

// ── Collapsible panels ────────────────────────────────────────────────────────
function togglePanel(id){
  const el = document.getElementById(id);
  if(!el) return;
  el.classList.toggle('collapsed');
}

// ── Auto-load last stored AI summary (no Gemini call) ────────────────────────
async function loadStoredAISummary(){
  const detectedPeriod = detectPeriodFromDateRange();
  if(currentTimeWindow === 'custom' && !detectedPeriod){
    clearAISummary();
    return;
  }
  const period = detectedPeriod || 'daily';
  const box    = document.getElementById('ai-content');
  try {
    const resp = await fetch('/api/ai_summary_stored?period=' + period);
    if(!resp.ok){
      clearAISummary();
      return;
    }
    const data = await resp.json();
    if(!data.summary){
      clearAISummary();
      return;
    }
    const dateRange = data.start===data.end ? data.start : data.start+' – '+data.end;
    const genAt  = data.generated_at ? new Date(data.generated_at+' UTC').toLocaleString() : '';
    const model  = data.model || 'Gemini';
    const srcLbl = data.run_type === 'scheduled' ? '🕔 Scheduled (5 AM)' : '📦 Stored';
    box.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;'+
      'padding:8px 12px;background:var(--bg);border-radius:6px;margin-bottom:12px;font-size:13px;color:var(--muted)">'+
      '<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">'+
      '<span style="color:#f59e0b;font-weight:600">'+srcLbl+'</span>'+
      '<span>'+model+'</span>'+
      '<span>📅 '+dateRange+'</span>'+
      (genAt ? '<span>🕐 '+genAt+'</span>' : '')+
      '</div>'+
      '<button class="btn" onclick="generateAISummary()" style="font-size:12px;padding:2px 10px">▶ Run</button>'+
      '</div>'+
      '<div style="max-height:520px;overflow-y:auto;padding-right:4px">'+_mdToHtml(data.summary)+'</div>';
  } catch(e) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────
applyTimeWindow('24h-from-5am');  // Default to last 24h ending at 5 AM
loadStoredAISummary();
</script>
</body>
</html>
"""

DEVICE_DETAIL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Device Detail — Pi-hole Analytics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#f6f8fa;--card:#fff;--border:#d0d7de;--border2:#e8ecf0;
  --accent:#0969da;--accent2:#8250df;--text:#1f2328;--text2:#0d1117;
  --muted:#3d444d;--green:#1a7f37;--red:#cf222e;--yellow:#9a6700;--orange:#bc4c00}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;min-height:100vh}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

header{background:#fff;border-bottom:1px solid var(--border);padding:12px 20px;
  display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.back-btn{display:flex;align-items:center;gap:6px;background:#f6f8fa;
  border:1px solid var(--border);border-radius:6px;padding:6px 14px;
  font-size:14px;color:var(--text);cursor:pointer;transition:all .15s;white-space:nowrap}
.back-btn:hover{border-color:var(--accent);color:var(--accent);background:#dbeafe;text-decoration:none}
.hdr-info{flex:1;min-width:0}
.hdr-name{font-size:18px;font-weight:700;color:var(--text2)}
.hdr-sub{font-size:14px;color:var(--muted);margin-top:2px}
.date-pick{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.date-pick label{font-size:14px;color:var(--muted)}
input[type=date]{background:#f6f8fa;border:1px solid var(--border);color:var(--text);
  padding:6px 10px;border-radius:6px;font-size:14px}
input[type=date]:disabled,input[type=datetime-local]:disabled{opacity:1;cursor:default;color:var(--text);background:#f6f8fa;border-color:var(--border)}
.btn{background:#f6f8fa;border:1px solid var(--border);color:var(--text);
  padding:6px 14px;border-radius:6px;cursor:pointer;font-size:14px;transition:all .15s;white-space:nowrap}
.btn:hover{border-color:var(--accent);color:var(--accent);background:#dbeafe}
.btn-primary{background:#0969da;border-color:#0969da;color:#fff}
.btn-primary:hover{background:#1a7dc8;border-color:#1a7dc8;color:#fff}

main{padding:16px 20px;max-width:1200px;margin:0 auto}

.stat-row{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.06);position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.stat-card.blue::before{background:var(--accent)}
.stat-card.red::before{background:var(--red)}
.stat-card.green::before{background:var(--green)}
.stat-card.yellow::before{background:var(--yellow)}
.stat-card.purple::before{background:var(--accent2)}
.stat-card.orange::before{background:var(--orange)}
.sval{font-size:24px;font-weight:700;color:var(--text2);line-height:1.1}
.slbl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:4px}
.ssub{font-size:13px;color:var(--muted);margin-top:4px}

.panel{background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:16px}
.panel-title{font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;
  font-weight:600;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.panel-title .badge{font-size:12px;background:var(--bg);border:1px solid var(--border);
  border-radius:10px;padding:2px 8px;color:var(--muted);font-weight:400;text-transform:none;letter-spacing:0}

.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:16px}
.grid-3{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:16px}

/* ── Alert banner ── */
.flag-banner{background:#fff0f0;border:1px solid #fca5a5;border-left:4px solid var(--red);
  border-radius:8px;padding:14px 16px;margin-bottom:16px}
.flag-banner.warn{background:#fffbeb;border-color:#fde68a;border-left-color:var(--yellow)}
.flag-banner h3{font-size:13px;font-weight:600;color:#b91c1c;margin-bottom:6px}
.flag-banner.warn h3{color:var(--yellow)}
.flag-banner p{font-size:14px;color:#7f1d1d}
.flag-banner.warn p{color:#78350f}

/* ── Flagged category tabs ── */
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.tab{padding:6px 14px;border-radius:20px;font-size:14px;cursor:pointer;border:1px solid var(--border);
  background:var(--bg);color:var(--text);transition:all .15s}
.tab:hover,.tab.active{background:var(--accent);border-color:var(--accent);color:#fff}
.tab.alert-tab{border-color:#fca5a5;background:#fff0f0;color:#b91c1c}
.tab.alert-tab:hover,.tab.alert-tab.active{background:var(--red);border-color:var(--red);color:#fff}
.tab.warn-tab{border-color:#fde68a;background:#fffbeb;color:var(--yellow)}
.tab.warn-tab:hover,.tab.warn-tab.active{background:var(--yellow);border-color:var(--yellow);color:#fff}
.tab-panel{display:none}
.tab-panel.active{display:block}

/* ── Table ── */
table{width:100%;border-collapse:collapse}
th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;
  padding:8px 10px;border-bottom:1px solid var(--border2);text-align:left;font-weight:500;white-space:nowrap}
th.sortable{cursor:pointer;user-select:none}
th.sortable:hover{color:var(--accent)}
td{padding:8px 10px;border-bottom:1px solid var(--border2);vertical-align:middle;font-size:14px}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f6f8fa}
td.mono{font-family:monospace;font-size:13px}
.cat-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;
  border-radius:10px;font-size:12px;font-weight:500}
.status-ok{background:#dcfce7;color:#15803d;border:1px solid #86efac;
  border-radius:8px;padding:2px 8px;font-size:12px;font-weight:600}
.status-blk{background:#fee2e2;color:#b91c1c;border:1px solid #fca5a5;
  border-radius:8px;padding:2px 8px;font-size:12px;font-weight:600}
.bar-wrap{background:var(--border2);border-radius:3px;height:5px;display:inline-block;
  vertical-align:middle;width:80px}
.bar-fill{height:5px;border-radius:3px}

/* ── Category horizontal bars ── */
.cat-bar-row{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.cat-bar-name{font-size:14px;width:130px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cat-bar-bg{flex:1;background:var(--border2);border-radius:4px;height:12px;min-width:60px}
.cat-bar-fg{height:12px;border-radius:4px;transition:width .4s}
.cat-bar-val{font-size:13px;color:var(--muted);width:70px;flex-shrink:0;text-align:right}

/* ── Hourly chart container ── */
.chart-wrap{position:relative;height:220px}
.chart-small{position:relative;height:120px;margin-top:8px}

/* ── Search / filter ── */
.search-row{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.search-row input[type=text]{flex:1;min-width:160px;padding:7px 12px;border:1px solid var(--border);
  border-radius:6px;font-size:14px;background:var(--bg);color:var(--text);outline:none}
.search-row input:focus{border-color:var(--accent);box-shadow:0 0 0 3px #dbeafe}
.cat-filter{display:flex;flex-wrap:wrap;gap:4px}
.cf-pill{padding:3px 10px;border-radius:10px;font-size:13px;cursor:pointer;
  border:1px solid var(--border);background:var(--bg);transition:all .15s}
.cf-pill.active{background:var(--accent);border-color:var(--accent);color:#fff}

/* ── Domain detail row expander ── */
.domain-row{cursor:pointer}
.domain-row:hover td{background:#edf6ff}
.expand-detail{display:none;background:#f6f8fa;border-top:1px solid var(--border2)}
.expand-detail td{font-size:13px;color:var(--muted);padding:8px 14px}
.expand-detail.open{display:table-row}

/* ── Summary badge ── */
.alert-badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;
  border-radius:20px;font-size:13px;font-weight:600;background:#fee2e2;
  color:#b91c1c;border:1px solid #fca5a5}
.warn-badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;
  border-radius:20px;font-size:13px;font-weight:600;background:#fef3c7;
  color:#92400e;border:1px solid #fcd34d}
.clean-badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;
  border-radius:20px;font-size:13px;font-weight:600;background:#dcfce7;
  color:#15803d;border:1px solid #86efac}

.loader{color:var(--muted);font-size:13px;padding:24px;text-align:center}
.empty{color:var(--muted);font-size:13px;padding:20px;text-align:center;font-style:italic}

@media(max-width:768px){
  .stat-row{grid-template-columns:repeat(3,1fr)}
  .grid-2,.grid-3{grid-template-columns:1fr}
}
@media(max-width:480px){
  .stat-row{grid-template-columns:repeat(2,1fr)}
}
</style>
</head>
<body>

<header>
  <a class="back-btn" href="/">← Back to Dashboard</a>
  <div class="hdr-info">
    <div class="hdr-name" id="hdr-name">Loading…</div>
    <div class="hdr-sub" id="hdr-sub"></div>
  </div>
  <div class="date-pick">
    <label>Date</label>
    <input type="date" id="date-pick" value="" disabled>
    <button class="btn btn-primary" onclick="reload()">Go</button>
  </div>
</header>

<main>

  <!-- Summary cards -->
  <div class="stat-row" id="stat-row">
    <div class="stat-card blue"><div class="sval" id="s-total">—</div><div class="slbl">Total Requests</div><div class="ssub" id="s-total-sub"></div></div>
    <div class="stat-card red"><div class="sval" id="s-blocked">—</div><div class="slbl">Blocked (%)</div><div class="ssub" id="s-blocked-sub"></div></div>
    <div class="stat-card green"><div class="sval" id="s-sites">—</div><div class="slbl">Unique Sites</div></div>
    <div class="stat-card yellow"><div class="sval" id="s-hours">—</div><div class="slbl">Active Hours</div></div>
    <div class="stat-card purple"><div class="sval" id="s-peak">—</div><div class="slbl">Peak Hour</div><div class="ssub" id="s-peak-sub"></div></div>
    <div class="stat-card orange"><div class="sval" id="s-topcat">—</div><div class="slbl">Top Category</div></div>
  </div>

  <!-- Flag banners (populated by JS) -->
  <div id="flag-banners"></div>

  <!-- Hourly chart + category breakdown -->
  <div class="grid-3">
    <div class="panel">
      <div class="panel-title">📈 Hourly Activity <span class="badge" id="hourly-date-badge"></span></div>
      <div class="chart-wrap"><canvas id="hourly-chart"></canvas></div>
    </div>
    <div class="panel">
      <div class="panel-title">📂 Categories</div>
      <div id="cat-bars"><div class="loader">Loading…</div></div>
    </div>
  </div>

  <!-- Flagged categories deep-dive -->
  <div id="flagged-section" style="display:none">
    <div class="panel">
      <div class="panel-title">🚨 Flagged Activity — Detailed Breakdown</div>
      <div class="tabs" id="flag-tabs"></div>
      <div id="flag-panels"></div>
    </div>
  </div>

  <!-- All domains -->
  <div class="panel">
    <div class="panel-title">🌐 All Domains Accessed <span class="badge" id="domains-count-badge"></span></div>
    <div class="search-row">
      <input type="text" id="domain-search" placeholder="Search domain or category…" oninput="filterDomains()">
      <div class="cat-filter" id="cat-filter"></div>
    </div>
    <div style="overflow-x:auto">
      <table id="domains-table">
        <thead>
          <tr>
            <th class="sortable" onclick="sortTable('domain')">Domain ↕</th>
            <th>Category</th>
            <th class="sortable" onclick="sortTable('queries')">Requests ↕</th>
            <th>% of Traffic</th>
            <th class="sortable" onclick="sortTable('blocked')">Blocked ↕</th>
            <th>First Seen</th>
            <th>Last Seen</th>
            <th>Hrs Active</th>
          </tr>
        </thead>
        <tbody id="domains-tbody"><tr><td colspan="8" class="loader">Loading domains…</td></tr></tbody>
      </table>
    </div>
  </div>

</main>

<script>
const CAT_COLORS={
  adult:'#dc2626',vpn_proxy:'#7c3aed',crypto:'#d97706',
  social_media:'#2563eb',gaming:'#16a34a',streaming:'#dc2626',
  music:'#0891b2',news:'#7c3aed',shopping:'#d97706',finance:'#059669',
  health:'#10b981',travel:'#0284c7',food:'#f59e0b',
  productivity:'#6366f1',tech:'#0969da',smart_home:'#8b5cf6',
  educational:'#15803d',sports:'#dc2626',government:'#374151',
  ads_tracking:'#6b7280',other:'#9ca3af'
};
const CAT_ICONS={
  adult:'🔞',vpn_proxy:'🔒',crypto:'₿',social_media:'📱',gaming:'🎮',
  streaming:'🎬',music:'🎵',news:'📰',shopping:'🛒',finance:'💰',
  health:'🏥',travel:'✈️',food:'🍔',productivity:'💼',tech:'💻',
  smart_home:'🏠',educational:'📚',sports:'⚽',government:'🏛️',
  ads_tracking:'🎯',other:'🌐'
};
const ALERT_CATS=new Set(['adult','vpn_proxy','crypto']);
const WATCH_CATS={social_media:900,gaming:1500,streaming:3000};

const params=new URLSearchParams(location.search);
const deviceIp=params.get('ip')||'';
let currentDate=params.get('date')||new Date().toISOString().slice(0,10);

document.getElementById('date-pick').value=currentDate;

function reload(){
  const d=document.getElementById('date-pick').value;
  if(d) location.href=`/device?ip=${encodeURIComponent(deviceIp)}&date=${d}`;
}

function fmt(n){return Number(n||0).toLocaleString()}
function hour12(h){const hh=parseInt(h);return hh===0?'12 AM':hh<12?`${hh} AM`:hh===12?'12 PM':`${hh-12} PM`}
function pct(a,b){return b?Math.round((a/b)*100):0}

let allDomains=[];
let sortKey='queries';
let sortAsc=false;
let filterCat='';
let hourlyChart=null;

async function init(){
  const [detail,hourly,catHourly,domains]=await Promise.all([
    fetch(`/api/device_detail?ip=${encodeURIComponent(deviceIp)}&date=${currentDate}`).then(r=>r.json()),
    fetch(`/api/device_hourly?ip=${encodeURIComponent(deviceIp)}&date=${currentDate}`).then(r=>r.json()),
    fetch(`/api/device_hourly_categories?ip=${encodeURIComponent(deviceIp)}&date=${currentDate}`).then(r=>r.json()),
    fetch(`/api/device_domains?ip=${encodeURIComponent(deviceIp)}&date=${currentDate}&limit=300`).then(r=>r.json()),
  ]);

  const s=detail.summary||{};
  const cats=detail.categories||[];
  allDomains=domains;

  // ── Header ──
  const name=s.client_name||deviceIp;
  document.getElementById('hdr-name').textContent=name;
  document.getElementById('hdr-sub').textContent=`${deviceIp}  ·  ${currentDate}`;
  document.title=`${name} — Pi-hole Device Detail`;

  // ── Stat cards ──
  const total=parseInt(s.total_queries)||0;
  const blocked=parseInt(s.blocked_queries)||0;
  const bp=total?((blocked/total)*100).toFixed(1):0;
  const sites=parseInt(s.unique_domains)||0;
  const peakH=s.peak_hour!=null?s.peak_hour:null;
  const peakQ=parseInt(s.peak_hour_queries)||0;
  const topCat=cats.length?cats[0]:null;

  // Active hours from hourly data
  const activeHours=hourly.filter(h=>h.queries>0).length;

  document.getElementById('s-total').textContent=fmt(total);
  document.getElementById('s-blocked').textContent=`${fmt(blocked)} (${bp}%)`;
  document.getElementById('s-blocked-sub').textContent=`${(100-bp).toFixed(1)}% allowed through`;
  document.getElementById('s-sites').textContent=fmt(sites);
  document.getElementById('s-hours').textContent=`${activeHours}/24`;
  document.getElementById('s-peak').textContent=peakH!=null?hour12(peakH):'—';
  document.getElementById('s-peak-sub').textContent=peakH!=null?`${fmt(peakQ)} requests`:'';
  document.getElementById('s-topcat').textContent=topCat?(CAT_ICONS[topCat.category]||'🌐')+' '+topCat.category.replace(/_/g,' '):'—';

  // ── Flag banners ──
  const alertFlags=cats.filter(c=>ALERT_CATS.has(c.category)&&c.queries>0);
  const warnFlags=cats.filter(c=>WATCH_CATS[c.category]&&c.queries>=WATCH_CATS[c.category]);
  const banners=document.getElementById('flag-banners');
  banners.innerHTML=[
    ...alertFlags.map(c=>`<div class="flag-banner">
      <h3>🚨 ${c.category.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase())} Detected — ${fmt(c.queries)} requests</h3>
      <p>This device accessed ${c.unique_domains||0} ${c.category.replace(/_/g,' ')} sites today. See the Flagged Activity section below for a full breakdown by time and domain.</p>
    </div>`),
    ...warnFlags.map(c=>`<div class="flag-banner warn">
      <h3>⚠️ High ${c.category.replace(/_/g,' ').replace(/\b\w/g,l=>l.toUpperCase())} Usage — ${fmt(c.queries)} requests</h3>
      <p>This device exceeded the watch threshold. See the Flagged Activity section below for a time-by-time breakdown.</p>
    </div>`)
  ].join('');

  // ── Hourly chart ──
  document.getElementById('hourly-date-badge').textContent=currentDate;
  const hours=Array.from({length:24},(_,i)=>String(i).padStart(2,'0'));
  const hourMap=Object.fromEntries(hourly.map(h=>[h.hour,h]));
  const hourlyQ=hours.map(h=>hourMap[h]?.queries||0);
  const hourlyB=hours.map(h=>hourMap[h]?.blocked||0);
  const hourlyA=hours.map(h=>(hourMap[h]?.queries||0)-(hourMap[h]?.blocked||0));
  const hourLabels=hours.map(h=>hour12(parseInt(h)));

  hourlyChart=new Chart(document.getElementById('hourly-chart'),{
    type:'bar',
    data:{
      labels:hourLabels,
      datasets:[
        {label:'Allowed',data:hourlyA,backgroundColor:'rgba(9,105,218,0.65)',stack:'s'},
        {label:'Blocked',data:hourlyB,backgroundColor:'rgba(207,34,46,0.55)',stack:'s'}
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'top',labels:{font:{size:11},boxWidth:12}},
               tooltip:{mode:'index',intersect:false}},
      scales:{
        x:{ticks:{font:{size:9},maxTicksLimit:12},grid:{display:false}},
        y:{ticks:{font:{size:10}},beginAtZero:true,stacked:true}
      }
    }
  });

  // ── Category bars ──
  const maxQ=cats.length?cats[0].queries:1;
  const catBarsHtml=cats.filter(c=>c.queries>0).map(c=>{
    const col=CAT_COLORS[c.category]||'#888';
    const pctW=Math.round((c.queries/maxQ)*100);
    const icon=CAT_ICONS[c.category]||'🌐';
    const isFlag=ALERT_CATS.has(c.category)||(WATCH_CATS[c.category]&&c.queries>=WATCH_CATS[c.category]);
    return `<div class="cat-bar-row" style="cursor:pointer" onclick="setCatFilter('${c.category}')">
      <div class="cat-bar-name" title="${c.category}">${icon} ${c.category.replace(/_/g,' ')}${isFlag?` <span style="color:var(--red);font-size:12px">⚠️</span>`:''}</div>
      <div class="cat-bar-bg"><div class="cat-bar-fg" style="width:${pctW}%;background:${col}"></div></div>
      <div class="cat-bar-val">${fmt(c.queries)}</div>
    </div>`;
  }).join('');
  document.getElementById('cat-bars').innerHTML=catBarsHtml||'<div class="empty">No category data</div>';

  // ── Flagged deep-dive ──
  const flaggedCats=[...alertFlags,...warnFlags];
  if(flaggedCats.length){
    document.getElementById('flagged-section').style.display='';
    const tabsEl=document.getElementById('flag-tabs');
    const panelsEl=document.getElementById('flag-panels');
    tabsEl.innerHTML='';
    panelsEl.innerHTML='';

    for(const [idx,fc] of flaggedCats.entries()){
      const isAlert=ALERT_CATS.has(fc.category);
      const tabCls=isAlert?'alert-tab':'warn-tab';
      const icon=CAT_ICONS[fc.category]||'⚠️';
      tabsEl.innerHTML+=`<div class="tab ${tabCls}${idx===0?' active':''}" onclick="switchTab(${idx})">${icon} ${fc.category.replace(/_/g,' ')}</div>`;
      panelsEl.innerHTML+=`<div class="tab-panel${idx===0?' active':''}" id="flag-panel-${idx}">
        <div class="loader" id="flag-loading-${idx}">Loading…</div>
      </div>`;
    }

    // Load all flagged panels
    for(const [idx,fc] of flaggedCats.entries()){
      loadFlaggedPanel(idx,fc.category,catHourly,total);
    }
  }

  // ── Domains table ──
  buildCatFilter(cats);
  renderDomains(total);
}

function switchTab(idx){
  document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',i===idx));
  document.querySelectorAll('.tab-panel').forEach((p,i)=>p.classList.toggle('active',i===idx));
}

async function loadFlaggedPanel(idx,category,catHourlyData,totalQueries){
  const data=await fetch(`/api/device_flagged_category?ip=${encodeURIComponent(deviceIp)}&date=${currentDate}&category=${encodeURIComponent(category)}`).then(r=>r.json());
  const panel=document.getElementById(`flag-panel-${idx}`);
  const isAlert=ALERT_CATS.has(category);
  const icon=CAT_ICONS[category]||'⚠️';

  // Build hourly mini-chart data
  const hours=Array.from({length:24},(_,i)=>String(i).padStart(2,'0'));
  const hmap=Object.fromEntries((data.hourly||[]).map(h=>[h.hour,h.queries]));
  const hq=hours.map(h=>hmap[h]||0);
  const col=isAlert?'rgba(207,34,46,0.7)':'rgba(202,138,4,0.7)';
  const peakH=hq.indexOf(Math.max(...hq));
  const peakVal=Math.max(...hq);

  const canvasId=`flag-chart-${idx}`;
  const domsHtml=(data.domains||[]).map((d,i)=>`
    <tr>
      <td class="mono">${i+1}. <a href="https://${d.domain}" target="_blank" rel="noopener">${d.domain}</a></td>
      <td>${fmt(d.queries)}</td>
      <td>${fmt(d.queries)}×</td>
      <td><span style="font-family:monospace;font-size:13px">${d.first_seen_time||'—'}</span></td>
      <td><span style="font-family:monospace;font-size:13px">${d.last_seen_time||'—'}</span></td>
    </tr>`).join('');

  panel.innerHTML=`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:14px;flex-wrap:wrap">
      <div>
        <div style="font-size:14px;color:var(--muted);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.4px">
          ${icon} When did this happen?
          ${peakVal>0?`<span style="float:right;font-weight:400">Peak: ${hour12(peakH)} (${fmt(peakVal)} requests)</span>`:''}
        </div>
        <div class="chart-small"><canvas id="${canvasId}"></canvas></div>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px;justify-content:center">
        <div><span style="font-size:22px;font-weight:700;color:${isAlert?'var(--red)':'var(--yellow)'}">${fmt(data.total_queries)}</span> <span style="font-size:14px;color:var(--muted)">total requests</span></div>
        <div><span style="font-size:18px;font-weight:600;color:var(--text2)">${data.unique_domains}</span> <span style="font-size:14px;color:var(--muted)">unique domains</span></div>
        <div style="font-size:13px;color:var(--muted)">${pct(data.total_queries,totalQueries)}% of this device's total traffic</div>
        <div style="font-size:13px;color:var(--muted)">Active in ${(data.hourly||[]).filter(h=>h.queries>0).length} hour(s) of the day</div>
      </div>
    </div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>#  Domain</th><th>Requests</th><th>Frequency</th><th>First Seen</th><th>Last Seen</th>
        </tr></thead>
        <tbody>${domsHtml||'<tr><td colspan="5" class="empty">No domains found</td></tr>'}</tbody>
      </table>
    </div>`;

  // Render mini chart
  new Chart(document.getElementById(canvasId),{
    type:'bar',
    data:{
      labels:hours.map(h=>hour12(parseInt(h))),
      datasets:[{label:'Requests',data:hq,backgroundColor:hq.map((_,i)=>i===peakH?col.replace('.7','1'):col)}]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{title:t=>t[0].label,label:l=>`${fmt(l.raw)} requests`}}},
      scales:{
        x:{ticks:{font:{size:8},maxTicksLimit:8},grid:{display:false}},
        y:{beginAtZero:true,ticks:{font:{size:9}}}
      }
    }
  });
}

function buildCatFilter(cats){
  const el=document.getElementById('cat-filter');
  el.innerHTML=`<span class="cf-pill active" onclick="setCatFilter('')">All</span>`+
    cats.filter(c=>c.queries>0).map(c=>
      `<span class="cf-pill" onclick="setCatFilter('${c.category}')">${CAT_ICONS[c.category]||'🌐'} ${c.category.replace(/_/g,' ')}</span>`
    ).join('');
}

function setCatFilter(cat){
  filterCat=cat;
  document.querySelectorAll('.cf-pill').forEach(p=>{
    const v=p.getAttribute('onclick').match(/'([^']*)'/)?.[1]||'';
    p.classList.toggle('active',v===cat);
  });
  filterDomains();
}

function filterDomains(){
  const q=(document.getElementById('domain-search').value||'').toLowerCase();
  const filtered=allDomains.filter(d=>{
    if(filterCat&&d.category!==filterCat) return false;
    if(q&&!d.domain.toLowerCase().includes(q)&&!(d.category||'').toLowerCase().includes(q)) return false;
    return true;
  });
  document.getElementById('domains-count-badge').textContent=`${filtered.length} / ${allDomains.length}`;
  renderDomainsRows(filtered);
}

function sortTable(key){
  if(sortKey===key) sortAsc=!sortAsc;
  else{sortKey=key;sortAsc=key==='domain'}
  filterDomains();
}

function renderDomains(totalQ){
  document.getElementById('domains-count-badge').textContent=`${allDomains.length}`;
  renderDomainsRows(allDomains,totalQ);
}

function renderDomainsRows(rows,totalQ){
  totalQ=totalQ||allDomains.reduce((s,d)=>s+(d.queries||0),0)||1;
  const sorted=[...rows].sort((a,b)=>{
    const av=a[sortKey]??0, bv=b[sortKey]??0;
    if(typeof av==='string') return sortAsc?av.localeCompare(bv):bv.localeCompare(av);
    return sortAsc?av-bv:bv-av;
  });
  const maxQ=Math.max(...sorted.map(d=>d.queries||0),1);
  const ALERT_SET=new Set(['adult','vpn_proxy','crypto']);
  const WATCH_MAP={social_media:900,gaming:1500,streaming:3000};
  const tbody=document.getElementById('domains-tbody');
  if(!sorted.length){tbody.innerHTML='<tr><td colspan="8" class="empty">No domains match</td></tr>';return}
  tbody.innerHTML=sorted.map((d,i)=>{
    const col=CAT_COLORS[d.category]||'#888';
    const icon=CAT_ICONS[d.category]||'🌐';
    const pctOfTotal=totalQ?Math.round((d.queries/totalQ)*100):0;
    const barW=Math.round((d.queries/maxQ)*100);
    const isFlag=ALERT_SET.has(d.category)||(WATCH_MAP[d.category]&&d.queries>=WATCH_MAP[d.category]);
    const rowStyle=isFlag?`style="background:#fff8f8"`:'';
    return `<tr class="domain-row" ${rowStyle}>
      <td class="mono"><a href="https://${d.domain}" target="_blank" rel="noopener noreferrer">${d.domain}</a>
        ${isFlag?`<span style="color:var(--red);font-size:12px;margin-left:4px">⚠️</span>`:''}
      </td>
      <td><span class="cat-pill" style="background:${col}18;color:${col};border:1px solid ${col}40">${icon} ${(d.category||'other').replace(/_/g,' ')}</span></td>
      <td>${fmt(d.queries)} <span class="bar-wrap"><span class="bar-fill" style="width:${barW}%;background:${col}"></span></span></td>
      <td>${pctOfTotal}%</td>
      <td>${d.blocked>0?`<span class="status-blk">${fmt(d.blocked)} blocked</span>`:`<span class="status-ok">Allowed</span>`}</td>
      <td class="mono">${d.first_seen_time||'—'}</td>
      <td class="mono">${d.last_seen_time||'—'}</td>
      <td>${d.active_hours||1}h</td>
      <td>${_ignoreBtn(d.domain)}</td>
    </tr>`;
  }).join('');
}

init().catch(e=>{
  document.querySelector('main').innerHTML=`<div class="loader">Failed to load device data: ${e.message}</div>`;
});
</script>
</body>
</html>"""

