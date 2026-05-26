"""SETA HTML report generator.

Produces a single self-contained HTML file from processed simulation
trace data (the output of ``processor.process_run()``).

The generated report embeds all CSS and JavaScript — no external
dependencies, no build step, opens directly in a browser.
"""

import html
import json
import os

# ---------------------------------------------------------------------------
# HTML template with placeholders:
#   {{SIM_DATA}}  — JSON-serialized data dict
#   {{SCENARIO}}  — scenario name (HTML-safe)
# ---------------------------------------------------------------------------
_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SETA Report — {{SCENARIO}}</title>
<style>
/* =========================================================
   CSS Variables & Reset
   ========================================================= */
:root {
  --bg-primary: #1a1a2e;
  --bg-secondary: #16213e;
  --bg-card: #1e2a4a;
  --bg-hover: #253555;
  --bg-sidebar: #14142b;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0b0;
  --text-muted: #6b7280;
  --border: #2a2a4e;
  --border-light: #35355a;
  --accent-blue: #3b82f6;
  --accent-green: #22c55e;
  --accent-red: #ef4444;
  --accent-orange: #f59e0b;
  --accent-purple: #a855f7;
  --accent-cyan: #06b6d4;
  --badge-warehouse: #64748b;
  --badge-production: #3b82f6;
  --badge-source: #22c55e;
  --badge-sink: #f59e0b;
  --badge-edge: #a855f7;
  --highlight-bg: rgba(251, 191, 36, 0.15);
  --sidebar-width: 280px;
  --header-height: 52px;
  --radius: 8px;
  --radius-sm: 4px;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: Consolas, "Courier New", "Source Code Pro", monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--accent-blue); text-decoration: none; }
a:hover { text-decoration: underline; }
a:focus-visible { outline: 2px solid var(--accent-blue); outline-offset: 2px; }

/* Scrollbar styling */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-light); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* =========================================================
   Layout
   ========================================================= */
#app {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Header */
.app-header {
  height: var(--header-height);
  min-height: var(--header-height);
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  z-index: 100;
}
.app-header .logo {
  font-weight: 700;
  font-size: 18px;
  letter-spacing: -0.5px;
  color: var(--accent-cyan);
  white-space: nowrap;
}
.app-header .logo small {
  font-weight: 400;
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 6px;
}
.app-header .header-stats {
  display: flex;
  gap: 16px;
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary);
}
.app-header .header-stats span {
  white-space: nowrap;
}
.app-header .header-stats strong {
  color: var(--text-primary);
  font-weight: 600;
}
.sidebar-toggle {
  display: none;
  background: none;
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

/* Body layout */
.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: var(--sidebar-width);
  min-width: var(--sidebar-width);
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.2s ease;
}
.sidebar-section {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}
.sidebar-section h3 {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-muted);
  margin-bottom: 10px;
  font-weight: 600;
}

