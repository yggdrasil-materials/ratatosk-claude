import builtins
import ast
import pathlib, json, re
exec(open('/root/flatten.py').read())

# ONE definition of the version, read from the package, so the notebook and
# the package can never disagree. Bump it in ratatosk/__init__.py.
VERSION = re.search(r'__version__\s*=\s*["\']([^"\']+)',
                    open(f"{PKG}/__init__.py").read()).group(1)

# ---------------------------------------------------------------- pipeline
src = open('/root/nb/cells.py').read()
parts = re.split(r'# ---8<--- CELL (\w+)\n', src)[1:]
pipeline = dict(zip(parts[0::2], parts[1::2]))

PREFIX = {"io.": "", "pm.": "", "sg.": "", "dt.": "", "ft.": "", "ql.": "",
          "an.": "", "pl.": "", "cy.": "", "rn.": ""}


def deprefix(t):
    for k, v in PREFIX.items():
        t = re.sub(r'(?<![\w.])' + re.escape(k), v, t)
    t = t.replace("ratatosk.__version__", "RATATOSK_VERSION")
    return t


TITLE = f"""# Ratatosk {VERSION} — GCPL electrochemical analysis

Galvanostatic cycling data in; cycling performance, dQ/dV curves, fitted redox
features tracked across life, and — this is the part that is new — a statement
about which of those numbers are measurements and which are not.

## How this notebook is arranged

Twelve **definition** cells, then twelve **execution** cells. Run top to bottom.
The definition cells declare functions and change nothing; the execution cells
do the work, in the order the data flows.

```
   DEFINITIONS                                  EXECUTION
   A  read a cycler export                      1  setup
   B  Q, V, I, t -> dQ/dV                       2  what to analyse   <- EDIT
   C  find peaks, choose reference cycle        3  load, open the run
   D  build and run the model                   4  preprocess
   E  does the answer mean anything             5  cycle integrity
   F  track, pair, attribute, classify         6a  cycling tables
   H1 dQ/dV figures                            6b  cycling figures (paper)
   H2 peak/fit/trend figures + adapters        6c  cycling figures (support)
   J1 J2 J3  cycling figures                    7  dQ/dV figures
   K  run folders and the manifest              8  detection
                                                9  fitting
                                               10  quality
                                               11  analysis
                                               12  fit figures
                                               13  export
                                               14  close the run
```

Data flows one way:

```
   A read  ->  B curve  ->  F integrity  ->  C detect  ->  D fit  ->  F analyse  ->  figures
                                 |                          |            |
                                 +-- decides the ------------+            |
                                     reference cycle          E quality --+
                                                              decides what
                                                              is withheld
```

`E quality` is consulted by the others and depends on none of them. Note that
**integrity runs before detection**: the test for a two-phase plateau reads
|dQ/dV| rather than a peak list, so it needs no peaks, and the reference-cycle
chooser can therefore be handed the integrity verdict.

## The four decisions this code makes, and where

Everything else is arithmetic. These four are judgements, and each is made in
one named place so it can be argued with.

**1. Which cycle defines the peak list.** (Cell C, `choose_reference_cycle`)
That cycle's peaks are fitted and tracked in *every* cycle, so a bad reference
cycle is not a bad cycle — it is a bad dataset. On P3 cell C the old hardcoded
default landed on a half-cycle with 19.9% coulombic efficiency, and its peak
list set the fit for all 220 cycles. The rule now: the **lowest** cycle at or
above 2 whose half-cycles both pass the integrity check. Lowest, not best — a
fingerprint should come from early in life.

**2. What the reversed charge was doing.** (Cell F, `classify_reversals`)
Where dQ/dV is negative during charge, the potential is moving backwards under
applied current. Three unrelated things do that and the old single threshold
conflated all three:

| verdict | test | meaning |
|---|---|---|
| `plateau` | full current, and \\|dQ/dV\\| there is >= 5% of this half-cycle's own maximum | a two-phase equilibrium. Real, intended charge |
| `cv_hold` | current below the constant-current value, within 50 mV of the window edge | protocol, not chemistry |
| `parasitic` | full current, \\|dQ/dV\\| small, away from the limit | charge with no redox process to account for it |

Every term is measured against the half-cycle **itself** — its own peak
\\|dQ/dV\\|, its own current, its own capacity. That is why it transfers between
chemistries, and it is exactly what a pooled threshold could not do. Measured
across 1,384 half-cycles of six cells: every anomalous one sits in a cycle
whose coulombic efficiency is below 60%, and above CE 60% nothing anywhere
carries more than 0.4% of its capacity backwards.

**3. How the model is set up.** (Cell D, `spec_for_profile`) The baseline degree
and sigma bounds come from the dataset's own profile class. A sharp two-phase
peak (LTO, LFP) sits on a flat background, so a wide sigma bound would let a
component inflate until it *is* the background: sigma 3-30 mV, linear baseline.
A broad layered oxide sits on a curved background a straight line cannot
follow: sigma 5-200 mV, cubic baseline. Getting this wrong is what a visibly
bad fit looks like — R2 0.27 against 0.54 on the same data.

**4. Whether a capacity share is a measurement.** (Cell E, `closure_interval`;
applied in Cell F, `capacity_attribution`) A broad pseudo-Voigt and a cubic
baseline across a 1.4 V window are nearly the same function. Where that is
true, the split between "peak" and "background" is not determined by the data,
and any single closure value is an artefact of the baseline degree somebody
chose. So the model is refitted at several baseline degrees and the **spread**
is reported. Measured: LTO 0.00-0.01, P3 0.00-0.09, NMC111 0.35-0.40. Above a
spread of 0.15 — inside the gap in those measurements — the per-peak *share* of
capacity is set to NaN and the reason recorded. The fitted areas are kept:
withholding a share is not deleting a number.

## What is measured twice, on purpose

```
   integral fidelity  =  integral(dQ/dV) dV  /  the counter's capacity
                         "does the derivative account for the charge?"

   capacity closure   =  sum(component areas)  /  integral(dQ/dV) dV
                         "do the fitted peaks account for the curve?"
```

They are deliberately orthogonal. Using the counter's capacity as closure's
denominator would hide a preprocessing failure inside a fitting number.

## Provenance

Every run writes to its own timestamped folder with a `run_manifest.json`
recording the input checksums, the package versions, and every switch in force.
With the version number deliberately held across a series of behaviour changes,
those switches are the only thing distinguishing one run from another."""

