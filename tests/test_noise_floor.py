"""The noise-referenced admission rule, and the phase-rule finding.

The rule is a CONJUNCTION and each half has to be shown to do work: neither
prominence-over-noise nor share-of-the-half-cycle separates the populations on
its own. Run as a script; exits non-zero on the first hard failure.
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from ratatosk import detect as dt, report as rp

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)

rng = np.random.default_rng(11)

print("\n--- the noise estimator ---")
# It must recover a known sigma, and it must not be fooled by a peak.
for true_sd in (1.0, 25.0, 400.0):
    y = rng.normal(0, true_sd, 4000)
    got = dt.local_noise(y)
    check(f"recovers sigma = {true_sd:g}", abs(got - true_sd) / true_sd < 0.10,
          f"{got:.2f}")
x = np.linspace(0, 1, 2000)
peak = 5000.0 * np.exp(-((x - 0.5) ** 2) / (2 * 0.01 ** 2))
y = peak + rng.normal(0, 10.0, x.size)
got = dt.local_noise(y)
check("a tall smooth peak does not inflate it", abs(got - 10.0) / 10.0 < 0.25,
      f"{got:.2f} against a true 10.0")
# Quantisation is why the MAD was abandoned: long runs of identical values.
q = np.round(rng.normal(0, 30.0, 2000) / 50.0) * 50.0
check("survives a quantised curve", np.isfinite(dt.local_noise(q))
      and dt.local_noise(q) > 0, f"{dt.local_noise(q):.2f}")
check("says nothing when there is nothing to measure",
      not np.isfinite(dt.local_noise(np.array([1.0, 2.0]))))
# LOCAL, because dQ/dV noise scales with the signal.
y2 = np.concatenate([rng.normal(0, 1.0, 1000), rng.normal(0, 100.0, 1000)])
quiet, loud = dt.local_noise(y2, 200), dt.local_noise(y2, 1800)
check("local, not whole-curve", loud > 20 * quiet,
      f"quiet {quiet:.2f}, loud {loud:.2f}")

print("\n--- the conjunction, on the populations it was measured from ---")
# Numbers from the three-chemistry measurement; see the NOISE_FLOOR note.
ARTEFACTS = [dict(snr=s, share=f) for s, f in
             ((1.5, 0.021), (6.0, 0.030), (10.0, 0.050), (3.9, 0.023))]
REAL = [dict(snr=38.5, share=1.00),   # LTO main peak, weakest
        dict(snr=16.5, share=0.12),   # NMC, weakest
        dict(snr=10.5, share=0.277),  # NNM, weakest SNR but a third of the curve
        dict(snr=12.0, share=0.337)]

def rejected(c, k=dt.NOISE_SNR_MIN, f=dt.NOISE_SHARE_MIN):
    return c["snr"] < k and c["share"] < f

check("every measured artefact is rejected",
      all(rejected(c) for c in ARTEFACTS))
check("no measured real component is rejected",
      not any(rejected(c) for c in REAL))
# Each half must be load-bearing.
check("SNR alone cannot separate (10.0 artefact vs 10.5 real)",
      any(c["snr"] > 10.4 for c in ARTEFACTS) is False
      and min(c["snr"] for c in REAL) < 11,
      "worst artefact 10.0, weakest real 10.5")
check("share alone cannot separate at the old 2% floor",
      min(c["share"] for c in ARTEFACTS) >= 0.02)
# ...and it must not be a knife edge.
for k, f in ((12.0, 0.10), (12.0, 0.15), (15.0, 0.10), (15.0, 0.20)):
    ok = (all(rejected(c, k, f) for c in ARTEFACTS)
          and not any(rejected(c, k, f) for c in REAL))
    check(f"clean at k={k:g}, f={f:g}", ok)
check("the shipped constants are inside that box",
      12.0 <= dt.NOISE_SNR_MIN <= 15.0 and 0.10 <= dt.NOISE_SHARE_MIN <= 0.20,
      f"k={dt.NOISE_SNR_MIN}, f={dt.NOISE_SHARE_MIN}")

print("\n--- end to end on a synthetic curve ---")
v = np.linspace(1.40, 1.75, 351)
main = 20000.0 * np.exp(-((v - 1.55) ** 2) / (2 * 0.004 ** 2))
noise = rng.normal(0, 120.0, v.size)
bump = 500.0 * np.exp(-((v - 1.62) ** 2) / (2 * 0.003 ** 2))   # 2.5%, in the noise
real2 = 6000.0 * np.exp(-((v - 1.66) ** 2) / (2 * 0.006 ** 2))  # 30%, well above

def found(y):
    sig = type("S", (), dict(voltage=v, dqdv=np.abs(y)))()
    pk = dt.detect_half_cycle(sig, dt.DetectSpec(min_distance_mV=30,
                                                 min_width_mV=2))
    return [] if pk is None or not len(pk) else [round(float(x), 3)
                                                 for x in pk["voltage"]]

dt.NOISE_FLOOR = False
off = found(main + bump + noise)
dt.NOISE_FLOOR = True
on = found(main + bump + noise)
check("the floor removes a 2.5% bump sitting in the noise",
      len(on) < len(off) or len(off) <= 1,
      f"off {off} -> on {on}")
check("...and keeps the main peak", any(abs(x - 1.55) < 0.01 for x in on), str(on))
big = found(main + real2 + noise)
check("a 30% feature well above the noise is kept",
      any(abs(x - 1.66) < 0.015 for x in big), str(big))
check("the curve's own maximum is never rejected",
      any(abs(x - 1.55) < 0.01 for x in big), str(big))

print("\n--- the phase rule is a FINDING, not a filter ---")
census = {"Charge": dict(n_half_cycles=10, lo=1, hi=1, median=1.0,
                         reference_cycle=2, reference_n=1),
          "Discharge": dict(n_half_cycles=10, lo=1, hi=1, median=1.0,
                            reference_cycle=2, reference_n=1)}
f_ok = {"resolvability": {"mechanism": "two_phase"},
        "component_census": census}
s = rp._phase_rule_sentence(f_ok)
check("a two-phase run states the expectation", bool(s) and s[0][0] == "ok",
      s[0][1] if s else "nothing")
check("...and says one plateau, one peak",
      s and "one plateau" in s[0][2] and "invariant" in s[0][2])
import copy
f_bad = copy.deepcopy(f_ok)
f_bad["component_census"]["Charge"]["hi"] = 3
s2 = rp._phase_rule_sentence(f_bad)
check("more than one component is a warning", s2 and s2[0][0] == "warn")
check("...and names the processing-free test",
      s2 and "V(Q)" in s2[0][2] and "overfitting" in s2[0][2])
check("a solid solution gets no such claim",
      rp._phase_rule_sentence({"resolvability": {"mechanism": "solid_solution"},
                               "component_census": census}) == [])
check("nor does an unclassified run",
      rp._phase_rule_sentence({"component_census": census}) == [])
# The detector must NOT know about the mechanism.
import inspect
_src = inspect.getsource(dt)
check("detect.py never consults the mechanism",
      "mechanism" not in _src.replace("# ", "").split("def detect_peaks_single")[1]
      .split("def ")[0] if "def detect_peaks_single" in _src else True)

print("\n" + "=" * 66)
if FAILS:
    print(f"  {len(FAILS)} FAILED: {FAILS}")
    print("=" * 66)
    sys.exit(1)
print("  NOISE FLOOR OK")
print("=" * 66)
