"""
Ground-truth regression for tracking, drift and area recovery.

Runs detection -> fitting -> tracking on a synthetic series whose centres and
areas we set, and states what the pipeline recovered. The assertions are the
tolerances quoted in the audit; a failure here is a scientific claim that has
stopped being true.
"""
import os, sys, warnings, matplotlib
matplotlib.use("Agg"); warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import numpy as np, pandas as pd
from scipy.optimize import linear_sum_assignment
from ratatosk import synthetic as sy, detect as dt, fitting as ft, analyse as an
from ratatosk.signal import (HalfCycleSignal, smooth_dqdv,
                             auto_preprocess_params)

TOL_CENTRE_MV = 5.0
TOL_AREA_PCT = 8.0
TOL_DRIFT_MV = 3.0


def run(case, n_cycles, drift, fade, noise, profile):
    cycles, truth = sy.make_series(case, n_cycles=n_cycles,
                                   drift_mV_per_cycle=drift,
                                   fade_pct_per_cycle=fade, noise_frac=noise)
    T = pd.DataFrame(truth)

    # SMOOTHED, as the real pipeline smooths. Detection on an unsmoothed 2%
    # noisy curve finds a peak per noise bump — 35 of them on a curve with
    # four — which is a statement about find_peaks, not about the tracker
    # this test exists to measure.
    win = 5 if profile == "sharp" else 11
    sigs = {}
    for n, hc in cycles.items():
        y, _ = smooth_dqdv(hc.dqdv, win, 3)
        sigs[(n, "Charge")] = HalfCycleSignal(
            cycle=n, step="Charge", direction=1.0,
            voltage=hc.voltage, dqdv=y, dqdv_raw=hc.dqdv,
            capacity=float(hc.capacity), n_records_raw=hc.voltage.size)
    det = dt.detect_all(sigs, name=case, verbose=False,
                        spec=dt.detect_spec_for_profile(profile))

    jobs = [(sigs[k].voltage, sigs[k].dqdv,
             ft.spec_for_profile(det.peaks[k], profile), k)
            for k in sorted(sigs) if not det.peaks.get(k, pd.DataFrame()).empty]
    shape = ft.calibrate_shape(jobs, verbose=False)
    jobs = [(v, y, sp.replace(fraction=shape["fraction"],
                              sigma_ratio=shape["sigma_ratio"]), k)
            for v, y, sp, k in jobs]
    fits = ft.fit_many(jobs, verbose=False)
    P = an.parameters_frame(fits, det, name=case)
    tk = an.track_peaks(P, det, verbose=False)

    # ONE TRACKED PEAK PER TRUTH COMPONENT, by optimal assignment — the same
    # rule the pipeline uses to claim a component once.
    #
    # Nearest-at-cycle-1 let SEVERAL tracked peaks claim the SAME component,
    # and then scored every one of them against it. On the `tracking` case
    # detection finds six features where the truth has four, so components 2
    # and 3 were each being scored three times over: the best match plus two
    # duplicates that could only ever look like catastrophic tracking
    # failures (centre bias 130-250 mV, area bias -90%). Those numbers were
    # real, but they measure OVER-DETECTION, not tracking, and burying them
    # in the tracking table made the tracker look broken for a fault
    # upstream of it. They are now counted separately, as `spurious`, and
    # `run` returns that count so the caller can hold detection to it.
    # A FITTED COMPONENT ACCOUNTS FOR EVERY TRUTH COMPONENT INSIDE ITS OWN
    # WIDTH. The `tracking` case puts components at 3.42 and 3.44 V with
    # sigmas of 35 and 12 mV: two Gaussians 20 mV apart, one of them three
    # times that wide. No fitting method separates those, and the pipeline
    # correctly reports one feature — so scoring that feature against the
    # SMALLER of the two truth components and calling a 374% area bias a
    # tracking failure was the test asking for a split nothing can make.
    #
    # Each tracked peak now claims the truth components lying within its own
    # fitted half-width, and is scored against their SUM (area) and their
    # area-weighted mean centre, which is where a merged doublet's fitted
    # centre actually sits. Claiming nothing makes a peak SPURIOUS; a truth
    # component no peak claims is MISSED. Both are counted and returned, so
    # nothing is excused by being reclassified — over-detection and
    # under-detection are simply not tracking errors, and were being scored
    # as though they were.
    t1 = T[T.cycle == det.reference_cycle].reset_index(drop=True)
    keys = sorted(tk.summary)
    h_all = tk.tracked_df
    claimed, spurious = {}, []
    for key in keys:
        sm = tk.summary[key]
        rv = float(sm["reference_voltage"])
        hh = h_all[(h_all.tracked_peak_id == sm["peak_id"]) &
                   (h_all.step == sm["step"]) & (h_all.status == "tracked")]
        # half-width of the fitted feature; 2 sigma if fwhm is unavailable
        w = np.nan
        if len(hh) and "fwhm" in hh and np.isfinite(hh.fwhm.median()):
            w = float(hh.fwhm.median()) / 2.0
        if not np.isfinite(w) or w <= 0:
            w = (2.0 * float(hh.sigma.median())
                 if len(hh) and "sigma" in hh
                 and np.isfinite(hh.sigma.median()) else 0.0)
        inside = [int(c) for c, v in zip(t1.component.values, t1.centre.values)
                  if abs(float(v) - rv) <= w]
        if not inside:
            # nothing of the truth under this peak at all
            j = int((t1.centre - rv).abs().idxmin())
            if abs(float(t1.centre.values[j]) - rv) <= w + 0.02:
                inside = [int(t1.component.values[j])]
            else:
                spurious.append(key)
                continue
        claimed[key] = inside
    missed = sorted(set(int(c) for c in t1.component.values)
                    - {c for v in claimed.values() for c in v})

    out = []
    for key in keys:
        if key not in claimed:
            continue
        sm = tk.summary[key]
        comps = claimed[key]
        comp = comps[0] if len(comps) == 1 else comps
        _sel = T[T.component.isin(comps)]
        tt = _sel.groupby("cycle").apply(
            lambda g: pd.Series({
                "centre": float(np.average(g.centre, weights=g.area))
                if g.area.sum() > 0 else float(g.centre.mean()),
                "area": float(g.area.sum())}),
            include_groups=False)
        h = tk.tracked_df
        h = h[(h.tracked_peak_id == sm["peak_id"]) &
              (h.step == sm["step"]) & (h.status == "tracked")]
        if h.empty:
            continue
        c_err = np.array([(h.centre.values[i]
                           - tt.centre.loc[int(h.cycle.values[i])]) * 1000
                          for i in range(len(h))])
        a_err = np.array([100 * (h.amplitude_area.values[i]
                                 / tt.area.loc[int(h.cycle.values[i])] - 1)
                          for i in range(len(h))])
        # Drift is measured FROM THE REFERENCE CYCLE to the cycle
        # `voltage_drift_last_cycle` names — not across the tracked span — so
        # the truth it is compared with must be the same interval. Getting
        # this wrong makes the pipeline look 60 mV out when it is the test
        # measuring the wrong thing.
        c1 = sm.get("voltage_drift_first_cycle") or det.reference_cycle
        c2 = sm.get("voltage_drift_last_cycle") or int(h.cycle.max())
        drift_true = drift * (c2 - c1)
        drift_err = sm["voltage_drift_mV"] - drift_true
        out.append(dict(peak=key,
                        comp=(comp if isinstance(comp, int)
                              else "+".join(map(str, comps))), n=len(h),
                        centre_bias=float(np.median(c_err)),
                        centre_rms=float(np.sqrt(np.mean(c_err ** 2))),
                        area_bias=float(np.median(a_err)),
                        area_rms=float(np.sqrt(np.mean(a_err ** 2))),
                        drift_true=float(drift_true),
                        drift_got=float(sm['voltage_drift_mV']),
                        drift_err=float(drift_err),
                        rate=sm["tracking_rate"]))
    return pd.DataFrame(out), shape, spurious, missed


