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
<title>SETA 报告 — {{SCENARIO}}</title>
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

/* Chart containers */
.chart-container {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-top: 16px;
}
.chart-container h3 {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 12px;
  font-weight: 600;
}
.chart-container .chart-wrap {
  position: relative;
  height: 250px;
}
</style>
</head>
<body>

<!-- Loading state -->
<div id="loading">
  <div class="spinner"></div>
  <span>正在加载仿真数据…</span>
</div>

<!-- Application root -->
<div id="app" style="display:none">
  <header class="app-header">
    <button class="sidebar-toggle" id="sidebarToggle" aria-label="切换侧边栏">☰</button>
    <div class="logo">SETA <small>仿真轨迹分析</small></div>
    <div class="header-stats" id="headerStats"></div>
  </header>
  <div class="app-body">
    <!-- Sidebar backdrop for mobile -->
    <div class="sidebar-backdrop" id="sidebarBackdrop"></div>

    <nav class="sidebar" id="sidebar">
      <div class="sidebar-section">
        <h3>节点</h3>
        <div class="filter-group" id="nodeFilters">
          <button class="filter-btn active" data-type="all">全部</button>
          <button class="filter-btn" data-type="warehouse">仓库</button>
          <button class="filter-btn" data-type="production">生产</button>
          <button class="filter-btn" data-type="source">源点</button>
          <button class="filter-btn" data-type="sink">汇点</button>
        </div>
        <input class="search-input" id="nodeSearch" type="text" placeholder="搜索节点…" autocomplete="off">
      </div>
      <div class="node-list" id="nodeList"></div>
      <div class="sidebar-section">
        <h3>边</h3>
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
     Chart.js library (embedded)
     ============================================================== -->
