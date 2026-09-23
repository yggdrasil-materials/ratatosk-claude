"""
Every figure still draws, from 1.9.0 objects, through 1.8.7's plotting code.

`plots.py` and `cycling.py` are ports: the drawing code is 1.8.7's, extracted
programmatically, and the regression that matters is visual. What this test can
check mechanically is that all 24 entry points run to completion on real cells
through the adapters — which is what caught the four defects listed below —
and that the adapters produce the shapes the ported code reads.

Defects this test found, all in code paths the notebook never exercised in this
order:

  plot_fit_quality selected its worst-converged half-cycle from a column named
      `success`; the adapter was writing `fit_success`.
  1.9.0 prefixed its polynomial baseline `bkg_`, and plot_fit_quality decides
      which component is the baseline by testing `'bg_' in name`. The baseline
      would have been drawn as a filled peak. The prefix is now `bg_`.
  Cell 9b used `palette` without ever assigning it, resolving to whatever an
      earlier cell had left in globals.
  Cell 12 read `is_anode` in its >100%-efficiency notice but assigned it later
      in the same loop — undefined on the first dataset, and the previous
      dataset's value thereafter.
"""
import sys, os, glob, warnings, tempfile
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd

from ratatosk import io, signal as sg, detect as dt, fitting as ft
from ratatosk import analyse as an, plots as pl, cycling as cy

UP = "/mnt/user-data/uploads/Python Scripting/Example Battery Data"
FILES = [("NNM_cellA", "JQ-P3-NaNiMnO2-35%-2-4.2V-0.1C-A-20062025.xlsx", "Positive"),
         ("NNM_cellB", "JQ-P3-NaNiMnO2-35%-2-4.2V-0.1C-B-20062025.xlsx", "Positive")]
MAX_CYCLE = 12
fails = []


def run(label, fn):
    try:
        out = fn()
        plt.close("all")
        print(f"    OK    {label}")
        return out
    except Exception as exc:                        # noqa: BLE001
        print(f"    FAIL  {label}: {type(exc).__name__}: {exc}")
        fails.append(label)
        plt.close("all")
        return None


if not glob.glob(f"{UP}/*.xlsx"):
    print("  SKIP  (example data not staged)")
    sys.exit(0)

OUT = tempfile.mkdtemp(prefix="ratatosk_figs_")
ED, UPARAMS, first = {}, {}, None
for name, f, etype in FILES:
    ds = io.read_neware(f"{UP}/{f}", name=name, electrode_type=etype,
                        verbose=False)
    ED[name] = ds.frame
    UPARAMS.update(pl.as_user_parameters(ds, composition="P3-NaNiMnO2",
                                         key_cycles=[1, 5, 10, 20, 40]))
    UPARAMS[name].update(active_mass_mg=5.0, active_material_fraction="90")
    first = first or ds

# --- the dQ/dV chain, on one cell ---------------------------------------
prof = sg.classify_dqdv_profile(first.frame, verbose=False)
params = sg.auto_preprocess_params(prof)
win = sg.voltage_window(first)
signals = {k: sg.half_cycle_report(first, *k, params, window=win)
           for k in first.half_cycle_keys() if k[0] <= MAX_CYCLE}
R, band = an.integrity_report(signals, window=win, name=first.name,
                              verbose=False)
det = dt.detect_all(signals, name=first.name, integrity=band, verbose=False)
jobs = [(s.voltage, s.dqdv, ft.FitSpec(det.peaks[k]["voltage"].values), k)
        for k, s in sorted(signals.items())
        if s.voltage.size and not det.peaks.get(k, pd.DataFrame()).empty]
fits = ft.fit_many(jobs, verbose=False)
P = an.parameters_frame(fits, det)
tk = an.track_peaks(P, det, verbose=False)
dv = an.delta_v(tk, is_anode=first.labels_swapped, verbose=False)
att = an.capacity_attribution(tk, verbose=False)

PD = pl.as_processed_dqdv(first, signals, params, window=win, profile=prof)
DP = pl.as_detected_peaks(det)
FR = pl.as_fit_results(fits, signals, P, name=first.name)
TR = pl.as_tracked(tk)

print("\n  adapters produce the shapes the ported code reads")
shape_ok = (
    set(PD[first.name]) >= {"data", "voltage_range", "parameters_used"}
    and set(DP[first.name]) >= {"peaks", "reference_cycle", "reference_peaks"}
    and set(FR[first.name]) >= {"fits", "parameters_df", "fit_summary"}
    and set(TR[first.name]) >= {"tracked_df", "summary", "reference_peaks"}
    and "success" in FR[first.name]["fit_summary"].columns)
