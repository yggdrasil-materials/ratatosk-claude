"""
The whole pipeline, on real cells, with the answers we already know.

This is not a bit-identity regression — 1.8.7 shipped no tracking CSV to
compare against, so tracking, dV and attribution are covered by extraction of
the value-determining functions plus the checks below, and the bit-identity
gate arrives when the 1.9.0 notebook can write both sets of CSVs side by side.

What IS checked here are claims made about these cells during development,
against the cells:

  1. P3 cell C's cycle 2 is the half-cycle that put in 580.9 mAh/g and got
     115.8 back. Integrity must find it, and the reference-cycle selector must
     then refuse to anchor the dataset to it.
  2. LTO's plateau must NOT read as parasitic. It is the case that broke every
     previous rule.
  3. Healthy half-cycles across three cells must carry no unaccounted charge.
  4. Attribution must be withheld exactly where the closure interval is wide.
"""
import sys, warnings, time
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])
import numpy as np, pandas as pd

from ratatosk import io, signal as sg, detect as dt, fitting as ft
from ratatosk import quality as ql, analyse as an

UP = "/mnt/user-data/uploads/Python Scripting/Example Battery Data"
CELLS = [
    ("P3 cell A", f"{UP}/JQ-P3-NaNiMnO2-35%-2-4.2V-0.1C-A-20062025.xlsx",
     "Positive", 160.0),
    ("P3 cell C", f"{UP}/JQ-P3-NaNiMnO2-35%-2-4.2V-0.1C-C-20062025.xlsx",
     "Positive", 160.0),
    ("LTO cell A", f"{UP}/JQ_LTO_2.5-1.2V_0.1C_A_08052026 (2).xlsx",
     "Negative", 175.0),
]
MAX_CYCLES = 30          # enough to exercise tracking; keeps the test minutes
fails = []


def check(label, cond, detail=""):
    print(f"    {'PASS' if cond else 'FAIL'}  {label}"
          + (f"   {detail}" if detail else ""))
    if not cond:
        fails.append(label)


