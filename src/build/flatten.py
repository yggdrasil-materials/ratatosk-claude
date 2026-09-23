"""Build the inline single-script notebook from the tested package."""
import ast, json, re, os

PKG = "/root/rat190/ratatosk"

# Every module the flattener emits, in no particular order —
# used by the import-shadowing guard.
MODULES = ("compat", "style", "io", "params", "signal", "detect", "fitting",
           "quality", "analyse", "plots", "cycling", "run", "report")


def load(mod):
    return open(f"{PKG}/{mod}.py").read()


def strip(src):
    """Remove what only makes sense inside a package."""
    lines = src.splitlines()
    tree = ast.parse(src)
    drop = set()
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and (n.level > 0 or n.module == "__future__"):
            drop.update(range(n.lineno, n.end_lineno + 1))
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id == "__all__"):
            drop.update(range(n.lineno, n.end_lineno + 1))
    out = [l for i, l in enumerate(lines, 1) if i not in drop]
    txt = "\n".join(out)
    txt = txt.replace("_ft.evaluate", "evaluate")
    # `cycling` reads the figure geometry through the plots MODULE so that
    # `set_figure_size` reaches it at call time. The flat notebook has one
    # namespace, where the bare global already behaves that way.
    # `cycling` re-exports two plot colours as its own module constants so
    # that its figures and the plotting module cannot drift apart. In one
    # namespace they ARE the same name, so the alias lines are dropped rather
    # than rewritten to `X = X` — which would be a self-assignment the
    # duplicate-definition guard is right to complain about.
    txt = re.sub(r"(?m)^([A-Z][A-Z0-9_]*) = _plots\.\1[ \t]*\n", "", txt)
    txt = txt.replace("_plots.", "")
    txt = re.sub(r"\n{4,}", "\n\n\n", txt)
    return txt.strip("\n")


def split_at(src, names, keep_head=True):
    """Split a module into (head, {name: block}) at top-level definitions."""
    tree = ast.parse(src)
    lines = src.splitlines()
    spans, first = {}, None
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names:
            start = n.lineno
            for d in n.decorator_list:
                start = min(start, d.lineno)
            # pull the comment block immediately above
            i = start - 2
            while i >= 0 and (lines[i].startswith("#") or not lines[i].strip()):
                if lines[i].startswith("#") or (
                        not lines[i].strip() and i > 0
                        and lines[i - 1].startswith("#")):
                    start = i + 1
                    i -= 1
                else:
                    break
            spans[n.name] = (start, n.end_lineno)
            first = start if first is None else min(first, start)
    head = "\n".join(lines[:first - 1]).strip("\n") if keep_head and first else ""
    return head, {k: "\n".join(lines[a - 1:b]) for k, (a, b) in spans.items()}


CYC_GROUPS = [
    ("J1", "Cycling: the summary table, voltage profiles and cycle life",
     # The three `_unusable*` helpers FIRST: every figure below asks them
     # which cycles are not a finished measurement, and a helper left out of
     # the flat notebook is a NameError at run time rather than at build.
     ["_unusable", "_unusable_cycles", "_ct_with_flag",
      "cycling_summary", "voltage_profiles", "voltage_profiles_key",
      "cycle_life"]),
    ("J2", "Cycling: comparison, retention and fade",
     ["comparative_capacity", "capacity_retention", "fade_rate"]),
    ("J3", "Cycling: energy, power, average voltage, efficiency and rate",
     # The rate-protocol helpers come BEFORE `rate_capability`, which now
     # calls them rather than keeping its own copies, and before
     # `annotate_rate_protocol`, which Cell 6a runs first of all so that
     # every caption downstream knows whether this run used one rate or ten.
     ["power_and_energy", "average_discharge_voltage", "energy_efficiency",
      "discharge_current_per_cycle", "group_cycles_by_rate",
      "current_to_crate", "snap_crate", "format_crate", "rate_phrase", "rate_protocol", "describe_rate",
      "annotate_rate_protocol", "rate_recovery",
      "rate_capability"]),
]
PLOT_GROUPS = [
    ("H1", "Figures: shared helpers and the dQ/dV views",
     ["_get_display_name", "_force_integer_cycles", "_discharge_label",
      "_charge_label", "_apply_pub_style", "_detect_short_halfcycles",
      "_waterfall_label_cycles", "plot_dqdv_all_cycles",
      "plot_dqdv_key_cycles_combined", "plot_dqdv_key_cycles_split",
      "plot_dqdv_waterfall", "plot_dqdv_heatmap", "plot_preprocessing_qc"]),
    ("H2", "Figures: peaks, fits, trends — and the adapters that feed them",
     ["plot_detected_peaks", "plot_fit_quality", "_areas_are_capacities",
      "plot_tracked_trends",
      "_build_ref_voltage_lookup", "plot_delta_v", "plot_capacity_attribution",
      "as_processed_dqdv", "as_detected_peaks", "_FitView", "as_fit_results",
      "as_tracked", "as_user_parameters"]),
]


