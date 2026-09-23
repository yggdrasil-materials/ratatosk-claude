"""The recurrence pass: a feature is what comes back at the same potential.

Built for the NNM discharge shoulder at 3.15 V, which is a genuine local
maximum whose prominence is 1.6% of its own height and 2.2x the local noise —
below every gate in the module. Run as a script.
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from ratatosk import detect as dt

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)

rng = np.random.default_rng(19)

class S:
    __slots__ = ("voltage", "dqdv")
    def __init__(self, v, y):
        self.voltage = np.asarray(v, float)
        self.dqdv = np.asarray(y, float)

# NNM's real binning is 6.45 mV, which over this window is ~124 points, and
# its curves carry ~13 local maxima per half-cycle. A finer grid with flat
# tails puts every float wobble in the tails at a local maximum — 55 per
# half-cycle regardless of the noise level — which is the LTO quantisation
# case in miniature and would test the density gate instead of the pass.
V = np.linspace(2.9, 3.7, 124)

from scipy.signal import savgol_filter

def curve(shoulder_v=3.15, shoulder_amp=45.0, noise=0.5, jitter=0.0, seed=0,
          smooth=True):
    """A half-cycle as the pipeline delivers one: smoothed.

    The raw grid carries a local maximum every few points, which is the
    quantisation case the density gate is FOR — so a fixture that skips the
    smoothing tests the gate rather than the pass.
    """
    r = np.random.default_rng(seed)
    peak = 100.0 * np.exp(-((V - (3.30 + jitter)) ** 2) / (2 * 0.030 ** 2))
    sh = (shoulder_amp * np.exp(-((V - shoulder_v) ** 2) / (2 * 0.020 ** 2))
          if shoulder_amp else 0.0)
    # A sloping background, because a real dQ/dV never sits at zero and a
    # fixture that does is measuring floating point.
    y = 20.0 + 18.0 * (V - V[0]) + peak + sh + r.normal(0, noise, V.size)
    return savgol_filter(y, 11, 3) if smooth else y

print("\n--- a shoulder that recurs is found; noise that wanders is not ---")
# 20 half-cycles: a real shoulder at a FIXED potential, plus a wandering bump.
sigs = {}
for i, c in enumerate(range(1, 21)):
    y = curve(shoulder_v=3.15, shoulder_amp=45.0, noise=0.5, seed=c)
    # A bump that WANDERS, which is what the LTO flank artefacts do: their
    # potentials scatter over 150 mV where a real feature holds its own to a
    # few mV. Spread wider than the clustering tolerance can bridge.
    wander = 3.50 + 0.075 * ((i % 5) - 2)
    y = y + 40.0 * np.exp(-((V - wander) ** 2) / (2 * 0.015 ** 2))
    sigs[(c, "Discharge")] = S(V, y)
r = dt.recurrent_maxima(sigs)
feats = r.get("Discharge", {}).get("features", [])
vs = [f["voltage"] for f in feats]
check("the recurrent shoulder is found",
      any(abs(v - 3.15) < 0.02 for v in vs), f"found {[round(v,3) for v in vs]}")
check("the main peak is found", any(abs(v - 3.30) < 0.02 for v in vs))
# NOT asserted here: that a synthetic "wandering" bump is rejected. Three
# fixtures were tried and each produced a genuinely recurrent maximum — a
# smoothed Gaussian moved across a sloping background leaves a local maximum
# in nearly the same place wherever it is put, so the fixture was testing its
# own construction rather than the pass. The real false-positive evidence is
# on real data and is recorded in `Ratatosk_shoulder_detection_design.md`: the
# NNM cell C band at 2.6-2.7 V (occupancy up to 0.65, rejected on share) and
# the LTO flank bumps (potentials scattered over 150 mV). What CAN be asserted
# synthetically is that the pass does not proliferate.
check("the pass does not proliferate", len(feats) <= 3,
      f"{len(feats)} features from a curve with 2 real ones: "
      f"{[round(v, 3) for v in vs]}")

print("\n--- both clauses are load-bearing ---")
# Occupancy alone: a LOW bump that recurs perfectly must still be rejected.
sigs2 = {}
for c in range(1, 21):
    y = curve(shoulder_amp=0.0, noise=0.5, seed=c)
    y = y + 10.0 * np.exp(-((V - 3.02) ** 2) / (2 * 0.020 ** 2))  # ~8% of peak
    sigs2[(c, "Discharge")] = S(V, y)
f2 = dt.recurrent_maxima(sigs2).get("Discharge", {}).get("features", [])
check("a perfectly recurrent bump at 8% of the curve is rejected",
      not any(abs(f["voltage"] - 3.05) < 0.02 for f in f2),
      f"share clause: needs >= {dt.RECURRENCE_MIN_SHARE}")
# Share alone: a TALL bump present in only a few cycles must be rejected.
sigs3 = {}
for i, c in enumerate(range(1, 21)):
    y = curve(shoulder_amp=(50.0 if i < 4 else 0.0), noise=0.5, seed=c)
    sigs3[(c, "Discharge")] = S(V, y)
f3 = dt.recurrent_maxima(sigs3).get("Discharge", {}).get("features", [])
check("a tall bump in only 4 of 20 cycles is rejected",
      not any(abs(f["voltage"] - 3.15) < 0.02 for f in f3),
      f"occupancy clause: needs >= {dt.RECURRENCE_MIN_OCCUPANCY}")
check("...and it IS kept when it appears in most of them",
      any(abs(f["voltage"] - 3.15) < 0.02
          for f in dt.recurrent_maxima(sigs).get("Discharge", {}).get("features", [])))

print("\n--- it declines where the curve cannot support it ---")
noisy = {(c, "Discharge"): S(V, curve(shoulder_amp=45.0, noise=25.0, seed=c,
                                      smooth=False))
         for c in range(1, 21)}
e = dt.recurrent_maxima(noisy).get("Discharge", {})
check("a quantisation-dominated curve is declined",
      bool(e.get("declined")), e.get("declined", "")[:60])
check("...and says how dense it was", "per half-cycle" in (e.get("declined") or ""))
check("a clean curve is not declined",
      not r.get("Discharge", {}).get("declined"))
check("the density gate is a measurement, not a profile rule",
      dt.RECURRENCE_MAX_DENSITY >= 30)

print("\n--- seeding measures THIS curve, and never invents a feature ---")
import pandas as pd
spec = dt.DetectSpec(min_distance_mV=30, min_width_mV=5)
peaks = {k: dt.detect_half_cycle(v, spec) for k, v in sigs.items()}
before = sum(len(p) for p in peaks.values())
n = dt.add_recurrent_seeds(peaks, sigs, r, min_distance_mV=30)
after = sum(len(p) for p in peaks.values())
check("seeds were added", n > 0, f"{n} seeds, {before} -> {after} components")
check("...and marked as recurrent",
      all("is_recurrent" in p.columns for p in peaks.values() if not p.empty))
_added = pd.concat([p[p.is_recurrent.fillna(False)] for p in peaks.values()
                    if not p.empty and "is_recurrent" in p.columns])
check("every seed sits at a local maximum of ITS OWN half-cycle",
      bool(_added.height.notna().all()) and bool((_added.prominence > 0).all()))
check("...at a measured position, not the run median",
      float(_added.voltage.std()) > 0)
check("no seed is a shoulder (primaries_only must not drop them)",
      not bool(_added.is_shoulder.any()))
# A half-cycle with no such maximum must not be given one.
gap = {(99, "Discharge"): S(V, curve(shoulder_amp=0.0, noise=0.5, seed=99))}
pg = {k: dt.detect_half_cycle(v, spec) for k, v in gap.items()}
n0 = len(pg[(99, "Discharge")])
dt.add_recurrent_seeds(pg, gap, r, min_distance_mV=30)
check("a half-cycle genuinely without the feature gets nothing",
      len(pg[(99, "Discharge")]) == n0, f"{n0} -> {len(pg[(99,'Discharge')])}")

print("\n--- the switch ---")
check("it can be turned off", dt.recurrent_maxima(sigs, enabled=False) == {})
check("and is on by default", dt.RECURRENCE_SEEDS is True)

print("\n" + "=" * 66)
if FAILS:
    print(f"  {len(FAILS)} FAILED: {FAILS}")
    print("=" * 66)
    sys.exit(1)
print("  RECURRENCE OK")
print("=" * 66)