print(f"    {'PASS' if shape_ok else 'FAIL'}  1.8.7 dictionary shapes")
if not shape_ok:
    fails.append("adapter shapes")

# The _FitView must answer what plot_fit_quality asks of a ModelResult, and
# answer it with the curve that was actually fitted.
k0 = next(k for k in sorted(FR[first.name]["fits"])
          if FR[first.name]["fits"][k]["lmfit_result"] is not None)
view = FR[first.name]["fits"][k0]["lmfit_result"]
comps = view.eval_components(x=signals[k0].voltage)
rebuilt = sum(comps.values())
view_ok = (np.abs(rebuilt - view.best_fit).max() < 1e-9
           and any(c.startswith("bg_") for c in comps))
print(f"    {'PASS' if view_ok else 'FAIL'}  _FitView rebuilds the fit without "
      f"a ModelResult   {len(comps)} components, baseline prefix "
      f"{'bg_' if any(c.startswith('bg_') for c in comps) else 'MISSING'}")
if not view_ok:
    fails.append("_FitView")

print("\n  dQ/dV figures")
for label, fn in [
    ("all cycles", lambda: pl.plot_dqdv_all_cycles(PD, UPARAMS, save_location=OUT)),
    ("key cycles", lambda: pl.plot_dqdv_key_cycles_combined(PD, UPARAMS, save_location=OUT)),
    ("key cycles, split", lambda: pl.plot_dqdv_key_cycles_split(PD, UPARAMS, save_location=OUT)),
    ("waterfall, charge", lambda: pl.plot_dqdv_waterfall(PD, UPARAMS, step="Charge", save_location=OUT)),
    ("waterfall, discharge", lambda: pl.plot_dqdv_waterfall(PD, UPARAMS, step="Discharge", save_location=OUT)),
    ("heatmap, charge", lambda: pl.plot_dqdv_heatmap(PD, UPARAMS, step="Charge", save_location=OUT)),
    ("heatmap, discharge", lambda: pl.plot_dqdv_heatmap(PD, UPARAMS, step="Discharge", save_location=OUT)),
    ("preprocessing QC", lambda: pl.plot_preprocessing_qc(PD, UPARAMS, cycle=2)),
    ("detected peaks", lambda: pl.plot_detected_peaks(PD, DP, UPARAMS, save_location=OUT)),
    ("fit quality", lambda: pl.plot_fit_quality(PD, DP, FR, UPARAMS, save_location=OUT)),
    ("tracked trends", lambda: pl.plot_tracked_trends(TR, UPARAMS, save_location=OUT)),
    ("delta-V", lambda: pl.plot_delta_v(
        {first.name: dict(pairs=dv.pairs, delta_v_df=dv.df,
                          delta_v_changes=dv.changes,
                          delta_v_windows=dv.windows)}, UPARAMS,
        save_location=OUT)),
    ("capacity attribution", lambda: pl.plot_capacity_attribution(
        {first.name: att}, TR, UPARAMS, save_location=OUT)),
]:
    run(label, fn)

print("\n  cycling figures")
tables = run("cycling summary",
             lambda: cy.cycling_summary(ED, UPARAMS, save_location=OUT))
for label, fn in [
    ("voltage profiles", lambda: cy.voltage_profiles(ED, UPARAMS, save_location=OUT)),
    ("voltage profiles, key", lambda: cy.voltage_profiles_key(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("cycle life", lambda: cy.cycle_life(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("comparative capacity", lambda: cy.comparative_capacity(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("capacity retention", lambda: cy.capacity_retention(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("fade rate", lambda: cy.fade_rate(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("power and energy", lambda: cy.power_and_energy(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("average discharge voltage", lambda: cy.average_discharge_voltage(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("energy efficiency", lambda: cy.energy_efficiency(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
    ("rate capability", lambda: cy.rate_capability(ED, UPARAMS, save_location=OUT, all_cycle_tables=tables)),
]:
    run(label, fn)

n = len(glob.glob(os.path.join(OUT, "*")))
print(f"\n  {n} files written to {OUT}")
print("=" * 66)
print("  " + ("ALL FIGURES DRAW" if not fails
              else f"{len(fails)} FAILED: " + "; ".join(fails)))
print("=" * 66)
sys.exit(1 if fails else 0)
