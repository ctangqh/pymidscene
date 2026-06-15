from __future__ import annotations

from typing import Any, Dict

from .utils import safe_script_json


REPORT_DUMP_MARKER = "<!-- PYMIDSCENE_REPORT_DUMPS -->"


def report_html_template(title: str) -> str:
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{safe_title}</title>
  <style>
    :root{{color-scheme:dark;--bg:#000;--panel:#05070b;--panel-soft:#0d1118;--panel-strong:#06080d;--text:#e6eaf2;--muted:#9da5b4;--muted-strong:#7f8797;--line:#303745;--line-soft:#212734;--line-strong:#d5d8de;--line-panel:#7d8188;--ok:#69d48f;--ok-bg:#143222;--fail:#ff8c8c;--fail-bg:#421b23;--running:#7ea7ff;--running-bg:#17294b;--pending:#a7b0c0;--pending-bg:#252c38;--accent:#66a4ff;--accent-soft:#1d2f4c;--shadow:none;--search-border:#6e7686;--search-bg:#eceff4;--search-text:#1b2230;--search-placeholder:#68758d;--filter-bg:#0d1016;--filter-bg-hover:#121621;--filter-text:#d9e0ef;--filter-border:#747c8c;--filter-active-bg:#151b26;--filter-active-border:#94bfff;--chip-border:#4ea1ff;--chip-bg:#f3f8ff;--chip-text:#2070d3;--summary-border:#3c4350;--summary-bg:#080b11;--panel-header-bg:#e5e8ed;--panel-header-bg-hover:#eceff3;--panel-header-text:#2b3240;--panel-meta:#5b6475;--recovery-title:#d8e1f8;--recovery-stage-bg:#1d3357;--recovery-stage-text:#8dc2ff;--shot-border:#37425b;--shot-bg:#0e121a;--surface-border:#2f3750;--surface-text:#d5ddf2;--modal-card-bg:#0f1720;--modal-bar-text:#dce7f7;--modal-close-bg:#243247;--modal-close-text:#fff;}}
    html[data-theme="light"]{{color-scheme:light;--bg:#f5f7fb;--panel:#fff;--panel-soft:#f4f7fc;--panel-strong:#fff;--text:#17202a;--muted:#5f6b7a;--muted-strong:#6d7786;--line:#d8e0ea;--line-soft:#e5ebf2;--line-strong:#cfd6e0;--line-panel:#c8d1de;--ok:#18794e;--ok-bg:#e8f7ef;--fail:#c73e1d;--fail-bg:#fff0ed;--running:#2563eb;--running-bg:#eaf2ff;--pending:#516072;--pending-bg:#eef2f7;--accent:#2f6fe4;--accent-soft:#dfeaff;--search-border:#c7d0dc;--search-bg:#fff;--search-text:#17202a;--search-placeholder:#7c8798;--filter-bg:#fff;--filter-bg-hover:#f5f8fc;--filter-text:#2f3b4b;--filter-border:#c7d0dc;--filter-active-bg:#edf3ff;--filter-active-border:#84b1ff;--chip-border:#69a7ff;--chip-bg:#edf5ff;--chip-text:#1660c7;--summary-border:#c7d0dc;--summary-bg:#fff;--panel-header-bg:#eef2f7;--panel-header-bg-hover:#e6ebf2;--panel-header-text:#2b3240;--panel-meta:#687386;--recovery-title:#324155;--recovery-stage-bg:#eef4ff;--recovery-stage-text:#2f5fbf;--shot-border:#d8e0ea;--shot-bg:#fff;--surface-border:#d8e0ea;--surface-text:#243247;--modal-card-bg:#fff;--modal-bar-text:#243247;--modal-close-bg:#dbe6f6;--modal-close-text:#1e2a3a;}}
    *{{box-sizing:border-box;}}
    body{{font-family:system-ui,Segoe UI,Arial;background:var(--bg);color:var(--text);max-width:980px;margin:0 auto;padding:18px 16px 44px;transition:background .16s ease,color .16s ease;}}
    button,input{{font:inherit;}}
    h1{{margin:0;font-size:22px;line-height:1.25;font-weight:600;letter-spacing:-.01em;}}
    .topbar{{display:flex;gap:14px;align-items:center;justify-content:space-between;margin-bottom:22px;flex-wrap:wrap;}}
    .search-wrap{{position:relative;flex:1 1 340px;max-width:340px;}}
    .search-wrap::before{{content:'';position:absolute;left:16px;top:50%;width:14px;height:14px;border:2px solid var(--search-placeholder);border-radius:50%;transform:translateY(-58%);}}
    .search-wrap::after{{content:'';position:absolute;left:28px;top:50%;width:7px;height:2px;background:var(--search-placeholder);transform:translateY(5px) rotate(45deg);transform-origin:left center;}}
    .search-input{{width:100%;border:1px solid var(--search-border);background:var(--search-bg);color:var(--search-text);border-radius:10px;padding:12px 16px 12px 40px;outline:none;box-shadow:none;}}
    .search-input::placeholder{{color:var(--search-placeholder);}}
    .toolbar-actions{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end;}}
    .theme-switch{{display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-size:12px;}}
    .theme-select{{border:1px solid var(--filter-border);background:var(--filter-bg);color:var(--filter-text);border-radius:6px;padding:8px 10px;min-height:38px;outline:none;}}
    .toolbar-filters{{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end;}}
    .filter-chip{{border:1px solid var(--filter-border);background:var(--filter-bg);color:var(--filter-text);border-radius:4px;padding:7px 10px;display:inline-flex;align-items:center;gap:8px;cursor:pointer;transition:.16s ease;min-height:38px;}}
    .filter-chip:hover{{border-color:var(--filter-active-border);background:var(--filter-bg-hover);}}
    .filter-chip.active{{border-color:var(--filter-active-border);background:var(--filter-active-bg);box-shadow:none;}}
    .filter-dot{{width:10px;height:10px;border-radius:50%;background:var(--pending);display:inline-block;}}
    .filter-dot.status-finished{{background:var(--ok);}}
    .filter-dot.status-failed{{background:var(--fail);}}
    .filter-dot.status-running{{background:var(--running);}}
    .filter-dot.status-pending{{background:var(--pending);}}
    .overview{{padding:0 0 12px;margin-bottom:6px;}}
    .overview-grid{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;align-items:start;}}
    .subtitle{{margin-top:6px;color:var(--muted);font-size:14px;line-height:1.5;max-width:900px;}}
    .crumb{{margin-top:4px;color:var(--muted-strong);font-size:12px;}}
    .chips{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}}
    .chip{{display:inline-flex;align-items:center;padding:4px 12px;border-radius:999px;border:1px solid var(--chip-border);background:var(--chip-bg);color:var(--chip-text);font-size:12px;font-weight:600;min-height:28px;}}
    .hero-stats{{display:grid;gap:10px;justify-items:end;align-self:center;}}
    .hero-stat{{text-align:right;min-width:72px;}}
    .hero-stat-label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}}
    .hero-stat-value{{margin-top:2px;font-size:15px;font-weight:600;}}
    .summary{{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 18px;}}
    .summary-card{{padding:4px 10px;border:1px solid var(--summary-border);border-radius:999px;background:var(--summary-bg);min-height:28px;display:inline-flex;align-items:center;gap:6px;}}
    .summary-label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}}
    .summary-value{{font-size:12px;font-weight:600;}}
    .summary-note{{display:none;}}
    .meta{{display:none;}}
    .execution-card{{padding:0;margin:0 0 22px;border-top:1px solid var(--line-strong);background:transparent;box-shadow:none;}}
    .execution-top{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:start;padding:14px 0 12px;}}
    .execution-title{{display:flex;align-items:flex-start;gap:12px;min-width:0;}}
    .execution-copy{{min-width:0;}}
    .execution-name{{font-size:20px;font-weight:600;line-height:1.25;letter-spacing:-.01em;word-break:break-word;}}
    .execution-desc{{margin-top:4px;color:var(--muted);font-size:13px;line-height:1.5;}}
    .execution-id{{margin-top:4px;color:var(--muted-strong);font-size:12px;}}
    .execution-meta{{display:flex;gap:20px;flex-wrap:wrap;justify-content:flex-end;color:var(--muted);font-size:12px;text-align:right;min-width:90px;}}
    .execution-pills{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;}}
    .execution-pill{{padding:0;border-radius:0;background:transparent;border:none;color:var(--muted);font-size:12px;}}
    .status{{display:inline-flex;align-items:center;gap:8px;border-radius:999px;padding:2px 0;font-size:12px;font-weight:600;text-transform:none;}}
    .status::before{{content:'';width:8px;height:8px;border-radius:50%;background:currentColor;display:inline-block;}}
    .status-finished{{background:transparent;color:var(--ok);}}
    .status-failed{{background:transparent;color:var(--fail);}}
    .status-running{{background:transparent;color:var(--running);}}
    .status-pending{{background:transparent;color:var(--pending);}}
    .panel{{overflow:hidden;border:1px solid var(--line-panel);border-radius:4px;background:var(--panel);}}
    .panel + .panel{{margin-top:12px;}}
    .panel-toggle{{width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px;border:none;background:var(--panel-header-bg);color:var(--panel-header-text);padding:12px 16px;font-weight:600;text-align:left;cursor:pointer;}}
    .panel-toggle:hover{{background:var(--panel-header-bg-hover);}}
    .panel-toggle-dark{{background:var(--panel-header-bg);color:var(--panel-header-text);border-top:none;}}
    .panel-toggle-dark:hover{{background:var(--panel-header-bg-hover);}}
    .toggle-left{{display:flex;align-items:center;gap:10px;min-width:0;}}
    .caret{{width:10px;height:10px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(-45deg);transition:transform .16s ease;flex:none;}}
    .panel[data-open="true"] > .panel-toggle .caret{{transform:rotate(45deg);}}
    .panel-meta{{color:var(--panel-meta);font-size:12px;font-weight:600;}}
    .panel-toggle-dark .panel-meta{{color:var(--panel-meta);}}
    .panel-body{{padding:0 0 8px;background:var(--bg);}}
    .steps-toolbar{{padding:14px 16px 0;}}
    .steps-search{{width:100%;border:1px solid #6e7686;background:#eceff4;color:#1b2230;border-radius:8px;padding:9px 14px;outline:none;}}
    .steps-search::placeholder{{color:#68758d;}}
    .step-list{{padding:10px 16px 8px;}}
    .step-row{{border-top:1px solid var(--line-soft);}}
    .step-row:first-child{{border-top:none;}}
    .step-summary{{display:grid;grid-template-columns:auto auto minmax(0,1fr) auto;gap:10px;align-items:center;padding:12px 2px;}}
    .step-toggle{{width:18px;height:18px;border:none;background:transparent;color:#a5afc5;cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center;}}
    .step-toggle .caret{{width:8px;height:8px;}}
    .step-row[data-collapsed="false"] .step-toggle .caret{{transform:rotate(45deg);}}
    .step-index{{color:var(--muted-strong);font-size:11px;width:24px;}}
    .step-copy{{min-width:0;}}
    .step-title{{font-size:14px;font-weight:600;line-height:1.45;word-break:break-word;}}
    .step-actions{{margin-top:2px;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
    .step-duration{{color:#97a4bf;font-size:12px;white-space:nowrap;}}
    .step-detail{{display:grid;grid-template-columns:minmax(0,1fr) minmax(240px,320px);gap:16px;padding:0 2px 16px 24px;}}
    .step-row[data-collapsed="true"] .step-detail{{display:none;}}
    .small{{font-size:13px;color:var(--muted);line-height:1.6;}}
    .detail-block{{margin-top:10px;}}
    .detail-label{{font-size:11px;color:var(--muted-strong);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;}}
    .error{{margin-top:10px;padding:10px 12px;background:var(--fail-bg);color:#ffd1d1;border-radius:4px;border:1px solid #66303a;}}
    .kv{{margin-top:8px;padding:10px 12px;background:var(--panel-soft);border:1px solid var(--surface-border);border-radius:4px;font-size:12px;color:var(--surface-text);word-break:break-word;line-height:1.6;}}
    .recovery{{margin-top:10px;padding:10px 12px;background:var(--panel-soft);border:1px solid var(--surface-border);border-radius:4px;}}
    .recovery-title{{font-size:12px;font-weight:700;color:var(--recovery-title);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;}}
    .recovery-item{{padding:8px 0;border-top:1px dashed var(--line);}}
    .recovery-item:first-child{{border-top:none;padding-top:0;}}
    .recovery-stage{{display:inline-flex;align-items:center;border-radius:999px;padding:2px 8px;background:var(--recovery-stage-bg);color:var(--recovery-stage-text);font-size:11px;font-weight:700;}}
    .recovery-meta{{margin-top:6px;font-size:12px;color:var(--muted);line-height:1.6;word-break:break-word;}}
    .shot{{background:var(--panel-soft);border:1px solid var(--surface-border);border-radius:4px;padding:10px;min-height:120px;}}
    .shot-btn{{display:block;width:100%;border:none;background:transparent;padding:0;cursor:zoom-in;}}
    .shot img{{max-width:100%;display:block;border-radius:10px;border:1px solid var(--shot-border);background:var(--shot-bg);}}
    .caption{{font-size:12px;color:var(--muted);margin-top:8px;line-height:1.5;word-break:break-word;}}
    .mono{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;}}
    .empty{{padding:18px;border:1px dashed var(--line);border-radius:4px;color:var(--muted);background:var(--panel-soft);}}
    .modal{{position:fixed;inset:0;background:rgba(9,16,29,.72);display:none;align-items:center;justify-content:center;padding:24px;z-index:9999;}}
    .modal.open{{display:flex;}}
    .modal-card{{max-width:min(1200px,96vw);max-height:92vh;background:var(--modal-card-bg);border-radius:16px;padding:14px;box-shadow:0 20px 60px rgba(0,0,0,.35);}}
    .modal-card img{{max-width:100%;max-height:calc(92vh - 72px);display:block;border-radius:10px;}}
    .modal-bar{{display:flex;justify-content:space-between;align-items:center;color:var(--modal-bar-text);margin-bottom:10px;gap:12px;}}
    .modal-close{{border:none;background:var(--modal-close-bg);color:var(--modal-close-text);border-radius:999px;padding:6px 12px;cursor:pointer;font-size:12px;font-weight:700;}}
    @media (max-width:980px){{.overview-grid{{grid-template-columns:1fr;}}.hero-stats{{grid-template-columns:repeat(3,minmax(0,1fr));justify-items:start;}}.execution-top{{grid-template-columns:1fr;}}.execution-meta{{justify-content:flex-start;text-align:left;}}.step-detail{{grid-template-columns:1fr;}}}}
    @media (max-width:720px){{h1{{font-size:18px;}}.step-summary{{grid-template-columns:auto auto minmax(0,1fr);}}.step-duration{{grid-column:3 / -1;padding-left:0;}}}}
  </style>
</head>
<body>
  <div class="topbar">
    <label class="search-wrap">
      <input id="report-search" class="search-input" type="search" placeholder="Search tests"/>
    </label>
    <div class="toolbar-actions">
      <label class="theme-switch" for="theme-select">Theme
        <select id="theme-select" class="theme-select">
          <option value="dark">Dark</option>
          <option value="light">Light</option>
        </select>
      </label>
      <div id="toolbar-filters" class="toolbar-filters"></div>
    </div>
  </div>
  <div class="overview">
    <div class="overview-grid">
      <div>
        <h1 id="report-title">{safe_title}</h1>
        <div id="hero-desc" class="subtitle"></div>
        <div id="hero-crumb" class="crumb mono"></div>
        <div id="hero-chips" class="chips"></div>
      </div>
      <div id="hero-stats" class="hero-stats"></div>
    </div>
  </div>
  <div id="summary"></div>
  <div id="root"></div>
  <div id="img-modal" class="modal">
    <div class="modal-card">
      <div class="modal-bar">
        <div id="img-modal-title" class="mono"></div>
        <button id="img-modal-close" class="modal-close" type="button">Close</button>
      </div>
      <img id="img-modal-image" alt="report screenshot preview"/>
    </div>
  </div>
  {REPORT_DUMP_MARKER}
  <script>
    function qsa(sel){{ return Array.from(document.querySelectorAll(sel)); }}
    function esc(v){{ return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }}
    const reportState = {{
      status: 'all',
      query: '',
      theme: 'dark',
      panelOpen: {{}},
      taskCollapsed: {{}},
      workerOpen: {{}},
    }};
    function applyTheme(theme) {{
      const normalized = theme === 'light' ? 'light' : 'dark';
      reportState.theme = normalized;
      document.documentElement.setAttribute('data-theme', normalized);
      const themeSelect = document.getElementById('theme-select');
      if (themeSelect && themeSelect.value !== normalized) themeSelect.value = normalized;
      try {{ window.localStorage.setItem('pymidscene-report-theme', normalized); }} catch (e) {{}}
    }}
    function initTheme() {{
      let preferred = 'dark';
      try {{
        const stored = window.localStorage.getItem('pymidscene-report-theme');
        if (stored === 'light' || stored === 'dark') preferred = stored;
      }} catch (e) {{}}
      applyTheme(preferred);
    }}
    function formatTs(ts) {{
      if (!ts) return '-';
      try {{ return new Date(Number(ts) * 1000).toLocaleString(); }} catch (e) {{ return String(ts); }}
    }}
    function formatDuration(seconds) {{
      const value = Number(seconds);
      if (!Number.isFinite(value) || value < 0) return '-';
      const ms = Math.round(value * 1000);
      if (ms < 1000) return ms + 'ms';
      if (ms < 60000) {{
        const whole = (ms / 1000).toFixed(ms % 1000 === 0 ? 0 : 1);
        return whole + 's';
      }}
      const minutes = Math.floor(ms / 60000);
      const secondsPart = ((ms % 60000) / 1000).toFixed(1).replace(/\\.0$/, '');
      return minutes + 'm ' + secondsPart + 's';
    }}
    function parseDumps() {{
      const dumps = qsa('script[type="pymidscene_dump"]');
      const executions = new Map();
      let meta = null;
      for (const s of dumps) {{
        try {{
          const d = JSON.parse(s.textContent || '{{}}');
          meta = d.meta || meta;
          const arr = d.executions || [];
          for (const e of arr) {{
            const id = (e && e.id) || ('no-id-' + Math.random());
            executions.set(id, e);
          }}
        }} catch (e) {{}}
      }}
      return {{ meta, executions: Array.from(executions.values()) }};
    }}
    function statusClass(status) {{
      const s = (status || '').toLowerCase();
      if (s === 'finished' || s === 'done' || s === 'success') return 'status-finished';
      if (s === 'failed' || s === 'error') return 'status-failed';
      if (s === 'running') return 'status-running';
      return 'status-pending';
    }}
    function normalizeStatus(status) {{
      const s = String(status || '').toLowerCase();
      if (s === 'done' || s === 'success') return 'finished';
      if (s === 'error') return 'failed';
      if (s === 'waiting') return 'pending';
      return s || 'pending';
    }}
    function imgTag(src) {{
      if (!src) return '';
      return '<div class="shot"><button class="shot-btn" type="button" data-shot-src="' + esc(src) + '"><img src="' + src + '"/></button><div class="caption">' + esc(src) + '</div></div>';
    }}
    function taskTitle(task) {{
      if (!task || typeof task !== 'object') return 'Step';
      if (typeof task.title === 'string' && task.title.trim()) return task.title.trim();
      if (task.param && typeof task.param === 'object') {{
        if (typeof task.param.prompt === 'string' && task.param.prompt.trim()) return task.param.prompt.trim();
        const locate = task.param.locate;
        if (locate && typeof locate === 'object') {{
          if (typeof locate.prompt === 'string' && locate.prompt.trim()) return locate.prompt.trim();
          if (typeof locate.description === 'string' && locate.description.trim()) return locate.description.trim();
        }}
      }}
      if (task.output && task.output.element && typeof task.output.element.description === 'string' && task.output.element.description.trim()) {{
        return task.output.element.description.trim();
      }}
      return task.sub_type || task.type || 'Step';
    }}
    function isTimelineHiddenTask(task) {{
      if (!task || typeof task !== 'object') return true;
      const type = String(task.type || '');
      const subType = String(task.sub_type || '');
      if (type === 'Planning' && subType === 'Plan') return true;
      if (type === 'Action Space' && subType === 'Finished') return true;
      return false;
    }}
    function aggregateStatus(tasks) {{
      const all = Array.isArray(tasks) ? tasks : [];
      const statuses = all.map(t => normalizeStatus(t && t.status));
      if (statuses.some(s => s === 'failed' || s === 'error')) return 'failed';
      if (statuses.some(s => s === 'running')) return 'running';
      if (statuses.some(s => s === 'pending')) return 'pending';
      return 'finished';
    }}
    function pickLeadTask(tasks) {{
      const all = Array.isArray(tasks) ? tasks : [];
      for (let i = all.length - 1; i >= 0; i--) {{
        const task = all[i];
        if (task && task.type !== 'Planning') return task;
      }}
      return all[all.length - 1] || null;
    }}
    function buildTimelineTasks(tasks) {{
      const all = Array.isArray(tasks) ? tasks : [];
      const timeline = [];
      let current = null;
      for (const task of all) {{
        if (isTimelineHiddenTask(task)) continue;
        const title = taskTitle(task);
        if (!current || current.title !== title) {{
          current = {{ title, tasks: [task] }};
          timeline.push(current);
        }} else {{
          current.tasks.push(task);
        }}
      }}
      return timeline.map(group => {{
        const leadTask = pickLeadTask(group.tasks) || group.tasks[group.tasks.length - 1] || {{}};
        return {{
          title: group.title,
          status: aggregateStatus(group.tasks),
          task: leadTask,
          tasks: group.tasks,
        }};
      }});
    }}
    function getTaskScreenshot(task) {{
      const ui = task && task.log && task.log.ui_context;
      const uiScreenshot = ui && ui.screenshot;
      if (uiScreenshot && (uiScreenshot.path || uiScreenshot.data_url)) return uiScreenshot;
      const recorder = Array.isArray(task && task.recorder) ? task.recorder : [];
      for (const item of recorder) {{
        const screenshot = item && item.screenshot;
        if (screenshot && (screenshot.path || screenshot.data_url)) return screenshot;
      }}
      return null;
    }}
    function countScreenshots(executions) {{
      let count = 0;
      for (const ex of executions) {{
        const tasks = Array.isArray(ex.tasks) ? ex.tasks : [];
        for (const t of tasks) {{
          const screenshot = getTaskScreenshot(t);
          if (screenshot && (screenshot.path || screenshot.data_url)) count += 1;
        }}
      }}
      return count;
    }}
    function executionDuration(execution) {{
      const tasks = Array.isArray(execution && execution.tasks) ? execution.tasks : [];
      let start = null;
      let end = null;
      let fallback = 0;
      for (const task of tasks) {{
        const timing = task && task.timing;
        const cost = Number(timing && timing.cost);
        if (Number.isFinite(cost) && cost > 0) fallback += cost;
        const currentStart = Number(timing && timing.start);
        const currentEnd = Number(timing && timing.end);
        if (Number.isFinite(currentStart)) start = start == null ? currentStart : Math.min(start, currentStart);
        if (Number.isFinite(currentEnd)) end = end == null ? currentEnd : Math.max(end, currentEnd);
      }}
      if (start != null && end != null && end >= start) return end - start;
      return fallback;
    }}
    function matchesQuery(text, query) {{
      if (!query) return true;
      return String(text || '').toLowerCase().includes(query);
    }}
    function taskSearchBlob(taskGroup) {{
      const task = taskGroup && taskGroup.task || {{}};
      const parts = [
        taskGroup && taskGroup.title,
        task && task.title,
        task && task.sub_type,
        task && task.type,
        task && task.log && task.log.message,
        task && task.error_message,
        task && task.error,
      ];
      return parts.filter(Boolean).join(' ').toLowerCase();
    }}
    function enrichExecutions(executions) {{
      return executions.map(execution => {{
        const timelineTasks = buildTimelineTasks(Array.isArray(execution && execution.tasks) ? execution.tasks : []);
        const status = aggregateStatus(timelineTasks.map(item => item && item.task));
        const duration = executionDuration(execution);
        return {{
          execution,
          timelineTasks,
          status,
          duration,
        }};
      }});
    }}
    function filterExecutions(executionEntries) {{
      const status = reportState.status;
      const query = String(reportState.query || '').trim().toLowerCase();
      const visible = [];
      for (const entry of executionEntries) {{
        const execution = entry.execution || {{}};
        const executionBlob = [execution.name, execution.description, execution.id].filter(Boolean).join(' ').toLowerCase();
        const filteredSteps = entry.timelineTasks.filter(taskGroup => {{
          if (!matchesQuery(taskSearchBlob(taskGroup), query) && !matchesQuery(executionBlob, query)) return false;
          if (status !== 'all' && normalizeStatus(taskGroup && taskGroup.status) !== status) return false;
          return true;
        }});
        const executionMatches = !query || matchesQuery(executionBlob, query);
        const visibleBecauseExecution = executionMatches;
        const keepForQuery = filteredSteps.length > 0 || visibleBecauseExecution;
        if (!keepForQuery) continue;
        visible.push({{
          execution: execution,
          timelineTasks: filteredSteps,
          allTimelineTasks: entry.timelineTasks,
          status: entry.status,
          duration: entry.duration,
        }});
      }}
      return visible;
    }}
    function countByStatus(entries) {{
      const counts = {{ all: 0, finished: 0, failed: 0, running: 0, pending: 0 }};
      for (const entry of entries) {{
        for (const taskGroup of entry.timelineTasks) {{
          counts.all += 1;
          const key = normalizeStatus(taskGroup && taskGroup.status);
          if (counts.hasOwnProperty(key)) counts[key] += 1;
        }}
      }}
      return counts;
    }}
    function countStepStatus(entries) {{
      const counts = {{ finished: 0, failed: 0, running: 0, pending: 0 }};
      for (const entry of entries) {{
        for (const taskGroup of entry.timelineTasks) {{
          const key = normalizeStatus(taskGroup && taskGroup.status);
          if (counts.hasOwnProperty(key)) counts[key] += 1;
        }}
      }}
      return counts;
    }}
    function taskCollapseKey(executionId, index) {{
      return executionId + ':' + index;
    }}
    function taskCollapsed(executionId, index, status) {{
      const key = taskCollapseKey(executionId, index);
      if (Object.prototype.hasOwnProperty.call(reportState.taskCollapsed, key)) return reportState.taskCollapsed[key];
      return normalizeStatus(status) === 'finished';
    }}
    function panelOpen(map, key, defaultValue) {{
      if (Object.prototype.hasOwnProperty.call(map, key)) return map[key];
      return defaultValue;
    }}
    function renderToolbarFilters(counts) {{
      const items = [
        ['all', 'All', counts.all],
        ['finished', 'Passed', counts.finished],
        ['failed', 'Failed', counts.failed],
        ['running', 'Running', counts.running],
        ['pending', 'Pending', counts.pending],
      ];
      return items.map(item => {{
        const key = item[0];
        const label = item[1];
        const count = item[2];
        const dotClass = key === 'all' ? '' : ' ' + statusClass(key);
        const active = reportState.status === key ? ' active' : '';
        return '<button class="filter-chip' + active + '" type="button" data-filter-status="' + key + '"><span class="filter-dot' + dotClass + '"></span><span>' + esc(label) + ' ' + count + '</span></button>';
      }}).join('');
    }}
    function renderActionRecovery(task) {{
      const recovery = Array.isArray(task && task.log && task.log.action_recovery) ? task.log.action_recovery : [];
      if (!recovery.length) return '';
      let html = '<div class="recovery"><div class="recovery-title">Action Recovery</div>';
      for (const item of recovery) {{
        const selectorRef = item && item.selector_ref ? JSON.stringify(item.selector_ref) : '';
        const position = item && item.position ? JSON.stringify(item.position) : '';
        html += '<div class="recovery-item">';
        html += '<div><span class="recovery-stage">' + esc(item && item.stage || 'unknown') + '</span></div>';
        html += '<div class="recovery-meta">';
        if (item && item.action_type) html += 'action: ' + esc(item.action_type) + '<br/>';
        if (selectorRef) html += 'selector_ref: ' + esc(selectorRef) + '<br/>';
        if (position) html += 'position: ' + esc(position) + '<br/>';
        if (item && item.error) html += 'error: ' + esc(item.error);
        html += '</div></div>';
      }}
      html += '</div>';
      return html;
    }}
    function renderSummary(meta, executionEntries) {{
      return '';
    }}
    function resolveCaseName(meta, executionEntries) {{
      const groupName = String(meta && meta.group_name || '').trim();
      if (groupName && groupName.toLowerCase() !== 'midscene report') return groupName;
      const heading = document.getElementById('report-title');
      const headingText = heading ? String(heading.textContent || '').trim() : '';
      if (headingText) return headingText;
      const firstExecution = executionEntries[0] && executionEntries[0].execution;
      if (firstExecution && firstExecution.name) return String(firstExecution.name);
      return 'Test Case';
    }}
    function aggregateEntryStatus(entries) {{
      const statuses = [];
      for (const entry of entries) {{
        for (const taskGroup of entry.timelineTasks) statuses.push(normalizeStatus(taskGroup && taskGroup.status));
      }}
      if (statuses.some(s => s === 'failed')) return 'failed';
      if (statuses.some(s => s === 'running')) return 'running';
      if (statuses.some(s => s === 'pending')) return 'pending';
      return 'finished';
    }}
    function flattenVisibleSteps(entries) {{
      const steps = [];
      for (const entry of entries) {{
        const ex = entry.execution || {{}};
        for (const item of entry.timelineTasks) {{
          steps.push({{
            execution: ex,
            item: item,
          }});
        }}
      }}
      return steps;
    }}
    function renderExecution(meta, visibleEntries, allEntries) {{
      const caseName = resolveCaseName(meta, allEntries);
      const steps = flattenVisibleSteps(visibleEntries);
      const totalSteps = allEntries.reduce((sum, entry) => sum + ((entry.allTimelineTasks || entry.timelineTasks || []).length), 0);
      const visibleSteps = steps.length;
      const failedSteps = allEntries.reduce((sum, entry) => sum + (entry.allTimelineTasks || entry.timelineTasks || []).filter(item => normalizeStatus(item && item.status) === 'failed').length, 0);
      const totalDuration = allEntries.reduce((sum, entry) => sum + (Number(entry.duration) || 0), 0);
      const caseStatus = aggregateEntryStatus(visibleEntries.length ? visibleEntries : allEntries);
      const caseKey = 'case-root';
      const open = panelOpen(reportState.panelOpen, caseKey, true);
      const workerOpen = panelOpen(reportState.workerOpen, caseKey, false);
      let html = '<div class="execution-card">';
      html += '<div class="execution-top">';
      html += '<div class="execution-title"><div class="execution-copy"><div class="execution-name">' + esc(caseName) + '</div>';
      if (meta && meta.group_description) html += '<div class="execution-desc">' + esc(meta.group_description) + '</div>';
      html += '<div class="execution-id mono">' + esc(meta && meta.device_type || '-') + '</div>';
      html += '<div class="execution-pills"><span class="execution-pill">steps ' + totalSteps + '</span><span class="execution-pill">failed ' + failedSteps + '</span><span class="execution-pill">runs ' + allEntries.length + '</span></div>';
      html += '<div class="status ' + statusClass(caseStatus) + '">' + esc(normalizeStatus(caseStatus)) + '</div>';
      html += '</div></div>';
      html += '<div class="execution-meta"><div><div>' + esc(formatDuration(totalDuration)) + '</div></div></div>';
      html += '</div>';
      html += '<div class="panel" data-open="' + String(open) + '">';
      html += '<button class="panel-toggle" type="button" data-panel-toggle="' + esc(caseKey) + '"><span class="toggle-left"><span class="caret"></span><span>Test Steps</span></span><span class="panel-meta">' + visibleSteps + ' / ' + totalSteps + ' visible</span></button>';
      if (open) {{
        html += '<div class="panel-body">';
        if (!steps.length) {{
          html += '<div class="step-list"><div class="empty">No step matches the current filters.</div></div>';
        }} else {{
          html += '<div class="step-list">';
          for (let i = 0; i < steps.length; i++) {{
            const current = steps[i] || {{}};
            const item = current.item || {{}};
            const t = item.task || {{}};
            const screenshot = getTaskScreenshot(t);
            const screenshotPath = (screenshot && (screenshot.path || screenshot.data_url)) || '';
            const collapsed = taskCollapsed(caseKey, i, item.status);
            const actions = Array.isArray(item.tasks) && item.tasks.length
              ? item.tasks.map(task => task && task.sub_type ? task.sub_type : (task && task.type ? task.type : 'Step')).join(' -> ')
              : '';
            html += '<div class="step-row" data-collapsed="' + String(collapsed) + '">';
            html += '<div class="step-summary">';
            html += '<button class="step-toggle" type="button" data-task-toggle="' + esc(taskCollapseKey(caseKey, i)) + '"><span class="caret"></span></button>';
            html += '<div class="step-index">#' + (i + 1) + '</div>';
            html += '<div class="step-copy"><div class="step-title">' + esc(item.title || taskTitle(t)) + '</div>';
            if (actions) html += '<div class="step-actions">' + esc(actions) + '</div>';
            if (current.execution && current.execution.name) html += '<div class="step-actions">from ' + esc(current.execution.name) + '</div>';
            html += '</div>';
            html += '<div class="step-duration"><span class="status ' + statusClass(item.status) + '">' + esc(normalizeStatus(item.status)) + '</span> ' + esc(formatDuration(t && t.timing && t.timing.cost)) + '</div>';
            html += '</div>';
            html += '<div class="step-detail"><div>';
            if (t.log && t.log.message) html += '<div class="small">' + esc(t.log.message) + '</div>';
            if (t.param) html += '<div class="detail-block"><div class="detail-label">Parameters</div><div class="kv">' + esc(JSON.stringify(t.param)) + '</div></div>';
            if (t.log && t.log.anomaly) html += '<div class="detail-block"><div class="detail-label">Anomaly</div><div class="kv">' + esc(JSON.stringify(t.log.anomaly)) + '</div></div>';
            html += renderActionRecovery(t);
            if (t.error_message || t.error) html += '<div class="error">' + esc(t.error_message || t.error) + '</div>';
            html += '</div>';
            html += '<div>' + (screenshotPath ? imgTag(screenshotPath) : '<div class="shot"><div class="caption">No screenshot</div></div>') + '</div>';
            html += '</div></div>';
          }}
          html += '</div>';
        }}
        html += '</div>';
      }}
      html += '</div>';
      html += '<div class="panel panel-toggle-dark" data-open="' + String(workerOpen) + '">';
      html += '<button class="panel-toggle panel-toggle-dark" type="button" data-worker-toggle="' + esc(caseKey) + '"><span class="toggle-left"><span class="caret"></span><span>Executed in Worker #0</span></span><span class="panel-meta">' + esc(caseStatus) + '</span></button>';
      if (workerOpen) {{
        const firstExecution = allEntries[0] && allEntries[0].execution || {{}};
        html += '<div class="panel-body"><div class="step-list"><div class="small">Case: <span class="mono">' + esc(caseName) + '</span><br/>Started: ' + esc(formatTs(firstExecution.log_time)) + '<br/>Duration: ' + esc(formatDuration(totalDuration)) + '</div></div></div>';
      }}
      html += '</div>';
      html += '</div>';
      return html;
    }}
    window.__pymidscene_render = function() {{
      const data = parseDumps();
      const root = document.getElementById('root');
      const summary = document.getElementById('summary');
      const heroDesc = document.getElementById('hero-desc');
      const heroChips = document.getElementById('hero-chips');
      const heroCrumb = document.getElementById('hero-crumb');
      const heroStats = document.getElementById('hero-stats');
      const toolbarFilters = document.getElementById('toolbar-filters');
      const meta = data.meta || {{}};
      const executionEntries = enrichExecutions(data.executions || []);
      const visibleExecutions = filterExecutions(executionEntries);
      const counts = countByStatus(executionEntries);
      const screenshotCount = countScreenshots((data.executions || []));
      const totalDuration = executionEntries.reduce((sum, item) => sum + (Number(item.duration) || 0), 0);
      heroDesc.textContent = meta.group_description || 'Execution report generated by PyMidscene.';
      heroCrumb.textContent = [meta.group_name || 'PyMidscene Report', meta.device_type || 'unknown-device', meta.report_version ? ('report v' + meta.report_version) : 'report'].join(' / ');
      const modelBriefs = Array.isArray(meta.model_briefs) ? meta.model_briefs : [];
      heroChips.innerHTML =
        '<span class="chip">' + esc(meta.device_type || 'device') + '</span>' +
        modelBriefs.slice(0, 1).map(m => '<span class="chip">' + esc((m.provider || '-') + '/' + (m.model || '-')) + '</span>').join('');
      toolbarFilters.innerHTML = renderToolbarFilters(counts);
      heroStats.innerHTML =
        '<div class="hero-stat"><div class="hero-stat-label">Duration</div><div class="hero-stat-value">' + esc(formatDuration(totalDuration)) + '</div></div>';
      summary.innerHTML = renderSummary(meta, visibleExecutions);
      if (!executionEntries.length) {{
        root.innerHTML = '<div class="empty">No execution data has been written to this report yet.</div>';
        return;
      }}
      if (!visibleExecutions.length) {{
        root.innerHTML = '<div class="meta"><div>sdk: ' + esc(meta.sdk_version || '-') + '</div><div>report_version: ' + esc(meta.report_version || '-') + '</div><div>models: ' + esc(modelBriefs.length) + '</div></div><div class="empty">No execution matches the current search or filter.</div>';
        return;
      }}
      let html = '<div class="meta"><div>sdk: ' + esc(meta.sdk_version || '-') + '</div><div>report_version: ' + esc(meta.report_version || '-') + '</div><div>models: ' + esc(modelBriefs.length) + '</div><div>visible_steps: ' + counts.all + '</div></div>';
      html += renderExecution(meta, visibleExecutions, executionEntries);
      root.innerHTML = html;
    }};
    initTheme();
    window.__pymidscene_render();
    document.getElementById('report-search').addEventListener('input', function(event) {{
      reportState.query = String(event.target.value || '');
      window.__pymidscene_render();
    }});
    document.getElementById('theme-select').addEventListener('change', function(event) {{
      applyTheme(String(event.target.value || 'dark'));
    }});
    document.addEventListener('click', function(event) {{
      const filterToggle = event.target.closest('[data-filter-status]');
      if (filterToggle) {{
        reportState.status = filterToggle.getAttribute('data-filter-status') || 'all';
        window.__pymidscene_render();
        return;
      }}
      const panelToggle = event.target.closest('[data-panel-toggle]');
      if (panelToggle) {{
        const key = panelToggle.getAttribute('data-panel-toggle') || '';
        reportState.panelOpen[key] = !panelOpen(reportState.panelOpen, key, true);
        window.__pymidscene_render();
        return;
      }}
      const workerToggle = event.target.closest('[data-worker-toggle]');
      if (workerToggle) {{
        const key = workerToggle.getAttribute('data-worker-toggle') || '';
        reportState.workerOpen[key] = !panelOpen(reportState.workerOpen, key, false);
        window.__pymidscene_render();
        return;
      }}
      const taskToggle = event.target.closest('[data-task-toggle]');
      if (taskToggle) {{
        const key = taskToggle.getAttribute('data-task-toggle') || '';
        const row = taskToggle.closest('.step-row');
        const current = row ? row.getAttribute('data-collapsed') === 'true' : !!reportState.taskCollapsed[key];
        reportState.taskCollapsed[key] = !current;
        window.__pymidscene_render();
        return;
      }}
      const shotBtn = event.target.closest('.shot-btn');
      if (shotBtn) {{
        const src = shotBtn.getAttribute('data-shot-src') || '';
        const modal = document.getElementById('img-modal');
        document.getElementById('img-modal-image').src = src;
        document.getElementById('img-modal-title').textContent = src;
        modal.classList.add('open');
        return;
      }}
      if (event.target.id === 'img-modal' || event.target.id === 'img-modal-close') {{
        document.getElementById('img-modal').classList.remove('open');
      }}
    }});
    document.addEventListener('keydown', function(event) {{
      if (event.key === 'Escape') {{
        document.getElementById('img-modal').classList.remove('open');
      }}
    }});
  </script>
</body>
</html>"""


def dump_script_tag(dump: Dict[str, Any]) -> str:
    return f"\n<script type=\"pymidscene_dump\">{safe_script_json(dump)}</script>\n"


def insert_dump_into_html(html: str, dump: Dict[str, Any]) -> str:
    return html.replace(REPORT_DUMP_MARKER, dump_script_tag(dump) + REPORT_DUMP_MARKER)