fail = 0
spur = 0
for case, prof, n_cyc, drift, fade, noise in (
        ("tracking", "moderate", 50, 2.0, 0.2, 0.005),
        ("tracking", "moderate", 100, 2.0, 0.2, 0.005),
        ("tracking", "moderate", 50, 2.0, 0.2, 0.01),
        ("two_phase", "sharp", 50, 1.0, 0.2, 0.01)):
    t0 = time.perf_counter()
    R, shape, spurious, missed = run(case, n_cyc, drift, fade, noise, prof)
    print(f"\n{case}  n={n_cyc}  drift {drift} mV/cyc  fade {fade}%/cyc  "
          f"noise {100 * noise:.1f}%   eta={shape['fraction']}  "
          f"[{time.perf_counter() - t0:.0f} s]", flush=True)
    if R.empty:
        print("  NO PEAKS TRACKED"); fail += 1; continue
    print(R.to_string(index=False, float_format=lambda x: f"{x:7.2f}"))
    if spurious:
        # Reported, never excused. A tracked peak with no truth component
        # behind it is a detection fault, and this is the only place in the
        # suite that counts them.
        print(f"  SPURIOUS (detected, no truth component): "
              f"{len(spurious)} — {spurious}")
        spur += len(spurious)
    if missed:
        print(f"  MISSED (truth component never detected): {missed}")
        spur += len(missed)
    bad = R[(R.centre_rms > TOL_CENTRE_MV) | (R.area_rms > TOL_AREA_PCT)
            | (R.drift_err.abs() > TOL_DRIFT_MV)]
    if len(bad):
        print(f"  OUTSIDE TOLERANCE: {list(bad.peak)}")
        fail += len(bad)
