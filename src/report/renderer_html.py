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
    :root{{color-scheme:light;--bg:#f5f7fb;--card:#fff;--text:#17202a;--muted:#5f6b7a;--line:#d8e0ea;--ok:#18794e;--fail:#c73e1d;--running:#2563eb;--accent:#5b8def;}}
    *{{box-sizing:border-box;}}
    body{{font-family:system-ui,Segoe UI,Arial;background:var(--bg);color:var(--text);max-width:1180px;margin:0 auto;padding:24px 16px 40px;}}
    h1{{margin:0 0 8px;font-size:30px;}}
    .hero{{background:linear-gradient(135deg,#ffffff 0%,#eef4ff 100%);border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 2px rgba(15,23,42,.03);}}
    .hero-desc{{color:var(--muted);font-size:14px;line-height:1.6;max-width:900px;}}
    .chips{{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}}
    .chip{{display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;background:#edf3ff;color:#2f5fbf;font-size:12px;font-weight:600;}}
    .summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:16px 0 18px;}}
    .summary-card,.exec{{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 2px rgba(15,23,42,.03);}}
    .summary-card{{padding:14px 16px;}}
    .summary-label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;}}
    .summary-value{{margin-top:6px;font-size:18px;font-weight:700;}}
    .meta{{display:flex;flex-wrap:wrap;gap:10px 16px;color:var(--muted);margin-bottom:12px;}}
    .exec{{padding:16px 18px;margin:14px 0;}}
    .exec h2{{margin:0 0 8px;font-size:20px;}}
    .exec-header{{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;}}
    .exec-side{{text-align:right;color:var(--muted);font-size:12px;min-width:180px;}}
    .exec-desc{{font-size:13px;color:var(--muted);margin-bottom:10px;}}
    .exec-stats{{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 4px;}}
    .exec-stat{{padding:6px 10px;border-radius:10px;background:#f7f9fc;border:1px solid #e8edf5;font-size:12px;color:var(--muted);}}
    .task{{position:relative;border-top:1px dashed var(--line);padding:14px 0 14px 18px;display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,420px);gap:14px;align-items:start;}}
    .task:first-child{{border-top:none;}}
    .task::before{{content:'';position:absolute;left:2px;top:20px;bottom:0;width:2px;background:#e6ebf2;}}
    .task:first-child::before{{top:26px;}}
    .task-main{{min-width:0;}}
    .task-head{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}}
    .step-no{{font-size:12px;color:var(--muted);width:32px;display:inline-block;}}
    .task-title{{font-weight:700;}}
    .toggle{{margin-left:auto;border:none;background:#eef4ff;color:#2f5fbf;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700;cursor:pointer;}}
    .status{{display:inline-flex;align-items:center;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:700;}}
    .status-finished{{background:#e8f7ef;color:var(--ok);}}
    .status-failed{{background:#fff0ed;color:var(--fail);}}
    .status-running{{background:#eaf2ff;color:var(--running);}}
    .status-pending{{background:#eef2f7;color:#516072;}}
    .small{{font-size:13px;color:var(--muted);line-height:1.5;}}
    .task-body{{margin-top:8px;}}
    .task[data-collapsed="true"] .task-body{{display:none;}}
    .error{{margin-top:8px;padding:10px 12px;background:#fff0ed;color:var(--fail);border-radius:10px;border:1px solid #ffd8cf;}}
    .kv{{margin-top:8px;font-size:12px;color:var(--muted);word-break:break-word;}}
    .shot{{background:#fafcff;border:1px solid var(--line);border-radius:12px;padding:10px;}}
    .shot-btn{{display:block;width:100%;border:none;background:transparent;padding:0;cursor:zoom-in;}}
    .shot img{{max-width:100%;display:block;border-radius:10px;border:1px solid #e6ebf2;}}
    .caption{{font-size:12px;color:var(--muted);margin-top:8px;}}
    .mono{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;}}
    .empty{{padding:22px;border:1px dashed var(--line);border-radius:14px;color:var(--muted);background:#fff;}}
    .modal{{position:fixed;inset:0;background:rgba(9,16,29,.72);display:none;align-items:center;justify-content:center;padding:24px;z-index:9999;}}
    .modal.open{{display:flex;}}
    .modal-card{{max-width:min(1200px,96vw);max-height:92vh;background:#0f1720;border-radius:16px;padding:14px;box-shadow:0 20px 60px rgba(0,0,0,.35);}}
    .modal-card img{{max-width:100%;max-height:calc(92vh - 72px);display:block;border-radius:10px;}}
    .modal-bar{{display:flex;justify-content:space-between;align-items:center;color:#dce7f7;margin-bottom:10px;gap:12px;}}
    .modal-close{{border:none;background:#243247;color:#fff;border-radius:999px;padding:6px 12px;cursor:pointer;font-size:12px;font-weight:700;}}
    @media (max-width:900px){{.task{{grid-template-columns:1fr;}}}}
  </style>
</head>
<body>
  <div class="hero">
    <h1>{safe_title}</h1>
    <div id="hero-desc" class="hero-desc"></div>
    <div id="hero-chips" class="chips"></div>
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
    function formatTs(ts) {{
      if (!ts) return '-';
      try {{ return new Date(Number(ts) * 1000).toLocaleString(); }} catch (e) {{ return String(ts); }}
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
    function imgTag(src) {{
      if (!src) return '';
      return '<div class="shot"><button class="shot-btn" type="button" data-shot-src="' + esc(src) + '"><img src="' + src + '"/></button><div class="caption">' + esc(src) + '</div></div>';
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
    window.__pymidscene_render = function() {{
      const data = parseDumps();
      const root = document.getElementById('root');
      const summary = document.getElementById('summary');
      const heroDesc = document.getElementById('hero-desc');
      const heroChips = document.getElementById('hero-chips');
      const meta = data.meta || {{}};
      const executions = data.executions || [];
      const tasks = executions.flatMap(ex => Array.isArray(ex.tasks) ? ex.tasks : []);
      const finishedCount = tasks.filter(t => String((t && t.status) || '').toLowerCase() === 'finished').length;
      const failedCount = tasks.filter(t => String((t && t.status) || '').toLowerCase() === 'failed').length;
      const screenshotCount = countScreenshots(executions);
      heroDesc.textContent = meta.group_description || 'Execution report generated by PyMidscene.';
      const modelBriefs = Array.isArray(meta.model_briefs) ? meta.model_briefs : [];
      heroChips.innerHTML =
        '<span class="chip">sdk ' + esc(meta.sdk_version || '-') + '</span>' +
        '<span class="chip">device ' + esc(meta.device_type || '-') + '</span>' +
        modelBriefs.map(m => '<span class="chip">' + esc((m.type || 'model') + ': ' + (m.provider || '-') + '/' + (m.model || '-')) + '</span>').join('');
      summary.innerHTML =
        '<div class="summary">' +
        '<div class="summary-card"><div class="summary-label">Group</div><div class="summary-value">' + esc(meta.group_name || '-') + '</div></div>' +
        '<div class="summary-card"><div class="summary-label">Device</div><div class="summary-value">' + esc(meta.device_type || '-') + '</div></div>' +
        '<div class="summary-card"><div class="summary-label">Executions</div><div class="summary-value">' + executions.length + '</div></div>' +
        '<div class="summary-card"><div class="summary-label">Finished Steps</div><div class="summary-value">' + finishedCount + '</div></div>' +
        '<div class="summary-card"><div class="summary-label">Failed Steps</div><div class="summary-value">' + failedCount + '</div></div>' +
        '<div class="summary-card"><div class="summary-label">Screenshots</div><div class="summary-value">' + screenshotCount + '</div></div>' +
        '</div>';
      if (!executions.length) {{
        root.innerHTML = '<div class="empty">No execution data has been written to this report yet.</div>';
        return;
      }}
      let html = '<div class="meta"><div>sdk: ' + esc(meta.sdk_version || '-') + '</div><div>report_version: ' + esc(meta.report_version || '-') + '</div><div>models: ' + esc(modelBriefs.length) + '</div></div>';
      for (const ex of executions) {{
        const exTasks = Array.isArray(ex.tasks) ? ex.tasks : [];
        const exFinished = exTasks.filter(t => String((t && t.status) || '').toLowerCase() === 'finished').length;
        const exFailed = exTasks.filter(t => String((t && t.status) || '').toLowerCase() === 'failed').length;
        html += '<div class="exec">';
        html += '<div class="exec-header"><div><h2>' + esc(ex.name || 'Unnamed Execution') + '</h2>';
        if (ex.description) html += '<div class="exec-desc">' + esc(ex.description) + '</div>';
        html += '</div><div class="exec-side"><div>id: <span class="mono">' + esc(ex.id || '-') + '</span></div><div>time: ' + esc(formatTs(ex.log_time)) + '</div></div></div>';
        html += '<div class="exec-stats"><div class="exec-stat">steps: ' + exTasks.length + '</div><div class="exec-stat">finished: ' + exFinished + '</div><div class="exec-stat">failed: ' + exFailed + '</div></div>';
        const tasks = exTasks;
        for (let i = 0; i < tasks.length; i++) {{
          const t = tasks[i] || {{}};
          const screenshot = getTaskScreenshot(t);
          const screenshotPath = (screenshot && (screenshot.path || screenshot.data_url)) || '';
          const collapsed = String((t.status || '')).toLowerCase() === 'finished' ? 'true' : 'false';
          html += '<div class="task" data-collapsed="' + collapsed + '">';
          html += '<div class="task-main">';
          html += '<div class="task-head"><span class="step-no">#' + (i + 1) + '</span><span class="task-title">' + esc(t.sub_type || t.type || 'Step') + '</span><span class="status ' + statusClass(t.status) + '">' + esc(t.status || 'pending') + '</span><button class="toggle" type="button">' + (collapsed === 'true' ? 'Expand' : 'Collapse') + '</button></div>';
          html += '<div class="task-body">';
          if (t.log && t.log.message) html += '<div class="small">' + esc(t.log.message) + '</div>';
          if (t.param) html += '<div class="kv">param: ' + esc(JSON.stringify(t.param)) + '</div>';
          if (t.log && t.log.anomaly) html += '<div class="kv">anomaly: ' + esc(JSON.stringify(t.log.anomaly)) + '</div>';
          if (t.error_message || t.error) html += '<div class="error">' + esc(t.error_message || t.error) + '</div>';
          html += '</div></div>';
          html += '<div>' + (screenshotPath ? imgTag(screenshotPath) : '<div class="shot"><div class="caption">No screenshot</div></div>') + '</div>';
          html += '</div>';
        }}
        html += '</div>';
      }}
      root.innerHTML = html;
    }};
    window.__pymidscene_render();
    document.addEventListener('click', function(event) {{
      const toggle = event.target.closest('.toggle');
      if (toggle) {{
        const task = toggle.closest('.task');
        const next = task.getAttribute('data-collapsed') !== 'true';
        task.setAttribute('data-collapsed', String(next));
        toggle.textContent = next ? 'Expand' : 'Collapse';
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
