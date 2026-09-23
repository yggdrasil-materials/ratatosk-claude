"""
Ratatosk 1.9.0 foundation tests. Run: python tests/test_foundation.py

These test against data whose right answer is known, which is the point. A
test that only checks Ratatosk agrees with itself would have passed every day
of the 1.8.x work while the baseline quietly absorbed 84% of a half-cycle.
"""
import sys, time, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from ratatosk import synthetic as S, fitting as F, quality as Q

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


CFG = {"two_phase": (0.05, 0.03), "mixed": (0.10, 0.05),
       "solid_solution": (0.40, 0.10), "degenerate": (0.50, 0.12),
       # The tracking ground truth: three separated peaks plus one genuine
       # shoulder. Same bounds as `mixed`; it is the same kind of curve.
       "tracking": (0.10, 0.05)}


def spec_for(case, h):
    smax, tol = CFG[case]
    return F.FitSpec(h.true_centres, baseline_degree=1, sigma_min=0.003,
                     sigma_max=smax, centre_tol=tol)


def test_generator():
    print("\n1. The generator produces self-consistent ground truth")
    for case in S.CASES:
        h = S.make_case(case, seed=1)
        recovered = np.trapezoid(h.dqdv_clean, h.voltage)
        check(f"{case}: capacity == integral of the clean curve",
              abs(recovered - h.capacity) / h.capacity < 0.005,
              f"{h.capacity:.2f} vs {recovered:.2f}")


def test_area_recovery():
    print("\n2. Fitting recovers KNOWN peak areas")
    for case in ("two_phase", "mixed"):
        h = S.make_case(case, seed=2)
        r = F.fit_half_cycle(h.voltage, h.dqdv, spec_for(case, h))
        if not r["success"]:
            check(f"{case}: fit succeeds", False, r["reason"][:60]); continue
        err = np.array([abs(c["area_in_window"] - t) / t
                        for c, t in zip(r["components"], h.true_areas)])
        check(f"{case}: every component area within 5% of truth",
              bool((err < 0.05).all()), f"worst {100*err.max():.1f}%")


def test_closure_interval():
    print("\n3. The closure interval separates determined from undetermined")
    widths = {}
    for case in S.CASES:
        h = S.make_case(case, seed=3)
        iv = Q.closure_interval(h.voltage, h.dqdv, spec_for(case, h), key=case)
        widths[case] = iv["width"]
        print(f"      {case:16s} true {h.true_closure:.2f}   "
              f"closure {iv['lo']:.2f}-{iv['hi']:.2f}   width {iv['width']:.2f}")
    check("two_phase is determined (width < 0.05)", widths["two_phase"] < 0.05)
    check("mixed is determined (width < 0.05)", widths["mixed"] < 0.05)
    check("solid_solution is flagged undetermined (width > 0.15)",
          widths["solid_solution"] > 0.15)
    check("degenerate is flagged undetermined (width > 0.15)",
          widths["degenerate"] > 0.15,
          "the case built to break the metric")


def test_integral_fidelity():
    print("\n4. Integral fidelity detects a corrupted derivative")
    h = S.make_case("mixed", seed=4)
    check("clean curve: fidelity within 1% of unity",
          abs(Q.integral_fidelity(h.voltage, h.dqdv, h.capacity) - 1) < 0.01)
    # Inject the failure mode this project actually met: a fabricated peak at
    # the top of the window, as the constant-voltage hold produced.
    bad = h.dqdv + S.pseudo_voigt(h.voltage, h.voltage.max() - 0.01, 0.006,
                                  0.5, 40.0)
    f = Q.integral_fidelity(h.voltage, bad, h.capacity)
    check("fabricated peak shows as an excess", f > 1.10, f"fidelity {f:.3f}")


def test_parallel_equivalence():
    print("\n5. Parallel and serial fitting agree exactly")
    jobs = []
    for i in range(8):
        h = S.make_case("mixed", seed=10 + i)
        jobs.append((h.voltage, h.dqdv, spec_for("mixed", h), ("mixed", i)))
    t = time.perf_counter(); serial = F.fit_many(jobs, n_jobs=1, verbose=False)
    t_ser = time.perf_counter() - t
    t = time.perf_counter()
    forced = [(v, y, s, k) for v, y, s, k in jobs]
    from joblib import Parallel, delayed
    par = Parallel(n_jobs=2)(delayed(F.fit_half_cycle)(v, y, s, key=k)
                             for v, y, s, k in forced)
    t_par = time.perf_counter() - t
    worst = 0.0
    for a, b in zip(serial, par):
        for ca, cb in zip(a["components"], b["components"]):
            for f_ in ("centre", "sigma", "amplitude_area", "area_in_window"):
                worst = max(worst, abs(ca[f_] - cb[f_]))
    check("identical results from a worker process", worst == 0.0,
          f"max difference {worst:.2e}   serial {t_ser:.1f}s  2 workers {t_par:.1f}s")
    # NaN-AWARE. A plain `==` on the result dict fails the moment any field
    # is NaN — and several legitimately are (`sigma_ratio_k` where the
    # half-cycle has no shoulders, `redchi` on a perfect fit) — which makes
    # the test look like a pickling failure when nothing has failed. What is
    # being asserted is that the round trip preserves the data, so compare it
    # the way a reader would.
    import pickle as _pk

    def _same(a, b):
        if isinstance(a, dict):
            return (isinstance(b, dict) and a.keys() == b.keys()
                    and all(_same(a[k], b[k]) for k in a))
        if isinstance(a, (list, tuple)):
            return (len(a) == len(b)
                    and all(_same(x, y) for x, y in zip(a, b)))
        if isinstance(a, float) and np.isnan(a):
            return isinstance(b, float) and np.isnan(b)
        return a == b

    check("a fit result survives stdlib pickle",
          _same(_pk.loads(_pk.dumps(serial[0])), serial[0]),
          "no cloudpickle needed")


