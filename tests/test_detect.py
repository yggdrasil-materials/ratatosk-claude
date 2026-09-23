"""
Unit tests for detection: the parts that must not depend on a label.

The port fidelity of the detector is checked in tests/test_detect_fidelity.py
against 1.8.7's own peak lists. What is checked HERE is the behaviour 1.8.7 did
not have: that orientation is measured rather than assumed, that the reference
cycle is chosen on evidence, and that a peak cut in half by the voltage window
is discarded rather than fitted.
"""
import sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from ratatosk import detect as dt
from ratatosk.synthetic import pseudo_voigt

fails = []


def check(label, cond, detail=""):
    print(f"    {'PASS' if cond else 'FAIL'}  {label}"
          + (f"   {detail}" if detail else ""))
    if not cond:
        fails.append(label)


# -- 1. Orientation is a property of the curve, not of a label ---------------
print("\n  1. orientation is measured, not assumed")
v = np.linspace(3.0, 4.0, 800)
y = (pseudo_voigt(v, 3.35, 0.020, 0.4, 30.0)
     + pseudo_voigt(v, 3.70, 0.035, 0.4, 45.0))
up = dt.detect_peaks_single(v, y)
down = dt.detect_peaks_single(v, -y)          # the same half-cycle, negated
check("a negated curve gives the same peak voltages",
      len(up) == len(down) == 2
      and np.allclose(up["voltage"].values, down["voltage"].values),
      f"{np.round(up['voltage'].values, 4)} vs "
      f"{np.round(down['voltage'].values, 4)}")
check("an explicit orientation still overrides",
      len(dt.detect_peaks_single(v, y, orientation=-1.0)) != 2)

# -- 2. The reference-cycle selector ----------------------------------------
print("\n  2. the reference cycle is chosen on evidence")
cycles = [1, 2, 3, 4, 5]
allc = lambda c: True

c, why, _sev = dt.choose_reference_cycle(cycles, allc)
check("no integrity check -> 1.8.6 behaviour", c == 2, why)

band = {}
for cy in cycles:
    for st in ("Charge", "Discharge"):
        band[(cy, st)] = "clean"
I = lambda cy, st: band.get((cy, st), "unknown")

c, why, _sev = dt.choose_reference_cycle(cycles, allc, integrity=I)
check("all clean -> the default", c == 2, why)

band[(2, "Charge")] = "ANOMALOUS"
c, why, _sev = dt.choose_reference_cycle(cycles, allc, integrity=I)
check("default anomalous -> lowest sound above it", c == 3, why)

band[(3, "Charge")] = band[(4, "Discharge")] = "ANOMALOUS"
c, why, _sev = dt.choose_reference_cycle(cycles, allc, integrity=I)
check("skips every anomalous cycle", c == 5, why)

for cy in (3, 4, 5):
    for st in ("Charge", "Discharge"):
        band[(cy, st)] = "ANOMALOUS"
c, why, _sev = dt.choose_reference_cycle(cycles, allc, integrity=I)
check("nothing above -> falls back BELOW the default", c == 1, why)

band[(1, "Charge")] = "ANOMALOUS"
c, why, _sev = dt.choose_reference_cycle(cycles, allc, integrity=I)
check("nothing at all -> says so rather than silently defaulting",
      c == 2 and "NO cycle passes" in why, why)

band = {k: "too few records" for k in band}
c, why, _sev = dt.choose_reference_cycle(cycles, allc, integrity=I)
check("'too few records' is not evidence of soundness",
      "NO cycle passes" in why, why)

c, why, _sev = dt.choose_reference_cycle(cycles, lambda cy: cy != 2,
                                   integrity=lambda cy, st: "clean")
check("a cycle with no half-cycles is not eligible", c == 3, why)

