"""
verify_section2_sampling.py
===========================
Python reference for Section 2 ("Duffing attractor sampling") of
docs/duffing_simulation.html.

It mirrors, exactly, the JavaScript ``attBuild()`` sampler:

  * one continuous Duffing trajectory of (M_burn + N) "years", where a year is
    one forcing period  L = 2*pi/W ;
  * phase resolution P frames/year (Monthly=12, Weekly=52, Daily=365) ;
  * frame k holds the state (X, dX/dt) at phase k/P of every recorded year,
    so each frame carries N dots ;
  * integration sub-step dt = (L/P)/nsub with nsub = max(1, round((L/P)/0.1)),
    so Monthly integrates at exactly dt = 0.1 — identical to the Section-1
    simulator (rkf5Step / NL3System.increment).

The same fixed-step RKF5 update used everywhere on the page is imported from
verify_duffing.py, so this is the *same physics*, not a fork.

Acceptance checks (printed):
  1. Monthly, N=52: frame-1 (January) dot X-values equal the January states of
     the 52 simulated years obtained by running the Section-1 integrator
     continuously; frame-12 = December. Numeric check for 3 sample years.
  2. N=1000 builds quickly; Weekly=52 and Daily=365 frame counts are correct.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from el_nino.duffing import default_params            # noqa: E402
from verify_duffing import rkf5_step                  # noqa: E402  (shared RKF5)

TARGET_DT = 0.1          # matches ATT_TARGET_DT in the page
TWO_PI = 6.283185307179586


def build_frames(params, x0, y0, t0, N, P, burn=0, wiki=False):
    """Exact port of attBuild(): returns (frames, hsample, nsub, dt_int).

    frames[k] is a list of X (we only need X for the checks) for every recorded
    year at phase k/P.  "One year" is 12 months for the calendar / El Niño
    modes and the forcing period 2*pi/W for the Wikipedia preset — matching the
    JavaScript.
    """
    W = params.get("W", TWO_PI / 12.0)
    L = (TWO_PI / W) if wiki else 12.0
    hsample = L / P
    nsub = max(1, round(hsample / TARGET_DT))
    dt_int = hsample / nsub
    total_years = burn + N

    framesX = [[] for _ in range(P)]
    t, X, Y = t0, x0, y0
    for yr in range(total_years):
        for k in range(P):
            if yr >= burn:
                framesX[k].append(X)
            for _ in range(nsub):
                X, Y = rkf5_step(t, X, Y, params, dt_int)
                t += dt_int
    return framesX, hsample, nsub, dt_int


def section1_monthly_states(params, x0, y0, t0, N, phase_month):
    """Run the Section-1 integrator continuously at dt=0.1 and read X at the
    requested calendar month (0=Jan .. 11=Dec) of each of N years.

    This is the independent 'ground truth' for acceptance check 1: it does NOT
    use the frame machinery — just the shared rkf5_step marched at 0.1 months.
    """
    dt = 0.1
    steps_per_month = round(1.0 / dt)         # 10
    # sample step index for year y, month m:  (12*y + m) * 10
    want = {(12 * y + phase_month) * steps_per_month: y for y in range(N)}
    out = [None] * N
    t, X, Y = t0, x0, y0
    step = 0
    if 0 in want:
        out[want[0]] = X
    max_step = max(want)
    while step < max_step:
        X, Y = rkf5_step(t, X, Y, params, dt)
        t += dt
        step += 1
        if step in want:
            out[want[step]] = X
    return out


def main():
    p = default_params()
    t0 = 0.5          # getStartTime() default (nb-tstart) — El Nino preset
    x0, y0 = 0.0, 0.0

    print("=" * 68)
    print("Section 2 sampling — Python reference vs Section-1 integrator")
    print(f"  params: K1={p['K1']}, K3={p['K3']}, FA={p['FA']}, FF={p['FF']}, "
          f"B={p['B']}, W={p['W']}")
    print(f"  t0={t0}, X0={x0}, Y0={y0}")

    # ---- Acceptance check 1: Monthly N=52 -----------------------------------
    N = 52
    framesX, hs, nsub, dti = build_frames(p, x0, y0, t0, N=N, P=12, burn=0)
    print("\n[1] Monthly, N=52  (P=12, "
          f"hsample={hs:.4f} mo, nsub={nsub}, dt_int={dti:.4f} mo)")

    jan_truth = section1_monthly_states(p, x0, y0, t0, N, phase_month=0)   # January
    dec_truth = section1_monthly_states(p, x0, y0, t0, N, phase_month=11)  # December

    frame1 = framesX[0]     # January
    frame12 = framesX[11]   # December

    import math
    max_jan = max(abs(frame1[y] - jan_truth[y]) for y in range(N))
    max_dec = max(abs(frame12[y] - dec_truth[y]) for y in range(N))

    print("    sample-year check (frame values vs Section-1 continuous run):")
    for y in (0, 25, 51):
        print(f"      year {y+1:>2}:  frame1(Jan)  X={frame1[y]:+.6f}   "
              f"Section1 X={jan_truth[y]:+.6f}   |d|={abs(frame1[y]-jan_truth[y]):.2e}")
        print(f"               frame12(Dec) X={frame12[y]:+.6f}   "
              f"Section1 X={dec_truth[y]:+.6f}   |d|={abs(frame12[y]-dec_truth[y]):.2e}")
    print(f"    max |d| over all 52 years:  January={max_jan:.2e}   December={max_dec:.2e}")
    ok1 = max_jan < 1e-9 and max_dec < 1e-9
    print(f"    RESULT: {'PASS' if ok1 else 'FAIL'} "
          f"(frame-1==January states, frame-12==December states)")

    # ---- Acceptance check 2: frame counts + N=1000 build --------------------
    print("\n[2] Frame counts and large-N build")
    for label, P in (("Monthly", 12), ("Weekly", 52), ("Daily", 365)):
        assert len(build_frames(p, x0, y0, t0, N=1, P=P)[0]) == P
        print(f"    {label:<8}: {P} frames/year  OK")

    for P, tag in ((12, "Monthly"), (365, "Daily")):
        t = time.perf_counter()
        fr, *_ = build_frames(p, x0, y0, t0, N=1000, P=P)
        dt_build = time.perf_counter() - t
        dots = len(fr[0])
        print(f"    N=1000 {tag:<8}: built {P} frames x {dots} dots "
              f"in {dt_build*1000:.0f} ms")
    ok2 = True

    print("\n" + "=" * 68)
    print(f"OVERALL: {'PASS' if (ok1 and ok2) else 'FAIL'}")
    print("=" * 68)
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
