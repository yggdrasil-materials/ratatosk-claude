"""
Ratatosk 1.9.0.49 — the cell-level integrity verdict.
Run: python tests/test_cell_verdict.py

Master-list items 5 and 6.

The run counted anomalous half-cycles and stopped. "9 anomalous half-cycles of
160" reads like a handful of bad readings; on NNM cell A it was a cell that
stalls on charge from cycle 1 to cycle 69, taking up to four times the charge
the material can hold. Same numbers, opposite readings, and the difference is
RECURRENCE — which nothing aggregated.

And a half-cycle passing 1.069x theoretical, with ten voltage reversals and
25.6 mAh/g going backwards, was reported "clean — no charge passed backwards
away from a redox process".
"""
import sys, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from ratatosk import analyse as A

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def table(flagged, n_cycles=80, ratio=1.5, step="Charge"):
    rows = []
    for c in range(1, n_cycles + 1):
        for st in ("Charge", "Discharge"):
            bad = (c in flagged and st == step)
            rows.append(dict(cycle=c, step=st,
                             band="ANOMALOUS" if bad else "clean",
                             capacity_ratio=(ratio if bad else 0.9),
                             capacity=100.0, plateau_charge=0.0,
                             cv_charge=0.0, parasitic_charge=0.0,
                             n_reversals=0))
    return pd.DataFrame(rows)


print("\n1. The four verdicts are told apart")
v = A.cell_integrity_verdict(table([]))
check("a clean cell is sound", v["verdict"] == "sound" and v["n_flagged"] == 0)

v = A.cell_integrity_verdict(table([1, 2]))
check("everything early is formation, not a fault", v["verdict"] == "formation",
      v["sentence"][:60])

v = A.cell_integrity_verdict(table([1, 6, 13, 19, 26, 34, 44, 54, 69]))
check("spread across the life of the cell is RECURRING",
      v["verdict"] == "recurring")
check("...and it says the span and the interval",
      "cycle 1 to cycle 69" in v["sentence"] and "cycles or so" in v["sentence"])
check("...and it says what that means for the numbers",
      "describe the fault as much as they describe the material"
      in v["sentence"])

v = A.cell_integrity_verdict(table([1, 12, 16, 20, 25]))
check("a run of events that stopped is CLUSTERED, not 'no pattern'",
      v["verdict"] == "clustered", v["sentence"][:70])
check("...and it says when it stopped", "changed at cycle 25" in v["sentence"])

v = A.cell_integrity_verdict(table([40]))
check("one late event is isolated", v["verdict"] == "isolated")

print("\n2. A table it cannot read says so — it does not say 'sound'")
# 1.9.0.50: the first version returned "sound" for an unreadable table, and
# the page rendered nothing for "sound", so a failure to assess and a healthy
# cell produced the same silence. A false all-clear is worse than an error.
for bad in (None, pd.DataFrame(), pd.DataFrame({"x": [1]})):
    try:
        r = A.cell_integrity_verdict(bad)
        ok = isinstance(r, dict) and r["verdict"] == "unknown" and r["sentence"]
        why = r["verdict"]
    except Exception as e:
        ok, why = False, f"{type(e).__name__}: {e}"
    check(f"an unreadable {type(bad).__name__} is 'unknown', not 'sound'",
          ok, why)
check("a real table with nothing wrong IS sound",
      A.cell_integrity_verdict(table([]))["verdict"] == "sound")

print("\n2b. Every verdict reaches the page — silence never means 'fine'")
from ratatosk import report as _R
for verdict in ("unknown", "sound", "formation", "clustered", "recurring",
                "isolated"):
    f = {"cell_integrity": {"verdict": verdict, "sentence": "s"},
         "resolvability": {}, "bands": {}, "anomalous": None,
         "over_theoretical": None, "plateau_sane": 0, "plateau_total": 0,
         "integral_fidelity": {}, "params": {}, "peaks": {}, "tracked": [],
         "coherence": []}
    heads = [h for _l, h, _b in _R._sentences(f)]
    check(f"'{verdict}' is rendered", len(heads) >= 1, "; ".join(heads[:2]))

