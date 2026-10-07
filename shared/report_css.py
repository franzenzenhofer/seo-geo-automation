"""Stylesheet for the self-contained HTML reports. No text is smaller than 16px."""

from __future__ import annotations

REPORT_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background:#0f172a; color:#e2e8f0; line-height:1.6; font-size:16px; }
.container { max-width:1200px; margin:0 auto; padding:16px; }
header { background:linear-gradient(135deg, #1e293b 0%, #334155 100%); padding:24px;
  border-radius:12px; margin-bottom:24px; }
header h1 { font-size:28px; color:#f8fafc; }
.meta { color:#94a3b8; font-size:16px; word-break:break-all; }
.summary { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:16px;
  margin:20px 0; }
.summary-card { background:#1e293b; border-radius:8px; padding:20px; text-align:center; }
.summary-card .num { font-size:36px; font-weight:bold; }
.summary-card .label { font-size:16px; color:#94a3b8; text-transform:uppercase; }
.num-total { color:#f8fafc; } .num-pages { color:#60a5fa; }
.num-pass, .cat-pass { color:#22c55e; }
.num-warn, .cat-warn { color:#f59e0b; }
.num-fail, .cat-fail { color:#ef4444; }
nav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:24px; }
nav a { padding:6px 14px; border-radius:6px; text-decoration:none; font-size:16px; font-weight:500; }
.nav-pass { background:#166534; color:#bbf7d0; }
.nav-warn { background:#854d0e; color:#fef08a; }
.nav-fail { background:#991b1b; color:#fecaca; }
.nav-ai { background:#1e3a5f; color:#93c5fd; }
.category { background:#1e293b; border-radius:12px; padding:20px; margin-bottom:20px; }
.category h2 { font-size:22px; margin-bottom:16px; color:#f8fafc; }
.category h2 small { font-size:16px; font-weight:normal; }
.check { border:1px solid #334155; border-radius:8px; padding:14px; margin-bottom:10px; }
.check-pass { border-left:4px solid #22c55e; } .check-warn { border-left:4px solid #f59e0b; }
.check-fail { border-left:4px solid #ef4444; } .check-info { border-left:4px solid #3b82f6; }
.check-error { border-left:4px solid #dc2626; }
.check-header { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:6px; }
.badge { display:inline-block; padding:2px 10px; border-radius:4px; font-size:16px;
  font-weight:bold; color:#fff; }
.check-name { color:#94a3b8; }
.details { margin-top:8px; border-collapse:collapse; width:100%; display:block; overflow-x:auto; }
.details td { padding:4px 8px; border-bottom:1px solid #334155; vertical-align:top;
  word-break:break-word; }
.detail-key { color:#94a3b8; white-space:nowrap; width:1%; }
.ai-section { background:linear-gradient(135deg, #1e293b, #1e3a5f); }
.ai-content pre { white-space:pre-wrap; font-size:16px; line-height:1.7; font-family:inherit; }
.table-wrap { overflow-x:auto; }
.pages { width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; }
.pages th { background:#334155; padding:12px 16px; text-align:left; text-transform:uppercase;
  color:#94a3b8; }
.pages td { padding:10px 16px; border-bottom:1px solid #334155; }
a { color:#60a5fa; text-decoration:none; } a:hover { text-decoration:underline; }
.row-fail { border-left:4px solid #ef4444; } .row-warn { border-left:4px solid #f59e0b; }
.row-pass { border-left:4px solid #22c55e; }
footer { text-align:center; padding:30px; color:#94a3b8; }
"""