SETUP = '''# CELL 1 — SETUP
# =============================================================================
# The one place the version is written. It names the run folder
# (<timestamp>_v<version>), is recorded in run_manifest.json and in each
# dataset_info.txt, and is printed on every report — so any figure can be
# traced back to the code that made it.
RATATOSK_VERSION = "{VERSION}"

# All of RATATOSK is in this notebook — there is no package to install and
# nothing to import beyond the scientific stack, so the whole pipeline can be
# read top to bottom. That stack itself is still required:
#
#   conda install -c conda-forge numpy pandas scipy matplotlib seaborn \\
#                                lmfit joblib openpyxl python-calamine
#
# python-calamine is optional and reads these Excel exports 5-7x faster than
# openpyxl, with a maximum numeric difference of exactly zero. seaborn is
# needed only for the key-cycle voltage profile. The versions actually
# present are printed below and recorded in the manifest.

import os, sys, re, glob, json, time, shutil, getpass, platform, hashlib
import contextlib, functools
import io as _io
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.ticker as mticker
import matplotlib.patheffects as path_effects
from matplotlib import gridspec
from matplotlib.colors import Normalize

import builtins as _builtins
from scipy.signal import find_peaks, peak_widths, savgol_filter
from scipy.optimize import linear_sum_assignment
from lmfit.models import PseudoVoigtModel, PolynomialModel

try:
    import seaborn as sns
except ImportError:
    sns = None

# FutureWarnings are suppressed for the whole run. They are the ones that
# change numbers between pandas releases, so this is not free: the fact that
# they were hidden is recorded in the manifest by `check_environment`, beside
# the versions that produced the run. Comment this out when a result looks
# wrong and you want to know why.
warnings.filterwarnings("ignore", category=FutureWarning)

# --------------------------------------------------------------------------
# WHERE THE SCIENTIFIC STACK CHANGED UNDER US
# --------------------------------------------------------------------------
# This is `ratatosk/compat.py`, and it lives in CELL 1 rather than in a
# definition cell of its own because it is part of setting the environment
# up: `check_environment()` is called at the bottom of this cell, and a name
# cannot be called in the cell above the one that defines it.
{COMPAT}
# --------------------------------------------------------------------------

print(f"Ratatosk {RATATOSK_VERSION}")
ENVIRONMENT = check_environment()
'''