print("\n2c. The import that carries it survives flattening")
_nb = open(__file__.rsplit("/rat190/", 1)[0] + "/nb/inline_all.py").read()
check("the flattened notebook calls the verdict",
      "cell_integrity_verdict(" in _nb)
check("...and carries no unrewritten relative import of it",
      "from .analyse import cell_integrity_verdict" not in _nb)

print("\n3. Over theoretical counts as flagged even when the band is clean")
t = table([])
t.loc[(t.cycle == 9) & (t.step == "Charge"), "capacity_ratio"] = 1.069
v = A.cell_integrity_verdict(t)
check("1.069x is picked up although the band says clean",
      v["n_flagged"] == 1 and v["first"] == 9,
      f"{v['n_flagged']} flagged")

print("\n4. And the classifier itself stops calling that clean (item 6)")


class _Sig:
    cycle, step, capacity, n_records_raw = 9, "Charge", 179.61, 500
    voltage = np.linspace(3.0, 4.2, 500)


import ratatosk.analyse as _an
_saved = _an.classify_reversals
try:
    _an.classify_reversals = lambda *a, **k: []          # no parasitic charge
    g = _an.half_cycle_integrity(_Sig(), window=5, theoretical_mAh_g=168.0)
    check("a half-cycle over theoretical is not 'clean'",
          g.band != "clean", f"band={g.band}, ratio={g.capacity_ratio:.3f}")
    check("...and the reason says why",
          "more went in than the material can hold" in g.reason, g.reason[:70])
    _Sig.capacity = 140.0
    g2 = _an.half_cycle_integrity(_Sig(), window=5, theoretical_mAh_g=168.0)
    check("a half-cycle under theoretical is still clean", g2.band == "clean",
          f"band={g2.band}")
finally:
    _an.classify_reversals = _saved

print("\n5. The waterfall says how far its tallest trace reaches (item 4)")
# The first version asked "is this trace taller than the PITCH" — but at
# OVERLAP = 0.5 the pitch is half the median, so a median trace spans two
# lanes by design and the note reported 17 of 17 traces. Worse than silence.
import matplotlib
matplotlib.use("Agg")
import io as _io, contextlib as _ctx
from ratatosk import plots as _P


def _waterfall(amps):
    """One synthetic dataset with the given per-cycle amplitudes."""
    rows = []
    for i, a in enumerate(amps, 1):
        v = np.linspace(3.0, 4.2, 60)
        y = a * np.exp(-0.5 * ((v - 3.6) / 0.1) ** 2)
        rows.append(pd.DataFrame({"Voltage": v, "dQ/dV_processed": y,
                                  "Cycle": i, "Step": "Charge"}))
    d = pd.concat(rows)
    data = {(int(c), s): g for (c, s), g in d.groupby(["Cycle", "Step"])}
    res = {"t": {"data": data, "voltage_range": (3.0, 4.2)}}
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        _P.plot_dqdv_waterfall(res, {"t": {}}, step="Charge",
                               save_location=None)
    return buf.getvalue()


out = _waterfall([100.0] * 10)
check("uniform traces raise no console note", "the median trace" not in out,
      out.strip()[:60] or "(silent)")
out = _waterfall([154.0] + [100.0] * 9)
check("one trace at 1.5x the median does", "1.5x the median trace" in out,
      out.strip()[:70])
out = _waterfall([4700.0] + [100.0] * 9)
check("a 47x spike is reported with its reach",
      "47.0x the median trace" in out and "row(s) above" in out,
      out.strip()[:80])
src = open(__file__.rsplit("/tests/", 1)[0] + "/ratatosk/plots.py").read()
check("and the figure always carries the note, threshold or not",
      "The tallest (cycle" in src)
check("the doubled set_title is gone",
      "ax.set_title(ax.get_title()" not in src)

print("\n" + ("ALL PASS" if not FAILURES else f"FAILED: {FAILURES}"))
sys.exit(1 if FAILURES else 0)