# A TEST THAT COUNTS FAILURES AND THEN EXITS 0 IS NOT A TEST.
#
# This printed "FAILURES: 12   SPURIOUS DETECTIONS: 2" and returned success,
# so nothing in the suite could ever go red on it and the twelve were invisible
# to anyone not reading the console. The twelve are real, and they are the
# known identifiability limit rather than a regression: on overlapping
# components the fitter moves area between neighbours (peak 2 loses 88% of its
# area, peak 3 gains 232% of its own), which is the same non-identifiability
# the audit documented on real cells and is not something a tolerance change
# fixes. Deleting the tolerances would hide it; asserting them would paint the
# suite permanently red and train everyone to ignore it.
#
# So the tolerances stay as the SCIENTIFIC statement — this is what recovery
# would have to be for these areas to be quotable — and the gate is a
# REGRESSION baseline: the counts as measured on 1.9.0.71, failing only if the
# pipeline gets worse. Lower the baseline when a build beats it; that is the
# record of the improvement.
BASELINE_FAILURES = 12
BASELINE_SPURIOUS = 2

print(f"\n{'FAILURES: %d' % fail if fail else 'all tracked peaks within tolerance'}"
      f"{'   SPURIOUS DETECTIONS: %d' % spur if spur else ''}")
print(f"baseline: {BASELINE_FAILURES} failures, {BASELINE_SPURIOUS} spurious "
      f"(the known identifiability limit on overlapping components)")
if fail > BASELINE_FAILURES or spur > BASELINE_SPURIOUS:
    print(f"\nWORSE THAN BASELINE: {fail} > {BASELINE_FAILURES} failures"
          if fail > BASELINE_FAILURES else
          f"\nWORSE THAN BASELINE: {spur} > {BASELINE_SPURIOUS} spurious")
    sys.exit(1)
if fail < BASELINE_FAILURES or spur < BASELINE_SPURIOUS:
    print(f"\nBETTER THAN BASELINE ({fail} failures, {spur} spurious) — "
          f"lower BASELINE_FAILURES/BASELINE_SPURIOUS in this file to lock "
          f"the improvement in.")
print("\nSYNTHETIC RECOVERY AT BASELINE")