def _check_split_complete(mod, src, listed):
    """Every top-level definition in the module must be named in a group.

    `split_at` keeps only the blocks it is asked for, so adding a function to
    plots.py or cycling.py and forgetting to list it here drops it silently
    from the inline notebook — and the failure surfaces as a NameError deep
    in a run, minutes later, on a machine that is not this one. It has
    happened twice (`report.py`'s module, then cycling's `_unusable`
    helpers), so it is checked at build time.
    """
    tree = ast.parse(src)
    defs = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            defs.append((n.lineno, n.name))
        elif isinstance(n, ast.Assign):
            # Module CONSTANTS too. `split_at` keeps only the function blocks
            # it is asked for, so a constant defined between two functions is
            # dropped as silently as a function is — and being a constant, it
            # fails at import of the cell rather than at first call, which is
            # if anything worse. `_BAND_NOTE` did exactly this.
            for t in n.targets:
                if (isinstance(t, ast.Name)
                        and re.fullmatch(r"_?[A-Z][A-Z0-9_]*", t.id)):
                    defs.append((n.lineno, t.id))
    # Everything before the first LISTED definition travels in the head, so
    # it is carried whether or not it is named. Only what follows can be lost.
    first = min((ln for ln, nm in defs if nm in set(listed)), default=None)
    missing = [nm for ln, nm in defs
               if nm not in set(listed) and first is not None and ln > first]
    if missing:
        raise SystemExit(
            f"inline build ABORTED — {mod}.py defines these at top level but "
            f"no group in flatten.py lists them, so they would be dropped "
            f"from the notebook: " + ", ".join(missing))


def check_import_shadowing():
    """
    A module-level NAME defined here must not be a name another module IMPORTS.

    `style.field` and `from dataclasses import field` are both top-level names
    in the flat notebook, and whichever cell ran last won — which turned every
    `field(...)` call into `dataclasses.field(...)` and killed the run at Cell
    9. The definition guard could not see it, because an import is not a
    FunctionDef.

    Checked here rather than fixed by ordering: in one namespace there is no
    ordering that makes two different meanings of one name both work.
    """
    import ast as _ast
    defined, imported = {}, {}
    for mod in MODULES:
        tree = _ast.parse(load(mod))
        for n in tree.body:
            if isinstance(n, (_ast.FunctionDef, _ast.ClassDef)):
                defined.setdefault(n.name, mod)
            elif isinstance(n, (_ast.Import, _ast.ImportFrom)):
                if isinstance(n, _ast.ImportFrom) and n.level:
                    continue          # relative imports are stripped
                for a in n.names:
                    nm = a.asname or a.name.split(".")[0]
                    imported.setdefault(nm, set()).add(mod)
    bad = {k: (defined[k], sorted(imported[k]))
           for k in set(defined) & set(imported)}
    if bad:
        lines = [f"  {k}  defined in {d}.py, imported by "
                 f"{', '.join(m + '.py' for m in ms)}"
                 for k, (d, ms) in sorted(bad.items())]
        raise SystemExit("inline build ABORTED — a module-level definition "
                         "collides with a name another module imports; in one "
                         "namespace only one of them survives:\n"
                         + "\n".join(lines))
    return len(defined)