def setup_source():
    """Cell 1, with the version and the compatibility layer filled in."""
    body = strip(load("compat"))
    return (SETUP.replace("{VERSION}", VERSION)
                 .replace("{COMPAT}", body))


def _check_shadowing(module_bodies, pipeline_bodies):
    """
    A flattened notebook has ONE namespace.

    A pipeline cell that assigns a name a module cell already defines silently
    replaces it. `_facts = {}` in the report cell shadowed `report._facts`, the
    function, and the run died with "'dict' object is not callable". The
    package cannot hit this because it has module namespaces; the inline
    notebook can, so it is checked at build time.
    """
    defined = set()
    dupes = {}
    for body in module_bodies:
        for n in ast.parse(body).body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                # TWO MODULES, ONE NAME. Harmless in a package, fatal when
                # flattened: `detect.spec_for_profile` and
                # `fitting.spec_for_profile` are different functions with
                # different signatures, and in one namespace the later one
                # silently replaces the earlier for every caller.
                if n.name in defined:
                    dupes.setdefault(n.name, 0)
                    dupes[n.name] += 1
                defined.add(n.name)
            # Module CONSTANTS too. A pipeline cell assigning a name a module
            # already uses as a switch silently rebinds it for every function
            # that reads it — which is how a Cell 2 knob called
            # USE_FILE_DIALOG would have taken over params.USE_FILE_DIALOG.
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if (isinstance(t, ast.Name)
                            and re.fullmatch(r"[A-Z][A-Z0-9_]*", t.id)):
                        defined.add(t.id)
    clashes = set()
    for body in pipeline_bodies:
        tree = ast.parse(body)
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                if n.id in defined:
                    clashes.add(n.id)
        # A pipeline `def`, not just a pipeline assignment. This was the gap:
        # a FunctionDef's name is a STRING ATTRIBUTE, not an ast.Name node, so
        # `ast.walk` never sees it in a Store context and the guard passed a
        # notebook helper called `_fmt` straight over `cycling._fmt`. The run
        # died in `comparative_capacity` with
        # `ValueError: Format 'not given' is not supported` — the notebook's
        # `_fmt(value, unit)` being called where the module's `_fmt(params)`
        # was meant, several cells and one module away from either.
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) \
                    and n.name in defined:
                clashes.add(n.name)
    if dupes:
        raise SystemExit(
            "inline build ABORTED — these names are defined by more than one "
            "module, so in the flat namespace the later definition replaces "
            "the earlier: " + ", ".join(sorted(dupes)))
    if clashes:
        raise SystemExit("inline build ABORTED — these pipeline names shadow "
                         "module definitions in the flat namespace: "
                         + ", ".join(sorted(clashes)))
    return len(defined)

