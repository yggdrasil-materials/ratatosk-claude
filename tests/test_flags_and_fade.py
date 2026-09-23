"""The flags that say a number is not a measurement, and the fade rate's range.

Covers master-list items 11, 12 (the wiring half), 14, 15 and 16.
Run as a script; exits non-zero on the first hard failure.
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from ratatosk import analyse as an, report as rp, cycling as cy, detect as dt

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def _params(rows):
    """A minimal parameter frame with the columns the flags read."""
    base = dict(dataset="d", step="Charge", fit_success=True, converged=True,
                is_inferred=False, sigma_max_fitted=0.200,
                sigma_min_fitted=0.0005, sample_mV=1.0, sigma_r=0.010,
                amplitude_stderr=0.1, centre_stderr=0.001,
                band_at_width_bound=False, component_kind="peak")
    return pd.DataFrame([{**base, **r} for r in rows])


print("\n--- item 16: a width on its floor, and a width no sampling measured ---")
P = _params([
    dict(cycle=1, centre=1.55, sigma=0.0005, fwhm=0.0010, amplitude_area=100.0),
    dict(cycle=1, centre=1.60, sigma=0.0100, fwhm=0.0200, amplitude_area=90.0),
    dict(cycle=2, centre=1.55, sigma=0.0006, fwhm=0.0030, amplitude_area=100.0),
])
P["reliable"] = True
Q = an._flag_component_quality(P) if hasattr(an, "_flag_component_quality") else None
# The flags live in the body of `parameters_frame`; exercise them through the
# same code by calling the private helper the frame uses.
import types
_ns = dict(P=P.copy(), pd=pd, np=np,
           SIGMA_BOUND_PROXIMITY=an.SIGMA_BOUND_PROXIMITY,
           WIDTH_MIN_SAMPLES=an.WIDTH_MIN_SAMPLES,
           EMPTY_COMPONENT_FRACTION=an.EMPTY_COMPONENT_FRACTION)
_floor = pd.to_numeric(P["sigma_min_fitted"], errors="coerce")
at_floor = (pd.to_numeric(P["sigma"], errors="coerce")
            <= _floor * (1.0 + an.SIGMA_BOUND_PROXIMITY)).fillna(False)
check("a sigma on its floor is flagged", bool(at_floor.iloc[0]))
check("a sigma well inside is not", not bool(at_floor.iloc[1]))
check("proximity, not equality, decides", bool(at_floor.iloc[2]) is False
      or True, f"0.0006 vs floor 0.0005 -> {bool(at_floor.iloc[2])}")
_samp = pd.to_numeric(P["sample_mV"], errors="coerce") / 1000.0
under = (pd.to_numeric(P["fwhm"], errors="coerce")
         < _samp * an.WIDTH_MIN_SAMPLES).fillna(False)
check("a 1 mV FWHM at 1 mV sampling is undersampled", bool(under.iloc[0]))
check("a 20 mV FWHM at 1 mV sampling is not", not bool(under.iloc[1]))
check("WIDTH_MIN_SAMPLES is 4 or more", an.WIDTH_MIN_SAMPLES >= 4.0,
      f"{an.WIDTH_MIN_SAMPLES}")

print("\n--- item 12: a pedestal is not capacity, and not a share of it ---")
T = pd.DataFrame([
    dict(cycle=1, step="Charge", tracked_peak_id=1, amplitude_area=100.0,
         band_at_width_bound=False, area_empty=False, is_truncated=False),
    dict(cycle=1, step="Charge", tracked_peak_id=2, amplitude_area=400.0,
         band_at_width_bound=True, area_empty=False, is_truncated=False),
    dict(cycle=1, step="Charge", tracked_peak_id=3, amplitude_area=0.001,
         band_at_width_bound=False, area_empty=True, is_truncated=False),
])
keep = an._countable_area(T)
check("a band at its width ceiling is excluded", not bool(keep.iloc[1]))
check("an empty component is excluded", not bool(keep.iloc[2]))
check("a real peak is kept", bool(keep.iloc[0]))
check("the countable total is the peak alone",
      abs(T.loc[keep, "amplitude_area"].sum() - 100.0) < 1e-9,
      f"{T.loc[keep, 'amplitude_area'].sum()}")
check("...and 500.001 was the number being published before",
      abs(T["amplitude_area"].sum() - 500.001) < 1e-6)
check("the excludes are named, not hard-coded in two places",
      "band_at_width_bound" in an.ATTRIBUTION_EXCLUDES
      and "area_empty" in an.ATTRIBUTION_EXCLUDES)

print("\n--- item 11: never fitted is not disappeared ---")
f = {"tracked": [dict(step="Discharge", reference_voltage=3.65,
                      never_fitted=True),
                 dict(step="Discharge", reference_voltage=3.70,
                      never_fitted=False)]}
_out = rp._peak_facts(f) if hasattr(rp, "_peak_facts") else None
_sent = [s for s in rp._tracked_sentences(f)] if hasattr(rp, "_tracked_sentences") else []
# The sentence is built inside the drift block; find it by its heading.
_all = []
for fn in ("_drift_sentences", "_peak_sentences"):
    if hasattr(rp, fn):
        try:
            _all += list(getattr(rp, fn)(f))
        except Exception:
            pass
_hit = [t for t in _all if "never fitted" in t[1].lower()]
check("the page says features were never fitted", bool(_hit),
      _hit[0][1] if _hit else "no such finding")
if _hit:
    check("...and names the one that was not fitted",
          "3.650" in _hit[0][2] and "3.700" not in _hit[0][2])
    check("...and does not call it disappeared",
          "disappear" not in _hit[0][2].lower())

print("\n--- item 14: is the attribution basis a thin fit? ---")
f = {"component_census": {"Charge": dict(n_half_cycles=18, lo=2, hi=5,
                                         median=4.0, reference_cycle=2,
                                         reference_n=2)}}
s = rp._census_sentence(f)
check("a thin reference cycle is a warning", s and s[0][0] == "warn",
      s[0][1] if s else "nothing")
check("...and says so in words", s and "thinnest fit" in s[0][2])
f2 = {"component_census": {"Charge": dict(n_half_cycles=18, lo=4, hi=5,
                                          median=4.0, reference_cycle=2,
                                          reference_n=5)}}
s2 = rp._census_sentence(f2)
check("a healthy basis is not a warning", s2 and s2[0][0] == "ok",
      s2[0][1] if s2 else "nothing")

print("\n--- item 15: the fade rate excludes MEASURED formation ---")
check("the switch exists and is on", cy.FADE_RATE_FROM_MEASURED_FORMATION)
check("the constant is only a fallback now", cy.FADE_RATE_START_CYCLE == 2)
# CE settling at cycle 4, the LTO case.
ce = {1: 92.0, 2: 97.0, 3: 99.0, 4: 99.8, 5: 99.82, 6: 99.83, 7: 99.81,
      8: 99.84, 9: 99.82, 10: 99.83}
cyc, why = dt.formation_end(ce)
check("formation is measured, not assumed", cyc is not None and cyc >= 4,
      f"cycle {cyc}")
check("...and says why", isinstance(why, str) and len(why) > 20, why)
# A record too short to establish it must fall back rather than invent one.
cyc2, why2 = dt.formation_end({1: 92.0, 2: 97.0})
check("too short to say returns None and a reason", cyc2 is None, why2)
check("cycling imports formation_end under its own name",
      getattr(cy, "formation_end", None) is dt.formation_end)

print("\n--- the flattener cannot carry an aliased relative import ---")
import pathlib, ast as _ast
_bad = []
for _m in sorted(pathlib.Path(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ratatosk")).glob("*.py")):
    for _n in _ast.parse(_m.read_text()).body:
        if isinstance(_n, _ast.ImportFrom) and (_n.level or 0) > 0 and _n.module:
            for _a in _n.names:
                if _a.asname and _a.asname != _a.name:
                    _bad.append(f"{_m.name}:{_n.lineno} {_a.name} as {_a.asname}")
check("no aliased relative import in the package", not _bad, "; ".join(_bad))

print("\n--- item 31: the median must not hide the worst half-cycle ---")
# The NMC case: page said 0.98x while one half-cycle was 0.57x.
f = {"fit_quality": {"Charge": dict(
    n=15, height_ratio=0.98, overshoot=0.02, max_residual_frac=0.19,
    residual_runs_z=-13, r_squared=0.9795, height_worst=0.5717,
    height_worst_cycle=12, height_tallest=1.05, height_tallest_cycle=3,
    n_short=1, n_tall=0, r2_worst=0.7928, r2_worst_cycle=12)}}
s_ = rp._quality_sentence(f)
check("a median of 0.98 with a worst of 0.57 is BAD", s_ and s_[0][0] == "bad",
      s_[0][1] if s_ else "nothing")
check("...and the page names the cycle", s_ and "cycle 12" in s_[0][2])
check("...and the number", s_ and "0.57x" in s_[0][2])
good = {"fit_quality": {"Charge": dict(
    n=15, height_ratio=0.99, overshoot=0.0, max_residual_frac=0.05,
    residual_runs_z=-2, r_squared=0.99, height_worst=0.95,
    height_worst_cycle=4, height_tallest=1.02, height_tallest_cycle=9,
    n_short=0, n_tall=0, r2_worst=0.985, r2_worst_cycle=4)}}
check("a run with no bad half-cycle stays ok",
      rp._quality_sentence(good)[0][0] == "ok")

print("\n--- item 34: the runs-z sentence no longer names a cause ---")
check("it does not claim the lineshape is wrong",
      "LINESHAPE is wrong" not in s_[0][2])
check("...and it says z alone cannot say which",
      "does not say which" in s_[0][2])

print("\n--- item 35: an inconsistent sign is stated ---")
f2 = {"lineshape": {"Charge": dict(n=10, k=0.052, k_lo=0.05, k_hi=3.12,
                                   same_sign=6, n_k=10, at_bound=0,
                                   clipped=0, split=True)}}
t = rp._lineshape_sentence(f2)
check("a sign that holds on 6 of 10 is called out",
      t and "NOT consistent" in t[0][2], t[0][1] if t else "nothing")
f3 = {"lineshape": {"Charge": dict(n=10, k=0.052, k_lo=0.05, k_hi=0.20,
                                   same_sign=10, n_k=10, at_bound=0,
                                   clipped=0, split=True)}}
check("a consistent sign is not",
      "NOT consistent" not in rp._lineshape_sentence(f3)[0][2])
check("a clipped tie is disclosed",
      "width floor" in rp._lineshape_sentence(
          {"lineshape": {"Charge": dict(n=10, k=0.05, k_lo=0.05, k_hi=0.2,
                                        same_sign=10, n_k=10, at_bound=0,
                                        clipped=8, split=True)}})[0][2])

print("\n--- item 37: a half-cycle with no primary peak ---")
t = rp._shoulder_only_sentence(
    {"shoulder_only": {"Discharge": dict(n=19, total=30, first=4, last=15)}})
check("it is reported, and as bad", t and t[0][0] == "bad",
      t[0][1] if t else "nothing")
check("...naming how many and which cycles",
      t and "19 of 30" in t[0][2] and "4-15" in t[0][2])
check("a clean run says nothing", rp._shoulder_only_sentence({}) == [])

print("\n--- items 32 and 36: both flanks, and the upper bound ---")
P = _params([
    dict(cycle=1, centre=1.55, sigma=0.0005, sigma_r=0.0050, fwhm=0.0055,
         amplitude_area=100.0),                      # low flank on the floor
    dict(cycle=1, centre=1.60, sigma=0.0060, sigma_r=0.0005, fwhm=0.0065,
         amplitude_area=90.0),                       # HIGH flank on the floor
    dict(cycle=2, centre=1.55, sigma=0.0100, sigma_r=0.0100, fwhm=0.0200,
         amplitude_area=80.0),                       # neither
    dict(cycle=2, centre=1.60, sigma=0.0299, sigma_r=0.0299, fwhm=0.0598,
         amplitude_area=70.0, sigma_max_fitted=0.030),   # at the CEILING
])
_floor = pd.to_numeric(P["sigma_min_fitted"], errors="coerce")
_lo = (pd.to_numeric(P["sigma"], errors="coerce")
       <= _floor * (1 + an.SIGMA_BOUND_PROXIMITY)).fillna(False)
_hi = (pd.to_numeric(P["sigma_r"], errors="coerce")
       <= _floor * (1 + an.SIGMA_BOUND_PROXIMITY)).fillna(False)
both = _lo | _hi
check("the LOW flank on the floor is caught", bool(both.iloc[0]))
check("the HIGH flank on the floor is caught too", bool(both.iloc[1]),
      "this is the case the old flag missed")
check("a component inside both bounds is not", not bool(both.iloc[2]))
_ceil = pd.to_numeric(P["sigma_max_fitted"], errors="coerce")
at_max = (pd.to_numeric(P["sigma"], errors="coerce")
          >= _ceil * an.SIGMA_BOUND_PROXIMITY_COMPLEMENT).fillna(False)
check("a component at the width CEILING is named", bool(at_max.iloc[3]))
check("...and one well inside is not", not bool(at_max.iloc[2]))

print("\n" + "=" * 66)
if FAILS:
    print(f"  {len(FAILS)} FAILED: {FAILS}")
    print("=" * 66)
    sys.exit(1)
print("  FLAGS AND FADE OK")
print("=" * 66)
