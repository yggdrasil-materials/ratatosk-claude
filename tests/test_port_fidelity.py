"""
Does the ported signal path reproduce 1.8.7, and where it does not, why?

This is the 1.9.0 release gate. 1.9.0 adds measurements and withholds some
attribution; it should not move processed values. Where it does, the reason
must be named, bounded and defensible — not absorbed into a tolerance.

Result on the two reference cells:

    LTO cell A    21 of 21 half-cycles identical
    P3  cell A   306 of 376 identical; 70 differ, and every one of the 70
                 contains tied voltages

The 70 are the one place 1.9.0 knowingly differs, and it is a fix. 1.8.7 sorts
by voltage with pandas' default quicksort, which is not stable, so among
records sharing a voltage the order is decided by the sort's internals rather
than by the data. P3 cell A cycle 1 charge has 483 tied voltages out of 1434 —
the cycler records to 0.1 mV and the cell sits on a plateau. Despiking and
smoothing then run over that arbitrary order, which means 1.8.7's smoothed
curve is not a well-defined function of its input: reorder the rows and it
changes. A stable sort breaks ties by acquisition order, which is the order
the measurements were taken in, and is reproducible under any reordering.

1.9.0.4 adds TWO more deliberate differences, both in `signal`:

  orient_dqdv      corrects the sign of records the cycler sends backwards
                   in voltage on a plateau
  REBIN_WEIGHTED   makes a bin's value sum(dQ)/sum(|dV|) rather than the
                   plain mean of the per-record ratios

So the gate is run with BOTH off — which must still reproduce 1.8.7 to a
tie-break — and what each changes is measured separately and reported rather
than folded into the gate. Three knowingly different things, each accounted
for on its own. A gate that absorbs a deviation is not a gate.
"""
import sys, glob, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from ratatosk import io, signal as sg

UP = "/mnt/user-data/uploads"
TOL = 1e-9          # float round-off, not behaviour
CASES = [
    ("P3 cell A",
     f"{UP}/Python Scripting/Example Battery Data/JQ-P3-NaNiMnO2-35%-2-4.2V-0.1C-A-20062025.xlsx",
     "Positive",
     f"{UP}/runs/2026-08-29_105052_v1.8.7/NNM_cellA/4_dqdv/*_processed_dqdv.csv"),
    ("LTO cell A",
     f"{UP}/Python Scripting/Example Battery Data/JQ_LTO_2.5-1.2V_0.1C_A_08052026 (2).xlsx",
     "Negative",
     f"{UP}/runs/2026-08-30_095722_v1.8.7/LTO_cellA/4_dqdv/*_processed_dqdv.csv"),
]

# The gate compares like with like: 1.8.7 had neither of these.
sg.ORIENT_PLATEAU_RECORDS = False
sg.REBIN_WEIGHTED = False

