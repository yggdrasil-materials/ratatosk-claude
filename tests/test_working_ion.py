"""The figures must not call a sodium cell lithiated.

Reported on an NTO anode at 1.9.0.74: every Cell 7 waterfall was captioned
"Lithiation"/"Delithiation" on a sodium half-cell. The working ion WAS
established (the interactive path asks for it and records `stated`); the
label helpers read `battery_chemistry` instead, which `infer_chemistry`
rightly answers `Unknown` for an abbreviation, and then defaulted to lithium.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ratatosk.style import (half_cycle_labels, working_ion,
                            WORKING_ION_WORDS, CAPACITY_COLUMN_ALIASES)
from ratatosk.plots import _charge_label, _discharge_label
import ratatosk.run as _run
import inspect, ratatosk.cycling as _cy

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}   {detail}")
    if not cond:
        fails.append(name)


def P(**kw):
    return dict(anode_labels_swapped=True, **kw)


print("=" * 70)
print("NAMING THE WORKING ION")
print("=" * 70)

# --- the reported bug -------------------------------------------------
na = P(counter_electrode_metal="Na", counter_electrode_metal_source="stated",
       battery_chemistry="Unknown")
check("a stated Na anode is sodiated, not lithiated",
      half_cycle_labels(na) == ("Sodiation", "Desodiation"),
      str(half_cycle_labels(na)))
check("...through the plots helpers too",
      (_charge_label(na), _discharge_label(na))
      == ("Sodiation", "Desodiation"))

# --- and its mirror ---------------------------------------------------
li = P(counter_electrode_metal="Li", counter_electrode_metal_source="stated",
       battery_chemistry="Unknown")
check("a stated Li anode is still lithiated",
      half_cycle_labels(li) == ("Lithiation", "Delithiation"))

# --- a GUESS must never reach a caption -------------------------------
guess = P(counter_electrode_metal="Na", counter_electrode_metal_source="assumed")
check("an ASSUMED metal gives neutral labels, not a guessed process",
      half_cycle_labels(guess) == ("Charge", "Discharge"),
      str(half_cycle_labels(guess)))
check("...and working_ion refuses to name it", working_ion(guess) == "")

# --- nothing known at all ---------------------------------------------
check("an unknown ion gives neutral labels, never lithium",
      half_cycle_labels(P()) == ("Charge", "Discharge"))
check("an empty params dict does not raise",
      half_cycle_labels({}) == ("Charge", "Discharge"))
check("None does not raise", half_cycle_labels(None) == ("Charge", "Discharge"))

# --- a cathode is unaffected ------------------------------------------
check("a positive electrode keeps Charge / Discharge",
      half_cycle_labels(dict(anode_labels_swapped=False,
                             counter_electrode_metal="Na",
                             counter_electrode_metal_source="stated"))
      == ("Charge", "Discharge"))

# --- the chemistry fallback still works -------------------------------
check("battery_chemistry Na-ion still resolves",
      half_cycle_labels(P(battery_chemistry="Na-ion"))
      == ("Sodiation", "Desodiation"))
check("battery_chemistry Li-ion still resolves",
      half_cycle_labels(P(battery_chemistry="Li-ion"))
      == ("Lithiation", "Delithiation"))
check("a stated metal OUTRANKS a stale chemistry string",
      half_cycle_labels(P(battery_chemistry="Li-ion",
                          counter_electrode_metal="Na",
                          counter_electrode_metal_source="stated"))
      == ("Sodiation", "Desodiation"))

print()
print("=" * 70)
print("NOTHING IS TYPED OUT TWICE")
print("=" * 70)

# --- no second implementation anywhere --------------------------------
_src = inspect.getsource(_cy)
check("cycling.py defines no local copy of the label helpers",
      "def _discharge_label" not in _src and "def _charge_label" not in _src)
check("no module hard-codes the Na-ion ternary any more",
      "'Na-ion' else 'Delithiation'" not in _src)

# --- the derived lists cover every ion --------------------------------
for ion, (cw, dw) in WORKING_ION_WORDS.items():
    check(f"{ion}: capacity column alias exists",
          f"{dw}_mAh_g" in CAPACITY_COLUMN_ALIASES)
_toks = dict(_run.FOLDER_RULES)["1_cycling"]
for ion, (cw, dw) in WORKING_ION_WORDS.items():
    check(f"{ion}: voltage file is filed into 1_cycling",
          f"{cw.lower()}_voltage" in _toks
          and f"{dw.lower()}_voltage" in _toks)
check("Discharge_mAh_g is still the first alias",
      CAPACITY_COLUMN_ALIASES[0] == "Discharge_mAh_g")

print()
print("ALL PASS" if not fails else f"{len(fails)} FAILURE(S): {fails}")
sys.exit(1 if fails else 0)