/* Filter buttons */
.filter-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.filter-btn {
  font-size: 11px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.filter-btn:hover {
  border-color: var(--text-muted);
  color: var(--text-primary);
}
.filter-btn.active {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
}

/* Search input */
.search-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.search-input:focus {
  border-color: var(--accent-blue);
}
.search-input::placeholder { color: var(--text-muted); }

/* Node/edge list in sidebar */
.node-list, .edge-list {
  overflow-y: auto;
  flex: 1;
}
.sidebar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  cursor: pointer;
  transition: background 0.1s;
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
}
.sidebar-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  text-decoration: none;
}
.sidebar-item.hidden {
  display: none;
}
.sidebar-item .item-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Badge */
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 10px;
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 1.6;
}
.badge-warehouse  { background: var(--badge-warehouse); color: #fff; }
.badge-production { background: var(--badge-production); color: #fff; }
.badge-source     { background: var(--badge-source); color: #fff; }
.badge-sink       { background: var(--badge-sink); color: #1a1a2e; }
.badge-edge       { background: var(--badge-edge); color: #fff; }
.badge-completed  { background: var(--accent-green); color: #fff; }
.badge-failed     { background: var(--accent-red); color: #fff; }
.badge-in_progress { background: var(--accent-orange); color: #1a1a2e; }

.badge-sm {
  font-size: 9px;
  padding: 0 6px;
  border-radius: 8px;
}

/* =========================================================
   Main Content
   ========================================================= */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
}

/* Breadcrumb */
.breadcrumb {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.breadcrumb a {
  color: var(--text-muted);
}
.breadcrumb a:hover {
  color: var(--accent-blue);
  text-decoration: none;
}
.breadcrumb .sep {
  margin: 0 6px;
  color: var(--border-light);
}

/* =========================================================
   Dashboard
   ========================================================= */
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 18px;
  transition: border-color 0.15s;
}
.stat-card:hover {
  border-color: var(--border-light);
}
.stat-card .stat-value {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.5px;
  line-height: 1.2;
}
.stat-card .stat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.stat-card .stat-sub {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

/* Status breakdown row */
.status-row {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}
.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.completed   { background: var(--accent-green); }
.status-dot.failed      { background: var(--accent-red); }
.status-dot.in_progress { background: var(--accent-orange); }

/* Quick links section */
.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 14px;
  color: var(--text-primary);
}
.quick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.quick-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
  text-decoration: none;
}
.quick-link:hover {
  border-color: var(--accent-blue);
  color: var(--text-primary);
  text-decoration: none;
}

/* =========================================================
   Node / Edge / Order View
   ========================================================= */
.view-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.view-header h1 {
  font-size: 22px;
  font-weight: 700;
}
.view-header .view-subtitle {
  color: var(--text-secondary);
  font-size: 13px;
}

/* Detail table */
.detail-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 20px;
  font-size: 13px;
}
.detail-table td {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
}
.detail-table td:first-child {
  color: var(--text-muted);
  width: 160px;
  white-space: nowrap;
  vertical-align: top;
}
.detail-table td:last-child {
  color: var(--text-primary);
}

/* Inventory list */
.inv-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
}
.inv-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

/* =========================================================
   Job Cards
   ========================================================= */
.job-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 12px;
  overflow: hidden;
  transition: border-color 0.15s;
}
.job-card:hover {
  border-color: var(--border-light);
}
.job-card.production {
  border-left: 3px solid var(--accent-blue);
}
.job-card.transport {
  border-left: 3px solid var(--accent-green);
}
.job-card.failed {
  border-left: 3px solid var(--accent-red);
}

.job-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}
.job-card-header:hover {
  background: var(--bg-hover);
}
.job-card-header .card-expand-icon {
  flex-shrink: 0;
  width: 16px;
  text-align: center;
  color: var(--text-muted);
  transition: transform 0.2s;
}
.job-card.expanded .card-expand-icon {
  transform: rotate(90deg);
}
.job-card-header .card-order-id {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-cyan);
  min-width: 60px;
}
.job-card-header .card-summary {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.job-card-header .card-status {
  flex-shrink: 0;
}
.job-card-body {
  display: none;
  border-top: 1px solid var(--border);
  padding: 12px 14px;
}
.job-card.expanded .job-card-body {
  display: block;
}

/* =========================================================
   Event List
   ========================================================= */
.event-list {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
}
.event-item {
  display: flex;
  gap: 8px;
  padding: 2px 0;
  border-radius: 2px;
  transition: background 0.15s;
  cursor: default;
  align-items: flex-start;
}
.event-item:hover {
  background: var(--bg-hover);
}
.event-item.highlighted {
  background: var(--highlight-bg);
  border-radius: var(--radius-sm);
}
.event-item .event-time {
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
  cursor: pointer;
  padding: 0 2px;
  border-radius: 2px;
  transition: background 0.1s;
}
.event-item .event-time:hover {
  background: var(--border);
  color: var(--text-primary);
}
.event-item .event-text {
  color: var(--text-primary);
  word-break: break-word;
}
.event-item .event-raw-toggle {
  flex-shrink: 0;
  font-family: sans-serif;
  font-size: 10px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  line-height: 1.8;
  transition: all 0.1s;
}
.event-item .event-raw-toggle:hover {
  border-color: var(--text-muted);
  color: var(--text-primary);
}
.event-raw-data {
  display: none;
  margin: 4px 0 4px 16px;
  padding: 8px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text-secondary);
  max-height: 300px;
  overflow-y: auto;
}

/* Event type colors */
.event-text .ev-materials_consumed   { color: var(--accent-orange); }
.event-text .ev-materials_received   { color: var(--accent-green); }
.event-text .ev-production_started   { color: var(--accent-cyan); }
.event-text .ev-production_output    { color: var(--accent-blue); }
.event-text .ev-production_completed { color: var(--accent-green); }
.event-text .ev-transport_loaded     { color: var(--accent-orange); }
.event-text .ev-transport_unloaded   { color: var(--accent-green); }
.event-text .ev-transport_completed  { color: var(--accent-green); }
.event-text .ev-capacity_warning     { color: var(--accent-orange); }
.event-text .ev-inventory_debited    { color: var(--accent-red); }
.event-text .ev-inventory_credited   { color: var(--accent-green); }
.event-text .ev-order_issued         { color: var(--accent-purple); }
.event-text .ev-order_activated      { color: var(--accent-cyan); }

/* =========================================================
   Warnings
   ========================================================= */
.warning-item {
  display: flex;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: var(--radius-sm);
  margin-bottom: 6px;
  font-size: 13px;
}
.warning-item .warning-icon {
  color: var(--accent-orange);
  flex-shrink: 0;
}

/* =========================================================
   Empty state / Not found
   ========================================================= */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.empty-state .empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.4;
}
.empty-state h2 {
  font-size: 18px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.empty-state p {
  font-size: 13px;
}

/* =========================================================
   Loading state
   ========================================================= */
#loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: var(--bg-primary);
  color: var(--text-muted);
  font-size: 16px;
  gap: 12px;
}
.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--border);
  border-top-color: var(--accent-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* =========================================================
   Responsive
   ========================================================= */
@media (max-width: 767px) {
  .sidebar-toggle { display: inline-block; }
  .sidebar {
    position: fixed;
    top: var(--header-height);
    left: 0;
    bottom: 0;
    z-index: 200;
    transform: translateX(-100%);
  }
  .sidebar.open {
    transform: translateX(0);
    box-shadow: 4px 0 20px rgba(0,0,0,0.4);
  }
  .sidebar-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 199;
  }
  .sidebar-backdrop.visible {
    display: block;
  }
  .content {
    padding: 16px;
  }
  .dashboard-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px;
  }
  .app-header .header-stats {
    display: none;
  }
}
</style>
</head>
<body>