# -- 3. Peaks at the window edge --------------------------------------------
# Two mechanisms, and it is worth being clear about which does the work.
#
# `_assess_truncation` only fires when scipy's `peak_widths` CLAMPS a
# half-maximum crossing at the array end. On a smooth flank it does not clamp:
# truncating the array raises the right-hand prominence base, which lowers the
# half-prominence level, which returns a narrower SYMMETRIC width — so the
# assessment never sees an asymmetry to judge. Measured on the real runs, the
# flag fires 3 times in 893 fitted rows for P3 cell A and 1 in 468 for the NNM
# triplicate: it is not what protects the fit.
#
# What protects the fit is `find_peaks`. A peak cut at or past its centre has
# its maximum at the array end, so it is not a local maximum and has no
# measurable width, and it is never detected. That is the behaviour tested
# here. The truncation logic remains as a flag for the cases where the clamp
# does happen, and is exercised by tests/test_detect_fidelity.py against those
# four real half-cycles.
print("\n  3. a peak the window cuts in half is not detected at all")
full = np.linspace(3.0, 4.0, 800)
yf = pseudo_voigt(full, 3.90, 0.030, 0.4, 40.0)
whole = dt.detect_peaks_single(full, yf)
kept = dt.detect_peaks_single(full[full <= 3.95], yf[full <= 3.95])
half = dt.detect_peaks_single(full[full <= 3.90], yf[full <= 3.90])
check("the whole peak is found and not flagged",
      len(whole) == 1 and not bool(whole["is_truncated"].iloc[0]))
check("a peak with a clipped flank but a real maximum is kept",
      len(kept) == 1 and abs(kept["voltage"].iloc[0] - 3.90) < 0.002)
check("a peak cut at its centre is dropped", len(half) == 0,
      f"{len(half)} kept")

# -- 4. detect_all over a dataset -------------------------------------------
print("\n  4. detect_all reports what it did")
from ratatosk.signal import HalfCycleSignal
sigs = {}
for cy in (1, 2, 3):
    for st, sgn in (("Charge", +1.0), ("Discharge", -1.0)):
        s = HalfCycleSignal(cycle=cy, step=st, direction=sgn)
        s.voltage, s.dqdv = v, sgn * y
        sigs[(cy, st)] = s
sigs[(2, "Charge")].voltage = np.empty(0)     # a half-cycle with no curve
det = dt.detect_all(sigs, name="synthetic", verbose=False)
check("an empty half-cycle is recorded as skipped, not as zero peaks",
      list(det.skipped) == [(2, "Charge")], str(det.skipped))
check("charge and discharge give the same peaks",
      np.allclose(det.reference_voltages("Discharge"),
                  det.peaks[(1, "Charge")]["voltage"].values))
det2 = dt.detect_all(sigs, name="synthetic", reference_cycle=3, verbose=False)
check("an explicit reference cycle is honoured",
      det2.reference_cycle == 3 and det2.reference_reason == "set explicitly")
det3 = dt.detect_all(sigs, name="synthetic", reference_cycle=99, verbose=False)
# The NEAREST available cycle. 1.8.7 took the second cycle in the record
# regardless of what was asked for, which for a request of 99 out of 1-3 is
# an arbitrary answer dressed as an adjustment.
check("an absent one is adjusted to the nearest, and says so",
      det3.reference_cycle == 3 and "not present" in det3.reference_reason,
      det3.reference_reason)
det4 = dt.detect_all(sigs, name="synthetic", reference_cycle=0, verbose=False)
check("and adjusts downward the same way",
      det4.reference_cycle == 1, str(det4.reference_cycle))
det5 = dt.detect_all({}, name="empty", reference_cycle=2, verbose=False)
check("an empty dataset with an explicit reference cycle does not raise",
      det5.reference_reason == "no cycles available", det5.reference_reason)

print("\n" + "=" * 64)
print("  " + ("ALL DETECTION UNIT TESTS PASS" if not fails
              else f"{len(fails)} FAILED: " + "; ".join(fails)))
print("=" * 64)
sys.exit(1 if fails else 0)