<script>{{CHART_JS}}</script>

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
     Chart helpers
     ------------------------------------------------------- */
  var _chartInstances = [];

  function _chartOpts (title, yLabel, color, fill) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      color: '#a0a0b0',
      scales: {
        x: { title: { display: true, text: '时间', color: '#a0a0b0' }, ticks: { color: '#a0a0b0' }, grid: { color: '#2a2a4e' } },
        y: { title: { display: true, text: yLabel, color: '#a0a0b0' }, beginAtZero: true, ticks: { color: '#a0a0b0' }, grid: { color: '#2a2a4e' } },
      },
      plugins: { legend: { display: false }, tooltip: { backgroundColor: '#1e2a4a', titleColor: '#e0e0e0', bodyColor: '#e0e0e0', borderColor: '#2a2a4e', borderWidth: 1 } },
    };
  }

  function _createChart (canvasId, type, data, opts) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    var chart = new Chart(canvas.getContext('2d'), { type: type, data: data, options: opts });
    _chartInstances.push(chart);
    return chart;
  }

  function _destroyCharts () {
    for (var i = 0; i < _chartInstances.length; i++) _chartInstances[i].destroy();
    _chartInstances = [];
  }

  function _storageChartConfig (chartData) {
    var opts = _chartOpts('库存水位', '托盘数', '#06b6d4', true);
    opts.scales.x.type = 'linear';
    return {
      type: 'line',
      data: {
        datasets: [{
          data: chartData.map(function (p) { return { x: p[0], y: p[1] }; }),
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.08)',
          fill: true,
          stepped: 'before',
          pointRadius: 0,
          borderWidth: 2,
        }],
      },
      options: opts,
    };
  }

  function _rateChartConfig (chartData, color, yLabel) {
    return {
      type: 'bar',
      data: {
        labels: chartData.map(function (p) { return p[0].toFixed(1); }),
        datasets: [{
          data: chartData.map(function (p) { return p[1]; }),
          backgroundColor: color,
          borderRadius: 2,
          borderWidth: 0,
        }],
      },
      options: _chartOpts('', yLabel, color, false),
    };
  }

  function _chartSafeId (prefix, id) {
    return prefix + id.replace(/[^a-zA-Z0-9_-]/g, '_');
  }

  var _pendingCharts = [];

  function _flushCharts () {
    for (var i = 0; i < _pendingCharts.length; i++) {
      var pc = _pendingCharts[i];
      var chart;
      if (pc.type === 'storage') {
        chart = _createChart(pc.id, 'line', pc.config.data, pc.config.options);
      } else {
        chart = _createChart(pc.id, 'bar', pc.config.data, pc.config.options);
      }
    }
    _pendingCharts = [];
  }

  /* -------------------------------------------------------
     Event display builder (ported from Python)
     ------------------------------------------------------- */
  function buildEventDisplay (ev) {
    var etype = ev.type;
    var count = ev.count || 1;
    var qty = ev.quantity || 0;
    var total = ev.total || 0;
    var sku = ev.sku || '';
    var t0 = ev.time;
    var tn = ev.end_time;
    var interval = ev.interval;

    if (count > 1) {
      var rangeStr = 't=' + t0 + '→' + (tn === Math.floor(tn) ? Math.floor(tn) : tn);
      var intervalStr = '';
      if (interval != null) {
        var iv = (interval === Math.floor(interval) ? Math.floor(interval) : interval);
        intervalStr = ', every ' + iv + 't';
      }

      if (etype === 'production_output') {
        return 'production_output: ' + count + ' steps × ' + qty + ' units = ' + total + ' total, ' + rangeStr + intervalStr + ' → ' + (ev.destination || '');
      }
      if (etype === 'received') {
        return 'received: ' + count + ' arrivals × ' + qty + ' units = ' + total + ' total, ' + rangeStr + intervalStr + ' from ' + (ev.source || '');
      }
      if (etype === 'debited') {
        return 'debited: ' + count + ' departures × ' + qty + ' units = ' + total + ' total, ' + rangeStr + intervalStr;
      }
    }

    // Single event
    if (etype === 'production_output') return 'production_output: ' + sku + ' × ' + qty + ' → ' + (ev.destination || '');
    if (etype === 'received') return 'received: ' + qty + ' units of ' + sku + ' at t=' + t0 + ' from ' + (ev.source || '');
    if (etype === 'debited') return 'debited: ' + qty + ' units of ' + sku + ' at t=' + t0;
    if (etype === 'production_started') return 'production_started: ' + sku + ' × ' + qty;
    if (etype === 'production_completed') return 'production_completed: ' + sku + ' × ' + qty;
    
    if (etype === 'materials_consumed') {
      var items = [];
      if (ev.inputs) {
        for (var k in ev.inputs) items.push(k + ': ' + ev.inputs[k]);
      }
      return 'materials_consumed: ' + sku + ' × ' + qty + ' | inputs: {' + items.join(', ') + '}';
    }

    if (etype === 'production_failed') {
      var req_s = []; if (ev.required) for (var k in ev.required) req_s.push(k + ': ' + ev.required[k]);
      var ava_s = []; if (ev.available) for (var k in ev.available) ava_s.push(k + ': ' + ev.available[k]);
      return 'production_failed: ' + sku + ' — ' + (ev.reason || '') + ' (required: {' + req_s.join(', ') + '}, available: {' + ava_s.join(', ') + '})';
    }

    if (etype === 'production_deferred') {
      var req_s = []; if (ev.required) for (var k in ev.required) req_s.push(k + ': ' + ev.required[k]);
      var ava_s = []; if (ev.available) for (var k in ev.available) ava_s.push(k + ': ' + ev.available[k]);
      return 'production_deferred: ' + sku + ' — ' + (ev.reason || '') + ' (defer ' + (ev.defer_minutes || 0) + ' min, required: {' + req_s.join(', ') + '}, available: {' + ava_s.join(', ') + '})';
    }

    if (etype === 'transport_order_added') return 'transport_order_added: #' + (ev.order_id || '') + ' ' + sku + ' × ' + qty + ' from ' + (ev.from_node || '') + ' → ' + (ev.to_node || '');
    if (etype === 'transport_started') return 'transport_started: #' + (ev.order_id || '') + ' ' + sku + ' × ' + qty + ' from ' + (ev.from_node || '') + ' → ' + (ev.to_node || '') + ' (' + (ev.pallets_count || 0) + ' pallets)';
    if (etype === 'transport_completed') return 'transport_completed: #' + (ev.order_id || '') + ' ' + sku + ' × ' + qty + ' from ' + (ev.from_node || '') + ' → ' + (ev.to_node || '');

    if (etype === 'capacity_warning') return 'capacity_warning: ' + (ev.pallets || 0) + ' pallets (max ' + (ev.max_pallets || 0) + ')';

    return etype + ': ' + sku + ' × ' + qty + ' at t=' + t0;
  }

  /* -------------------------------------------------------
     Breadcrumb
     ------------------------------------------------------- */
  function setBreadcrumb (parts) {
    var html = '<a href="#/">仪表盘</a>';
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
    html += '<span class="event-text">' + esc(buildEventDisplay(ev)) + suffix;

    // Show raw toggle if raw data is non-empty
    if (ev.raw && typeof ev.raw === 'object' && Object.keys(ev.raw).length > 0) {
      html += ' <button class="event-raw-toggle" onclick="window.SETA_toggleRaw(this)">原始</button>';
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
      return '<div class="empty-state" style="padding:20px"><p>暂无事件记录。</p></div>';
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

    var summary = order.display_summary || ('订单 #' + order.order_id + ' — ' + order.sku + ' ×' + order.quantity);

    var html = '<div class="' + cardCls + '">';
    html += '<div class="job-card-header" onclick="window.SETA_toggleCard(this)">';
    html += '<span class="card-expand-icon">▶</span>';
    html += '<span class="card-order-id">#' + esc(String(order.order_id)) + '</span>';
    html += '<span class="card-summary">' + esc(summary) + '</span>';
    html += badgeSm(statusCls === 'completed' ? '完成' : statusCls === 'failed' ? '失败' : '…', statusCls);
    html += '</div>';
    html += '<div class="job-card-body">';

    // Detail table
    html += '<table class="detail-table">';
    html += '<tr><td>SKU</td><td>' + esc(order.sku || '—') + '</td></tr>';
    html += '<tr><td>数量</td><td>' + esc(String(order.quantity)) + '</td></tr>';
    html += '<tr><td>类型</td><td>' + esc(order.order_type) + '</td></tr>';
    html += '<tr><td>状态</td><td>' + badge(order.status, order.status) + '</td></tr>';
    if (order.activate_time != null) html += '<tr><td>激活时间</td><td>' + timeLink(order.activate_time) + '</td></tr>';
    if (order.expect_time != null) html += '<tr><td>预计结束</td><td>' + timeLink(order.expect_time) + '</td></tr>';
    if (order.actual_start != null) html += '<tr><td>实际开始</td><td>' + timeLink(order.actual_start) + '</td></tr>';
    if (order.actual_end != null) html += '<tr><td>实际结束</td><td>' + timeLink(order.actual_end) + '</td></tr>';
    if (order.duration != null) html += '<tr><td>时长</td><td>' + esc(fmtTime(order.duration)) + '</td></tr>';
    if (order.from_node) html += '<tr><td>从</td><td><a href="#/node/' + esc(order.from_node) + '">' + esc(order.from_node) + '</a></td></tr>';
    if (order.to_node) html += '<tr><td>到</td><td><a href="#/node/' + esc(order.to_node) + '">' + esc(order.to_node) + '</a></td></tr>';
    if (order.node_name) html += '<tr><td>节点</td><td><a href="#/node/' + esc(order.node_name) + '">' + esc(order.node_name) + '</a></td></tr>';
    html += '</table>';

    // Events
    if (order.events && order.events.length > 0) {
      html += '<div style="margin-top:10px;font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">事件时间线</div>';
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
    if (!m) return '<div class="empty-state"><h2>无元数据</h2></div>';

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
    html += '<div class="stat-card"><div class="stat-value">' + esc(m.scenario) + '</div><div class="stat-label">场景</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(fmtTime(m.sim_duration)) + '</div><div class="stat-label">时长</div><div class="stat-sub">时间单位</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(m.management_type || '—') + '</div><div class="stat-label">管理方式</div><div class="stat-sub">每 ' + esc(fmtTime(m.decision_interval)) + 't</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.num_nodes)) + '</div><div class="stat-label">节点</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.num_edges)) + '</div><div class="stat-label">边</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.order_count)) + '</div><div class="stat-label">订单</div></div>';
    html += '<div class="stat-card"><div class="stat-value">' + esc(String(m.event_count)) + '</div><div class="stat-label">事件</div></div>';
    html += '<div class="stat-card"><div class="stat-value" style="color:var(--accent-green)">' + esc(String(statusCounts.completed)) + '</div><div class="stat-label">已完成</div></div>';
    html += '<div class="stat-card"><div class="stat-value" style="color:var(--accent-red)">' + esc(String(statusCounts.failed)) + '</div><div class="stat-label">失败</div></div>';
    html += '<div class="stat-card"><div class="stat-value" style="color:var(--accent-orange)">' + esc(String(statusCounts.in_progress)) + '</div><div class="stat-label">进行中</div></div>';
    html += '</div>';

    // Status breakdown
    var total = orderIds.length;
    if (total > 0) {
      html += '<div class="status-row">';
      html += '<div class="status-item"><span class="status-dot completed"></span> 已完成: ' + statusCounts.completed + '</div>';
      html += '<div class="status-item"><span class="status-dot failed"></span> 失败: ' + statusCounts.failed + '</div>';
      html += '<div class="status-item"><span class="status-dot in_progress"></span> 进行中: ' + statusCounts.in_progress + '</div>';
      html += '<div class="status-item" style="color:var(--text-muted)">总订单: ' + total + '</div>';
      html += '</div>';
    }

    // Quick links — nodes
    if (SIM_DATA.node_list && SIM_DATA.node_list.length > 0) {
      html += '<h2 class="section-title">节点</h2>';
      html += '<div class="quick-links">';
      for (var j = 0; j < SIM_DATA.node_list.length; j++) {
        var n = SIM_DATA.node_list[j];
        html += '<a class="quick-link" href="#/node/' + esc(n.id) + '">' + badgeSm(n.type, n.type) + ' ' + esc(n.display_name || n.id) + '</a>';
      }
      html += '</div>';
    }

    // Quick links — edges
    if (SIM_DATA.edge_list && SIM_DATA.edge_list.length > 0) {
      html += '<h2 class="section-title" style="margin-top:20px;">边</h2>';
      html += '<div class="quick-links">';
      for (var k = 0; k < SIM_DATA.edge_list.length; k++) {
        var e = SIM_DATA.edge_list[k];
        html += '<a class="quick-link" href="#/edge/' + esc(e.id) + '">' + badgeSm('边', 'edge') + ' ' + esc(e.display_name || e.id) + '</a>';
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
    if (!node) return renderNotFound('未找到节点 "' + esc(nodeId) + '"');

    setBreadcrumb([{ label: '节点: ' + (node.display_name || node.id), url: null }]);

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
    html += '<tr><td>类型</td><td>' + badge(node.type, node.type) + '</td></tr>';
    html += '<tr><td>任务</td><td>' + esc(String((node.jobs && node.jobs.length) || 0)) + '</td></tr>';
    html += '<tr><td>事件</td><td>' + esc(String((node.events && node.events.length) || 0)) + '</td></tr>';
    html += '</table>';

    // Chart: storage (warehouse) or production output (production)
    if (node.chart_storage) {
      var cid = _chartSafeId('c_s_', node.id);
      html += '<div class="chart-container"><h3>库存水位</h3><div class="chart-wrap"><canvas id="' + cid + '"></canvas></div></div>';
      _pendingCharts.push({ id: cid, type: 'storage', config: _storageChartConfig(node.chart_storage) });
    }
    if (node.chart_production) {
      var cid = _chartSafeId('c_p_', node.id);
      html += '<div class="chart-container"><h3>产出率</h3><div class="chart-wrap"><canvas id="' + cid + '"></canvas></div></div>';
      _pendingCharts.push({ id: cid, type: 'bar', config: _rateChartConfig(node.chart_production, '#22c55e', '件数') });
    }

    // Initial inventory
    if (node.init_inventory && Object.keys(node.init_inventory).length > 0) {
      html += '<h2 class="section-title">初始库存</h2>';
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
      html += '<h2 class="section-title">任务</h2>';
      for (var j = 0; j < node.jobs.length; j++) {
        var oid = node.jobs[j];
        var order = getOrder(oid);
        if (order) {
          html += renderJobCard(order);
        } else {
          html += '<div class="job-card"><div class="job-card-header">订单 #' + esc(String(oid)) + '（数据未找到）</div></div>';
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
        html += '<h2 class="section-title" style="margin-top:20px;">节点事件</h2>';
        html += renderEventList(otherEvents);
      }

      if (warnings.length > 0) {
        html += '<h2 class="section-title" style="margin-top:20px;">告警</h2>';
        for (var w = 0; w < warnings.length; w++) {
          var warn = warnings[w];
          html += '<div class="warning-item" data-time="' + esc(fmtTime(warn.time)) + '">';
          html += '<span class="warning-icon">⚠</span>';
          html += '<span><strong>[t=' + timeLink(warn.time) + ']</strong> ' + esc(warn.display || warn.reason || '容量告警');
          if (warn.raw && typeof warn.raw === 'object' && Object.keys(warn.raw).length > 0) {
      html += ' <button class="event-raw-toggle" onclick="window.SETA_toggleRaw(this)">原始</button>';
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
    if (!edge) return renderNotFound('未找到边 "' + esc(edgeId) + '"');

    setBreadcrumb([{ label: '边: ' + (edge.display_name || edge.id), url: null }]);

    var html = '';

    // Header
    html += '<div class="view-header">';
    html += badge('边', 'edge');
    html += '<h1>' + esc(edge.display_name || edge.id) + '</h1>';
    html += '<span class="view-subtitle">' + esc(edge.id) + '</span>';
    html += '</div>';

    // From → To
    html += '<table class="detail-table">';
    html += '<tr><td>ID</td><td>' + esc(edge.id) + '</td></tr>';
    html += '<tr><td>从</td><td><a href="#/node/' + esc(edge.from) + '">' + esc(edge.from_display || edge.from) + '</a></td></tr>';
    html += '<tr><td>到</td><td><a href="#/node/' + esc(edge.to) + '">' + esc(edge.to_display || edge.to) + '</a></td></tr>';
    html += '<tr><td>任务</td><td>' + esc(String((edge.jobs && edge.jobs.length) || 0)) + '</td></tr>';
    html += '<tr><td>事件</td><td>' + esc(String((edge.events && edge.events.length) || 0)) + '</td></tr>';
    html += '</table>';

    // Chart: edge traffic
    if (edge.chart_traffic) {
      var cid = _chartSafeId('c_e_', edge.id);
      html += '<div class="chart-container"><h3>运输原物料</h3><div class="chart-wrap"><canvas id="' + cid + '"></canvas></div></div>';
      _pendingCharts.push({ id: cid, type: 'bar', config: _rateChartConfig(edge.chart_traffic, '#a855f7', '件数') });
    }

    // Jobs on this edge
    if (edge.jobs && edge.jobs.length > 0) {
      html += '<h2 class="section-title">运输任务</h2>';
      for (var i = 0; i < edge.jobs.length; i++) {
        var order = getOrder(edge.jobs[i]);
        if (order) {
          html += renderJobCard(order);
        }
      }
    }

    // Edge events
    if (edge.events && edge.events.length > 0) {
      html += '<h2 class="section-title" style="margin-top:20px;">边事件</h2>';
      html += renderEventList(edge.events);
    }

    return html;
  }

  /* -------------------------------------------------------
     Order View
     ------------------------------------------------------- */
  function renderOrderView (orderId) {
    var order = getOrder(orderId);
    if (!order) return renderNotFound('未找到订单 #' + esc(orderId));

    setBreadcrumb([{ label: '订单 #' + order.order_id, url: null }]);

    var html = '';

    // Header
    html += '<div class="view-header">';
    html += badge(order.status, order.status);
    html += '<h1>订单 #' + esc(String(order.order_id)) + '</h1>';
    html += '<span class="view-subtitle">' + esc(order.sku || '') + ' ×' + esc(String(order.quantity)) + '</span>';
    html += '</div>';

    // Full detail table
    html += '<table class="detail-table">';
    html += '<tr><td>订单ID</td><td>' + esc(String(order.order_id)) + '</td></tr>';
    html += '<tr><td>SKU</td><td>' + esc(order.sku || '—') + '</td></tr>';
    html += '<tr><td>数量</td><td>' + esc(String(order.quantity)) + '</td></tr>';
    html += '<tr><td>类型</td><td>' + esc(order.order_type) + '</td></tr>';
    html += '<tr><td>状态</td><td>' + badge(order.status, order.status) + '</td></tr>';

    if (order.activate_time != null) html += '<tr><td>激活时间</td><td>' + timeLink(order.activate_time) + '</td></tr>';
    if (order.expect_time != null) html += '<tr><td>预计结束</td><td>' + timeLink(order.expect_time) + '</td></tr>';
    if (order.actual_start != null) html += '<tr><td>实际开始</td><td>' + timeLink(order.actual_start) + '</td></tr>';
    if (order.actual_end != null) html += '<tr><td>实际结束</td><td>' + timeLink(order.actual_end) + '</td></tr>';
    if (order.duration != null) html += '<tr><td>时长</td><td>' + esc(fmtTime(order.duration)) + '</td></tr>';

    if (order.from_node) {
      html += '<tr><td>从</td><td><a href="#/node/' + esc(order.from_node) + '">' + esc(order.from_node) + '</a></td></tr>';
    }
    if (order.to_node) {
      html += '<tr><td>到</td><td><a href="#/node/' + esc(order.to_node) + '">' + esc(order.to_node) + '</a></td></tr>';
    }
    if (order.node_name) {
      html += '<tr><td>生产节点</td><td><a href="#/node/' + esc(order.node_name) + '">' + esc(order.node_name) + '</a></td></tr>';
    }

    if (order.nodes_involved && order.nodes_involved.length > 0) {
      html += '<tr><td>涉及节点</td><td>';
      for (var ni = 0; ni < order.nodes_involved.length; ni++) {
        if (ni > 0) html += ', ';
        html += '<a href="#/node/' + esc(order.nodes_involved[ni]) + '">' + esc(order.nodes_involved[ni]) + '</a>';
      }
      html += '</td></tr>';
    }

    html += '</table>';

    // Event timeline
    if (order.events && order.events.length > 0) {
      html += '<h2 class="section-title">事件时间线</h2>';
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
      + '<h2>未找到</h2>'
      + '<p>' + esc(msg || '请求的页面不存在。') + '</p>'
      + '<p style="margin-top:12px"><a href="#/">返回仪表盘</a></p>'
      + '</div>';
  }

  /* -------------------------------------------------------
     Router
     ------------------------------------------------------- */
  function route () {
    var hash = window.location.hash.replace(/^#/, '') || '/';
    var parts = hash.split('/').filter(Boolean).map(function(p){return decodeURIComponent(p);});
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
      html = renderNotFound('未知路由: ' + esc(hash));
    }

    _destroyCharts();
    document.getElementById('viewContent').innerHTML = html;
    _flushCharts();

    // Update header stats
    var m = SIM_DATA.meta;
    if (m) {
      document.getElementById('headerStats').innerHTML =
        '<span>场景: <strong>' + esc(m.scenario) + '</strong></span>'
        + '<span>订单: <strong>' + esc(String(m.order_count)) + '</strong></span>'
        + '<span>事件: <strong>' + esc(String(m.event_count)) + '</strong></span>'
        + '<span>时长: <strong>' + esc(fmtTime(m.sim_duration)) + '</strong></span>';
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
          + badgeSm('边', 'edge')
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
      btnEl.textContent = isHidden ? '隐藏' : '原始';
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
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_fields(obj, visited=None):
    """Recursively remove keys from all dicts in a nested structure.

    This dramatically reduces the serialised data volume.
    We strip:
    - 'raw': carries a copy of the original event record.
    - 'display': now generated on-the-fly in the frontend JS.
    """
    if visited is None:
        visited = set()
    
    obj_id = id(obj)
    if obj_id in visited:
        return
    visited.add(obj_id)

    if isinstance(obj, dict):
        obj.pop("raw", None)
        obj.pop("display", None)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _strip_fields(v, visited)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                _strip_fields(v, visited)


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
    # Strip fields before serialisation.
    _strip_fields(data)

    scenario = data.get("meta", {}).get("scenario", "SETA 报告")
    scenario_safe = html.escape(str(scenario))

    # Embed Chart.js library
    chart_js_path = os.path.join(os.path.dirname(__file__), "chart.umd.min.js")
    chart_js = ""
    try:
        with open(chart_js_path, "r", encoding="utf-8") as f:
            chart_js = f.read()
    except FileNotFoundError:
        pass

    # Split template at the data placeholder and write in chunks to avoid
    # holding the full HTML string in memory (which was the primary OOM cause).
    template_head, template_tail = _TEMPLATE.split("{{SIM_DATA}}", 1)
    template_head = template_head.replace("{{SCENARIO}}", scenario_safe).replace("{{CHART_JS}}", chart_js)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(template_head)
        # Use json.dump instead of dumps to stream directly to file,
        # saving memory for very large reports.
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(template_tail)

    return output_path