<!-- Loading state -->
<div id="loading">
  <div class="spinner"></div>
  <span>Loading simulation data…</span>
</div>

<!-- Application root -->
<div id="app" style="display:none">
  <header class="app-header">
    <button class="sidebar-toggle" id="sidebarToggle" aria-label="Toggle sidebar">☰</button>
    <div class="logo">SETA <small>sim trace analyzer</small></div>
    <div class="header-stats" id="headerStats"></div>
  </header>
  <div class="app-body">
    <!-- Sidebar backdrop for mobile -->
    <div class="sidebar-backdrop" id="sidebarBackdrop"></div>

    <nav class="sidebar" id="sidebar">
      <div class="sidebar-section">
        <h3>Nodes</h3>
        <div class="filter-group" id="nodeFilters">
          <button class="filter-btn active" data-type="all">All</button>
          <button class="filter-btn" data-type="warehouse">WH</button>
          <button class="filter-btn" data-type="production">Prod</button>
          <button class="filter-btn" data-type="source">Src</button>
          <button class="filter-btn" data-type="sink">Sink</button>
        </div>
        <input class="search-input" id="nodeSearch" type="text" placeholder="Search nodes…" autocomplete="off">
      </div>
      <div class="node-list" id="nodeList"></div>
      <div class="sidebar-section">
        <h3>Edges</h3>
      </div>
      <div class="edge-list" id="edgeList"></div>
    </nav>

    <main class="content" id="content">
      <div class="breadcrumb" id="breadcrumb"></div>
      <div id="viewContent"></div>
    </main>
  </div>
</div>

<!-- ==============================================================
     Embedded data block
     ============================================================== -->
<script>const SIM_DATA = {{SIM_DATA}};</script>

<!-- ==============================================================
     Application JavaScript
     ============================================================== -->
