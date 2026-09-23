"""
Ratatosk 1.9.0.47 — the mechanism verdict reaches the reader.
Run: python tests/test_report_mechanism.py

`quality.assess_resolvability` decides, before a single production fit runs,
what produced the curve and therefore which model to fit it with. It said so in
the console and nowhere else: a reader of START_HERE could not tell whether
their data had been fitted with pseudo-Voigts, with flat-topped bands, or with
both — the one thing this build decides differently for every dataset.

Master-list item 1.
"""
import sys, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from ratatosk import report as R

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def facts(mech, reason="", sf=None, tracked=()):
    return {"resolvability": ({} if mech is None else
                              dict(mechanism=mech, mechanism_reason=reason,
                                   shoulder_fraction=sf)),
            "tracked": list(tracked)}


print("\n1. Every mechanism produces a sentence a person can read")
for mech in ("two_phase", "multi_transition", "solid_solution", "mixed"):
    out = R._mechanism_sentence(facts(mech, "shoulders 0.42 of components"))
    ok = len(out) == 1 and mech.replace("_", " ") in out[0][2]
    body = out[0][2] if out else ""
    check(f"{mech} is named and explained", ok and len(body) > 120,
          f"{len(body)} chars")
    check(f"...and {mech} says what was FITTED",
          any(w in body for w in ("band", "peak")), "")

print("\n2. It is silent when there is no verdict")
check("no resolvability -> no sentence", R._mechanism_sentence(facts(None)) == [])
check("empty dict -> no sentence", R._mechanism_sentence({}) == [])

print("\n3. An unknown mechanism does not crash the page")
out = R._mechanism_sentence(facts("something_new"))
check("an unrecognised class still renders", len(out) == 1
      and "something new" in out[0][2])

print("\n4. The shape each feature was fitted with is looked up per peak")
tracked = [dict(step="Charge", reference_voltage=3.665, component_kind="band",
                component_kind_mixed=False),
           dict(step="Charge", reference_voltage=3.754, component_kind="peak",
                component_kind_mixed=True),
           dict(step="Discharge", reference_voltage=3.446,
                component_kind=None, component_kind_mixed=False)]
k = R._kind_by_ref(facts("mixed", tracked=tracked))
check("a band is named in words", k.get(("Charge", 3.665)) == "flat-topped band")
check("a component that changed shape says so",
      "band in some cycles" in k.get(("Charge", 3.754), ""),
      k.get(("Charge", 3.754), ""))
check("a feature with no kind is simply absent",
      ("Discharge", 3.446) not in k)

print("\n5. The run summary RUNS — not just contains the right source")
# 1.9.0.48: the first version of this test asserted on the SOURCE TEXT of
# `build_run_summary` and passed while the function raised. `mechanism` was
# added to the row dicts and not to `_COLS`, which is an explicit column
# list, so the column was dropped and `r.mechanism` raised AttributeError.
# The per-cell pages were written, RUN_SUMMARY was not, and nothing said
# why. A test that reads code instead of running it is not a test.
import inspect


def _fact(mech, label):
    return {"params": {"composition": "X", "cell_id": label},
            "resolvability": ({} if mech is None else dict(mechanism=mech)),
            "n_cycles": 20, "last_good_cycle": 20, "retention": 90.0,
            "median_ce": 99.0, "first_last_discharge": (120.0, 110.0),
            "integral_fidelity": {"Charge": 0.99}, "withheld": (0, 20),
            "anomalous": None, "over_theoretical": None, "peaks": {},
            "tracked": [], "coherence": [], "drift": []}


for tag, facts in (
        ("all cells agree",
         {"a": _fact("mixed", "A"), "b": _fact("mixed", "B")}),
        ("cells disagree",
         {"a": _fact("mixed", "A"), "b": _fact("multi_transition", "B")}),
        ("no mechanism at all",
         {"a": _fact(None, "A"), "b": _fact(None, "B")}),
        ("one cell only", {"a": _fact("two_phase", "A")})):
    try:
        md, _T, _Rep = R.build_run_summary(facts, run_id="t",
                                           n_files=len(facts))
        ok, why = isinstance(md, str) and len(md) > 200, f"{len(md)} chars"
    except Exception as e:
        ok, why = False, f"{type(e).__name__}: {e}"
    check(f"build_run_summary returns a page when {tag}", ok, why)

_agree, _, _ = R.build_run_summary({"a": _fact("mixed", "A"),
                                    "b": _fact("mixed", "B")})
check("...and says so when they agree",
      "classified **mixed**" in _agree and "comparable" in _agree)
_differ, _, _ = R.build_run_summary({"a": _fact("mixed", "A"),
                                     "b": _fact("multi_transition", "B")})
check("...and warns when they do not",
      "not all fitted with the same model" in _differ
      and "should not be pooled" in _differ)
_none, _, _ = R.build_run_summary({"a": _fact(None, "A"),
                                   "b": _fact(None, "B")})
check("...and stays quiet when there is no verdict",
      "How these cells were modelled" not in _none)

src = inspect.getsource(R)
check("`mechanism` is in the explicit column list", '"mechanism"]' in src,
      "adding it to the row dict alone silently drops it")
nb = open(__file__.rsplit("/rat190/", 1)[0] + "/nb/cells.py").read()
check("the notebook passes it", "resolvability=resolvability.get(name)" in nb)

print("\n6. A plateau is only innocent where the mechanism says it is (item 7)")


def _plateau(mech, sane=1.0):
    f = dict(resolvability=({} if mech is None else dict(mechanism=mech)),
             plateau_sane=sane, plateau_total=sane, integral_fidelity={},
             params={}, peaks={}, tracked=[], coherence=[])
    hits = [x for x in R._sentences(f) if "lateau" in x[1]]
    return hits[0] if hits else None


for mech in ("two_phase", "multi_transition"):
    lvl, head, body = _plateau(mech)
    check(f"{mech}: a plateau is the transition, and it is fine",
          lvl == "ok" and "not a fault" in body, head)

for mech in ("solid_solution", "mixed"):
    lvl, head, body = _plateau(mech)
    check(f"{mech}: a plateau is flagged, not excused",
          lvl == "bad" and "not expected physics" in head, head)
    check(f"...and {mech} says WHY a solid solution cannot hold potential",
          "must move as that composition changes" in body, "")
    check(f"...and {mech} does not call it a first-order transition",
          "That is a first-order" not in body, "")

lvl, head, body = _plateau(None)
check("no mechanism: neither claim is made",
      lvl == "ok" and "has not been established" in body, head)

print("\n7. The sibling sentence stops offering the same excuse")


def _unaccounted(mech):
    import pandas as pd
    f = dict(resolvability=({} if mech is None else dict(mechanism=mech)),
             bands={"clean": 3}, over_theoretical=None, anomalous=None,
             plateau_sane=0, plateau_total=0, integral_fidelity={},
             params={}, peaks={}, tracked=[], coherence=[])
    return [x for x in R._sentences(f) if "naccounted" in x[1] or "should not have" in x[1]]


h = _unaccounted("two_phase")
check("two_phase still reports 'No unaccounted charge'",
      bool(h) and h[0][0] == "ok", h[0][1] if h else "none")
h = _unaccounted("solid_solution")
check("a solid solution does not get that excuse",
      bool(h) and h[0][0] == "warn", h[0][1] if h else "none")

print("\n" + ("ALL PASS" if not FAILURES else f"FAILED: {FAILURES}"))
sys.exit(1 if FAILURES else 0)