def _check_defined(code_cells, label):
    """Every module-level name a cell READS must be defined by an earlier one.

    The package notebook used `RATATOSK_VERSION` in Cell 3a and defined it
    nowhere: Cell 1 imported `ratatosk` and printed `ratatosk.__version__`,
    while the shared cell source — written for the inline build — expected a
    bare name. It had never been run end to end, so nothing caught it. A
    notebook is only shipped if every free name at module level resolves.

    Names inside functions are left alone: their scope is decided at call
    time and a great deal of legitimate code would trip over it.
    """
    import builtins

    def _binds(node, into):
        for n in ast.walk(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
                into.add(n.name)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                into.add(n.id)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    into.add((a.asname or a.name).split(".")[0])
            elif isinstance(n, ast.arg):
                into.add(n.arg)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                into.add(n.name)
            elif isinstance(n, ast.alias) and n.asname:
                into.add(n.asname)

    known = set(dir(builtins)) | {"__name__", "__file__"}
    missing = []
    for body in code_cells:
        for stmt in ast.parse(body).body:
            # Bindings first, then reads. Within ONE statement that is
            # slightly permissive — `for k in d:` binds k before its body is
            # read — and across statements and cells, which is where the
            # real failure lives, it is exact.
            _binds(stmt, known)
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                continue          # a function's scope is decided at call time
            for n in ast.walk(stmt):
                if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                        and n.id not in known):
                    missing.append((n.id, n.lineno))
    if missing:
        names = sorted({m for m, _ in missing})
        raise SystemExit(
            f"{label} ABORTED — these names are read at the top level of a "
            f"cell but never defined by an earlier one: " + ", ".join(names))
    return True


cells = [("md", TITLE), ("code", setup_source())]

# definitions
for tag, title, body in module_cells():
    # No opening banner line: the FIRST line of a cell is what Jupyter shows
    # when the cell is collapsed, so it has to say what the cell does.
    banner = (f"# DEFINITIONS {tag} — {title.upper()}\n"
              "# " + "=" * 77 + "\n")
    cells.append(("code", banner + body))

# execution
ORDER = ["md_loading", "parameters", "load", "params_cell",
         "md_preprocess", "preprocess", "md_integrity", "integrity",
         "md_cycling", "cycling_tables", "cycling_figures", "cycling_more",
         "md_dqdv", "dqdv_figures", "md_heatmaps", "heatmaps",
         "md_detect", "detect", "md_fit", "fit", "md_quality", "quality",
         "md_analyse", "analyse", "md_fit_figures", "fit_figures",
         "md_export", "export",
         "close", "md_report", "report",
         # The science appendix, LAST. Jupyter cannot collapse all markdown at
         # once, so explanation interleaved with code makes the notebook
         # unnavigable — which is what 1.8.x did. Reference material goes
         # where it can be skipped.
         "md_appendix_1", "md_appendix_2", "md_appendix_3",
         "md_appendix_4", "md_appendix_5"]

# EVERY cell in cells.py must be placed in ORDER, or it silently vanishes
# from the notebook — which is how the science appendix went missing on its
# first build, and how the package notebook's own Cell 1 sat in cells.py for
# a release being edited by nobody and read by nothing.
#
# This used to check only the markdown cells, and excused `md_title` and
# `setup` because the package notebook consumed them. The inline notebook is
# now the only build, both of those cells are gone, and the guard covers the
# code cells too: there is no longer any such thing as a cell that lives in
# this file legitimately unplaced.
_missing = sorted(set(pipeline) - set(ORDER))
if _missing:
    raise SystemExit(f"inline build ABORTED — cells defined in cells.py but "
                     f"never placed in ORDER, so they would be dropped from "
                     f"the notebook: {', '.join(_missing)}")
_unknown = [k for k in ORDER if k not in pipeline]
if _unknown:
    raise SystemExit(f"inline build ABORTED — ORDER names cells that "
                     f"cells.py does not define: {', '.join(_unknown)}")
