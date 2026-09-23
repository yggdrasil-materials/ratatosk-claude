"""
Ratatosk 1.9.0.46 — the cycle cut-off carries forward.
Run: python tests/test_cycle_cutoff.py

Datasets analysed together are usually replicates, so a cap set on the first is
almost always wanted on the rest — and when it is not applied consistently the
comparative figures compare different cycle ranges without saying so. That is
not hypothetical: the NNM triplicate was analysed to cycle 80 in one build and
75 in the next, and the difference only surfaced when two runs were compared
component by component.

The prompt logic is exercised directly here rather than through the 600-line
interactive cell, because what needs pinning is the decision table.
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def answer(typed, carried):
    """The decision the prompt makes. Mirrors `collect_parameters`."""
    t = (typed or "").strip()
    if not t:
        return carried, "kept"
    if t.lower() in ("all", "none"):
        return None, "cleared"
    try:
        n = int(t)
    except ValueError:
        return "REASK", "not a number"
    if n < 1:
        return "REASK", "below 1"
    return n, "set"


print("\n1. The first dataset behaves exactly as it always did")
check("blank means all cycles", answer("", None)[0] is None)
check("a number sets the cap", answer("80", None)[0] == 80)

print("\n2. Later datasets inherit it, and blank keeps it")
check("blank keeps the carried cap", answer("", 80)[0] == 80,
      "this is the whole point")
check("a number overrides it", answer("75", 80)[0] == 75)
check("'all' removes the cap for this dataset", answer("all", 80)[0] is None)
check("'none' does too", answer("none", 80)[0] is None)
check("case does not matter", answer("ALL", 80)[0] is None)

print("\n3. Bad input is re-asked, not guessed at")
for bad in ("0", "-3", "eighty", "8.5"):
    check(f"{bad!r} is refused", answer(bad, 80)[0] == "REASK")

print("\n4. What is carried is what the dataset settled on")
carried = None
seq = [("80", 80), ("", 80), ("75", 75), ("", 75), ("all", None), ("", None)]
ok = True
for typed, want in seq:
    got, _ = answer(typed, carried)
    if got != want:
        ok = False
        print(f"      after typing {typed!r} expected {want}, got {got}")
    carried = got
check("a three-dataset sequence carries and overrides correctly", ok,
      "80 -> keep -> 75 -> keep -> all -> keep")

print("\n5. Mismatched cut-offs are reported, not left to be noticed")
src = open(__file__.rsplit("/tests/", 1)[0] + "/ratatosk/params.py").read()
check("the summary tests whether the cut-offs agree",
      "len(set(_all_cuts.values())) > 1" in src)
check("...and names the datasets with no cap",
      "_uncapped" in src and "No cap on:" in src)
check("...and says what it does to the comparative figures",
      "compare different cycle ranges" in src)

print("\n6. And through the REAL prompt sequence, not a mirror of it")
import copy, io, contextlib
import pandas as pd
from ratatosk import params as pm


def _frame():
    rows = []
    for c in range(1, 21):
        for step in ("Charge", "Discharge"):
            for i in range(5):
                rows.append(dict(Cycle=c, Step=step, Voltage=1.5 + 0.01 * i,
                                 Charge_Capacity=float(i),
                                 Discharge_Capacity=float(i),
                                 Current=1e-4, Test_Time=i))
    return pd.DataFrame(rows)


_data = {"cellA": _frame(), "cellB": _frame(), "cellC": _frame()}
_meta = {n: dict(active_material_mass_mg=5.0, cycle_count=220,
                 voltage_upper_V=4.3, voltage_lower_V=1.9, c_rate=0.1)
         for n in _data}
_base = {n: {"Composition": "LTO", "Theoretical capacity": 175,
             "Electrode type": "positive", "Cell identifier": n[-1]}
         for n in _data}


def _run(extra):
    ans = copy.deepcopy(_base)
    for k, v in extra.items():
        ans[k]["Maximum cycle to analyse"] = v
    with contextlib.redirect_stdout(io.StringIO()):
        up, _ = pm.collect_parameters(_data, cycler_metadata=_meta,
                                      answers=ans, headless=True,
                                      verbose=False)
    return {n: up[n].get("max_cycle") for n in _data}


check("nobody sets a cap -> none anywhere",
      _run({}) == {"cellA": None, "cellB": None, "cellC": None})
check("a cap on the first dataset reaches the other two",
      _run({"cellA": 80}) == {"cellA": 80, "cellB": 80, "cellC": 80},
      "this is the change")
check("an override carries on rather than reverting",
      _run({"cellA": 80, "cellB": 75}) == {"cellA": 80, "cellB": 75,
                                           "cellC": 75})
check("'all' clears it, and the clearing carries too",
      _run({"cellA": 80, "cellB": "all"}) == {"cellA": 80, "cellB": None,
                                              "cellC": None})

print("\n" + ("ALL PASS" if not FAILURES else f"FAILED: {FAILURES}"))
sys.exit(1 if FAILURES else 0)