def test_scheduler_refuses():
    print("\n6. The scheduler refuses a pool it cannot repay")
    h = S.make_case("mixed", seed=99)
    jobs = [(h.voltage, h.dqdv, spec_for("mixed", h), i) for i in range(6)]
    workers, _, est = F.plan_workers(jobs, n_jobs=4, verbose=False)
    check("small job stays serial", workers == 1,
          f"estimated {est:.1f}s, floor {F.PARALLEL_MIN_SECONDS:.0f}s")


# ---------------------------------------------------------------------------
# The derivative-free path (1.9.0.14)
# ---------------------------------------------------------------------------


def test_histogram_dqdv():
    print("\n7. The histogram path accounts for the charge it was given")
    import numpy as _np
    from ratatosk import signal as _sg
    from ratatosk import quality as _ql

    # A REAL two-phase voltage curve: a short steep entry, a long nearly-flat
    # plateau carrying most of the charge, a short steep exit — and quantised
    # to 0.1 mV like the instrument. This is the shape a numerical derivative
    # cannot handle and the histogram can.
    n = 3000
    q = _np.linspace(0.0, 100.0, n)
    v = _np.where(q < 8.0, 2.50 - (2.50 - 1.575) * (q / 8.0),
                  _np.where(q > 92.0,
                            1.545 - (1.545 - 1.20) * ((q - 92.0) / 8.0),
                            1.575 - 0.030 * ((q - 8.0) / 84.0)))
    v = _np.round(v / 1e-4) * 1e-4                          # 0.1 mV quantised
    centres, y, info = _sg.histogram_dqdv(v, q, bin_width_mV=1.0)

    # EXACT property first: every record's charge is counted once, so the
    # bin totals must add to the delivered capacity. This is the arithmetic
    # the method rests on, and it holds whatever the curve looks like.
    exact = float(_np.sum(_np.abs(y)) * info["bin_width_mV"] / 1000.0)
    check("every record's charge is counted exactly once",
          abs(exact - 100.0) / 100.0 < 0.005,
          f"bin totals sum to {exact:.3f} of a true 100.000")

    # And the trapezoidal integral — what `integral_fidelity` uses — agrees,
    # because the plateau spans many bins. It would NOT agree on a peak one
    # bin wide, where the trapezium rule halves a spike; that is a property
    # of the integration, not of the method.
    area = float(_np.trapezoid(_np.abs(y), centres))
    check("and the trapezoidal integral agrees",
          abs(area - 100.0) / 100.0 < 0.03,
          f"integral {area:.2f} of a true 100.00")
    check("the peak sits on the plateau",
          1.545 <= centres[_np.argmax(_np.abs(y))] <= 1.575,
          f"peak at {centres[_np.argmax(_np.abs(y))]:.3f} V, "
          f"plateau 1.545-1.575")

    # Area is conserved by the smoothing, exactly — that is what makes the
    # kernel legitimate rather than a reintroduction of ad-hoc smoothing.
    areas = []
    for k in (0, 1, 4, 8):
        _, yk, ik = _sg.histogram_dqdv(v, q, bin_width_mV=1.0, smooth_kernel=k)
        areas.append(float(_np.sum(_np.abs(yk)) * ik["bin_width_mV"] / 1000.0))
    check("smoothing conserves the area",
          (max(areas) - min(areas)) / max(areas) < 0.01,
          f"{min(areas):.2f}-{max(areas):.2f} across kernels 0, 1, 4, 8")

    # The module constants must be readable at CALL time, not frozen as
    # default arguments — a whole parameter sweep once returned identical
    # numbers because of exactly that.
    _old = _sg.HISTOGRAM_BIN_MV
    try:
        _sg.HISTOGRAM_BIN_MV = 10.0
        c2, _, i2 = _sg.histogram_dqdv(v, q)
        check("module constants are read at call time, not frozen",
              abs(i2["bin_width_mV"] - 10.0) < 1e-6,
              f"bin width {i2['bin_width_mV']:.2f} mV after setting the "
              f"constant to 10")
    finally:
        _sg.HISTOGRAM_BIN_MV = _old

    check("sign follows the step label, not the direction",
          _sg.dqdv_sign("Charge") > 0 and _sg.dqdv_sign("Discharge") < 0,
          "Charge +1, Discharge -1")

    # Voltage reconstruction: the objective test, and it must handle a
    # FALLING half-cycle, which is every discharge.
    rec = _ql.voltage_reconstruction(centres, y, q, v)
    check("the voltage curve is reconstructed on a falling half-cycle",
          rec["ape_pct"] < 5.0 and rec["rmse_V"] < 0.05,
          f"APE {rec['ape_pct']:.2f}%, RMSE {1000 * rec['rmse_V']:.0f} mV")


if __name__ == "__main__":
    print("=" * 66)
    print("  Ratatosk 1.9.0 — foundation tests against known ground truth")
    print("=" * 66)
    for fn in (test_generator, test_area_recovery, test_closure_interval,
               test_integral_fidelity, test_parallel_equivalence,
               test_scheduler_refuses, test_histogram_dqdv):
        fn()
    print("\n" + "=" * 66)
    print(f"  {'ALL PASS' if not FAILURES else 'FAILURES: ' + ', '.join(FAILURES)}")
    print("=" * 66)
    sys.exit(1 if FAILURES else 0)


