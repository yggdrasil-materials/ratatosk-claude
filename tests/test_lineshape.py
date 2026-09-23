"""The lineshape: the split pseudo-Voigt, the sigma_g correction, and the
promise that `evaluate` draws the curve that was fitted.

Run as a script. Exits non-zero on the first hard failure.
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from lmfit.models import PseudoVoigtModel
from ratatosk import fitting as ft
from ratatosk.compat import trapezoid

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)

X = np.linspace(-2.0, 2.0, 400001)

def fwhm_of(y, x=X):
    h = y.max() / 2.0
    i = np.where(y > h)[0]
    return float(x[i[-1]] - x[i[0]])

print("\n--- the band model's peak limit IS the pseudo-Voigt ---")
# It was not: until 1.9.0.51 rect_pseudo_voigt used sigma in the Gaussian
# instead of sigma / sqrt(2 ln 2), so its w -> 0 limit was a different shape,
# up to 15% different and 17.7% wider at half maximum, while _derived went on
# reporting fwhm = 2 * sigma for it.
m = PseudoVoigtModel(); p = m.make_params()
worst = 0.0
for eta in (0.0, 0.25, 0.5, 0.75, 1.0):
    for s in (0.005, 0.02, 0.1):
        p['center'].set(0.0); p['sigma'].set(s)
        p['amplitude'].set(3.0); p['fraction'].set(eta)
        a = m.eval(p, x=X)
        for got in (ft.rect_pseudo_voigt(X, 3.0, 0.0, 0.0, s, eta),
                    ft.asym_rect_pseudo_voigt(X, 3.0, 0.0, 0.0, s, s, eta)):
            worst = max(worst, float(np.max(np.abs(a - got)) / a.max()))
check("w=0 reproduces PseudoVoigtModel", worst < 1e-12, f"worst rel diff {worst:.2e}")

# ...which is what makes the reported fwhm = 2 * sigma true.
for eta in (0.0, 0.5, 1.0):
    got = fwhm_of(ft.rect_pseudo_voigt(X, 1.0, 0.0, 0.0, 0.02, eta))
    check(f"fwhm = 2*sigma at eta={eta}", abs(got - 0.04) < 5e-4,
          f"{got:.5f} vs 0.04000")

print("\n--- the split shape is a strict generalisation ---")
worst = 0.0
for w in (0.0, 0.05, 0.3):
    for s in (0.005, 0.02, 0.1):
        for eta in (0.0, 0.5, 1.0):
            a = ft.rect_pseudo_voigt(X, 1.0, 0.0, w, s, eta)
            b = ft.asym_rect_pseudo_voigt(X, 1.0, 0.0, w, s, s, eta)
            worst = max(worst, float(np.max(np.abs(a - b)) / max(a.max(), 1e-30)))
check("sigma_r == sigma is the symmetric shape exactly", worst == 0.0,
      f"worst rel diff {worst:.2e}")

# amplitude is still the AREA, and the join at the centre is continuous.
for w in (0.0, 0.2):
    for sl, sr in ((0.01, 0.04), (0.05, 0.01)):
        y = ft.asym_rect_pseudo_voigt(X, 7.0, 0.0, w, sl, sr, 0.5)
        area = float(trapezoid(y, X))
        i = int(np.argmin(np.abs(X)))
        jump = abs(y[i] - y[i + 1]) / y.max()
        check(f"area conserved w={w} sl={sl} sr={sr}", abs(area - 7.0) < 0.05,
              f"{area:.4f}")
        check(f"continuous at the centre w={w} sl={sl} sr={sr}", jump < 1e-4,
              f"{jump:.1e}")

# fwhm of the split shape is sigma + sigma_r, which is what _derived returns.
got = fwhm_of(ft.asym_rect_pseudo_voigt(X, 1.0, 0.0, 0.0, 0.01, 0.04, 0.0))
check("split fwhm = sigma + sigma_r", abs(got - 0.05) < 1e-3, f"{got:.5f} vs 0.05")
_f, _h = ft._derived(0.01, 5.0, 0.5, 0.04)
check("_derived agrees", abs(_f - 0.05) < 1e-12, f"{_f:.5f}")

print("\n--- a symmetric curve is not made asymmetric ---")
# The model may be free to split; on a symmetric peak it must not want to.
rng = np.random.default_rng(7)
v = np.linspace(1.40, 1.75, 351)
truth = ft.rect_pseudo_voigt(v, 30.0, 1.55, 0.0, 0.004, 0.5)
y = truth + rng.normal(0, truth.max() * 0.01, v.size)
spec = ft.spec_for_profile([1.55], "sharp", asymmetry=True, baseline_degree=1)
r = ft.fit_half_cycle(v, y, spec, key=(1, "Charge"))
check("symmetric peak fits", bool(r.get("success")))
if r.get("success"):
    k = r["asymmetry_k"]
    check("asymmetry ratio comes back ~1", 0.6 < k < 1.7, f"k = {k:.3f}")
    check("area recovered", abs(r["components"][0]["amplitude_area"] - 30.0) / 30.0 < 0.05,
          f"{r['components'][0]['amplitude_area']:.2f} vs 30.00")
    check("not reported as pinned", not r["asymmetry_at_bound"])

print("\n--- an asymmetric curve is recovered ---")
truth = ft.asym_rect_pseudo_voigt(v, 30.0, 1.55, 0.0, 0.002, 0.010, 0.5)
y = truth + rng.normal(0, truth.max() * 0.01, v.size)
r = ft.fit_half_cycle(v, y, spec, key=(1, "Charge"))
check("asymmetric peak fits", bool(r.get("success")))
if r.get("success"):
    k = r["asymmetry_k"]
    check("ratio recovered (truth 5.0)", 3.0 < k < 8.0, f"k = {k:.3f}")
    check("area recovered", abs(r["components"][0]["amplitude_area"] - 30.0) / 30.0 < 0.10,
          f"{r['components'][0]['amplitude_area']:.2f} vs 30.00")
    # ...and the symmetric model should do measurably worse on it.
    r2 = ft.fit_half_cycle(v, y, ft.spec_for_profile([1.55], "sharp",
                                                     asymmetry=False,
                                                     baseline_degree=1),
                           key=(1, "Charge"))
    check("split beats symmetric on BIC", r["bic"] < r2["bic"],
          f"{r['bic']:.0f} vs {r2['bic']:.0f}")

print("\n--- evaluate draws the curve that was fitted ---")
# plots._FitView takes best_fit AND the residual panel from `evaluate`. Until
# 1.9.0.51 it rebuilt every component as a bare PseudoVoigtModel whatever the
# fit had used, so a band was redrawn as a tall narrow peak of the same area:
# measured on NMC111 cell A cycle 5 charge, 12% max residual fitted and 354%
# drawn, the composite 3.75x the height of the data.
for tag, kw in (("bare", {}),
                ("band", dict(band_width_max=0.5)),
                ("split", dict(asymmetry=True))):
    sp = ft.spec_for_profile([1.52, 1.58], "sharp", baseline_degree=1, **kw)
    model, params = ft.build_model(v, y, sp)
    res = model.fit(np.abs(y), params, x=v, max_nfev=sp.max_nfev,
                    fit_kws=dict(ftol=ft.FIT_TOLERANCE, xtol=ft.FIT_TOLERANCE))
    rr = ft.fit_half_cycle(v, y, sp, key=(1, "Charge"))
    if not rr.get("success"):
        check(f"{tag}: fits", False); continue
    drawn = ft.evaluate(rr, v)["total"]
    truth_curve = res.eval(x=v)
    # Compare the two REBUILD paths on the same parameters, which is the
    # promise: rebuild what lmfit would have evaluated.
    comps = res.eval_components(x=v)
    rebuilt = ft.evaluate(dict(components=[
        dict(peak_index=i,
             centre=res.params[f"p{i}_center"].value,
             sigma=res.params[f"p{i}_sigma"].value,
             sigma_r=(res.params[f"p{i}_sigma_r"].value
                      if f"p{i}_sigma_r" in res.params
                      else res.params[f"p{i}_sigma"].value),
             amplitude_area=res.params[f"p{i}_amplitude"].value,
             fraction=res.params[f"p{i}_fraction"].value,
             band_width=(res.params[f"p{i}_width"].value
                         if f"p{i}_width" in res.params else 0.0))
        for i in (0, 1)],
        baseline_coeffs={k: p.value for k, p in res.params.items()
                         if k.startswith("bg_")}), v)["total"]
    amp = float(np.abs(y).max() - np.abs(y).min())
    err = float(np.max(np.abs(truth_curve - rebuilt)) / amp)
    check(f"{tag}: evaluate == lmfit's own composite", err < 1e-9,
          f"max diff {err*100:.4f}% of amplitude")

print("\n--- the profile chooses the model ---")
check("sharp is asymmetric", ft.PROFILE_SPECS["sharp"]["asymmetry"] is True)
check("moderate is not", ft.PROFILE_SPECS["moderate"]["asymmetry"] is False)
check("broad is not", ft.PROFILE_SPECS["broad"]["asymmetry"] is False)
check("spec_for_profile carries it",
      ft.spec_for_profile([1.5], "sharp").asymmetry is True
      and ft.spec_for_profile([3.5], "broad").asymmetry is False)
check("one shared parameter, not one per component",
      ft.ASYMMETRY_SHARED is True)
sp = ft.spec_for_profile([1.50, 1.55, 1.60], "sharp")
_m, _p = ft.build_model(v, np.abs(y), sp)
n_vary = sum(1 for q in _p.values() if q.vary)
sp2 = ft.spec_for_profile([1.50, 1.55, 1.60], "sharp", asymmetry=False)
_m2, _p2 = ft.build_model(v, np.abs(y), sp2)
n_vary2 = sum(1 for q in _p2.values() if q.vary)
check("three components cost ONE extra parameter", n_vary - n_vary2 == 1,
      f"{n_vary2} -> {n_vary}")

print("\n--- the four numbers R2 hides ---")
good = ft.rect_pseudo_voigt(v, 30.0, 1.55, 0.0, 0.004, 0.5)
q = ft.fit_quality(v, good, good, np.zeros_like(v))
check("a perfect fit scores 1.00 height", abs(q["height_ratio"] - 1.0) < 1e-9)
check("...and no overshoot", q["overshoot"] == 0.0)
short = ft.rect_pseudo_voigt(v, 30.0, 1.55, 0.0, 0.012, 0.5)
q = ft.fit_quality(v, good, short, np.zeros_like(v))
check("a fit too short reads below 1", q["height_ratio"] < 0.5,
      f"{q['height_ratio']:.2f}")
tall = ft.rect_pseudo_voigt(v, 60.0, 1.55, 0.0, 0.004, 0.5)
q = ft.fit_quality(v, good, tall, np.zeros_like(v))
check("a fit too tall reads above 1", q["height_ratio"] > 1.5,
      f"{q['height_ratio']:.2f}")
check("...and is caught overshooting", q["overshoot"] > 0.5,
      f"{q['overshoot']:.2f}")
z_noise = ft._runs_z(rng.normal(0, 1, 400))
z_struct = ft._runs_z(np.sin(np.linspace(0, 4 * np.pi, 400)))
check("runs z is quiet on noise", abs(z_noise) < 3, f"z = {z_noise:.1f}")
check("runs z fires on structure", z_struct < -15, f"z = {z_struct:.1f}")

print("\n" + "=" * 66)
if FAILS:
    print(f"  {len(FAILS)} FAILED: {FAILS}")
    print("=" * 66)
    sys.exit(1)
print("  LINESHAPE OK")
print("=" * 66)
