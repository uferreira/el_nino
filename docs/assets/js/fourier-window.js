/* =====================================================================
 * assets/js/fourier-window.js
 * ---------------------------------------------------------------------
 * The date selector that drives the Fourier analysis window on every
 * data page, plus the per-plot range captions.
 *
 * The maths lives in assets/js/fourier-filter.js (EnsoFourier); this file
 * is only the user interface around it:
 *
 *   EnsoFourierWindow.request()      read the requested window
 *                                    (?from=YYYY-MM&to=YYYY-MM, else the
 *                                    defaults resolved by EnsoFourier)
 *   EnsoFourierWindow.mount(...)     render the control panel and the
 *                                    per-plot captions
 *
 * Applying a new window reloads the page with the new query string. Every
 * derived quantity on these pages (means, accelerations, axis domains,
 * animation timelines) is computed at load time from the filtered arrays,
 * so a reload is the only way to guarantee that all of them are rebuilt
 * from the new window rather than half-refreshed.
 * ===================================================================== */

var EnsoFourierWindow = (function () {
  'use strict';

  var MONTHS = EnsoFourier.MONTH_ABBR;
  var STORAGE_KEY = 'enso.fourier.window';

  /** The window the user has asked for: URL first, then last session's choice. */
  function request() {
    var q = new URLSearchParams(window.location.search);
    var from = q.get('from'), to = q.get('to');
    if (!from && !to) {
      try {
        var saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
        if (saved) { from = saved.start; to = saved.end; }
      } catch (e) { /* private mode / disabled storage — defaults are fine */ }
    }
    return { start: from || null, end: to || null };
  }

  function remember(req) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(req)); } catch (e) { /* ignore */ }
  }

  /** Widest span across all raw records, used to populate the year lists. */
  function recordExtent(rawSeries) {
    var first = Infinity, last = -Infinity;
    Object.keys(rawSeries).forEach(function (k) {
      var r = rawSeries[k], n = r.year.length;
      if (!n) return;
      first = Math.min(first, EnsoFourier.ym(r.year[0], r.month[0]));
      last = Math.max(last, EnsoFourier.ym(r.year[n - 1], r.month[n - 1]));
    });
    return { firstYM: first, lastYM: last };
  }

  function select(id, values, labels, selected) {
    var html = '<select id="' + id + '">';
    for (var i = 0; i < values.length; i++) {
      html += '<option value="' + values[i] + '"'
        + (String(values[i]) === String(selected) ? ' selected' : '') + '>'
        + labels[i] + '</option>';
    }
    return html + '</select>';
  }

  function monthValues() { return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]; }

  function yearValues(extent) {
    var out = [];
    for (var y = Math.floor((extent.firstYM - 1) / 12); y <= Math.floor((extent.lastYM - 1) / 12); y++) out.push(y);
    return out;
  }

  var CSS = [
    '.fw-panel{background:var(--card,#1a1a28);border:1px solid var(--border,#2a2a40);',
    'border-radius:8px;padding:1rem 1.2rem;margin:0 0 1.4rem;}',
    '.fw-head{font-size:.8rem;font-weight:600;text-transform:uppercase;letter-spacing:.07em;',
    'color:var(--muted,#888899);margin-bottom:.7rem;}',
    '.fw-row{display:flex;flex-wrap:wrap;gap:.6rem 1.1rem;align-items:center;}',
    '.fw-row label{font-size:.82rem;color:var(--muted,#888899);display:flex;align-items:center;gap:.35rem;}',
    '.fw-row select{background:var(--surface,#12121a);border:1px solid var(--border,#2a2a40);',
    'border-radius:4px;color:var(--text,#e8e8f0);font-size:.82rem;padding:.25rem .35rem;}',
    '.fw-row button{background:var(--accent,#4488ff);border:none;border-radius:4px;color:#fff;',
    'font-size:.82rem;font-weight:600;padding:.35rem .9rem;cursor:pointer;}',
    '.fw-row button.fw-secondary{background:transparent;border:1px solid var(--border,#2a2a40);',
    'color:var(--muted,#888899);}',
    '.fw-summary{margin-top:.7rem;font-size:.82rem;color:var(--text,#e8e8f0);}',
    '.fw-summary strong{color:var(--accent,#4488ff);font-family:monospace;}',
    '.fw-note{margin-top:.45rem;font-size:.76rem;color:#e0a030;line-height:1.45;}',
    '.fw-err{margin-top:.45rem;font-size:.76rem;color:#ff7766;}',
    '.fw-table{margin-top:.6rem;font-size:.75rem;color:var(--muted,#888899);',
    'display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:.15rem .9rem;}',
    '.fw-table span b{color:var(--text,#e8e8f0);font-weight:600;}',
    '.fw-caption{font-size:.72rem;color:var(--muted,#888899);text-align:center;',
    'padding:.3rem .2rem 0;font-family:monospace;}'
  ].join('');

  /**
   * Render the control panel into #fourier-window and caption every plot.
   *
   * opts.rawSeries  the RAW_SERIES object embedded in the page
   * opts.params     { HN1, HN2, NDOTS, baseYear }
   * opts.results    the output of EnsoFourier.runAll for the active window
   * opts.plotSeries optional map of element id -> dataset name, used to
   *                 caption a specific plot with that dataset's own range
   */
  function mount(opts) {
    var host = document.getElementById('fourier-window');
    var raw = opts.rawSeries, results = opts.results;
    var req = request();

    if (!document.getElementById('fw-style')) {
      var st = document.createElement('style');
      st.id = 'fw-style';
      st.textContent = CSS;
      document.head.appendChild(st);
    }

    // Headline range: the SST record if present, else the first dataset.
    var names = Object.keys(raw);
    var headName = names.indexOf('observedData') >= 0 ? 'observedData' : names[0];
    var head = results[headName];
    var extent = recordExtent(raw);

    var startYM = head && head.window ? head.window.startYM
      : EnsoFourier.parseMonth(req.start) || extent.firstYM;
    var endYM = head && head.window ? head.window.endYM
      : EnsoFourier.parseMonth(req.end) || extent.lastYM;
    // When the user asked for a wider window than SST covers, the controls
    // must show what was ASKED, not the SST clipping.
    if (req.start) startYM = EnsoFourier.parseMonth(req.start);
    if (req.end) endYM = EnsoFourier.parseMonth(req.end);

    if (host) {
      var years = yearValues(extent), yl = years.map(String);
      var mv = monthValues(), ml = MONTHS;
      host.innerHTML =
        '<div class="fw-panel">'
        + '<div class="fw-head">Fourier analysis window</div>'
        + '<div class="fw-row">'
        + '<label>From '
        + select('fw-mo-start', mv, ml, (startYM - 1) % 12 + 1)
        + select('fw-yr-start', years, yl, Math.floor((startYM - 1) / 12))
        + '</label>'
        + '<label>To '
        + select('fw-mo-end', mv, ml, (endYM - 1) % 12 + 1)
        + select('fw-yr-end', years, yl, Math.floor((endYM - 1) / 12))
        + '</label>'
        + '<button id="fw-apply">Recalculate</button>'
        + '<button id="fw-reset" class="fw-secondary">Reset to default</button>'
        + '</div>'
        + '<div class="fw-summary" id="fw-summary"></div>'
        + '<div class="fw-table" id="fw-table"></div>'
        + '<div class="fw-note" id="fw-note" hidden></div>'
        + '<div class="fw-err" id="fw-err" hidden></div>'
        + '</div>';

      var summary = document.getElementById('fw-summary');
      if (head && head.window) {
        summary.innerHTML = 'The low-pass filter, the interpolation and the derivatives are '
          + 'recomputed in your browser over <strong>' + head.window.rangeLabel + '</strong> ('
          + head.window.nMonths + ' months). Each series is clipped to its own record.';
      } else {
        summary.textContent = 'No dataset covers the requested window.';
      }

      var table = document.getElementById('fw-table');
      table.innerHTML = names.map(function (n) {
        var r = results[n];
        return '<span><b>' + (r.label || n) + ':</b> ' + r.rangeLabel
          + (r.nMonths ? ' (' + r.nMonths + ' mo)' : '') + '</span>';
      }).join('');

      // Warnings: endpoint phase, clipping, and datasets that dropped out.
      var notes = [];
      names.forEach(function (n) {
        var r = results[n];
        if (r.window && r.window.notes.length) {
          r.window.notes.forEach(function (t) { notes.push((r.label || n) + ': ' + t); });
        }
      });
      var noteEl = document.getElementById('fw-note');
      if (notes.length) {
        noteEl.hidden = false;
        noteEl.innerHTML = notes.map(function (t) { return '⚠ ' + t; }).join('<br>');
      }
      var failures = results.__failures || {};
      var failNames = Object.keys(failures);
      if (failNames.length) {
        var errEl = document.getElementById('fw-err');
        errEl.hidden = false;
        errEl.innerHTML = failNames.map(function (n) {
          return '✕ ' + ((raw[n] && raw[n].label) || n) + ': ' + failures[n];
        }).join('<br>');
      }

      document.getElementById('fw-apply').addEventListener('click', function () {
        var s = document.getElementById('fw-yr-start').value + '-'
          + String(document.getElementById('fw-mo-start').value).padStart(2, '0');
        var e = document.getElementById('fw-yr-end').value + '-'
          + String(document.getElementById('fw-mo-end').value).padStart(2, '0');
        if (EnsoFourier.parseMonth(e) - EnsoFourier.parseMonth(s) < 11) {
          window.alert('The Fourier window must span at least 12 months — the '
            + 'monthly climatology needs every calendar month.');
          return;
        }
        remember({ start: s, end: e });
        var q = new URLSearchParams(window.location.search);
        q.set('from', s); q.set('to', e);
        window.location.search = q.toString();
      });

      document.getElementById('fw-reset').addEventListener('click', function () {
        try { sessionStorage.removeItem(STORAGE_KEY); } catch (err) { /* ignore */ }
        var q = new URLSearchParams(window.location.search);
        q.delete('from'); q.delete('to');
        window.location.search = q.toString();
      });
    }

    captionPlots(opts);
  }

  /**
   * Write the analysed period under every plot.
   *
   * Two passes. First every plot named in opts.plotSeries gets that series'
   * own clipped range, which is what makes each panel state the period it
   * actually shows. Then any remaining plot container gets the page-wide
   * window, so no plot is left without a period.
   *
   * Plot containers differ across these pages — some canvases sit in a bare
   * <div>, some in a .plot-box, some are Plotly divs — so the caption is
   * appended to the nearest .plot-box if there is one, else to the element's
   * parent.
   */
  function captionPlots(opts) {
    var results = opts.results, map = opts.plotSeries || {};
    var names = Object.keys(opts.rawSeries);
    var headName = names.indexOf('observedData') >= 0 ? 'observedData' : names[0];
    var fallback = results[headName] && results[headName].window
      ? results[headName].window.rangeLabel : null;

    function host(el) {
      var box = el.closest ? el.closest('.plot-box') : null;
      return box || el.parentElement;
    }

    function caption(target, text) {
      if (!target || target.querySelector('.fw-caption')) return;
      var cap = document.createElement('div');
      cap.className = 'fw-caption';
      cap.textContent = text;
      target.appendChild(cap);
    }

    Object.keys(map).forEach(function (id) {
      var el = document.getElementById(id);
      var r = results[map[id]];
      if (!el || !r) return;
      caption(host(el), (r.label || map[id]) + ' · ' + r.rangeLabel);
    });

    if (!fallback) return;
    document.querySelectorAll('.plot-box, [data-fourier-series]').forEach(function (box) {
      var name = box.getAttribute('data-fourier-series');
      var r = name && results[name];
      caption(box, r ? (r.label || name) + ' · ' + r.rangeLabel
                     : 'Fourier window · ' + fallback);
    });
  }

  return { request: request, mount: mount, captionPlots: captionPlots };
})();

if (typeof window !== 'undefined') window.EnsoFourierWindow = EnsoFourierWindow;