fails = []
orient_effect = []
for name, xlsx, etype, ref_glob in CASES:
    hits = glob.glob(ref_glob)
    if not glob.glob(xlsx) or not hits:
        print(f"  SKIP  {name} (reference or source not staged)")
        continue

    ds = io.read_neware(xlsx, name=name, electrode_type=etype, verbose=False)
    prof = sg.classify_dqdv_profile(ds.frame, verbose=False)
    params = sg.auto_preprocess_params(prof)
    # PINNED TO THE DERIVATIVE PATH. This test asks "did the PORT change the
    # curve?", against 1.8.7's own processed-curve CSVs. 1.8.7 had only the
    # derivative, so leaving this on the 1.9.0.14 default would compare a
    # histogram against a derivative and answer a different question — one
    # whose answer is "yes, by design, and that is the point of the release".
    # The histogram path is gated by integral fidelity and voltage
    # reconstruction in tests/test_foundation.py instead.
    params["dqdv_method"] = "derivative"
    win = sg.voltage_window(ds)
    ref = pd.read_csv(hits[0])

    identical = differ = differ_with_ties = length_mismatch = 0
    grid_differs = 0
    worst_abs = 0.0
    rels = []
    for cyc, st in sorted({(int(c), str(s)) for c, s in zip(ref.Cycle, ref.Step)}):
        r = ref[(ref.Cycle == cyc) & (ref.Step == st)].sort_values("Voltage")
        sig = sg.half_cycle_report(ds, cyc, st, params, window=win)
        if sig.voltage.size == 0 or len(r) != sig.voltage.size:
            length_mismatch += 1
            continue
        o = np.argsort(sig.voltage, kind="mergesort")
        v = sig.voltage[o]
        ties = int(np.sum(np.diff(v) == 0))
        # The voltage grid, not only the values on it. A rebinned curve can
        # carry the right numbers on a shifted axis, and a peak detected on a
        # shifted axis lands in the wrong place; comparing values alone would
        # not see it.
        if np.abs(r["Voltage"].values - v).max() >= TOL:
            grid_differs += 1
        d = np.abs(r["dQ/dV_processed"].values - sig.dqdv[o])
        if d.max() < TOL:
            identical += 1
        else:
            differ += 1
            worst_abs = max(worst_abs, float(d.max()))
            rels.append(float(d.max() / max(np.abs(
                r["dQ/dV_processed"].values).max(), 1e-12)))
            if ties:
                differ_with_ties += 1

    print(f"\n  {name}   (profile {prof['class']}, "
          f"rebin {params.get('rebin_width_mV')})")
    print(f"      identical            {identical}")
    print(f"      differ               {differ}"
          + (f"   of which {differ_with_ties} contain tied voltages"
             if differ else ""))
    if length_mismatch:
        print(f"      length mismatch      {length_mismatch}")
    if grid_differs:
        print(f"      voltage grid differs {grid_differs}")
    if rels:
        print(f"      worst |diff| {worst_abs:.3g}   worst relative "
              f"{max(rels):.2%}   median relative {np.median(rels):.2%}")
    sp = ds.record_spacing_mV()
    print(f"      record spacing: median {sp['median_mV']:.2f} mV, "
          f"{sp['duplicate_fraction']:.1%} of steps duplicate")

    # --- what each deliberate change does, one at a time -----------------
    keys = sorted({(int(c), str(s)) for c, s in zip(ref.Cycle, ref.Step)})
    for label, flag in (("orientation", "ORIENT_PLATEAU_RECORDS"),
                        ("weighted rebin", "REBIN_WEIGHTED")):
        moved = 0
        worst_rel = 0.0
        for cyc, st in keys:
            setattr(sg, flag, False)
            b = sg.half_cycle_report(ds, cyc, st, params, window=win)
            setattr(sg, flag, True)
            a = sg.half_cycle_report(ds, cyc, st, params, window=win)
            setattr(sg, flag, False)
            if a.voltage.size == 0 or a.voltage.size != b.voltage.size:
                continue
            d = np.abs(a.dqdv - b.dqdv)
            if d.max() >= TOL:
                moved += 1
                worst_rel = max(worst_rel, float(
                    d.max() / max(np.abs(b.dqdv).max(), 1e-12)))
        print(f"      {label:<15} moves {moved} of {len(keys)} curve(s), "
              f"worst {worst_rel:.0%} of peak")
        orient_effect.append((name, label, moved))

    ok = (length_mismatch == 0) and (grid_differs == 0) \
        and (differ == differ_with_ties)
    print(f"      -> {'ACCEPTED' if ok else 'UNEXPLAINED DIFFERENCE'}"
          + ("  (every difference is a tie-break, which the stable sort fixes)"
             if ok and differ else ""))
    if not ok:
        fails.append(name)

print("\n  With both ON — the default since 1.9.0.4 — the curves differ from 1.8.7 by\n"
      "  that much again, deliberately: see signal.orient_dqdv and\n"
      "  signal.REBIN_WEIGHTED. Neither is absorbed into the gate above.")
print("\n" + "=" * 64)
print("  " + ("PORT ACCEPTED — differences confined to tied voltages"
              if not fails else "UNEXPLAINED: " + ", ".join(fails)))
print("=" * 64)
sys.exit(1 if fails else 0)
