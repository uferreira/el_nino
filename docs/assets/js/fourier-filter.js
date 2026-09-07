/* =====================================================================
 * assets/js/fourier-filter.js
 * ---------------------------------------------------------------------
 * Browser port of the Fourier low-pass filter, the Fourier interpolation
 * / differentiation step, and the analysis-window selection.
 *
 * THIS FILE IS WHERE THE FILTERING IS DONE ON THE WEBSITE.
 *
 * It is a line-for-line port of the Python reference implementation and
 * must stay numerically identical to it:
 *
 *   EnsoFourier.passaBaixa      <-  src/el_nino/filter.py   passa_baixa()
 *   EnsoFourier.deriFourier     <-  src/el_nino/filter.py   deri_fourier()
 *   EnsoFourier.computeSigma    <-  src/el_nino/filter.py   compute_sigma()
 *   EnsoFourier.climatology     <-  src/el_nino/pipeline.py _compute_climatology()
 *   EnsoFourier.runDataset      <-  src/el_nino/pipeline.py _run_pipeline_steps()
 *                                                            + _write_dat()
 *   EnsoFourier.resolveWindow   <-  src/el_nino/pipeline.py resolve_fourier_window()
 *   EnsoFourier.selectWindow    <-  src/el_nino/pipeline.py select_fourier_window()
 *   EnsoFourier.defaultStartYM  <-  src/el_nino/pipeline.py default_start_ym()
 *
 * tests/test_fourier_window_parity.py runs both implementations on the
 * same input and asserts they agree, so any change made here must be made
 * in the Python files above as well (and vice versa).
 *
 * Why the browser recomputes instead of reading a pre-filtered array:
 * the sine expansion, the detrending endpoints and the monthly
 * climatology all depend on the chosen window, so a window change is not
 * a slice of an existing result — the whole filter has to run again.
 * ===================================================================== */