for k in ORDER:
    body = pipeline[k]
    if k.startswith("md_"):
        t = body.strip()
        if t.startswith('\"\"\"') and t.endswith('\"\"\"'):
            t = t[3:-3].strip()
        cells.append(("md", t))
    else:
        cells.append(("code", deprefix(body).strip("\n")))

# SETUP is checked too. It was in NEITHER argument, so Cell 1's bindings were
# never compared against the module definitions — which is how one name for
# numpy's trapezoid ended up defined in Cell 1 and again in a module cell.
_n = _check_shadowing([b for _, _, b in module_cells()],
                      [deprefix(pipeline[k]) for k in ORDER
                       if not k.startswith("md_")]
                      + [setup_source()])
print(f"  shadowing check: {_n} module functions, no clashes")
_ni = check_import_shadowing()
print(f"  import-shadowing check: {_ni} module definitions, none shadowed "
      f"by an import")

nb = {"cells": [], "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python",
                       "name": "python3"},
        "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
for kind, body in cells:
    if kind == "md":
        nb["cells"].append({"cell_type": "markdown", "metadata": {},
                            "source": (body + "\n").splitlines(True)})
    else:
        ast.parse(body)
        nb["cells"].append({"cell_type": "code", "metadata": {},
                            "execution_count": None, "outputs": [],
                            "source": (body + "\n").splitlines(True)})
out = f"/root/rat190/Ratatosk {VERSION} inline.ipynb"
json.dump(nb, open(out, "w"), indent=1)
print(f"{out}\n  {len(nb['cells'])} cells, "
      f"{sum(len(b.splitlines()) for _, b in cells)} lines")

_check_defined([b for k, b in cells if k == "code"], "inline build")
print("  free-name check: every top-level name resolves")

# --- the guard the flattened build cannot give you -------------------------
# `_check_defined` above resolves names against the WHOLE flattened script,
# which is one namespace. A module that uses a helper it never imported is
# therefore invisible to it: `analyse.py` called `style.section` in three
# reporting blocks without importing it, the notebook ran fine because the
# flat build had `section` defined higher up, and the PACKAGE — the tarball
# the RSE team receives — raised NameError in the delta-V summary, the
# capacity-attribution withholding notice and the coherence audit table.
# So each module is now also checked in isolation, against its own imports.
_import_fail = []
for _m in sorted(_p.stem for _p in
                 pathlib.Path("/root/rat190/ratatosk").glob("*.py")
                 if not _p.stem.startswith("__")):
    _src = open(f"/root/rat190/ratatosk/{_m}.py").read()
    _tree = ast.parse(_src)
    _have = set(dir(builtins))
    for _n in ast.walk(_tree):
        if isinstance(_n, ast.ImportFrom):
            _have |= {a.asname or a.name for a in _n.names}
        elif isinstance(_n, ast.Import):
            _have |= {(a.asname or a.name).split(".")[0] for a in _n.names}
        elif isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            _have.add(_n.name)
        elif isinstance(_n, ast.Assign):
            for _t in _n.targets:
                if isinstance(_t, ast.Name):
                    _have.add(_t.id)
        elif isinstance(_n, (ast.arg, ast.Name)) and isinstance(
                getattr(_n, "ctx", None), ast.Store):
            _have.add(_n.id)
        elif isinstance(_n, ast.arg):
            _have.add(_n.arg)
        elif isinstance(_n, ast.ExceptHandler) and _n.name:
            _have.add(_n.name)
        elif isinstance(_n, (ast.Global, ast.Nonlocal)):
            _have |= set(_n.names)
    for _fn in ast.walk(_tree):
        if isinstance(_fn, (ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.Lambda)):
            for _a in ast.walk(_fn.args):
                if isinstance(_a, ast.arg):
                    _have.add(_a.arg)
    _used = {_n.id for _n in ast.walk(_tree)
             if isinstance(_n, ast.Name) and isinstance(_n.ctx, ast.Load)}
    _missing = sorted(_used - _have)
    if _missing:
        _import_fail.append((_m, _missing))
