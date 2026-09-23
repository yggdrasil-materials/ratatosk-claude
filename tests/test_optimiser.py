"""
Ratatosk 1.9.0.44 — the optimiser. Run: python tests/test_optimiser.py

Master-list items 8, 9 and 13 turned out to be one fault seen three ways:
scipy's leastsq was being asked for eight significant figures (ftol = xtol =
1.5e-8) from a dQ/dV curve that carries three, so a five-component fit ran to
the 20,000-evaluation ceiling and was then recorded as "not converged" — and a
reliability gate built on that status demoted the fits that were still
descending, which on NNM were the BETTER fits.

These tests pin the three things that must stay true.
"""
import sys, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

import pandas as pd
from ratatosk import fitting as F, analyse as A, synthetic as S

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def test_tolerance_is_set_and_reaches_the_fit():
    print("\n1. The tolerance is explicit, and it reaches the optimiser")
    check("FIT_TOLERANCE is set, not left at the library default",
          F.FIT_TOLERANCE is not None and 0 < F.FIT_TOLERANCE < 1e-2,
          f"{F.FIT_TOLERANCE:g}")
    h = S.make_case("mixed", seed=11)
    spec = F.FitSpec(h.centres if hasattr(h, "centres") else [h.voltage.mean()],
                     baseline_degree=2, sigma_min=0.005, sigma_max=0.2)
    loose = F.fit_half_cycle(h.voltage, h.dqdv, spec, key="loose")
    _saved = F.FIT_TOLERANCE
    try:
        F.FIT_TOLERANCE = None          # the old library default
        tight = F.fit_half_cycle(h.voltage, h.dqdv, spec, key="tight")
    finally:
        F.FIT_TOLERANCE = _saved
    check("a looser tolerance costs fewer evaluations",
          loose["nfev"] <= tight["nfev"],
          f"{loose['nfev']} against {tight['nfev']} at the default")
    check("...and does not cost fit quality here",
          abs(loose["r_squared"] - tight["r_squared"]) < 0.01,
          f"R2 {loose['r_squared']:.4f} against {tight['r_squared']:.4f}")


def test_staging_is_off_and_the_reason_is_recorded():
    print("\n2. The staged refinement is retired, not silently deleted")
    check("STAGED_REFINEMENT is off", F.STAGED_REFINEMENT is False)
    check("the code path is still there to re-test",
          "STAGED_REFINEMENT and len(spec.centres)" in
          open(F.__file__).read(),
          "a flag, not a deletion")


def test_convergence_no_longer_gates_reliability():
    print("\n3. Convergence is reported; it does not decide")
    n = 12
    P = pd.DataFrame(dict(
        cycle=range(1, n + 1), step="Charge", peak_index=0,
        centre=1.5, sigma=0.02, amplitude_area=50.0, amplitude_stderr=1.0,
        fraction=0.5, r_squared=0.99,
        sigma_max_fitted=0.2, is_inferred=False,
        converged=[i % 2 == 0 for i in range(n)],
        hit_iteration_cap=[i % 2 == 1 for i in range(n)]))
    rel = A._flag_reliable_peaks(P, sigma_max_mV=200)
    check("the component-level filter ignores convergence",
          bool(rel.all()), f"{int(rel.sum())} of {n} reliable")
    src = open(A.__file__).read()
    check("neither reliability path reads `converged` as a gate",
          'P["converged"].fillna(True)' not in src
          and '_cv = row.get("converged")' not in src,
          "both gates removed together")


def test_area_determinacy_is_measured():
    print("\n4. The replacement is a measurement, and it is honest about NaN")
    P = pd.DataFrame(dict(
        amplitude_area=[100.0, 100.0, 100.0, 0.0],
        amplitude_stderr=[1.0, 90.0, np.nan, 1.0]))
    se = pd.to_numeric(P["amplitude_stderr"], errors="coerce")
    ar = pd.to_numeric(P["amplitude_area"], errors="coerce").abs()
    ratio = se / ar.where(ar > 0)
    missing = se.isna() & ar.notna()
    bad = (ratio > A.AREA_STDERR_RATIO_MAX).fillna(False) | missing
    check("a well-determined area passes", not bool(bad.iloc[0]),
          f"ratio {ratio.iloc[0]:.2f}")
    check("a 90% standard error fails", bool(bad.iloc[1]),
          f"ratio {ratio.iloc[1]:.2f}")
    check("a MISSING standard error fails — unknown is not small",
          bool(bad.iloc[2]), "no covariance could be estimated")
    check("flagged, not enforced, by default",
          A.ENFORCE_AREA_DETERMINACY is False,
          "turning it on is a decision about what the tool will quote")


for t in (test_tolerance_is_set_and_reaches_the_fit,
          test_staging_is_off_and_the_reason_is_recorded,
          test_convergence_no_longer_gates_reliability,
          test_area_determinacy_is_measured):
    t()

print("\n" + ("ALL PASS" if not FAILURES else f"FAILED: {FAILURES}"))
sys.exit(1 if FAILURES else 0)