var EnsoFourier = (function () {
  'use strict';

  var MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  /* ===================================================================
   * 1.  Analysis window
   *     Port of the "Fourier analysis window" section of pipeline.py.
   * =================================================================== */

  /** Serial month index, so windows compare as plain integers. */
  function ym(year, month) { return year * 12 + month; }

  /** Parse a "YYYY-MM" bound; null / "" mean "not specified". */
  function parseMonth(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === 'number') return value;
    var text = String(value).trim();
    if (!text) return null;
    var parts = text.replace(/\//g, '-').split('-');
    if (parts.length < 2) throw new Error("window bound must look like 'YYYY-MM', got " + value);
    var y = parseInt(parts[0], 10), m = parseInt(parts[1], 10);
    if (!(m >= 1 && m <= 12)) throw new Error('window month must be in 1..12, got ' + value);
    return ym(y, m);
  }

  /** Inverse of parseMonth: serial month index -> "YYYY-MM". */
  function formatMonth(v) {
    var y = Math.floor((v - 1) / 12), m = (v - 1) % 12 + 1;
    return String(y).padStart(4, '0') + '-' + String(m).padStart(2, '0');
  }

  /** Human label: serial month index -> "Sep 1975". */
  function labelMonth(v) {
    var y = Math.floor((v - 1) / 12), m = (v - 1) % 12 + 1;
    return MONTH_ABBR[m - 1] + ' ' + y;
  }

  /**
   * Calendar month a window must start in to span whole 12-month cycles.
   * Port of pipeline.py cycle_start_month().
   */
  function cycleStartMonth(endYM) {
    var endMonth = (endYM - 1) % 12 + 1;
    return endMonth % 12 + 1;
  }

  /**
   * First month of the default window for a record ending at endYM.
   *
   * The window starts in baseYear, in the calendar month that FOLLOWS the
   * end month, so it spans a whole number of complete 12-month seasonal
   * cycles. An end of August 2026 gives September 1975: 612 observations,
   * exactly 51 full years, every calendar month equally represented.
   */
  function defaultStartYM(endYM, baseYear) {
    return ym(baseYear === undefined ? 1975 : baseYear, cycleStartMonth(endYM));
  }

  /** Earliest whole-cycle start month the record actually contains. */
  function firstCycleStartAtOrAfter(recordFirst, endYM) {
    var candidate = ym(Math.floor((recordFirst - 1) / 12), cycleStartMonth(endYM));
    while (candidate < recordFirst) candidate += 12;
    return candidate;
  }

  /**
   * Resolve a requested window against one dataset's actual record.
   *
   * The request is honoured exactly as given — nothing is silently moved —
   * and then clipped to what the record contains, so a window wider than a
   * station's record falls back to that record's own first/last month.
   */
  function resolveWindow(raw, requested, baseYear) {
    requested = requested || {};
    baseYear = baseYear === undefined ? 1975 : baseYear;
    var n = raw.year.length;
    if (!n) throw new Error('cannot resolve a Fourier window for an empty record');

    var recordFirst = ym(raw.year[0], raw.month[0]);
    var recordLast = ym(raw.year[n - 1], raw.month[n - 1]);

    var requestedEnd = parseMonth(requested.end);
    var endYM = requestedEnd === null ? recordLast : requestedEnd;

    var requestedStart = parseMonth(requested.start);
    var startYM = requestedStart === null
      ? defaultStartYM(Math.min(endYM, recordLast), baseYear)
      : requestedStart;

    var notes = [];
    var clippedEnd = Math.min(endYM, recordLast);
    var clippedStart;
    if (startYM < recordFirst) {
      // The request reaches back beyond this record. Rather than starting at
      // whatever calendar month the record happens to open with, start at the
      // first month that still gives whole 12-month cycles — the same rule the
      // default start uses, applied to this record's own beginning.
      clippedStart = firstCycleStartAtOrAfter(recordFirst, clippedEnd);
      notes.push('start moved to ' + labelMonth(clippedStart) + ': the record begins '
        + labelMonth(recordFirst) + ' and this is its first whole-cycle start');
    } else {
      clippedStart = startYM;
    }
    if (clippedEnd !== endYM) {
      notes.push('end clipped to ' + labelMonth(clippedEnd) + ' (record ends then)');
    }
    if (clippedEnd - clippedStart < 11) {
      // One complete seasonal cycle is the hard floor: the monthly
      // climatology needs every calendar month at least once.
      throw new Error('Fourier window must span at least 12 months; got '
        + formatMonth(clippedStart) + '..' + formatMonth(clippedEnd));
    }

    var startMonth = (clippedStart - 1) % 12 + 1;
    var endMonth = (clippedEnd - 1) % 12 + 1;
    var wholeCycles = startMonth === (endMonth % 12 + 1);
    if (!wholeCycles) {
      notes.push('window does not span whole 12-month cycles (starts in '
        + MONTH_ABBR[startMonth - 1] + ', ends in ' + MONTH_ABBR[endMonth - 1] + '); '
        + 'the sine expansion joins different phases of the seasonal cycle at its '
        + 'endpoints and the monthly climatology is unbalanced');
    }

    return {
      startYM: clippedStart,
      endYM: clippedEnd,
      start: formatMonth(clippedStart),
      end: formatMonth(clippedEnd),
      startLabel: labelMonth(clippedStart),
      endLabel: labelMonth(clippedEnd),
      rangeLabel: labelMonth(clippedStart) + ' – ' + labelMonth(clippedEnd),
      nMonths: clippedEnd - clippedStart + 1,
      wholeCycles: wholeCycles,
      notes: notes
    };
  }

  /** Slice a continuous monthly record down to a resolved window. */
  function selectWindow(raw, win) {
    var year = [], month = [], values = [];
    for (var i = 0; i < raw.year.length; i++) {
      var s = ym(raw.year[i], raw.month[i]);
      if (s >= win.startYM && s <= win.endYM) {
        year.push(raw.year[i]);
        month.push(raw.month[i]);
        values.push(raw.values[i]);
      }
    }
    return { year: year, month: month, values: values };
  }

  /* ===================================================================
   * 2.  Trigonometric tables
   *
   *     Both routines below evaluate sin(IW * IT * PI / D) for integer
   *     IW and IT. Tabulating sin(PI*k/D) for k = 0..2D-1 and indexing by
   *     (IW*IT) mod 2D gives the identical value with one lookup instead
   *     of one transcendental call, which keeps a full recomputation of
   *     every dataset well under a frame budget.
   * =================================================================== */

  function trigTable(D) {
    var period = 2 * D, sin = new Float64Array(period), cos = new Float64Array(period);
    for (var k = 0; k < period; k++) {
      sin[k] = Math.sin(Math.PI * k / D);
      cos[k] = Math.cos(Math.PI * k / D);
    }
    return { period: period, sin: sin, cos: cos };
  }

  /* ===================================================================
   * 3.  The filter itself
   * =================================================================== */

  /**
   * Fourier low-pass filter. Port of filter.py passa_baixa().
   *
   * HN1 and HN2 are HALF-period parameters (this is a half-range sine
   * expansion): HN1=10, HN2=9 put the transition band at full periods of
   * 20 and 18 months. Each coefficient is scaled by a sigmoid window, so
   * there is no Gibbs ringing. Mean and linear trend are removed before
   * the transform and restored afterwards.
   */
  function passaBaixa(HN1, HN2, ST0) {
    var NT = ST0.length, NM1 = NT - 1;
    if (NT < 3) throw new Error('ST0 must contain at least three observations');
    if (!(HN1 > HN2 && HN2 > 0)) throw new Error('low-pass cutoffs must satisfy HN1 > HN2 > 0');

    var STA = new Float64Array(NT), i;
    var HMEDIA = 0;
    for (i = 0; i < NT; i++) HMEDIA += ST0[i];
    HMEDIA /= NT;
    for (i = 0; i < NT; i++) STA[i] = ST0[i] - HMEDIA;
    var FIRST = STA[0], HLAST = STA[NT - 1];
    for (i = 0; i < NT; i++) STA[i] -= FIRST + i * (HLAST - FIRST) / NM1;

    var IWmax = Math.floor(NM1 / 2);
    var T = trigTable(NM1);
    // FOURIER(IW) = (2/NM1) * sum_{IT=1..NM1} STA[IT] * sin(IW*IT*PI/NM1)
    var FOURIER = new Float64Array(IWmax);
    for (var iw = 1; iw <= IWmax; iw++) {
      var acc = 0, idx = 0;
      for (var it = 1; it <= NM1; it++) {
        idx += iw;
        if (idx >= T.period) idx -= T.period;
        acc += STA[it] * T.sin[idx];
      }
      FOURIER[iw - 1] = (2 / NM1) * acc;
    }

    // Sigmoid window over mode number.
    var W1 = NM1 / HN1, W2 = NM1 / HN2;
    var DW2 = Math.abs(W2 - W1) / 2, W0 = (W1 + W2) / 2;

    var STB = new Float64Array(NT);
    for (iw = 1; iw <= IWmax; iw++) {
      var coef = FOURIER[iw - 1] / (1 + Math.exp((iw - W0) / DW2));
      if (coef === 0) continue;
      var j = 0;
      for (it = 0; it < NT; it++) {
        STB[it] += coef * T.sin[j];
        j += iw;
        if (j >= T.period) j -= T.period;
      }
    }
    for (i = 0; i < NT; i++) STB[i] += HMEDIA + FIRST + i * (HLAST - FIRST) / NM1;
    return STB;
  }

  /**
   * Fourier interpolation + analytic derivatives.
   * Port of filter.py deri_fourier(), including its corrected derivative
   * time scale (NM1 = NT-1 monthly intervals, not NT).
   *
   * Returns SST (interpolated series), VST (dT/dt, per month) and AST
   * (d2T/dt2, per month squared) on a grid of NDOTS sub-points per month.
   */
  function deriFourier(NDOTS, ST0) {
    var NT = ST0.length, NM1 = NT - 1;
    if (NT < 3) throw new Error('ST0 must contain at least three observations');
    if (!(NDOTS > 0)) throw new Error('NDOTS must be a positive integer');
    var NTD = NM1 * NDOTS + 1, NTDM1 = NTD - 1, i;

    var STA = new Float64Array(NT);
    var HMEDIA = 0;
    for (i = 0; i < NT; i++) HMEDIA += ST0[i];
    HMEDIA /= NT;
    for (i = 0; i < NT; i++) STA[i] = ST0[i] - HMEDIA;
    var FIRST = STA[0], HLAST = STA[NT - 1];
    for (i = 0; i < NT; i++) STA[i] -= FIRST + i * (HLAST - FIRST) / NM1;

    var IWmax = Math.floor(NM1 / 2);
    var Tc = trigTable(NM1);
    var FOURIER = new Float64Array(IWmax);
    for (var iw = 1; iw <= IWmax; iw++) {
      var acc = 0, idx = 0;
      for (var it = 1; it <= NM1; it++) {
        idx += iw;
        if (idx >= Tc.period) idx -= Tc.period;
        acc += STA[it] * Tc.sin[idx];
      }
      FOURIER[iw - 1] = (2 / NM1) * acc;
    }

    // Output grid maps [0, NTDM1] -> [0, NM1]; no sigmoid window here,
    // every mode is kept for the interpolation.
    var To = trigTable(NTDM1);
    var SST = new Float64Array(NTD), VST = new Float64Array(NTD), AST = new Float64Array(NTD);
    for (iw = 1; iw <= IWmax; iw++) {
      var F = FOURIER[iw - 1];
      if (F === 0) continue;
      var w = iw * Math.PI / NM1;
      var Fv = F * w, Fa = -F * w * w, j = 0;
      for (it = 0; it < NTD; it++) {
        SST[it] += F * To.sin[j];
        VST[it] += Fv * To.cos[j];
        AST[it] += Fa * To.sin[j];
        j += iw;
        if (j >= To.period) j -= To.period;
      }
    }
    var slope = (HLAST - FIRST) / NM1;
    for (i = 0; i < NTD; i++) {
      SST[i] += HMEDIA + FIRST + i * (HLAST - FIRST) / NTDM1;
      VST[i] += slope;
    }
    return { SST: SST, VST: VST, AST: AST };
  }

  /** RMS diagnostics. Port of filter.py compute_sigma(). */
  function computeSigma(ST0, filtered, interp, NDOTS) {
    var n = ST0.length, a = 0, b = 0;
    for (var i = 0; i < n; i++) {
      var d1 = filtered[i] - ST0[i]; a += d1 * d1;
      var d2 = ST0[i] - interp[i * NDOTS]; b += d2 * d2;
    }
    return { sigma30: Math.sqrt(a / n), sigma04: Math.sqrt(b / n) };
  }

  /** Mean value for each calendar month. Port of pipeline._compute_climatology. */
  function climatology(MES, data) {
    var sums = new Float64Array(12), counts = new Int32Array(12), i;
    for (i = 0; i < MES.length; i++) { sums[MES[i] - 1] += data[i]; counts[MES[i] - 1]++; }
    var clim = new Float64Array(12);
    for (i = 0; i < 12; i++) {
      if (!counts[i]) throw new Error('climatology requires all 12 calendar months');
      clim[i] = sums[i] / counts[i];
    }
    return clim;
  }

  /* ===================================================================
   * 4.  One dataset, end to end
   *     Port of pipeline._run_pipeline_steps() + _write_dat().
   * =================================================================== */

  /**
   * raw     : { label, unit, deseasonalize, values[], year[], month[] }
   * params  : { HN1, HN2, NDOTS, baseYear }
   * request : { start:"YYYY-MM"|null, end:"YYYY-MM"|null }
   *
   * Returns the same shape the pages consume:
   *   { x, y, year, month, irest, window, sigma30, sigma04, ... }
   * x is the interpolated observable, y its rate of change per month.
   *
   * Values are rounded to two decimals to match the F7.2 columns the
   * Python pipeline writes to data/output/*.dat, so the page shows
   * exactly the numbers the reference implementation publishes.
   */
  function runDataset(raw, params, request) {
    var HN1 = params.HN1, HN2 = params.HN2, NDOTS = params.NDOTS;
    var win = resolveWindow(raw, request, params.baseYear);
    var w = selectWindow(raw, win);
    var values = w.values, MES = w.month, NT = values.length, i;

    var filtered;
    if (raw.deseasonalize) {
      // Absolute series (SST NINO1+2, sea level): remove the monthly
      // climatology, filter the anomaly, then add the cycle back, so the
      // 12-month harmonic is never attenuated by the 18-20 month cutoff.
      var clim = climatology(MES, values);
      var anomaly = new Float64Array(NT);
      for (i = 0; i < NT; i++) anomaly[i] = values[i] - clim[MES[i] - 1];
      var fa = passaBaixa(HN1, HN2, anomaly);
      filtered = new Float64Array(NT);
      for (i = 0; i < NT; i++) filtered[i] = fa[i] + clim[MES[i] - 1];
    } else {
      // NOAA NINO3 / NINO4 / NINO3.4 columns are already anomalies.
      filtered = passaBaixa(HN1, HN2, values);
    }

    var d = deriFourier(NDOTS, filtered);
    var sig = computeSigma(values, filtered, d.SST, NDOTS);

    var NTD = (NT - 1) * NDOTS + 1;
    var x = new Array(NTD), y = new Array(NTD);
    var year = new Array(NTD), month = new Array(NTD), irest = new Array(NTD);
    for (var I = 1; I <= NTD; I++) {
      var IOLD = 1 + Math.floor((I - 1) / NDOTS);
      irest[I - 1] = I - (IOLD - 1) * NDOTS - 1;
      year[I - 1] = w.year[IOLD - 1];
      month[I - 1] = MES[IOLD - 1];
      x[I - 1] = Math.round(d.SST[I - 1] * 100) / 100;
      y[I - 1] = Math.round(d.VST[I - 1] * 100) / 100;
    }

    return {
      x: x, y: y, year: year, month: month, irest: irest,
      label: raw.label, unit: raw.unit, group: raw.group,
      window: win, rangeLabel: win.rangeLabel, nMonths: win.nMonths,
      sigma30: sig.sigma30, sigma04: sig.sigma04,
      raw: { values: values, year: w.year, month: MES },
      filtered: filtered, accel: d.AST
    };
  }

  /** Run every dataset in a RAW_SERIES object through runDataset. */
  function runAll(rawSeries, params, request) {
    var out = {}, failures = {};
    Object.keys(rawSeries).forEach(function (name) {
      try {
        out[name] = runDataset(rawSeries[name], params, request);
      } catch (err) {
        // A window that misses a short record must not blank the page:
        // keep an empty dataset and report why in the control panel.
        failures[name] = err.message;
        out[name] = {
          x: [], y: [], year: [], month: [], irest: [],
          label: rawSeries[name].label, unit: rawSeries[name].unit,
          group: rawSeries[name].group,
          window: null, rangeLabel: 'no data in window', nMonths: 0,
          error: err.message
        };
      }
    });
    out.__failures = failures;
    return out;
  }

  return {
    MONTH_ABBR: MONTH_ABBR,
    ym: ym,
    parseMonth: parseMonth,
    formatMonth: formatMonth,
    labelMonth: labelMonth,
    cycleStartMonth: cycleStartMonth,
    defaultStartYM: defaultStartYM,
    resolveWindow: resolveWindow,
    selectWindow: selectWindow,
    passaBaixa: passaBaixa,
    deriFourier: deriFourier,
    computeSigma: computeSigma,
    climatology: climatology,
    runDataset: runDataset,
    runAll: runAll
  };
})();

/* Exposed as a global for the pages, and as a module for the Node-based
 * parity test in tests/test_fourier_window_parity.py. */
if (typeof window !== 'undefined') window.EnsoFourier = EnsoFourier;
if (typeof module !== 'undefined' && module.exports) module.exports = EnsoFourier;
