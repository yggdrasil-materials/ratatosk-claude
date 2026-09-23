"""
Unit tests for analysis: the parts that must not depend on a threshold.

The real-cell behaviour is in tests/test_analyse_end_to_end.py. What is checked
here is the logic, on data whose answer is constructed rather than measured.
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])
import numpy as np, pandas as pd

from ratatosk import analyse as an, detect as dt
from ratatosk.signal import HalfCycleSignal, Reversal
from ratatosk.synthetic import pseudo_voigt

fails = []


def check(label, cond, detail=""):
    print(f"    {'PASS' if cond else 'FAIL'}  {label}"
          + (f"   {detail}" if detail else ""))
    if not cond:
        fails.append(label)


# ---------------------------------------------------------------------------
# 1. Mechanism: the three things a reversal can be
# ---------------------------------------------------------------------------
print("\n  1. a reversal is classified by where it sat on the curve")
V = np.linspace(3.0, 4.2, 1200)
Y = pseudo_voigt(V, 3.40, 0.020, 0.4, 60.0)      # one sharp feature; flat after
WINDOW = (3.0, 4.2)


def make(reversals, cap=100.0, n=400):
    s = HalfCycleSignal(cycle=5, step="Charge", direction=1.0,
                        capacity=cap, n_records_raw=n)
    s.voltage, s.dqdv = V, Y
    s.reversals = reversals
    return s


def rev(v, q, full=True, span=2.0):
    return Reversal(i0=0, i1=1, charge=q, v_start=v, v_end=v + span / 1000,
                    span_mV=span, seconds=10.0, at_full_current=full,
                    n_records=2)


got = an.classify_reversals(make([rev(3.40, 5.0),      # on the peak
                                  rev(3.90, 5.0),      # flat, full current
                                  rev(4.19, 5.0, full=False),   # at the limit
                                  rev(3.90, 5.0, full=False)]), # taper, mid-scan
                            window=WINDOW)
check("on the feature -> plateau", got[0]["mechanism"] == "plateau",
      f"|dQ/dV| there is {got[0]['dqdv_share']:.0%} of the maximum")
check("full current, nothing there -> parasitic",
      got[1]["mechanism"] == "parasitic",
      f"{got[1]['dqdv_share']:.1%} of the maximum")
check("current tapering at the limit -> cv_hold",
      got[2]["mechanism"] == "cv_hold")
check("current tapering mid-scan -> current_taper, not parasitic",
      got[3]["mechanism"] == "current_taper")

# The failure mode of the obvious alternative, kept as a test so it cannot
# come back: a wide two-phase plateau is many times wider than its peak's FWHM.
plateau_v = 3.40 + 0.10        # well outside the FWHM (2*sigma = 40 mV)
share = float(np.abs(Y)[np.argmin(np.abs(V - plateau_v))] / np.abs(Y).max())
check("the plateau test is |dQ/dV|, not proximity to a centre",
      share < an.PLATEAU_DQDV_FRACTION,
      f"100 mV off-centre is {share:.1%} of the maximum — correctly NOT a "
      f"plateau on this sharp peak")

# ---------------------------------------------------------------------------
# 2. Bands, judged against the half-cycle's own capacity
# ---------------------------------------------------------------------------
print("\n  2. the band comes from the half-cycle's own capacity")
g = an.half_cycle_integrity(make([rev(3.40, 20.0)]), window=WINDOW)
check("a plateau reversal is clean whatever its size",
      g.band == "clean" and g.plateau_charge == 20.0, g.reason)
g = an.half_cycle_integrity(make([rev(3.90, 5.0)], cap=100.0), window=WINDOW)
check("5 of 100 mAh/g unaccounted -> ANOMALOUS", g.band == "ANOMALOUS",
      f"{g.parasitic_fraction:.0%}")
g = an.half_cycle_integrity(make([rev(3.90, 5.0)], cap=1000.0), window=WINDOW)
check("the same 5 mAh/g of 1000 -> suspect, not ANOMALOUS",
      g.band == "suspect", f"{g.parasitic_fraction:.1%}")
g = an.half_cycle_integrity(make([], n=8), window=WINDOW)
check("a short half-cycle is 'too few records', not 'clean'",
      g.band == "too few records", g.reason)
check("and that band is not sound enough to anchor a dataset",
      "too few records" not in dt.SOUND_BANDS)

sigs = {(1, "Charge"): make([rev(3.90, 5.0)]),
        (2, "Charge"): make([rev(3.40, 9.0)]),
        (2, "Discharge"): make([]),
        (3, "Charge"): make([]), (3, "Discharge"): make([])}
for (c, s), v in sigs.items():
    v.cycle, v.step = c, s
R, band = an.integrity_report(sigs, window=WINDOW, name="synthetic",
                              verbose=False)
check("integrity_report returns the callable detect takes",
      band(1, "Charge") == "ANOMALOUS" and band(2, "Charge") == "clean"
      and band(9, "Charge") == "unknown")
check("and needs no peak list to produce it",
      "detect" not in an.classify_reversals.__code__.co_names)

# ---------------------------------------------------------------------------
# 3. Tracking
# ---------------------------------------------------------------------------
print("\n  3. tracking joins per-cycle fits into histories")
REF = pd.DataFrame(dict(peak_id=[1, 2], voltage=[3.40, 3.80],
                        is_shoulder=[False, False],
                        is_truncated=[False, False]))
CYCLES = list(range(1, 31))
rows = []
for cy in CYCLES:
    rows.append(dict(cycle=cy, step="Charge", centre=3.40 + 0.002 * cy,
                     amplitude_area=50.0, sigma=0.02, fraction=0.5,
                     r_squared=0.99, reliable=True))
    if cy <= 12:                      # peak 2 vanishes after cycle 12
        rows.append(dict(cycle=cy, step="Charge", centre=3.80,
                         amplitude_area=40.0, sigma=0.02, fraction=0.5,
                         r_squared=0.99, reliable=True))
P = pd.DataFrame(rows)
det = dt.Detection(name="synthetic", reference_cycle=2,
                   peaks={(c, "Charge"): pd.DataFrame() for c in CYCLES},
                   reference_peaks={"Charge": REF, "Discharge": pd.DataFrame()})
tk = an.track_peaks(P, det, verbose=False)
s1 = tk.summary["Charge_peak1"]
s2 = tk.summary["Charge_peak2"]
check("a drifting peak is tracked every cycle", s1["tracking_rate"] == 1.0)
# Drift is measured from the REFERENCE cycle, not cycle 1, and BOTH ENDS ARE
# A MEDIAN of `DRIFT_ENDPOINT_CYCLES` cycles — so on cycles 2..30 the interval
# is the median of {2,3,4} to the median of {28,29,30}, i.e. cycle 3 to cycle
# 29. The endpoints are named, so the test asserts against the interval the
# summary itself reports rather than against a hardcoded span.
_c1 = s1["voltage_drift_first_cycle"]
_c2 = s1["voltage_drift_last_cycle"]
check("its drift is measured from the REFERENCE cycle, not cycle 1",
      _c1 == 2 + (an.DRIFT_ENDPOINT_CYCLES - 1) // 2,
      f"first cycle of the drift interval is {_c1}, expected "
      f"{2 + (an.DRIFT_ENDPOINT_CYCLES - 1) // 2}")
check("drift matches the interval the summary names",
      abs(s1["voltage_drift_mV"] - (_c2 - _c1) * 2.0) < 1e-6,
      f"{s1['voltage_drift_mV']:+.1f} mV over cycles {_c1}-{_c2}")
check("and is reported per cycle at the rate it was built with",
      abs(s1["voltage_drift_mV_per_cycle"] - 2.0) < 1e-6,
      f"{s1['voltage_drift_mV_per_cycle']:+.3f} mV/cycle, expected +2.000")
check("a peak that vanishes has its loss recorded",
      s2["tracked"] == 12 and s2["disappeared"] == 18,
      f"{s2['tracking_rate']:.0%} tracked")
check("losing it at cycle 13 is a transient, not a failure",
      s2["discontinuity_events"] >= 1
      and not s2["discontinuity_is_failure"],
      f"{s2['discontinuity_events']} event(s); established first: "
      f"{s2['discontinuity_is_failure']}")

P2 = P[~((P.step == "Charge") & (P.centre == 3.80) & (P.cycle > 20))].copy()
P2 = pd.concat([P2, pd.DataFrame([
    dict(cycle=cy, step="Charge", centre=3.80, amplitude_area=40.0,
         sigma=0.02, fraction=0.5, r_squared=0.99, reliable=True)
    for cy in range(13, 21)])], ignore_index=True)
tk2 = an.track_peaks(P2, det, verbose=False)
s2b = tk2.summary["Charge_peak2"]
check("losing it at cycle 21, after 20 good cycles, IS a failure",
      s2b["discontinuity_is_failure"],
      f"first event cycle {s2b['first_discontinuity_cycle']}")
check("cell_discontinuity counts only established primaries",
      tk.cell_discontinuity == 0 and tk2.cell_discontinuity == 1)

# ---------------------------------------------------------------------------
# 4. Pairing, and the sign of delta-V
# ---------------------------------------------------------------------------
print("\n  4. pairing respects the electrode")
C = pd.DataFrame(dict(peak_id=[1, 2], voltage=[3.45, 3.85],
                      is_shoulder=[False, False]))
D = pd.DataFrame(dict(peak_id=[1, 2], voltage=[3.35, 3.75],
                      is_shoulder=[False, False]))
pc = an._auto_pair_peaks(C, D, 200, is_anode=False)
check("a cathode pairs charge above discharge",
      len(pc) == 2 and all(cv > dv for _, _, cv, dv, _ in pc),
      ", ".join(f"{cv:.2f}/{dv:.2f}" for _, _, cv, dv, _ in pc))
pa = an._auto_pair_peaks(D, C, 200, is_anode=True)
check("an anode, whose labels were swapped upstream, pairs the other way",
      len(pa) == 2 and all(cv < dv for _, _, cv, dv, _ in pa),
      ", ".join(f"{cv:.2f}/{dv:.2f}" for _, _, cv, dv, _ in pa))
crossed = an._auto_pair_peaks(
    C, pd.DataFrame(dict(peak_id=[1, 2], voltage=[3.75, 3.35],
                         is_shoulder=[False, False])), 200)
check("assignment is global, so a near neighbour cannot steal a partner",
      sorted((cv, dv) for _, _, cv, dv, _ in crossed)
      == [(3.45, 3.35), (3.85, 3.75)])

# ---------------------------------------------------------------------------
# 5. Attribution is withheld where the split is not determined
# ---------------------------------------------------------------------------
print("\n  5. attribution reports a share only where a share exists")
ivs = {(c, "Charge"): ((0.50, 0.52) if c % 2 else (0.20, 0.90))
       for c in CYCLES}
att = an.capacity_attribution(tk, closure_intervals=ivs, verbose=False)["Charge"]
narrow = att[~att.attribution_withheld]
wide = att[att.attribution_withheld]
check("a narrow interval reports a fraction",
      len(narrow) and narrow["peak1_fraction"].notna().all(),
      f"{len(narrow)} cycles")
check("a wide one does not", len(wide)
      and wide.filter(like="_fraction").isna().all().all(),
      f"{len(wide)} cycles withheld")
check("but keeps the areas it fitted",
      wide["peak1_area"].notna().all() and (wide["peak1_area"] == 50.0).all())
check("the threshold sits in the measured gap",
      0.09 < an.ATTRIBUTION_WITHHOLD_ABOVE < 0.35,
      f"{an.ATTRIBUTION_WITHHOLD_ABOVE} — P3 reaches 0.09, NMC111 starts 0.35")

# ---------------------------------------------------------------------------
# 6. Coherence
# ---------------------------------------------------------------------------
print("\n  6. coherence judges on the median, not the tails")
P3 = P.copy()
P3.loc[(P3.centre > 3.7), "centre"] = 3.80 + np.random.default_rng(0).normal(
    0, 0.040, int((P3.centre > 3.7).sum()))
C6 = an.coherence_audit(P3, det, verbose=False)
v = {r.reference_voltage: r.verdict for r in C6.itertuples()}
check("a peak drifting 2 mV/cycle is coherent", v.get(3.40) == "coherent",
      f"median {C6[C6.reference_voltage == 3.40].median_drift_mV.iloc[0]:.1f} mV")
check("a peak jumping tens of mV is not trend-worthy",
      v.get(3.80) == "NOT trend-worthy",
      f"median {C6[C6.reference_voltage == 3.80].median_drift_mV.iloc[0]:.1f} mV")
short = an.coherence_audit(P[P.cycle <= 5], det, verbose=False)
check("fewer than 8 pairs -> declines to judge, rather than guessing",
      set(short.verdict) == {"not assessable"}, str(set(short.verdict)))

# ---------------------------------------------------------------------------
# 7. A half-cycle the export caught mid-flight
# ---------------------------------------------------------------------------
print("\n  7. an unfinished half-cycle is recognised by its VOLTAGE")


class _FakeDS:
    """The smallest thing `termination_check` needs: a frame in acquisition
    order, half-cycle lookup, and a measured direction."""

    def __init__(self, frame):
        self.frame = frame

    def half_cycle_keys(self):
        return [(int(c), str(s)) for c, s in
                self.frame[["Cycle", "Step"]].drop_duplicates().values]

    def half_cycle(self, cycle, step):
        f = self.frame
        return f[(f.Cycle == cycle) & (f.Step == step)]

    def step_direction(self, cycle, step):
        v = self.half_cycle(cycle, step)["Voltage"].to_numpy()
        return 1.0 if v[-1] >= v[0] else -1.0


def _ds(n_cycles=6, last_v_end=None):
    """Charge falls 2.5 -> 1.2, discharge rises 1.2 -> 2.5, every cycle."""
    rows = []
    for c in range(1, n_cycles + 1):
        for st, a, b in (("Charge", 2.5, 1.2), ("Discharge", 1.2, 2.5)):
            end = b
            if last_v_end is not None and c == n_cycles and st == "Discharge":
                end = last_v_end
            for v in np.linspace(a, end, 40):
                rows.append(dict(Cycle=c, Step=st, Voltage=v))
    return _FakeDS(pd.DataFrame(rows))


keys, why = an.half_cycles_in_progress(_ds())
check("a file whose last half-cycle reached the cut-off is complete",
      keys == set(), why)
keys, why = an.half_cycles_in_progress(_ds(last_v_end=1.9))
check("one stopping 600 mV short is the export catching it mid-flight",
      keys == {(6, "Discharge")}, str(keys))
T = an.termination_check(_ds(last_v_end=1.9))
check("and only the LAST half-cycle is ever called unfinished",
      int((~T.reached).sum()) == 1 and bool(T[~T.reached].is_last.iloc[0]))
# A dying cell still drives to the cut-off, which is the whole reason this
# is asked of the voltage and not of the capacity: on P3 cell B an
# 80%-of-the-previous capacity rule fires 15 times on a cell that is merely
# dead, and every one of those half-cycles is real data.
keys, why = an.half_cycles_in_progress(_ds(last_v_end=2.4995))
check("a cut-off met to within a millivolt still counts as reached",
      keys == set(), why)

# ---------------------------------------------------------------------------
# 1.9.0.37 — the provenance flags actually demote, on every dtype
# ---------------------------------------------------------------------------
# Two traps, both hit while writing this: `bool(np.nan)` is True, so reading
# a missing flag with a bare `bool()` marked EVERY row inferred; and
# `np.True_ is True` is False, so the identity test that replaced it fired on
# nothing. A guard that looks right and does nothing is the defect this whole
# audit exists to remove, so it gets a test.
print("\n  9. inferred components are not reliable; convergence no longer gates")

_ref = pd.DataFrame(dict(peak_id=[1], voltage=[3.40],
                         is_shoulder=[False], is_truncated=[False]))
_cyc = list(range(1, 11))


def _tk(extra):
    _rows = []
    for _c in _cyc:
        _r = dict(cycle=_c, step="Charge", centre=3.40 + 0.002 * _c,
                  amplitude_area=50.0, sigma=0.02, fraction=0.5,
                  r_squared=0.99, reliable=True)
        _r.update(extra(_c))
        _rows.append(_r)
    _det = dt.Detection(name="t", reference_cycle=2,
                        peaks={(c, "Charge"): pd.DataFrame() for c in _cyc},
                        reference_peaks={"Charge": _ref,
                                         "Discharge": pd.DataFrame()})
    return an.track_peaks(pd.DataFrame(_rows), _det, verbose=False)


_t = _tk(lambda c: dict(is_inferred=(c > 5)))
_n = int((~_t.tracked_df["reliable"]).sum())
check("an inferred component is not reliable, on a bool column", _n >= 5,
      f"{_n} unreliable of {len(_t.tracked_df)}")

# 1.9.0.44: `converged` is lmfit's EXIT STATUS, not a statement about the
# fit's quality, and on NNM it was exactly `not hit_iteration_cap` — it
# demoted 405 of 405 and 462 of 462 components whose fits had the HIGHER
# median R2. It is measured and reported; it no longer decides.
_t = _tk(lambda c: dict(converged=(c <= 5)))
_n = int(_t.tracked_df["reliable"].sum())
check("convergence status does not demote a component",
      _n == len(_t.tracked_df),
      f"{_n} reliable of {len(_t.tracked_df)} — status is reported, not enforced")

# ...and the flag that replaced it demotes only when it is switched on.
_t = _tk(lambda c: dict(area_poorly_determined=(c > 5)))
_n = int(_t.tracked_df["reliable"].sum())
check("area determinacy is flagged, not enforced, by default",
      _n == len(_t.tracked_df) if not an.ENFORCE_AREA_DETERMINACY else _n <= 5,
      f"{_n} reliable of {len(_t.tracked_df)}; "
      f"ENFORCE_AREA_DETERMINACY={an.ENFORCE_AREA_DETERMINACY}")
_old = an.ENFORCE_AREA_DETERMINACY
an.ENFORCE_AREA_DETERMINACY = True
_t = _tk(lambda c: dict(area_poorly_determined=(c > 5)))
_n = int((~_t.tracked_df["reliable"]).sum())
an.ENFORCE_AREA_DETERMINACY = _old
check("...and demotes when it is switched on", _n >= 5,
      f"{_n} unreliable of {len(_t.tracked_df)}")

_t = _tk(lambda c: {})
_n = int(_t.tracked_df["reliable"].sum())
check("a frame stating neither flag keeps every component reliable",
      _n == len(_t.tracked_df),
      f"{_n} reliable of {len(_t.tracked_df)} — NaN must not read as True")


print("\n" + "=" * 66)
print("  " + ("ALL ANALYSIS UNIT TESTS PASS" if not fails
              else f"{len(fails)} FAILED: " + "; ".join(fails)))
print("=" * 66)
sys.exit(1 if fails else 0)