if _import_fail:
    for _m, _names in _import_fail:
        print(f"  !! {_m}.py uses but does not import/define: "
              f"{', '.join(_names)}")
    raise SystemExit("module-isolation check failed — the package would "
                     "raise NameError even though the notebook runs")
print("  module-isolation check: every module resolves its own names")

# --- relative imports must be at MODULE SCOPE ------------------------------
# The flattener rewrites top-level `from .x import y`; a relative import
# inside a function body it leaves alone, and that line then runs in the
# notebook where there is no package to resolve against. In 1.9.0.49 one such
# import sat inside a try/except in `report._facts`, so the ImportError became
# silence and the cell-level integrity verdict disappeared from every notebook
# run without a word. Nothing could have caught that at runtime; this catches
# it at build time.
# A DELIBERATE one is allowed, and has to say why on the line itself:
# mark it `# inline-ok: <reason>`. `run.default_flags` is the standing case —
# it imports the modules to ask them for their constants, catches the
# ImportError the notebook raises, and reads plain globals instead. That is
# handled; the one this check exists for was swallowed.
_late = []
for _m in sorted(pathlib.Path(PKG).glob("*.py")):
    _src = _m.read_text()
    _lines = _src.splitlines()
    _tree = ast.parse(_src)
    for _node in ast.walk(_tree):
        if not isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
            continue
        for _sub in ast.walk(_node):
            if isinstance(_sub, ast.ImportFrom) and (_sub.level or 0) > 0:
                _span = "\n".join(
                    _lines[_sub.lineno - 1:(_sub.end_lineno or _sub.lineno)])
                if "inline-ok" in _span:
                    continue
                _names = ", ".join(a.name for a in _sub.names)
                _late.append(f"{_m.name}:{_sub.lineno} in {_node.name}() — "
                             f"from {'.' * _sub.level}{_sub.module or ''} "
                             f"import {_names}")
if _late:
    for _l in _late:
        print(f"  !! relative import inside a function: {_l}")
    raise SystemExit("late-relative-import check failed — the flattener "
                     "cannot rewrite these, so they raise ImportError in the "
                     "notebook. Move them to module scope.")
print("  late-import check: no relative import inside a function body")

# ...AND AN ALIASED ONE AT MODULE SCOPE IS THE SAME BUG WEARING A HAT.
# `strip()` DELETES every relative import rather than rewriting it, because
# the flat notebook is one namespace and the name is already there — under
# the name the DEFINING module gave it. `from .detect import formation_end as
# _formation_end` therefore leaves `_formation_end` defined nowhere, and the
# free-name check above does not see it when the use is inside a function
# body. Caught here instead: import relative names under their own names.
# `from . import plots as _plots` is a different thing and is fine — the
# module alias is stripped separately by `strip()`, which rewrites `_plots.`
# away entirely.
_aliased = []
for _m in sorted(pathlib.Path(PKG).glob("*.py")):
    _tree = ast.parse(_m.read_text())
    for _node in _tree.body:
        if not (isinstance(_node, ast.ImportFrom) and (_node.level or 0) > 0):
            continue
        for _a in _node.names:
            if _a.asname and _a.asname != _a.name and _node.module:
                _aliased.append(f"{_m.name}:{_node.lineno} — "
                                f"import {_a.name} as {_a.asname}")
if _aliased:
    for _l in _aliased:
        print(f"  !! aliased relative import: {_l}")
    raise SystemExit("aliased-relative-import check failed — the flattener "
                     "drops these lines, so the alias resolves to nothing in "
                     "the notebook. Import under the original name.")
print("  alias check: no aliased relative import")

# flat script for testing
script = "\n\n\n".join(b for k, b in cells if k == "code")
open("/root/nb/inline_all.py", "w").write(script)
ast.parse(script)
print(f"  flat script: {len(script.splitlines())} lines, parses")