for name, path, etype, theoretical in CELLS:
    t0 = time.perf_counter()
    ds = io.read_neware(path, name=name, electrode_type=etype, verbose=False)
    prof = sg.classify_dqdv_profile(ds.frame, verbose=False)
    params = sg.auto_preprocess_params(prof)
    win = sg.voltage_window(ds)
    keys = [k for k in ds.half_cycle_keys() if k[0] <= MAX_CYCLES]
    signals = {k: sg.half_cycle_report(ds, *k, params, window=win) for k in keys}

    # integrity BEFORE detection — the plateau test reads the curve, not peaks
    # WITH the theoretical capacity. Without it `capacity_ratio` is NaN and
    # the over-theoretical test — the one that condemns a half-cycle on its
    # total charge, whatever its curve looks like — cannot fire at all. A
    # harness that leaves it out is not exercising the check it asserts on.
    R, band = an.integrity_report(signals, window=win, name=name,
                                  theoretical_mAh_g=theoretical, verbose=False)
    det = dt.detect_all(signals, name=name, integrity=band, verbose=False)

    jobs, jkeys = [], []
    for k in sorted(signals):
        s, pk = signals[k], det.peaks.get(k)
        if s.voltage.size == 0 or pk is None or pk.empty:
            continue
        jobs.append((s.voltage, s.dqdv,
                     ft.FitSpec(pk["voltage"].values,
                                sigma_min=0.003, sigma_max=0.200), k))
        jkeys.append(k)
    fits = ft.fit_many(jobs, verbose=False)
    P = an.parameters_frame(fits, det)
    tk = an.track_peaks(P, det, verbose=False)

    # closure interval on a sample, then attribution that respects it
    sample = ql.sample_half_cycles(jkeys, n=6)
    ivs = {}
    for k in sample:
        i = jkeys.index(k)
        v, y, spec, _ = jobs[i]
        r = ql.closure_interval(v, y, spec, key=k)
        ivs[k] = (r["lo"], r["hi"])
    att = an.capacity_attribution(tk, closure_intervals=ivs, verbose=False)
    dv = an.delta_v(tk, is_anode=ds.labels_swapped, verbose=False)
    coh = an.coherence_audit(P, det, profile=prof["class"], verbose=False)

    print(f"\n  {name}  ({len(signals)} half-cycles, {len(fits)} fitted, "
          f"{time.perf_counter() - t0:.0f} s)")
    counts = R["band"].value_counts().to_dict()
    print(f"      integrity  " + "  ".join(f"{v} {k}" for k, v in counts.items()))
    print(f"      reference cycle {det.reference_cycle}  "
          f"({det.reference_reason})")
    print(f"      tracked    {len(tk.summary)} peaks, "
          f"median rate {np.median([s['tracking_rate'] for s in tk.summary.values()]):.0%}"
          f", {tk.cell_discontinuity} failure(s), "
          f"{tk.transient_losses} transient")
    print(f"      coherence  " + ", ".join(
        f"{n} {v}" for v, n in coh["verdict"].value_counts().items()))
    w = [hi - lo for lo, hi in ivs.values() if np.isfinite(lo) and np.isfinite(hi)]
    print(f"      closure interval width {min(w):.2f}-{max(w):.2f} "
          f"on {len(w)} sampled half-cycles")

    # --- the claims -----------------------------------------------------
    para = R[R["parasitic_charge"] > 0]
    healthy = R[R["band"] == "clean"]
    if name == "P3 cell C":
        c2 = R[(R["cycle"] == 2) & (R["step"] == "Charge")]
        # 581 mAh/g out of a theoretical 160 — 3.6x what the material can
        # hold. It is condemned on that, which is a fact about the charge
        # that passed, and needs nothing from the shape of the curve. Before
        # `orient_dqdv` this half-cycle was reached by the OTHER route: its
        # plateau records carried the wrong sign, so the charge on them was
        # called parasitic. Right verdict, wrong reason.
        check("cycle 2 charge is found anomalous",
              len(c2) == 1 and c2["band"].iloc[0] == "ANOMALOUS",
              f"{c2['capacity'].iloc[0]:.0f} mAh/g, "
              f"{c2['capacity_ratio'].iloc[0]:.1f}x theoretical" if len(c2)
              else "")
        check("and condemned on the charge, not on the curve",
              len(c2) == 1 and bool(c2["over_theoretical"].iloc[0]),
              c2["reason"].iloc[0][:90] if len(c2) else "")
        check("the selector refuses to anchor to it",
              det.reference_cycle != 2 and "integrity check" in det.reference_reason,
              f"cycle {det.reference_cycle}: {det.reference_reason}")
    if name.startswith("LTO"):
        check("the two-phase plateau is not called parasitic",
              R["plateau_charge"].sum() > 0
              and (R["parasitic_fraction"].fillna(0) < 0.02).mean() > 0.9,
              f"plateau {R['plateau_charge'].sum():.0f} mAh/g, "
              f"parasitic {R['parasitic_charge'].sum():.1f} mAh/g")
    check("no clean half-cycle carries unaccounted charge",
          bool((healthy["parasitic_charge"] <= 0).all()),
          f"{len(healthy)} clean of {len(R)}")
    check("attribution withheld exactly where the interval is wide",
          all(bool(A.loc[A["closure_interval_width"].notna(),
                         "attribution_withheld"].eq(
              A.loc[A["closure_interval_width"].notna(),
                    "closure_interval_width"]
              > an.ATTRIBUTION_WITHHOLD_ABOVE).all())
              for A in att.values()))
    check("a withheld row keeps its areas and loses only the fraction",
          all(not (A["attribution_withheld"]
                   & A.filter(like="_fraction").notna().any(axis=1)).any()
              for A in att.values()))
    check("delta-V sign matches the electrode",
          dv.df.empty or (dv.df["delta_v_mV"].median() < 0) == ds.labels_swapped,
          f"median dV {dv.df['delta_v_mV'].median():+.0f} mV, "
          f"labels_swapped={ds.labels_swapped}" if not dv.df.empty else "no pairs")

print("\n" + "=" * 66)
print("  " + ("END-TO-END PASS" if not fails
              else f"{len(fails)} FAILED: " + "; ".join(fails)))
print("=" * 66)
sys.exit(1 if fails else 0)