<script>
(function () {
  'use strict';

  /* -------------------------------------------------------
     Helpers
     ------------------------------------------------------- */
  function getNode (id) { return SIM_DATA.nodes[id] || null; }
  function getEdge (id) { return SIM_DATA.edges[id] || null; }
  function getOrder (id) { return SIM_DATA.orders[id] || null; }

  function esc (s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                     .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fmtTime (t) {
    if (t == null) return '—';
    return Number(t).toFixed(1);
  }

  function badge (label, cls) {
    return '<span class="badge badge-' + esc(cls) + '">' + esc(label) + '</span>';
  }

  function badgeSm (label, cls) {
    return '<span class="badge badge-sm badge-' + esc(cls) + '">' + esc(label) + '</span>';
  }

  function timeLink (t) {
    var f = fmtTime(t);
    return '<a href="#" class="time-link" data-time="' + f + '" onclick="return window.SETA_highlightTime(\\'' + f + '\\')">' + f + '</a>';
  }

  /* -------------------------------------------------------
     Breadcrumb
     ------------------------------------------------------- */
  function setBreadcrumb (parts) {
    var html = '<a href="#/">Dashboard</a>';
    parts.forEach(function (p) {
      html += '<span class="sep">›</span>';
      if (p.url) {
        html += '<a href="' + esc(p.url) + '">' + esc(p.label) + '</a>';
      } else {
        html += '<span>' + esc(p.label) + '</span>';
      }
    });
    document.getElementById('breadcrumb').innerHTML = html;
  }

  /* -------------------------------------------------------
     Render event line (shared across views)
     ------------------------------------------------------- */
  function renderEvent (ev) {
    var timeStr = ev.end_time != null
      ? timeLink(ev.time) + '→' + timeLink(ev.end_time)
      : timeLink(ev.time);

    var suffix = '';
    if (ev.count > 1) {
      suffix = ' <span class="ev-count">×' + ev.count + '</span>';
    }

    var html = '<div class="event-item" data-time="' + esc(fmtTime(ev.time)) + '">';
    html += '<span class="event-time">[t=' + timeStr + ']</span>';
    html += '<span class="event-text">' + esc(ev.display) + suffix;

    // Show raw toggle if raw data is non-empty
    if (ev.raw && typeof ev.raw === 'object' && Object.keys(ev.raw).length > 0) {
      html += ' <button class="event-raw-toggle" onclick="window.SETA_toggleRaw(this)">raw</button>';
    }
    html += '</span></div>';

    if (ev.raw && typeof ev.raw === 'object' && Object.keys(ev.raw).length > 0) {
      html += '<div class="event-raw-data">' + esc(JSON.stringify(ev.raw, null, 1)) + '</div>';
    }

    return html;
  }

  /* -------------------------------------------------------
     Render event list from an array
     ------------------------------------------------------- */
  function renderEventList (events) {
    if (!events || events.length === 0) {
      return '<div class="empty-state" style="padding:20px"><p>No events recorded.</p></div>';
    }
    var html = '<div class="event-list">';
    for (var i = 0; i < events.length; i++) {
      html += renderEvent(events[i]);
    }
    html += '</div>';
    return html;
  }

  /* -------------------------------------------------------
     Render job card
     ------------------------------------------------------- */
  function renderJobCard (order) {
    var statusCls = order.status || 'in_progress';
    var typeCls = order.order_type === 'transport' ? 'transport' : 'production';

    var cardCls = 'job-card ' + typeCls;
    if (statusCls === 'failed') cardCls += ' failed';

    var summary = order.display_summary || ('Order #' + order.order_id + ' — ' + order.sku + ' ×' + order.quantity);

    var html = '<div class="' + cardCls + '">';
    html += '<div class="job-card-header" onclick="window.SETA_toggleCard(this)">';
    html += '<span class="card-expand-icon">▶</span>';
    html += '<span class="card-order-id">#' + esc(String(order.order_id)) + '</span>';
    html += '<span class="card-summary">' + esc(summary) + '</span>';
    html += badgeSm(statusCls === 'completed' ? 'OK' : statusCls === 'failed' ? 'FAIL' : '…', statusCls);
    html += '</div>';
    html += '<div class="job-card-body">';

    // Detail table
    html += '<table class="detail-table">';
    html += '<tr><td>SKU</td><td>' + esc(order.sku || '—') + '</td></tr>';
    html += '<tr><td>Quantity</td><td>' + esc(String(order.quantity)) + '</td></tr>';
    html += '<tr><td>Type</td><td>' + esc(order.order_type) + '</td></tr>';
    html += '<tr><td>Status</td><td>' + badge(order.status, order.status) + '</td></tr>';
    if (order.activate_time != null) html += '<tr><td>Activate time</td><td>' + timeLink(order.activate_time) + '</td></tr>';
    if (order.expect_time != null) html += '<tr><td>Expected end</td><td>' + timeLink(order.expect_time) + '</td></tr>';
    if (order.actual_start != null) html += '<tr><td>Actual start</td><td>' + timeLink(order.actual_start) + '</td></tr>';
    if (order.actual_end != null) html += '<tr><td>Actual end</td><td>' + timeLink(order.actual_end) + '</td></tr>';
    if (order.duration != null) html += '<tr><td>Duration</td><td>' + esc(fmtTime(order.duration)) + '</td></tr>';
    if (order.from_node) html += '<tr><td>From</td><td><a href="#/node/' + esc(order.from_node) + '">' + esc(order.from_node) + '</a></td></tr>';
    if (order.to_node) html += '<tr><td>To</td><td><a href="#/node/' + esc(order.to_node) + '">' + esc(order.to_node) + '</a></td></tr>';
    if (order.node_name) html += '<tr><td>Node</td><td><a href="#/node/' + esc(order.node_name) + '">' + esc(order.node_name) + '</a></td></tr>';
    html += '</table>';

    // Events
    if (order.events && order.events.length > 0) {
      html += '<div style="margin-top:10px;font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Event Timeline</div>';
      html += renderEventList(order.events);
    }

    html += '</div>'; // card-body
    html += '</div>'; // card
    return html;
  }

  /* -------------------------------------------------------
     Dashboard
     ------------------------------------------------------- */
  function renderDashboard () {
    var m = SIM_DATA.meta;
    if (!m) return '<div class="empty-state"><h2>No metadata</h2></div>';

    setBreadcrumb([]);

    // Compute status counts
    var statusCounts = { completed: 0, failed: 0, in_progress: 0 };
    var orderIds = Object.keys(SIM_DATA.orders);
    for (var i = 0; i < orderIds.length; i++) {
      var s = SIM_DATA.orders[orderIds[i]].status;
      if (statusCounts.hasOwnProperty(s)) statusCounts[s]++;
    }

    var html = '';

    // Summary grid
    html += '<div class="dashboard-grid">';
    html += '<div class="stat-card"><div class="stat-value">' + esc(m.scenario) + '</div><div class="stat-label">Scenario</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(fmtTime(m.sim_duration)) + '</div><div class="stat-label">Duration</div><div class="stat-sub">time units</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(m.management_type || '—') + '</div><div class="stat-label">Management</div><div class="stat-sub">every ' + esc(fmtTime(m.decision_interval)) + 't</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.num_nodes)) + '</div><div class="stat-label">Nodes</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.num_edges)) + '</div><div class="stat-label">Edges</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.order_count)) + '</div><div class="stat-label">Orders</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.event_count)) + '</div><div class="stat-label">Events</div></div>';
    html += '<div class="stat-card"><div class="stat-value" style="color:var(--accent-green)">' + esc(String(statusCounts.completed)) + '</div><div class="stat-label">Completed</div></div>';
    html += '<div class="stat-card"><div class="stat-value" style="color:var(--accent-red)">' + esc(String(statusCounts.failed)) + '</div><div class="stat-label">Failed</div></div>';
    html += '<div class="stat-card"><div class="stat-value" style="color:var(--accent-orange)">' + esc(String(statusCounts.in_progress)) + '</div><div class="stat-label">In Progress</div></div>';
    html += '</div>';

    // Status breakdown
    var total = orderIds.length;
    if (total > 0) {
      html += '<div class="status-row">';
      html += '<div class="status-item"><span class="status-dot completed"></span> Completed: ' + statusCounts.completed + '</div>';
      html += '<div class="status-item"><span class="status-dot failed"></span> Failed: ' + statusCounts.failed + '</div>';
      html += '<div class="status-item"><span class="status-dot in_progress"></span> In Progress: ' + statusCounts.in_progress + '</div>';
      html += '<div class="status-item" style="color:var(--text-muted)">Total orders: ' + total + '</div>';
      html += '</div>';
    }

    // Quick links — nodes
    if (SIM_DATA.node_list && SIM_DATA.node_list.length > 0) {
      html += '<h2 class="section-title">Nodes</h2>';
      html += '<div class="quick-links">';
      for (var j = 0; j < SIM_DATA.node_list.length; j++) {
        var n = SIM_DATA.node_list[j];
        html += '<a class="quick-link" href="#/node/' + esc(n.id) + '">' + badgeSm(n.type, n.type) + ' ' + esc(n.display_name || n.id) + '</a>';
      }
      html += '</div>';
    }

    // Quick links — edges
    if (SIM_DATA.edge_list && SIM_DATA.edge_list.length > 0) {
      html += '<h2 class="section-title" style="margin-top:20px;">Edges</h2>';
      html += '<div class="quick-links">';
      for (var k = 0; k < SIM_DATA.edge_list.length; k++) {
        var e = SIM_DATA.edge_list[k];
        html += '<a class="quick-link" href="#/edge/' + esc(e.id) + '">' + badgeSm('edge', 'edge') + ' ' + esc(e.display_name || e.id) + '</a>';
      }
      html += '</div>';
    }

    return html;
  }

  /* -------------------------------------------------------
     Node View
     ------------------------------------------------------- */
  function renderNodeView (nodeId) {
    var node = getNode(nodeId);
    if (!node) return renderNotFound('Node "' + esc(nodeId) + '" not found.');

    setBreadcrumb([{ label: 'Node: ' + (node.display_name || node.id), url: null }]);

    var html = '';

    // Header
    html += '<div class="view-header">';
    html += badge(node.type, node.type);
    html += '<h1>' + esc(node.display_name || node.id) + '</h1>';
    html += '<span class="view-subtitle">' + esc(node.id) + '</span>';
    html += '</div>';

    // Detail table
    html += '<table class="detail-table">';
    html += '<tr><td>ID</td><td>' + esc(node.id) + '</td></tr>';
    html += '<tr><td>Type</td><td>' + badge(node.type, node.type) + '</td></tr>';
    html += '<tr><td>Jobs</td><td>' + esc(String((node.jobs && node.jobs.length) || 0)) + '</td></tr>';
    html += '<tr><td>Events</td><td>' + esc(String((node.events && node.events.length) || 0)) + '</td></tr>';
    html += '</table>';

    // Initial inventory
    if (node.init_inventory && Object.keys(node.init_inventory).length > 0) {
      html += '<h2 class="section-title">Initial Inventory</h2>';
      html += '<div class="inv-list">';
      var invKeys = Object.keys(node.init_inventory);
      for (var i = 0; i < invKeys.length; i++) {
        var sku = invKeys[i];
        html += '<span class="inv-tag">' + esc(sku) + ': ' + esc(String(node.init_inventory[sku])) + '</span>';
      }
      html += '</div>';
    }

    // Job cards (orders touching this node)
    if (node.jobs && node.jobs.length > 0) {
      html += '<h2 class="section-title">Jobs</h2>';
      for (var j = 0; j < node.jobs.length; j++) {
        var oid = node.jobs[j];
        var order = getOrder(oid);
        if (order) {
          html += renderJobCard(order);
        } else {
          html += '<div class="job-card"><div class="job-card-header">Order #' + esc(String(oid)) + ' (data not found)</div></div>';
        }
      }
    }

    // Non-job events (inventory changes, warnings, etc.)
    if (node.events && node.events.length > 0) {
      // Separate warnings and other events
      var warnings = [];
      var otherEvents = [];
      for (var k = 0; k < node.events.length; k++) {
        var ev = node.events[k];
        if (ev.type === 'capacity_warning') {
          warnings.push(ev);
        } else {
          otherEvents.push(ev);
        }
      }

      if (otherEvents.length > 0) {
        html += '<h2 class="section-title" style="margin-top:20px;">Node Events</h2>';
        html += renderEventList(otherEvents);
      }

      if (warnings.length > 0) {
        html += '<h2 class="section-title" style="margin-top:20px;">Warnings</h2>';
        for (var w = 0; w < warnings.length; w++) {
          var warn = warnings[w];
          html += '<div class="warning-item" data-time="' + esc(fmtTime(warn.time)) + '">';
          html += '<span class="warning-icon">⚠</span>';
          html += '<span><strong>[t=' + timeLink(warn.time) + ']</strong> ' + esc(warn.display || warn.reason || 'capacity_warning');
          if (warn.raw && typeof warn.raw === 'object' && Object.keys(warn.raw).length > 0) {
            html += ' <button class="event-raw-toggle" onclick="window.SETA_toggleRaw(this)">raw</button>';
            html += '<div class="event-raw-data">' + esc(JSON.stringify(warn.raw, null, 1)) + '</div>';
          }
          html += '</span></div>';
        }
      }
    }

    return html;
  }

  /* -------------------------------------------------------
     Edge View
     ------------------------------------------------------- */
  function renderEdgeView (edgeId) {
    var edge = getEdge(edgeId);
    if (!edge) return renderNotFound('Edge "' + esc(edgeId) + '" not found.');

    setBreadcrumb([{ label: 'Edge: ' + (edge.display_name || edge.id), url: null }]);

    var html = '';

    // Header
    html += '<div class="view-header">';
    html += badge('edge', 'edge');
    html += '<h1>' + esc(edge.display_name || edge.id) + '</h1>';
    html += '<span class="view-subtitle">' + esc(edge.id) + '</span>';
    html += '</div>';

    // From → To
    html += '<table class="detail-table">';
    html += '<tr><td>ID</td><td>' + esc(edge.id) + '</td></tr>';
    html += '<tr><td>From</td><td><a href="#/node/' + esc(edge.from) + '">' + esc(edge.from_display || edge.from) + '</a></td></tr>';
    html += '<tr><td>To</td><td><a href="#/node/' + esc(edge.to) + '">' + esc(edge.to_display || edge.to) + '</a></td></tr>';
    html += '<tr><td>Jobs</td><td>' + esc(String((edge.jobs && edge.jobs.length) || 0)) + '</td></tr>';
    html += '<tr><td>Events</td><td>' + esc(String((edge.events && edge.events.length) || 0)) + '</td></tr>';
    html += '</table>';

    // Jobs on this edge
    if (edge.jobs && edge.jobs.length > 0) {
      html += '<h2 class="section-title">Transport Jobs</h2>';
      for (var i = 0; i < edge.jobs.length; i++) {
        var order = getOrder(edge.jobs[i]);
        if (order) {
          html += renderJobCard(order);
        }
      }
    }

    // Edge events
    if (edge.events && edge.events.length > 0) {
      html += '<h2 class="section-title" style="margin-top:20px;">Edge Events</h2>';
      html += renderEventList(edge.events);
    }

    return html;
  }

  /* -------------------------------------------------------
     Order View
     ------------------------------------------------------- */
  function renderOrderView (orderId) {
    var order = getOrder(orderId);
    if (!order) return renderNotFound('Order #' + esc(orderId) + ' not found.');

    setBreadcrumb([{ label: 'Order #' + order.order_id, url: null }]);

    var html = '';

    // Header
    html += '<div class="view-header">';
    html += badge(order.status, order.status);
    html += '<h1>Order #' + esc(String(order.order_id)) + '</h1>';
    html += '<span class="view-subtitle">' + esc(order.sku || '') + ' ×' + esc(String(order.quantity)) + '</span>';
    html += '</div>';

    // Full detail table
    html += '<table class="detail-table">';
    html += '<tr><td>Order ID</td><td>' + esc(String(order.order_id)) + '</td></tr>';
    html += '<tr><td>SKU</td><td>' + esc(order.sku || '—') + '</td></tr>';
    html += '<tr><td>Quantity</td><td>' + esc(String(order.quantity)) + '</td></tr>';
    html += '<tr><td>Type</td><td>' + esc(order.order_type) + '</td></tr>';
    html += '<tr><td>Status</td><td>' + badge(order.status, order.status) + '</td></tr>';

    if (order.activate_time != null) html += '<tr><td>Activate time</td><td>' + timeLink(order.activate_time) + '</td></tr>';
    if (order.expect_time != null) html += '<tr><td>Expected end</td><td>' + timeLink(order.expect_time) + '</td></tr>';
    if (order.actual_start != null) html += '<tr><td>Actual start</td><td>' + timeLink(order.actual_start) + '</td></tr>';
    if (order.actual_end != null) html += '<tr><td>Actual end</td><td>' + timeLink(order.actual_end) + '</td></tr>';
    if (order.duration != null) html += '<tr><td>Duration</td><td>' + esc(fmtTime(order.duration)) + '</td></tr>';

    if (order.from_node) {
      html += '<tr><td>From</td><td><a href="#/node/' + esc(order.from_node) + '">' + esc(order.from_node) + '</a></td></tr>';
    }
    if (order.to_node) {
      html += '<tr><td>To</td><td><a href="#/node/' + esc(order.to_node) + '">' + esc(order.to_node) + '</a></td></tr>';
    }
    if (order.node_name) {
      html += '<tr><td>Production node</td><td><a href="#/node/' + esc(order.node_name) + '">' + esc(order.node_name) + '</a></td></tr>';
    }

    if (order.nodes_involved && order.nodes_involved.length > 0) {
      html += '<tr><td>Nodes involved</td><td>';
      for (var ni = 0; ni < order.nodes_involved.length; ni++) {
        if (ni > 0) html += ', ';
        html += '<a href="#/node/' + esc(order.nodes_involved[ni]) + '">' + esc(order.nodes_involved[ni]) + '</a>';
      }
      html += '</td></tr>';
    }

    html += '</table>';

    // Event timeline
    if (order.events && order.events.length > 0) {
      html += '<h2 class="section-title">Event Timeline</h2>';
      html += renderEventList(order.events);
    }

    return html;
  }

  /* -------------------------------------------------------
     Not Found
     ------------------------------------------------------- */
  function renderNotFound (msg) {
    setBreadcrumb([]);
    return '<div class="empty-state">'
      + '<div class="empty-icon">🔍</div>'
      + '<h2>Not Found</h2>'
      + '<p>' + esc(msg || 'The requested page does not exist.') + '</p>'
      + '<p style="margin-top:12px"><a href="#/">Back to Dashboard</a></p>'
      + '</div>';
  }

  /* -------------------------------------------------------
     Router
     ------------------------------------------------------- */
  function route () {
    var hash = window.location.hash.replace(/^#/, '') || '/';
    var parts = hash.split('/').filter(Boolean);
    var html = '';

    if (parts.length === 0 || parts[0] === '') {
      html = renderDashboard();
    } else if (parts[0] === 'node' && parts[1]) {
      html = renderNodeView(parts[1]);
    } else if (parts[0] === 'edge' && parts[1]) {
      html = renderEdgeView(parts[1]);
    } else if (parts[0] === 'order' && parts[1]) {
      html = renderOrderView(parts[1]);
    } else {
      html = renderNotFound('Unknown route: ' + esc(hash));
    }

    document.getElementById('viewContent').innerHTML = html;

    // Update header stats
    var m = SIM_DATA.meta;
    if (m) {
      document.getElementById('headerStats').innerHTML =
        '<span>Scenario: <strong>' + esc(m.scenario) + '</strong></span>'
        + '<span>Orders: <strong>' + esc(String(m.order_count)) + '</strong></span>'
        + '<span>Events: <strong>' + esc(String(m.event_count)) + '</strong></span>'
        + '<span>Duration: <strong>' + esc(fmtTime(m.sim_duration)) + '</strong></span>';
    }
  }

  /* -------------------------------------------------------
     Init: build sidebar, start router
     ------------------------------------------------------- */
  function init () {
    // Hide loading, show app
    document.getElementById('loading').style.display = 'none';
    document.getElementById('app').style.display = 'flex';

    // Build node list in sidebar
    var nodeListEl = document.getElementById('nodeList');
    var nodeHtml = '';
    if (SIM_DATA.node_list) {
      for (var i = 0; i < SIM_DATA.node_list.length; i++) {
        var n = SIM_DATA.node_list[i];
        nodeHtml += '<a class="sidebar-item" data-type="' + esc(n.type) + '" data-name="' + esc((n.display_name || n.id).toLowerCase()) + '" href="#/node/' + esc(n.id) + '">'
          + badgeSm(n.type, n.type)
          + '<span class="item-label">' + esc(n.display_name || n.id) + '</span>'
          + '</a>';
      }
    }
    nodeListEl.innerHTML = nodeHtml;

    // Build edge list in sidebar
    var edgeListEl = document.getElementById('edgeList');
    var edgeHtml = '';
    if (SIM_DATA.edge_list) {
      for (var j = 0; j < SIM_DATA.edge_list.length; j++) {
        var e = SIM_DATA.edge_list[j];
        edgeHtml += '<a class="sidebar-item" href="#/edge/' + esc(e.id) + '">'
          + badgeSm('edge', 'edge')
          + '<span class="item-label">' + esc(e.display_name || e.id) + '</span>'
          + '</a>';
      }
    }
    edgeListEl.innerHTML = edgeHtml;

    // Node type filter
    var filterBtns = document.querySelectorAll('#nodeFilters .filter-btn');
    for (var fb = 0; fb < filterBtns.length; fb++) {
      filterBtns[fb].addEventListener('click', function () {
        var type = this.getAttribute('data-type');
        filterBtns.forEach(function (b) { b.classList.remove('active'); });
        this.classList.add('active');

        var items = nodeListEl.querySelectorAll('.sidebar-item');
        for (var it = 0; it < items.length; it++) {
          if (type === 'all') {
            items[it].classList.remove('hidden');
          } else {
            var itemType = items[it].getAttribute('data-type');
            items[it].classList.toggle('hidden', itemType !== type);
          }
        }
      });
    }

    // Node search
    var searchInput = document.getElementById('nodeSearch');
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        var q = this.value.toLowerCase().trim();
        var items = nodeListEl.querySelectorAll('.sidebar-item');
        var activeFilter = document.querySelector('#nodeFilters .filter-btn.active');
        var filterType = activeFilter ? activeFilter.getAttribute('data-type') : 'all';

        for (var it = 0; it < items.length; it++) {
          var name = items[it].getAttribute('data-name') || '';
          var itemType = items[it].getAttribute('data-type') || '';
          var matchesSearch = !q || name.indexOf(q) !== -1;
          var matchesFilter = filterType === 'all' || itemType === filterType;
          items[it].classList.toggle('hidden', !matchesSearch || !matchesFilter);
        }
      });
    }

    // Sidebar toggle (mobile)
    var sidebarToggle = document.getElementById('sidebarToggle');
    var sidebar = document.getElementById('sidebar');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (sidebarToggle) {
      sidebarToggle.addEventListener('click', function () {
        sidebar.classList.toggle('open');
        backdrop.classList.toggle('visible');
      });
    }
    if (backdrop) {
      backdrop.addEventListener('click', function () {
        sidebar.classList.remove('open');
        backdrop.classList.remove('visible');
      });
    }

    // Close sidebar on navigation (mobile)
    sidebar.addEventListener('click', function () {
      if (window.innerWidth < 768) {
        sidebar.classList.remove('open');
        backdrop.classList.remove('visible');
      }
    });

    // Watch hash changes
    window.addEventListener('hashchange', route);

    // Initial route
    route();
  }

  /* -------------------------------------------------------
     Expose global event handlers (for inline onclick)
     ------------------------------------------------------- */
  window.SETA_toggleCard = function (headerEl) {
    var card = headerEl.closest('.job-card');
    if (card) card.classList.toggle('expanded');
  };

  window.SETA_toggleRaw = function (btnEl) {
    var dataEl = btnEl.parentElement.nextElementSibling;
    if (dataEl && dataEl.classList.contains('event-raw-data')) {
      var isHidden = dataEl.style.display === 'none' || dataEl.style.display === '';
      dataEl.style.display = isHidden ? 'block' : 'none';
      btnEl.textContent = isHidden ? 'hide' : 'raw';
    }
  };

  window.SETA_highlightTime = function (timeStr) {
    // Remove previous highlights
    var prev = document.querySelectorAll('.event-item.highlighted');
    for (var p = 0; p < prev.length; p++) {
      prev[p].classList.remove('highlighted');
    }

    // Find and highlight matching events
    var targets = document.querySelectorAll('.event-item[data-time="' + timeStr.replace(/"/g, '') + '"]');
    for (var t = 0; t < targets.length; t++) {
      targets[t].classList.add('highlighted');
    }

    // Also highlight warning items
    var warns = document.querySelectorAll('.warning-item[data-time="' + timeStr.replace(/"/g, '') + '"]');
    for (var w = 0; w < warns.length; w++) {
      warns[w].style.outline = '2px solid var(--accent-orange)';
      setTimeout(function (el) { el.style.outline = ''; }, 2000);
    }

    // Scroll to first target
    if (targets.length > 0) {
      targets[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else if (warns.length > 0) {
      warns[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    return false; // prevent default anchor click
  };

  /* -------------------------------------------------------
     Start on DOMContentLoaded
     ------------------------------------------------------- */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_report(data: dict, output_path: str) -> str:
    """Generate the HTML report and write to *output_path*.  Returns *output_path*.

    Parameters
    ----------
    data : dict
        Processed simulation data dict (the output of ``processor.process_run()``).
    output_path : str
        Absolute or relative filesystem path for the generated ``.html`` file.

    Returns
    -------
    str
        The same *output_path* that was passed in (for convenience in chaining).
    """
    json_data = json.dumps(data, indent=1, ensure_ascii=False)
    # Safeguard: escape any </script> that might appear inside the JSON data
    json_data = json_data.replace("</script>", "<\\/script>")

    scenario = data.get("meta", {}).get("scenario", "SETA Report")
    scenario_safe = html.escape(str(scenario))

    output = (
        _TEMPLATE.replace("{{SIM_DATA}}", json_data)
        .replace("{{SCENARIO}}", scenario_safe)
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    return output_path