def module_cells():
    """The definition cells, in dependency order."""
    cells = []

    def add(tag, title, body):
        cells.append((tag, title, body.strip("\n")))

    # `compat` is NOT here. It defines `trapezoid`, which every later cell
    # integrates with, and `check_environment`, which Cell 1 calls — so it is
    # emitted INTO Cell 1 by `setup_source()` rather than as a definition
    # cell of its own. A name cannot be called in the cell above the one that
    # defines it, and the environment report belongs with setup.
    # `style` first, then: every cell below prints with `entry`/`verdict`.
    add("A0", "How this notebook talks to you", strip(load("style")))
    add("A", "Reading a cycler export", strip(load("io")))
    add("A2", "What the operator is asked, and what the file already knows",
        strip(load("params")))
    add("B", "Q, V, I, t  ->  a dQ/dV curve", strip(load("signal")))
    add("C", "Finding features, and choosing the reference cycle",
        strip(load("detect")))
    add("D", "Building and running the model", strip(load("fitting")))
    add("E", "Does the answer mean anything?", strip(load("quality")))
    add("F", "Tracking, pairing, attribution, mechanism", strip(load("analyse")))

    p = strip(load("plots"))
    head, blocks = split_at(p, [n for _, _, ns in PLOT_GROUPS for n in ns])
    add("H1", PLOT_GROUPS[0][2] and PLOT_GROUPS[0][1],
        head + "\n\n\n" + "\n\n\n".join(blocks[n] for n in PLOT_GROUPS[0][2]))
    add("H2", PLOT_GROUPS[1][1],
        "\n\n\n".join(blocks[n] for n in PLOT_GROUPS[1][2]))

    _check_split_complete("plots", p, [n for _, _, ns in PLOT_GROUPS
                                       for n in ns])

    c = strip(load("cycling"))
    head, blocks = split_at(c, [n for _, _, ns in CYC_GROUPS for n in ns])
    for i, (tag, title, names) in enumerate(CYC_GROUPS):
        body = ((head + "\n\n\n") if i == 0 else "") + \
               "\n\n\n".join(blocks[n] for n in names)
        add(tag, title, body)
    _check_split_complete("cycling", c, [n for _, _, ns in CYC_GROUPS
                                         for n in ns])

    r = strip(load("run"))
    r = r.replace("""    from . import signal, detect, fitting, quality, analyse, plots
    out = {}
    for mod in (signal, detect, fitting, quality, analyse, plots):
        for k in dir(mod):
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
                continue
            v = getattr(mod, k)
            if v is None or isinstance(v, (bool, int, float, str)):
                out[f"{mod.__name__.rsplit('.', 1)[-1]}.{k}"] = v
            elif isinstance(v, (list, tuple)) and all(
                    isinstance(x, (bool, int, float, str)) for x in v):
                out[f"{mod.__name__.rsplit('.', 1)[-1]}.{k}"] = list(v)
    return out""",
"""    out = {}
    for k, v in sorted(globals().items()):
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
            continue
        if v is None or isinstance(v, (bool, int, float, str)):
            out[k] = v
        elif isinstance(v, (list, tuple)) and all(
                isinstance(x, (bool, int, float, str)) for x in v):
            out[k] = list(v)
    return out""")
    r = r.replace("""    Collected by asking each module for its own constants, so the manifest is
    complete whatever order the notebook was run in. 1.8.7 read a hardcoded
    name list out of `globals()`, and noted in its own docstring that a flag
    defined in Module 4 could not be seen from Cell 3b.""",
"""    Every ALL-CAPS module-level constant, whatever cell defined it. 1.8.7 read
    a HARDCODED LIST of names out of globals() and noted in its own docstring
    that a flag defined in Module 4 could not be seen from Cell 3b. Taking
    everything means the manifest cannot fall behind the code.""")
    add("K", "Run folders, the manifest, provenance", r)
    add("L", "The way in: START_HERE and the run summary", strip(load("report")))
    return cells
