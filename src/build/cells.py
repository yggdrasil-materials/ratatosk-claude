# Ratatosk — the pipeline cells, one per notebook cell.
#
# THE INLINE NOTEBOOK IS THE ONLY BUILD. Cell 1 is not here: it is the SETUP
# template in build_inline.py, because it has to carry the version as a
# literal and the compatibility layer inline. Nor is the title cell: that is
# TITLE, in the same file. Every cell in THIS file must be named in
# build_inline.ORDER or the build aborts.
#
# ---8<--- CELL md_loading
"""
## Loading, and what the cycler already knows

Ratatosk reads Neware `.xlsx` exports. Two sheets matter: `record`, which holds
the per-point voltage, current, capacity and dQ/dV, and `test`, which holds the
metadata the operator entered when the schedule was built — active mass,
voltage limits, C-rate, currents, planned cycle count.

**The `test` sheet is read first, and it matters.** Every number in it becomes
the default for a prompt in the next cell, marked `[from file]`. A mass typed
twice is a mass that can disagree with itself; a mass read from the schedule
cannot.

`read_neware` uses `calamine` when it is installed, which is 5–7× faster than
`openpyxl` on these files with a maximum numeric difference of exactly zero.

### On the electrode convention

For a **positive** electrode the cycler's step labels already match the
electrochemistry: charge oxidises the working electrode. For a **negative**
electrode they do not — the full cell discharges while the working electrode is
lithiated or sodiated.

So for a negative electrode Ratatosk swaps the step labels, the capacity and
energy columns, and the sign of dQ/dV, so that **"Discharge" is the useful
half-cycle for both polarities**. Every figure, table and ΔV downstream is then
directly comparable between a cathode and an anode.

This is applied in Cell 3b rather than at load, because which electrode is
under test is one of the things Cell 3b asks. Applying it twice is a no-op.
"""

# ---8<--- CELL parameters
# CELL 2 — WHAT TO ANALYSE            <-- this is the cell you edit
# =============================================================================
# ---------------------------- WHERE THE DATA IS, AND WHERE THE OUTPUT GOES
# The folder holding the Neware .xlsx exports.
#
# LEAVE IT BLANK AND IT IS SEARCHED FOR. Until 1.9.0.74 this line named one
# person's Google Drive letter, which meant the notebook ran on exactly one
# machine and raised NotADirectoryError on every other — including its own
# author's second computer. `find_data_dir` looks in the obvious places (cloud
# drives on every mounted letter, the home folder, the working directory) and
# prints which one it chose and why.
#
# Three ways to be explicit, in the order they win:
#
#   1. set the RATATOSK_DATA_DIR environment variable before starting
#      Jupyter — the one to use if you move between machines, run this on a
#      schedule, or hand it to somebody else;
#   2. put the path on the line below;
#   3. leave it blank and let the search find it.
#
# A folder that exists but holds no file matching PATTERN is not treated as
# the data folder, because otherwise the search would stop at Documents on
# almost every machine.
#
# BLANK, not `os.environ.get(...)`. The environment variable is read inside
# `find_data_dir`, which is the ONE place that decides where the data is —
# reading it here as well would be two places computing one quantity, which
# is the bug this build has now found four times.
DATA_DIR    = ""

# Where run folders are created. One per run, named <timestamp>_v<version>.
# Written relative to whoever is logged in, so the notebook does not carry one
# person's home directory into somebody else's run; replace it with an
# absolute path if you keep results somewhere specific.
OUTPUT_BASE = os.path.join(os.path.expanduser("~"), "Documents",
                           "electrochemical_analysis_output")

# Which files. Leave FILES empty and Cell 3a opens a file dialog on DATA_DIR
# — 1.8.7's Tkinter picker, so you can browse, sort by date and multi-select a
# triplicate. Where no dialog can be shown (a headless kernel, no display) it
# falls back to listing DATA_DIR grouped by chemistry and asking: answer with
# numbers, ranges like `1-3`, or blank for all. Set FILES explicitly to skip
# the question entirely, or FILE_DIALOG = False to always use the list.
FILES   = []
PATTERN = "*.xlsx"
FILE_DIALOG = True

# ------------------------------------------ WHERE THE PARAMETERS COME FROM
# How parameters are collected.
#   "ask"   Cell 3b prompts for each dataset, pre-filled from the cycler's own
#           'test' sheet. This is the 1.8.6 behaviour and the one to use: the
#           prompt shows "[from file: 4.72]" against a mass read out of the
#           workbook and "[default: 12.0]" against a convention, so you can see
#           which numbers you are actually responsible for.
#   "dict"  take them from PARAMETERS below, no prompting. For a scheduled run,
#           for a reproduction of an earlier run, or for a front end.
PARAMETER_MODE = "ask"

# Used only when PARAMETER_MODE == "dict". Composition, theoretical capacity
# and electrode type have no defensible default and must be given; everything
# else falls back to the cycler metadata and then to a documented default.
PARAMETERS = {
    # "JQ-P3-NaNiMnO2-35%-2-4.2V-0.1C-A-20062025": dict(
    #     composition="P3-NaNiMnO2", cell_id="A", electrode_type="Positive",
    #     theoretical_capacity_mAh_g=160.0,
    #     key_cycles=[1, 5, 10, 20, 50, 100],
    #     # dQ/dV preprocessing. Omit or leave "auto" to let the profile of
    #     # each dataset's own curve decide; set a value to override it.
    #     smoothing_window="auto", spike_removal="auto",
    #     rebin_width_mV="auto",
    # ),
}

# ---------------------------------- HOW MUCH OF THE CELL'S LIFE TO ANALYSE
# Cap the analysis while you are setting a run up; None = every cycle.
# Applied ONCE, to the dataset itself, in Cell 3b — so every later stage sees
# the same cycles and no stage can disagree with another about how many there
# were.
MAX_CYCLE = None

# Stop FITTING once the cell has stopped delivering charge. The plots still
# show every cycle — a cell going flat at 130 is exactly what the heatmap is
# for — but there is nothing to fit in a flat line, and on the P3 cells this
# is 40-70% of the fitting time.
STOP_FITTING_AT_DEATH = True

# --------------------------------------------------- HOW dQ/dV IS COMPUTED
# The single most consequential setting in the file.
#
#   "histogram"   charge binned by voltage — no derivative, no smoothing
#                 parameters. The curve integrates back to the delivered
#                 capacity by construction, so a peak area IS a capacity.
#   "derivative"  the cycler's own dQ/dV column, sorted, rebinned, despiked
#                 and smoothed. What every Ratatosk result before 1.9.0.14
#                 used.
#
# Measured on the LTO triplicate, same fits, only this changed:
#
#     integral fidelity   0.62 -> 0.995      area retention   141% -> 100%
#
# The derivative loses 40% of the charge on a two-phase plateau; the
# histogram does not. Keep "derivative" only to reproduce an earlier run —
# and if you do, note it, because the two are not comparable.
DQDV_COMPUTATION = "histogram"

# Voltage bin width for the histogram path, in mV — the ONLY parameter it has,
# and it means what it says: the voltage resolution of the curve.
#
# None lets the measured profile choose, as every other preprocessing setting
# already does: 1 mV for a sharp two-phase peak, 5 mV for a broad layered
# oxide whose features are 30-200 mV wide. Put a number to force one. It is
# widened automatically wherever the records are sparser than the bin, and
# the width actually used is recorded in dataset_info.txt.
DQDV_BIN_MV = None

# -------------------------------------------------- HOW MUCH FITTING TO DO
# Fit the dQ/dV peaks at all? The cycling analysis (Cells 5-7) does not need
# it, and on a rate test or a screening run there may be nothing worth fitting.
#
# In PARAMETER_MODE == "ask" this is only the DEFAULT: Cell 3b asks the same
# question at the end of the prompts and the answer there replaces this value.
# In "dict" mode nothing asks, and this is the setting.
RUN_PEAK_FITTING = True

# How many half-cycles the closure interval is measured on. Each one costs
# THREE fits (one per baseline degree), so this is the single biggest lever on
# how long Cell 10 takes: on a 200-cycle cell, None is 600 half-cycles and
# 1,800 fits — three times the cost of Cell 9's fitting.
# Evenly spaced, the default pins the median and the pass fraction well inside
# the width being measured; see quality.CLOSURE_SAMPLE_DEFAULT for the number
# and for why that is enough.
CLOSURE_SAMPLE = ql.CLOSURE_SAMPLE_DEFAULT

# Fit a dataset whose reference cycle says its peaks are not resolvable?
#
# True keeps the old behaviour exactly: everything is fitted, and the
# resolvability verdict is reported for information. False skips the
# decomposition for those datasets and reports positions and the envelope
# instead — which is what a solid-solution layered oxide can actually
# support, and it turns an hour of fitting into a few seconds.
#
# Left ON by default, because the verdict is new and a reader should be able
# to disagree with it and see the fit for themselves.
FIT_UNRESOLVED = True

RUN_NOTE = ""      # free text, recorded in the manifest

# How a long stage reports progress. Nothing is printed until it has been
# running for PROGRESS_QUIET_S, so a fast dataset stays silent instead of
# emitting ten lines of "2 of 21 (0 s)"; after that, a line roughly every
# PROGRESS_EVERY_S with an estimate of what is left.
PROGRESS_QUIET_S = 3.0
PROGRESS_EVERY_S = 10.0

# FIGURE GEOMETRY, in inches, applied to every figure the run produces.
# 6.73 x 5.0 is an RSC double-column. Set here rather than in a figure cell:
# `set_figure_size` writes a MODULE GLOBAL that the dQ/dV figures (Cell 7)
# and the fit figures (Cell 12) inherit, so setting it inside Cell 6 made
# those two cells depend on a cell neither of them needs. It went unnoticed
# because the values were the module defaults already, making the call a
# no-op that looked like configuration.
FIGURE_WIDTH_IN = 6.73
FIGURE_HEIGHT_IN = 5.0
pl.set_figure_size(FIGURE_WIDTH_IN, FIGURE_HEIGHT_IN)

# How much the cycling cells say. False quietens the per-dataset commentary
# in Cells 6a-6c and keeps the tables, figures and CSVs.
CYCLING_VERBOSE = True

# Which cycle the preprocessing QC figure (Cell 7) shows raw against
# processed for. Was a literal 2 in the call; a cycle inside formation is a
# poor advertisement for what the preprocessing does to a settled curve.
QC_CYCLE = 3

# ---------------------------------------------------------------- CHECKED
# The five headings above are SOURCE dividers, not prints. Printing them put
# six headings in the output with nothing underneath any of them — a settings
# cell that reported its own table of contents. Only a heading with something
# under it is worth a rule.
#
# Read back, and the run refused now if any of it is impossible. A mistyped
# PARAMETER_MODE used to fall through to the declarative branch and run on a
# NaN theoretical capacity; a mistyped DATA_DIR surfaced as an empty glob a
# cell later. See params.validate_run_settings for what each check is for.
print(rule("SETTINGS AS READ BACK"))
# Blank means "find it" — see the note against DATA_DIR above. Resolved here
# rather than on the assignment so the search prints inside this cell's own
# banner, with everything else that was read back.
if not DATA_DIR.strip():
    DATA_DIR = find_data_dir(pattern=PATTERN, verbose=True)
RUN_SETTINGS = validate_run_settings(
    data_dir=DATA_DIR, output_base=OUTPUT_BASE, files=FILES, pattern=PATTERN,
    parameter_mode=PARAMETER_MODE, parameters=PARAMETERS,
    max_cycle=MAX_CYCLE, dqdv_computation=DQDV_COMPUTATION,
    dqdv_bin_mV=DQDV_BIN_MV, closure_sample=CLOSURE_SAMPLE,
    run_peak_fitting=RUN_PEAK_FITTING)

# Written back NORMALISED, so the cells below compare against what was
# checked rather than against what was typed. `PARAMETER_MODE = "Ask"`
# satisfied the check and then failed a case-sensitive `== "ask"` two cells
# later, which is the same silent fall-through in a new place.
PARAMETER_MODE   = RUN_SETTINGS["parameter_mode"]
DQDV_COMPUTATION = RUN_SETTINGS["dqdv_computation"]
print(rule())

# ---8<--- CELL load
# CELL 3a — CHOOSE THE FILES, AND READ WHAT THE CYCLER ALREADY KNOWS
# =============================================================================
# A folder holds more than one experiment. Eight files here are three
# chemistries, and loading all of them puts an LTO anode and an NMC cathode on
# the same axes. So the files are listed, grouped by chemistry, and you pick.
#
# Then the 'test' sheet of each chosen export is read: active mass, voltage
# limits, C-rate, currents, planned cycle count. Every one of those becomes the
# default for a prompt in the next cell, marked [from file].
#
# Each workbook is opened ONCE and both sheets read through the one handle.
# Opening it twice parsed it twice — and the second read, being by path, fell
# back to openpyxl while the first was using calamine. Measured on a 34 MB
# export: 3.02 s against 1.33 s, 36% of the whole load.

print(rule("CHOOSING FILES"))

def _natural(text):
    """Sort A2 before A10. `sorted()` alone puts A10 first, which makes a
    listing of a triplicate read as though cells were missing."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", str(text))]

_all = ([os.path.join(DATA_DIR, f) for f in FILES] if FILES
        else sorted(glob.glob(os.path.join(DATA_DIR, PATTERN)), key=_natural))
if not _all:
    # Raised whether or not a dialog was on offer. Handing an empty list to
    # the picker showed an empty dialog and then failed with a confusing
    # error about the selection, rather than saying the folder is empty.
    raise FileNotFoundError(
        f"No files matched {PATTERN!r} in:\n    {DATA_DIR}\n"
        f"  the folder holds "
        f"{len(os.listdir(DATA_DIR))} entries; check PATTERN in Cell 2.")

# FILES set explicitly means you have already chosen; otherwise, choose now.
_paths = _all if FILES else select_files(_all, initialdir=DATA_DIR,
                                         use_dialog=FILE_DIALOG)
if not _paths:
    raise FileNotFoundError("No files were selected — nothing to analyse.")

print(rule("READING"))
datasets, cycler_metadata = {}, {}
_t0 = time.time()
for _i, path in enumerate(_paths, 1):
    name = os.path.splitext(os.path.basename(path))[0]
    # Two exports with the same stem in different folders would silently
    # overwrite each other, and the run would report one file where two were
    # loaded. Named rather than dropped, so the second is still analysed.
    if name in datasets:
        _stem, _k = name, 2
        while name in datasets:
            name, _k = f"{_stem} ({_k})", _k + 1
        print(f"  two files share the stem {_stem!r}; this one is {name!r}")
    print(section(f"  [{_i}/{len(_paths)}] {name}"))
    _book, _engine = open_workbook(path)
    try:
        cycler_metadata[name] = extract_neware_metadata(_book)
        # Read WITHOUT applying the electrode convention: which electrode this
        # is is one of the things Cell 3b asks, and it cannot be applied before
        # it has been answered. This is the order 1.8.6 used, for the same
        # reason.
        datasets[name] = read_neware(path, name=name,
                                     electrode_type="Positive",
                                     meta=cycler_metadata[name],
                                     book=_book, engine=_engine, verbose=True)
    finally:
        _book.close()

# A record table missing any of these is not a Neware GCPL export, and every
# later stage assumes all of them. Said here, naming the file and the columns
# actually present, rather than as a KeyError inside a figure four cells
# later. The names are the RENAMED ones (io.COLUMNS), which is what the rest
# of the pipeline reads.
_needed = ("Cycle", "Step", "Voltage", "Charge_Capacity", "Discharge_Capacity")
for name, ds in datasets.items():
    _absent = [c for c in _needed if c not in ds.frame.columns]
    if _absent:
        raise KeyError(
            f"{name}: the 'record' sheet has no "
            f"{', '.join(_absent)} column{'s' if len(_absent) > 1 else ''}.\n"
            f"  columns found: {', '.join(map(str, ds.frame.columns))}")
    if ds.frame.empty:
        raise ValueError(f"{name}: the 'record' sheet is empty.")

# `electrochemical_data` was a second dict holding exactly `ds.frame` for every
# dataset, updated by hand in Cell 3b and read in three places. One of those
# updates was missed in 1.9.0.9 and the two disagreed for a whole release. It
# is now a VIEW built from the datasets, so it cannot fall behind them.
electrochemical_data = {n: ds.frame for n, ds in datasets.items()}

print(rule())
print(f"  {len(datasets)} file{'s' if len(datasets) != 1 else ''} read in "
      f"{time.time() - _t0:.1f} s")
print("\nRead from the cycler's own file:")
print(describe_defaults(cycler_metadata))

# ---8<--- CELL params_cell
# CELL 3b — PARAMETERS, AND THE ELECTRODE CONVENTION
# =============================================================================
# What the file cannot tell us: what the material is, what its theoretical
# capacity is, which electrode is under test, how the electrode was made, and
# how you want the figures to look.
#
# The electrode type is applied here rather than at load. For a NEGATIVE
# electrode the step labels and the sign of dQ/dV are swapped, so that the
# useful half-cycle reads as "Discharge" for both polarities and every figure
# and table downstream is comparable. It is applied ONCE, to a dataset loaded
# as Positive; `apply_electrode_convention` refuses to run over a dataset
# whose labels have already been swapped rather than quietly swapping them
# back.

# The run folder FIRST, so that a run which is then abandoned at the prompts
# leaves a folder saying what was attempted — and so the folder is not created
# only after five minutes of typing.
RUN_DIR, MANIFEST = start_run(OUTPUT_BASE, RATATOSK_VERSION,
                              input_paths=_paths, note=RUN_NOTE)
MANIFEST["environment"] = ENVIRONMENT
MANIFEST["run_settings"] = RUN_SETTINGS
write_manifest(RUN_DIR, MANIFEST)
print(rule("RUN FOLDER"))
print(f"  {RUN_DIR}")

print(rule("PARAMETERS"))
if PARAMETER_MODE == "ask":
    # The prompts ask about peak fitting too, and the answer given there is
    # the one that counts — Cell 2's RUN_PEAK_FITTING is only the default it
    # is offered against. Named on both sides so that is visible.
    user_parameters, RUN_PEAK_FITTING = collect_parameters(
        electrochemical_data, cycler_metadata)
else:
    # Not a fallback: PARAMETER_MODE is checked in Cell 2 and can only be
    # "ask" or "dict" by the time this runs, and dict mode with an empty
    # PARAMETERS is refused there. What used to be here was a synthetic
    # `theoretical_capacity_mAh_g=np.nan` for every dataset, which passed the
    # required-field check and then disabled the over-theoretical guard for
    # the whole run, because `x > 1.2 * nan` is False.
    user_parameters = parameters_from_dict(PARAMETERS, cycler_metadata)

print(rule("APPLYING THEM"))
for name, params in user_parameters.items():
    datasets[name] = apply_electrode_convention(
        datasets[name], params.get("electrode_type", "Positive"))
    # Cut the DATASET, which is what every later stage reads, and cut it once
    # for both caps: MAX_CYCLE from Cell 2 and the per-dataset `max_cycle`
    # answered in the prompts. Before 1.9.0.9 the prompt's answer was applied
    # to a copy that the next line overwrote, so it changed nothing while the
    # console, dataset_info.txt and the manifest all said it had — and
    # MAX_CYCLE reached only the dQ/dV half, so the two halves of one run
    # could cover different cycles.
    # `is not None`, not truthiness: `max_cycle = 0` is a mistake worth
    # reporting, not a cap to be silently ignored.
    _cap = [int(c) for c in (MAX_CYCLE, params.get("max_cycle"))
            if c is not None]
    if _cap:
        _n_before = int(datasets[name].frame["Cycle"].max())
        datasets[name] = truncate_cycles(datasets[name], min(_cap))
        _n_after = int(datasets[name].frame["Cycle"].max())
        params["max_cycle"] = min(_cap)
        if _n_after < _n_before:
            print(f"  {name}: cut at cycle {min(_cap)} "
                  f"(was 1-{_n_before}, now 1-{_n_after})")
    params["anode_labels_swapped"] = datasets[name].labels_swapped
    if datasets[name].labels_swapped:
        print(f"  {name}: negative electrode — labels and dQ/dV sign swapped")

# Rebuilt from the datasets, not patched alongside them. See Cell 3a.
electrochemical_data = {n: ds.frame for n, ds in datasets.items()}

print(rule("COMMITTED"))

def _or_dash(value, unit="", places=1):
    """A number and its unit, or an honest dash. `f"{None:.1f}"` is a
    TypeError and `f"{nan:.1f}"` prints "nan mAh/g", which reads as a
    measurement."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "not given"
    return f"{v:.{places}f} {unit}".strip() if np.isfinite(v) else "not given"

for name, params in user_parameters.items():
    print(section(f"  {name}"))
    print(entry("composition", params.get("composition", "—"),
                params.get("cell_id", "") and f"cell {params['cell_id']}"))
    print(entry("electrode", params.get("electrode_type", "Positive"),
                "labels and dQ/dV sign swapped"
                if params.get("anode_labels_swapped") else ""))
    print(entry("theoretical capacity",
                _or_dash(params.get("theoretical_capacity_mAh_g"), "mAh/g")))
    print(entry("active mass",
                _or_dash(params.get("active_material_mass_mg"), "mg", 2)))
    print(entry("cycles",
                f"1-{int(datasets[name].frame['Cycle'].max())}"))

MANIFEST["datasets"] = {
    n: dict(source=ds.source_path, sha256=ds.source_sha256,
            electrode_type=ds.electrode_type,
            labels_swapped=ds.labels_swapped,
            cycler_metadata=cycler_metadata.get(n, {}),
            parameters=user_parameters[n])
    for n, ds in datasets.items()}
MANIFEST["run_settings"]["run_peak_fitting"] = bool(RUN_PEAK_FITTING)
write_manifest(RUN_DIR, MANIFEST)
print(rule())
# The folder itself was printed when it was opened, at the top of this cell.
# Saying the whole path again here made the reader check whether it was a
# different one.
print("  manifest written")

# ---8<--- CELL md_preprocess
"""
## dQ/dV preprocessing

Differentiating a measurement amplifies its noise, and a raw dQ/dV from a
cycler is spiky. Four things are done about it, and the settings for all four
come from the **shape of each dataset's own curve** rather than from a single
house default.

| step | what it does | why it is not one setting for everything |
|---|---|---|
| **constant-voltage hold removal** | drops the trailing points where the current is tapering at the voltage limit | a CV hold puts a large spike at the limit that is protocol, not chemistry |
| **rebinning** | averages onto a regular voltage grid | a sharp profile logs at 0.3 mV with 22% duplicate voltages; a broad one at 9 mV. Rebinning helps the first and destroys the second |
| **spike removal** | drops points far from the local median | a genuine sharp peak *is* far from its local median. Disabled for sharp profiles |
| **Savitzky–Golay smoothing** | polynomial smoothing over a moving window | a window that flatters a broad feature erases a narrow one |

`classify_dqdv_profile` measures two things — the interquartile range of dQ/dV
as a fraction of its full range, and the fraction of the curve sitting on a
plateau — and returns **sharp**, **moderate** or **broad**. LTO and LFP come
out sharp; layered oxides come out broad. The classification is printed with
the numbers behind it so it can be argued with.

Anything you set in Cell 3b overrides the automatic choice for that dataset.
Leave a field on `"auto"` to let the profile decide.

### The voltage window

The window is computed **once per dataset** — global minimum and maximum,
trimmed by 50 mV at each end — and every half-cycle is clipped to it. Computing
it per half-cycle instead, which is the obvious-looking thing, trims 50 mV off
each half-cycle's own extremes and silently removes real data from all of them.

### One deliberate difference from 1.8.x

Records are sorted by voltage with a **stable** sort. 1.8.x used pandas'
default quicksort, which is not stable, so where several records share a
voltage the order among them was decided by the sort's internals rather than by
the data — and a first charge can carry 483 tied voltages in 1434 records,
because the cycler logs to 0.1 mV and the cell sits on a plateau. Despiking and
smoothing then ran over that arbitrary order, which means 1.8.x's smoothed
curve was not a well-defined function of its input: reorder the rows and it
changed. A stable sort breaks ties by acquisition order.
"""

# ---8<--- CELL preprocess
# CELL 4 — Q, V, I, t  ->  dQ/dV
# =============================================================================
# The preprocessing is chosen from the SHAPE of each dataset's own dQ/dV, and
# the class it finds is printed — it is the only decision this cell makes, and
# it sets the smoothing, the bin width, and downstream the baseline degree and
# the sigma bounds.
#
# WHICH KNOBS APPLY DEPENDS ON THE PATH. The histogram reads two of them; the
# derivative reads the other seven. Anything set in Cell 3b for the path that
# is NOT running is named and ignored, rather than echoed back as though it
# had been applied — which is what happened for three releases after the
# histogram became the default.
#
#   histogram    histogram_bin_mV            voltage resolution of the curve
#                histogram_smooth_bins       binomial kernel half-width, in bins
#
#   derivative   smoothing_window            Savitzky-Golay window, in points
#                polyorder                   its polynomial order
#                spike_removal               median-deviation despiking on/off
#                spike_window_size           its window
#                spike_threshold_multiplier  how far from the local median counts
#                rebin_width_mV              regular voltage grid, in mV
#                second_smooth_window        an optional second pass
#
# Anything left on "auto" is decided here from the measured profile.
profiles, preprocess_params, windows, signals = {}, {}, {}, {}
# The cut-off approach removed per step, kept so Cell 14 can record it.
trims = {}
reconstruction = {}   # per dataset: APE and voltage RMSE per half-cycle

for name, ds in datasets.items():
    print(rule(name))
    prof = classify_dqdv_profile(ds.frame, verbose=True)
    profiles[name] = prof
    auto = auto_preprocess_params(prof)
    overrides = preprocess_overrides(user_parameters.get(name, {}))
    # An override for the path that is not running changes nothing. Say so
    # here, where it can still be acted on.
    _mine = set(pm.KEYS_BY_DQDV_METHOD[DQDV_COMPUTATION])
    _theirs = {k: v for k, v in overrides.items() if k not in _mine}
    _used = {k: v for k, v in overrides.items() if k in _mine}
    if _used:
        print(entry("operator overrides",
                    ", ".join(f"{k}={v}" for k, v in sorted(_used.items()))))
    if _theirs:
        print(verdict("caution", f"{len(_theirs)} override(s) belong to the "
                                 f"{'derivative' if DQDV_COMPUTATION == 'histogram' else 'histogram'} "
                                 f"path and do nothing here"))
        print(bullet(", ".join(f"{k}={v}" for k, v in sorted(_theirs.items()))
                     + " — set DQDV_COMPUTATION in Cell 2 to use them, or "
                       "remove them."))
    preprocess_params[name] = {**auto, **overrides,
                               "dqdv_method": DQDV_COMPUTATION}
    if DQDV_BIN_MV is not None:           # None = let the profile choose
        preprocess_params[name]["histogram_bin_mV"] = DQDV_BIN_MV

    # THE ANALYSIS AXIS, not the protocol window. Cell 3b measured the window
    # the cell was CYCLED between (the median of the per-cycle limits, e.g.
    # 1.2-2.5 V) and put it in the methods record. This is the voltage axis
    # the curve is COMPUTED on: the full extent of the data, trimmed 50 mV, so
    # that every half-cycle of one dataset shares one axis. They are different
    # quantities and they do not have to agree — cell A's open-circuit start
    # at 2.684 V puts this 134 mV above the protocol top.
    windows[name] = voltage_window(ds)
    # No cycle filter here. The dataset itself was cut in Cell 3b, once, for
    # both caps — a second filter against MAX_CYCLE alone could only ever
    # disagree with it, by ignoring the per-dataset `max_cycle` the prompts
    # asked for.
    keys = list(ds.half_cycle_keys())
    signals[name] = {}
    # Progress only once the work is SLOW ENOUGH TO WAIT FOR. A fixed
    # every-nth-item ticker printed ten lines of "2 of 21 (0 s)" for a job
    # that finished in under a second, which is noise dressed as reassurance.
    # Nothing is printed for the first few seconds; after that, roughly every
    # PROGRESS_EVERY_S, with an estimate of what is left.
    _t0, _next = time.time(), PROGRESS_QUIET_S
    for _i, k in enumerate(keys, 1):
        signals[name][k] = half_cycle_report(ds, *k, preprocess_params[name],
                                             window=windows[name])
        _el = time.time() - _t0
        if _el >= _next and _i < len(keys):
            print(f"      {_i} of {len(keys)} half-cycles   {_el:.0f} s "
                  f"elapsed, ~{_el * (len(keys) - _i) / _i:.0f} s left",
                  flush=True)
            _next = _el + PROGRESS_EVERY_S
    n_curve = sum(1 for s in signals[name].values() if s.voltage.size)
    print(entry("curves", f"{n_curve} of {len(keys)}",
                f"half-cycles; axis {windows[name][0]:.4f}-"
                f"{windows[name][1]:.4f} V, {time.time() - _t0:.0f} s"))

    # DOES THE CURVE GIVE THE VOLTAGE CURVE BACK? A derivative is reversible,
    # so the cumulative integral of dQ/dV against V should reproduce the
    # (Q, V) curve it came from. That is the objective test of a dQ/dV
    # computation — many parameter choices look right, few reconstruct — and
    # it is how the histogram path earned the default.
    _rec, _bw, _empty, _bins = [], [], 0, 0
    for k, sg_ in signals[name].items():
        if not sg_.voltage.size:
            continue
        if np.isfinite(sg_.bin_width_mV):
            _bw.append(sg_.bin_width_mV)
        _empty += sg_.n_empty_bins
        _bins += sg_.voltage.size
        # The SAME frame the signal was built from. `ds.half_cycle` is now a
        # cached dict lookup rather than a full-frame scan, so asking twice is
        # no longer expensive — but asking once is still clearer.
        _hc = ds.half_cycle(*k)
        _qc = ("Charge_Capacity" if str(k[1]).lower().startswith("c")
               else "Discharge_Capacity")
        if _qc not in _hc.columns:
            continue
        _rec.append(ql.voltage_reconstruction(
            sg_.voltage, sg_.dqdv,
            pd.to_numeric(_hc[_qc], errors="coerce").to_numpy(),
            pd.to_numeric(_hc["Voltage"], errors="coerce").to_numpy()))
    # --- TRIM THE CUT-OFF APPROACH ---------------------------------------
    # A half-cycle ends on a VOLTAGE, and as the cell reaches it dV/dQ
    # collapses so dQ/dV climbs: within 20 mV of the cut-off the NNM charge
    # curve stands at 5.2x its own median height. That rise is protocol, not
    # chemistry — the same argument this pipeline already makes about a
    # constant-voltage hold — and left in it is fitted as a peak, with the
    # cubic baseline straining to follow what the peaks cannot. That was the
    # whole cause of the fitting not converging.
    #
    # PER STEP, because a half-cycle has one cut-off and it is at a different
    # end for each: charge terminates high, discharge terminates low. The trim
    # is measured on every half-cycle and the step's MEDIAN applied to all of
    # them, so the voltage axis stays common within a step — which the
    # reference peak list depends on.
    trims[name] = {}
    if sg.TERMINAL_TRIM and signals[name]:
        for _st in ("Charge", "Discharge"):
            _mine = [v for k, v in signals[name].items() if k[1] == _st]
            if not _mine:
                continue
            # A FIXED span at the terminating end when one is set, because
            # the measured rule is bimodal across a full run and its median
            # is not a physical quantity — see signal.TERMINAL_TRIM.
            _fx = sg.TERMINAL_TRIM_FIXED_MV
            if _fx:
                _lo = (_fx / 1000.0) if _st == "Discharge" else 0.0
                _hi = (_fx / 1000.0) if _st == "Charge" else 0.0
            else:
                _m = [sg.terminal_trim(x.voltage, x.dqdv) for x in _mine
                      if np.size(x.voltage) > 20]
                if not _m:
                    continue
                _lo = float(np.median([a for a, _ in _m]))
                _hi = float(np.median([b for _, b in _m]))
            trims[name][_st] = (_lo, _hi)
            if _lo <= 0 and _hi <= 0:
                continue
            for k in [k for k in signals[name] if k[1] == _st]:
                signals[name][k] = sg.apply_terminal_trim(
                    signals[name][k], _lo, _hi)
        _said = {k: v for k, v in trims[name].items() if max(v) > 0}
        if _said:
            for _st, (_lo, _hi) in sorted(_said.items()):
                _end = "top" if _hi > _lo else "bottom"
                print(entry(f"{_st.lower()} cut-off trimmed",
                            f"{1000 * max(_lo, _hi):.0f} mV",
                            f"off the {_end} of the window — the approach to "
                            f"the cut-off, not a redox feature"))
            print(bullet("The charge that passed there is still the cell's "
                         "and is still counted; it is no longer in the curve, "
                         "so integral fidelity now reports the shortfall "
                         "instead of a baseline absorbing it."))
        else:
            print(entry("cut-off trim", "none needed",
                        "TERMINAL_TRIM is off — see §A11"))

    reconstruction[name] = _rec
    print(entry("dQ/dV method", DQDV_COMPUTATION,
                "charge binned by voltage, no derivative"
                if DQDV_COMPUTATION == "histogram"
                else "cycler column, sorted, rebinned, despiked, smoothed"))
    print(ql.describe_reconstruction(
        _rec, method=DQDV_COMPUTATION, window=windows[name],
        bin_widths=_bw if DQDV_COMPUTATION == "histogram" else None,
        empty_fraction=(_empty / _bins) if _bins else None))

    # On a two-phase plateau the true dV per record drops below the cycler's
    # voltage resolution and the recorded voltage wobbles backwards, so the
    # instrument divides a positive dQ by a negative dV and reports the wrong
    # sign with a huge magnitude. Sorting by voltage then interleaves those
    # with the honest records and smoothing averages the two — which is the
    # up-and-down pattern on a first cycle, and at the LTO plateau an
    # inverted peak. A high count here is a FLAT PLATEAU, not a fault.
    #
    # DERIVATIVE PATH ONLY. The histogram never sorts and never divides, so
    # it has nothing to correct and reports 0 every time — this block was
    # printing nothing on the default path while explaining itself at length.
    if DQDV_COMPUTATION == "derivative":
        _nor = {k: s.n_oriented for k, s in signals[name].items()
                if s.n_oriented}
        if _nor:
            _tot = sum(_nor.values())
            _wor = max(_nor, key=_nor.get)
            print(entry("plateau sign corrected", f"{_tot} record(s)",
                        f"across {len(_nor)} half-cycle(s); most in cycle "
                        f"{_wor[0]} {_wor[1]} ({_nor[_wor]})"))
print(rule())

# ---8<--- CELL md_integrity
"""
## Cycle integrity — where did the charge go?

During charge, dQ/dV should be positive: charge goes in and the potential
rises. Where it is negative the potential is moving *backwards* under applied
current. Three unrelated things do that, and 1.8.x conflated all three under a
single threshold that transferred neither between the cells of one triplicate
nor between chemistries.

Every contiguous backwards run is now inventoried — how much charge passed,
over what voltage band, at what current — and classified by **where on the
curve it sat**:

| verdict | test | what it is |
|---|---|---|
| `plateau` | at full current, and \|dQ/dV\| there is ≥ 5% of this half-cycle's own maximum | a two-phase equilibrium pinning the potential. Real, intended charge |
| `cv_hold` | current below the constant-current value, within 50 mV of the window edge | protocol, not chemistry |
| `parasitic` | at full current, \|dQ/dV\| small, away from the limit | charge passed with no redox process to account for it |

Only the third is a fault. Every term is measured against the half-cycle
**itself** — its own peak \|dQ/dV\|, its own current, its own capacity — which
is why it transfers, and it is exactly what a pooled threshold could not do.

The plateau test reads the curve, **not a peak list**. That is why integrity
runs before detection, and why the reference-cycle chooser in Cell 8 can be
handed its verdict.

**Measured on 1,384 half-cycles across six cells:** every half-cycle flagged
ANOMALOUS sits in a cycle whose coulombic efficiency is below 60%, and above
CE 60% nothing anywhere carries more than 0.4% of its capacity backwards.

### Bands

- **clean** — no charge passed backwards away from a redox process
- **suspect** — some did, but under 2% of this half-cycle's own capacity
- **ANOMALOUS** — at or above 2%
- **too few records** — the half-cycle is too short to read. *Not* the same as
  clean: it means we could not tell, and the reference-cycle chooser refuses to
  anchor a dataset to it.

### Where the cell died

This cell also finds the point at which the cell stopped delivering, judged
against its own working capacity (the 90th percentile, not the median — where
a cell dies a third of the way into a long record, the median is
0.04 mAh/g and useless).

**That limit stops the fitting, not the plots.** There is nothing to fit in a
flat line, and every such fit is discarded downstream — but the heatmap and the
waterfall should still show the whole record, because a cell going flat at
cycle 130 is exactly what the reader needs to see.
"""

# ---8<--- CELL integrity
# CELL 5 — CYCLE INTEGRITY
# =============================================================================
# Where did the charge go? Every contiguous run in which the potential moved
# against the applied current is classified by WHERE on the curve it sat:
#
#   plateau     |dQ/dV| there is a substantial share of this half-cycle's own
#               maximum — a two-phase equilibrium. Real, intended charge.
#   cv_hold     current below the constant-current value, at the voltage
#               limit. Protocol, not chemistry.
#   parasitic   full current, |dQ/dV| small, away from the limit. Charge with
#               no redox process to account for it.
#
# Only the third is a fault, and it is measured against the half-cycle's own
# capacity, never against a population.
#
# A SECOND, independent test needs no dQ/dV at all: did more charge pass than
# the material can hold? A half-cycle above 1.2x the theoretical capacity is
# condemned whatever the shape of its curve, because a curve cannot vouch for
# charge the material could not have held. On P3 cell A that is the difference
# between reporting 598 mAh/g of reassuring "two-phase plateau" and reporting
# 38 — the other 559 are on half-cycles running at up to 4.3x theoretical.
#
# A THIRD asks how each half-cycle ENDED. A galvanostatic half-cycle
# terminates on voltage, so one that stopped short either was caught by the
# export mid-flight (`in_progress`) or stopped on something else — a step
# timer, a safety limit, an aborted schedule (`early_stops`). Both are
# excluded from the FIT and kept in every figure.
integrity, integrity_band, fit_limit = {}, {}, {}
in_progress = {}      # (cycle, step) caught part-way through, per dataset
early_stops = {}      # half-cycles that stopped short WITHOUT being caught
not_measurements = {}  # the union of the two — what the fit skips
for name in datasets:
    print(rule(name))
    R, band = an.integrity_report(
        signals[name], window=windows[name], name=name, verbose=True,
        theoretical_mAh_g=user_parameters.get(name, {}).get(
            "theoretical_capacity_mAh_g"))
    integrity[name], integrity_band[name] = R, band
    # Flat, like every other output in this notebook; Cell 14's `organise_run`
    # files it into <cell>/1_cycling/ by its filename prefix.
    R.to_csv(os.path.join(RUN_DIR, f"{name}_cycle_integrity.csv"), index=False)

    # Where the cell stopped delivering. This limits the FIT, not the plots.
    _caps = {k: s.capacity for k, s in signals[name].items()}
    if not _caps:
        print(verdict("bad", "no half-cycles — nothing to judge"))
        fit_limit[name] = None
        in_progress[name], early_stops[name] = set(), pd.DataFrame()
        not_measurements[name] = set()
        continue
    _last, _why = last_useful_cycle(_caps)
    # `is not None`, not truthiness. `last_useful_cycle` returns the cycle
    # BEFORE the death and documents in its own body that returning 0 would
    # read as "never dies" to a caller testing truthiness — this is that
    # caller, and it should not be the reason that stays true.
    fit_limit[name] = _last if STOP_FITTING_AT_DEATH else None
    _n = max(c for c, _ in _caps)
    if fit_limit[name] is not None:
        print(verdict("caution", f"fitting stops at cycle {fit_limit[name]} "
                                 f"of {_n} "
                                 f"({(1 - fit_limit[name] / _n):.0%} of the "
                                 f"record skipped)"))
        print(bullet(_why))
    elif _last is not None:
        print(verdict("caution", "the cell died, and the whole record will "
                                 "be fitted anyway"))
        print(bullet(f"{_why}. STOP_FITTING_AT_DEATH is False in Cell 2."))
    else:
        print(verdict("ok", "the cell never stopped delivering"))
        print(bullet(f"{_why} — fitting the whole record"))

    # ONE termination check, two questions asked of it. Each used to run its
    # own: 10.6 s apiece on P3 cell A, for an identical frame.
    _T = an.termination_check(datasets[name])

    # A cycler export is usually written while the cell is still running,
    # so the file's last half-cycle is unfinished. The question is settled
    # on VOLTAGE, because that is what a galvanostatic half-cycle terminates
    # on: a finished one reaches the cut-off, an interrupted one stops
    # wherever it had got to. Omitted from the FIT at half-cycle granularity
    # — the completed half of the same cycle is kept — and still plotted.
    in_progress[name], _ip_why = an.half_cycles_in_progress(datasets[name],
                                                            checked=_T)
    print(verdict("caution" if in_progress[name] else "ok",
                  "the export caught a half-cycle mid-flight"
                  if in_progress[name] else "every half-cycle finished on "
                                            "its cut-off voltage",
                  label="termination"))
    print(bullet(_ip_why))

    # A half-cycle that stopped short of the cut-off but ran a NORMAL LENGTH
    # of time was not caught by the export — it terminated on something else
    # (a step timer, a safety limit, an aborted schedule). That is a finding
    # about the experiment, not a footnote about the file.
    #
    # It is now ACTED ON as well as printed. Until 1.9.0.16 this frame was
    # computed, described in one console line, and then never referred to
    # again: not excluded from the fit, not recorded in dataset_info.txt, not
    # in the manifest, not written to a CSV. A half-cycle that terminated on
    # a step timer is not a capacity measurement, and it was going into every
    # mean and every retention figure as though it were.
    early_stops[name] = an.early_terminations(datasets[name], checked=_T)
    if not early_stops[name].empty:
        early_stops[name].to_csv(
            os.path.join(RUN_DIR, f"{name}_early_terminations.csv"),
            index=False)
        print(verdict("bad", f"{len(early_stops[name])} half-cycle(s) ended "
                             f"short of the cut-off WITHOUT being caught "
                             f"mid-export"))
        for _, _e in early_stops[name].iterrows():
            _d = ("" if not np.isfinite(_e["duration_frac"])
                  else f", after {100 * _e['duration_frac']:.0f}% of a "
                       f"normal duration")
            print(bullet(f"cycle {int(_e['cycle'])} {_e['step']}: "
                         f"{_e['v_end']:.4f} V, {_e['short_mV']:.0f} mV short"
                         f"{_d} — {_e['termination_class']}"))
        print(bullet("Excluded from the fit and from the capacity tables, "
                     "kept in every figure, and listed in "
                     f"{name}_early_terminations.csv."))

    # What the fit skips, from both causes at once.
    not_measurements[name] = set(in_progress[name]) | {
        (int(r.cycle), str(r.step)) for r in early_stops[name].itertuples()}
print(rule())

# ---8<--- CELL md_cycling
"""
## Cycling performance

Capacity, coulombic efficiency, retention, fade rate, energy and power density,
average discharge voltage, round-trip energy efficiency, and rate capability.

This is arithmetic on the cycler's own counters. Whether a given cycle's
numbers *mean* anything is the previous cell's question, and the two are kept
deliberately apart: a capacity is a capacity whether or not the charge that
produced it went where it was supposed to.

### Three cells, not one

This was one cell producing 23,500 characters of console and 26 figures, which
is more than Cells 4, 5, 8, 9, 10 and 11 put together and impossible to
navigate. It is now split by what you do with the output:

| | | output |
|---|---|---|
| **6a** | the per-cycle tables and headline metrics | 6.2k, 1 CSV |
| **6b** | the four figures a cycling paper is built from | 7.5k, 13 files |
| **6c** | retention, fade, energy, power, efficiency, rate | 9.8k, 22 files |

Run 6a first whatever else you skip: it returns `all_cycle_tables`, and every
figure in 6b and 6c reads it — both for the values and for which cycles Cell 5
found were not measurements. Without it each figure would rebuild the same
tables from the raw records and they would be free to disagree.

Capacity is computed as max − min per half-cycle rather than taken from the
cycler's running column, so the plotted values match the summary table.

**Energy and power densities here are on the ACTIVE-MASS basis**, computed
from the active mass, the blend fraction and the electrode area — all three
of which you supplied in Cell 3b. Whole-cell densities would additionally
need the separator, electrolyte and counter-electrode masses; Ratatosk
estimates only the counter electrode, from geometry and metal density, and
`counter_electrode_measured` records whether it was weighed or guessed.
Earlier versions of this cell claimed the other two were looked up and
recorded with `*_source` fields. They were not, and the machinery has been
removed rather than left reading as a feature.
"""

# ---8<--- CELL cycling_tables
# CELL 6a — CYCLING PERFORMANCE: THE TABLES
# =============================================================================
# Capacity, coulombic efficiency, retention and fade, per cycle, per cell —
# and the headline metrics a paper quotes. Arithmetic on the cycler's own
# counters; whether a given cycle's numbers MEAN anything is Cell 5's
# question, deliberately kept separate.
#
# This cell also computes `all_cycle_tables`, which every figure in 6b and 6c
# reads. Run it first: without it each figure would rebuild the same tables
# from the raw records, and they would be free to disagree with these.
_CYCLING = dict(save_location=RUN_DIR, verbose=CYCLING_VERBOSE)

# WHAT RATE WAS THIS CELL ACTUALLY CYCLED AT? Answered from the recorded
# current, once, before any figure is drawn — because the cycler header
# records only its FIRST step, and a rate-capability run that ramps from
# C/20 to 5C had every caption in this notebook saying "0.05 C". The answer
# is stored on `user_parameters` and read by the captions, the retention
# figures and the report.
cy.annotate_rate_protocol(electrochemical_data, user_parameters,
                          verbose=CYCLING_VERBOSE)

# `not_measurements` so the tables leave out exactly the half-cycles the fit
# does — one verdict, read in both places.
all_cycle_tables = cy.cycling_summary(electrochemical_data, user_parameters,
                                      in_progress=not_measurements, **_CYCLING)

# ---8<--- CELL cycling_figures
# CELL 6b — CYCLING PERFORMANCE: THE FIGURES THAT GO IN THE PAPER
# =============================================================================
# The four a cycling paper is built from:
#
#   voltage_profiles        V against specific capacity, every cycle
#   voltage_profiles_key    the same, filtered to the key cycles
#   cycle_life              capacity and coulombic efficiency against cycle
#   comparative_capacity    every cell on one axis
#
# Each is saved in the format the operator asked for in Cell 3b, and each
# marks or omits the half-cycles Cell 5 found were not measurements.
cy.voltage_profiles(electrochemical_data, user_parameters,
                    all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.voltage_profiles_key(electrochemical_data, user_parameters,
                        all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.cycle_life(electrochemical_data, user_parameters,
              all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.comparative_capacity(electrochemical_data, user_parameters,
                        all_cycle_tables=all_cycle_tables, **_CYCLING)

# ---8<--- CELL cycling_more
# CELL 6c — CYCLING PERFORMANCE: THE SUPPORTING FIGURES
# =============================================================================
# Everything that supports the four above rather than appearing beside them:
#
#   capacity_retention          retention against a reference cycle
#   fade_rate                   loss per cycle, and cumulative
#   power_and_energy            three normalisations, plus the Ragone plot
#   average_discharge_voltage   mean discharge voltage against cycle
#   energy_efficiency           round-trip energy efficiency
#   rate_capability             capacity grouped by C-rate
#
# This is the largest of the three by output — `power_and_energy` alone
# writes eleven files — which is why it is last and on its own.
# `rate_capability` reports and skips on a single-rate run.
cy.capacity_retention(electrochemical_data, user_parameters,
                      all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.fade_rate(electrochemical_data, user_parameters,
             all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.power_and_energy(electrochemical_data, user_parameters,
                    all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.average_discharge_voltage(electrochemical_data, user_parameters,
                             all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.energy_efficiency(electrochemical_data, user_parameters,
                     all_cycle_tables=all_cycle_tables, **_CYCLING)
cy.rate_capability(electrochemical_data, user_parameters,
                   all_cycle_tables=all_cycle_tables, **_CYCLING)

# ---8<--- CELL md_dqdv
"""
## dQ/dV figures

Six views of the same data, because no single one shows everything.

1. **All-cycle overlay** — every cycle on one axis, coloured by cycle number.
   The figure every paper includes.
2. **Key-cycle overlay** — the same, filtered to the key cycles, for
   publication.
3. **Split key cycles** — charge and discharge on separate panels with
   sequential colourmaps. More readable when the peaks overlap.
4. **Waterfall** — stacked offset traces. Shows a peak splitting, shifting or
   dying in a way an overlay cannot. Every complete cycle is plotted: the
   figure height is bounded and the trace pitch compressed to fit, so a
   200-cycle run gives a dense ridgeline rather than a silently thinned subset.
5. **Voltage–cycle heatmap** — the whole degradation story in one figure.
6. **Preprocessing QC** — raw against processed for one cycle, to check the
   smoothing has not invented or erased a feature.

Figure widths default to 6.73 in, the RSC double-column width. Colours are
Okabe–Ito, chosen to survive the common forms of colour blindness and
greyscale printing.
"""

# ---8<--- CELL dqdv_figures
# CELL 7 — dQ/dV FIGURES
# =============================================================================
# Seven figures per dataset, each with a caption you can paste into a
# manuscript — which is why the captions are held to the same standard as the
# numbers. Two things they now get right that they did not before:
#
#   the voltage window   is the PROTOCOL window measured in Cell 3b, not the
#                        analysis axis from Cell 4. Those differ, and the
#                        caption used to quote the second: "cycled between
#                        1.25 and 2.63 V" for a cell cycled 1.2-2.5 V, with
#                        three different cut-offs across a triplicate cycled
#                        identically.
#   incomplete cycles    are named. They are KEPT in every figure on purpose —
#                        seeing where the run has got to is the point — but a
#                        caption has to say which ones are not measurements.
processed_dqdv = {}
for name, ds in datasets.items():
    # What Cell 5 found, handed to the captions. `_get_display_name` and the
    # caption builders read `user_parameters`, so that is where it goes.
    user_parameters.setdefault(name, {})["incomplete_cycles"] = sorted(
        {c for c, _ in not_measurements.get(name, ())})
    processed_dqdv.update(pl.as_processed_dqdv(
        ds, signals[name], preprocess_params[name],
        window=windows[name], profile=profiles[name]))

print(rule("dQ/dV FIGURES"))
pl.plot_dqdv_all_cycles(processed_dqdv, user_parameters, save_location=RUN_DIR)
pl.plot_dqdv_key_cycles_combined(processed_dqdv, user_parameters,
                                 save_location=RUN_DIR)
pl.plot_dqdv_key_cycles_split(processed_dqdv, user_parameters,
                              save_location=RUN_DIR)
for step in ("Charge", "Discharge"):
    pl.plot_dqdv_waterfall(processed_dqdv, user_parameters, step=step,
                           save_location=RUN_DIR)
# The heat maps have their own cell below — see CELL 7b.

# THE QC FIGURE IS SAVED NOW. It was the only plot in the module with no
# `save_location` — it drew, called plt.show(), and vanished with the kernel,
# so a run folder had seven dQ/dV figures and no record of what the
# preprocessing had actually done to the curve.
# The cycle is a named setting rather than a literal 2 buried in the call.
pl.plot_preprocessing_qc(processed_dqdv, user_parameters,
                         cycle=QC_CYCLE, save_location=RUN_DIR)

# ONE construction of the processed curve, not two. `as_processed_dqdv` above
# already built exactly these three columns per half-cycle; this used to
# rebuild them from `signals` a second time, so the CSV and the figures were
# free to diverge.
for name in datasets:
    rows = [df.assign(Cycle=cyc, Step=step)
            for (cyc, step), df in sorted(processed_dqdv[name]["data"].items())]
    if rows:
        pd.concat(rows).to_csv(
            os.path.join(RUN_DIR, f"{name}_processed_dqdv.csv"), index=False)
print(rule())

# ---8<--- CELL md_heatmaps
"""
## 7b. The heat maps

One figure per step, and the one worth the most time. The waterfall above
shows every cycle drawn over every other; this shows the same data as a
surface, so a peak that walks, splits, or dies is a shape rather than a
thicket of overlapping lines.

Two things about how it is drawn, because both change what it means.

**The grid comes from the DATA, not from the protocol window.** A cell cycled
between 1.2 and 2.5 V may be analysed from 1.25 to 2.63 V, and binning onto
the protocol window throws away whatever lies outside it. It also used to fill
the region a half-cycle never reached with a repeat of its nearest measured
value, which renders as the same near-black as a measured zero — so a third of
some panels was colour that no measurement supported.

**A voltage a half-cycle never reached is now unmeasured, and drawn as such.**
Those cells are masked, one shade off the zero end of the ramp, and the blue
step line traces the edge of the range each cycle actually traversed. Where
that edge moves — LTO's delithiation stops 622 mV lower by cycle 10, and NNM
cell B's whole window collapses as it dies — the line is the finding, and the
per-cell page says the same thing in words.

Both versions are written: `..._dQdV_heatmap_<Step>.png` with the line, and
`..._dQdV_heatmap_<Step>_plain.png` without it, for a talk where the shape is
the whole point.
"""

# ---8<--- CELL heatmaps
# CELL 7b — dQ/dV HEAT MAPS
# =============================================================================
# Their own cell rather than two lines inside Cell 7. They are the figure most
# often read and the one most often exported, and they were being drawn in the
# middle of a loop that also produced six other things.
print(rule("dQ/dV HEAT MAPS"))
for step in ("Charge", "Discharge"):
    # WITH the envelope: the reading of the panel that cannot mislead.
    pl.plot_dqdv_heatmap(processed_dqdv, user_parameters, step=step,
                         save_location=RUN_DIR, envelope=True)
    # ...and the version that does not raise the question. No line, no note,
    # and the unvisited cells take the colormap's own zero colour, so the
    # panel reads as one continuous surface — which is what it looked like
    # before any of this was fixed. It is a SECOND file and never a
    # replacement: two versions, one that hides the issue and one that
    # highlights it, and the run always writes both.
    pl.plot_dqdv_heatmap(processed_dqdv, user_parameters, step=step,
                         save_location=RUN_DIR, envelope=False,
                         suffix="_plain")
print(rule())

# ---8<--- CELL md_detect
"""
## Peak detection, and choosing the reference cycle

Detection is two passes plus two filters. `find_peaks` with an adaptive
prominence finds clean maxima; a second-derivative pass finds shoulders on the
flanks that never become maxima; anything found twice within 20 mV is
deduplicated, keeping the more prominent; and a peak the voltage window has cut
in half is discarded rather than fitted, because its centre would be an
extrapolation.

### Why the reference cycle is chosen rather than assumed

One cycle's peak list is fitted and tracked in **every** cycle of the dataset.
A bad reference cycle is therefore not a bad cycle — it is a bad dataset, and
nothing downstream can recover from it.

Hard-coding it to an early cycle and checking only that the cycle exists is not
enough. On one
C, cycle 2 was a half-cycle that put in 580.9 mAh/g and got 115.8 back —
coulombic efficiency 19.9%, 1301 records against a median of 290. Its peak list
set the fit for all 220 cycles:

```
  charge reference peaks
    cell A   3.220*, 3.301, 3.643, 3.700*
    cell B           3.306, 3.648, 3.703*
    cell C           3.640, 3.879, 3.901, 4.193
```

Cell C misses the 3.30 V feature that both other cells track for a hundred
cycles, and carries a 4.193 V ghost instead. Nothing in the output said so.

**The rule now:** the lowest cycle at or above 2 whose Charge and Discharge
half-cycles both pass the integrity check. *Lowest*, not best — a fingerprint
should come from early in the life of the cell, and moving further into the run
means tracking against a peak list that has already aged. Pass
`reference_cycle=N` to choose it yourself; it is honoured, checked and warned
about, never overridden.
"""

# ---8<--- CELL detect
# CELL 8 — PEAK DETECTION AND THE REFERENCE CYCLE
# =============================================================================
# The reference cycle's peak list is fitted and tracked in EVERY cycle, so a
# bad one is not a bad cycle — it is a bad dataset.
#
# It is chosen as the lowest cycle that is BOTH past formation AND passes Cell
# 5's integrity check. Those are two different questions and the second cannot
# answer the first: a cycle can be perfectly clean and still be the wrong
# fingerprint, because the cell was still forming when it was measured.
#
# There is no consensus number of formation cycles — the 2024 Energy &
# Environmental Science review says protocols run from one 1.7 h cycle to
# multi-day schedules and that no general comparison between them is possible.
# What the field agrees on is the CRITERION: coulombic efficiency settling.
# So it is measured per cell; see detect.formation_end, and set
# dt.REFERENCE_CYCLE_FLOOR if you want a house rule (6 is a defensible
# conservative choice) applied on top.
#
# To choose it yourself, set `reference_cycle` in Cell 3b — an explicit answer
# is honoured, checked and warned about, never overridden.
#
# The minimum separation between two peaks is a statement about peak WIDTH, so
# it comes from the profile: 30 mV apart is one feature on a broad layered
# oxide and two on a sharp two-phase material.
detections = {}
for name in datasets:
    print(rule(pl._get_display_name(name, user_parameters.get(name, {}),
                                    user_parameters)))
    _ov = detection_overrides(user_parameters.get(name, {}))
    if _ov:
        print(entry("operator overrides",
                    ", ".join(f"{k}={v}" for k, v in sorted(_ov.items()))))
    _dspec = dt.detect_spec_for_profile(
        profiles[name],
        min_distance_mV=_ov.get("peak_min_distance_mV"),
        prominence_fraction=_ov.get("peak_prominence_fraction"),
        min_width_mV=_ov.get("peak_min_width_mV"),
        edge_exclusion_mV=_ov.get("edge_exclusion_mV"),
        shoulder_detection=_ov.get("shoulder_detection"))
    print(entry("profile", profiles[name]["class"],
                f"peaks must be {_dspec.min_distance_mV:.0f} mV apart, "
                f"prominence >= {_dspec.prominence_fraction:.0%} of the "
                f"curve's own maximum"))

    # COULOMBIC EFFICIENCY PER CYCLE, from Cell 6a's own tables, with the
    # half-cycles Cell 5 judged were not measurements left out — an unfinished
    # final cycle reads as CE 52% and would drag the median it is compared
    # against. This is what tells the selector where formation ended.
    _ct = all_cycle_tables.get(name)
    _eff = {}
    if _ct is not None and not _ct.empty and "CE_%" in _ct.columns:
        _bad = {c for c, _ in not_measurements.get(name, ())}
        _eff = {int(c): float(v)
                for c, v, inc in zip(_ct["Cycle"], _ct["CE_%"],
                                     _ct.get("Incomplete", False)
                                     if "Incomplete" in _ct.columns
                                     else [False] * len(_ct))
                if int(c) not in _bad and not bool(inc)
                and v is not None and np.isfinite(v)}
    _an = analysis_overrides(user_parameters.get(name, {}))
    detections[name] = dt.detect_all(signals[name], name=name, spec=_dspec,
                                     reference_cycle=_an.get("reference_cycle"),
                                     integrity=integrity_band[name],
                                     efficiency=_eff, verbose=True)
print(rule())

detected_peaks = {}
for d in detections.values():
    detected_peaks.update(pl.as_detected_peaks(d))
pl.plot_detected_peaks(processed_dqdv, detected_peaks, user_parameters,
                       save_location=RUN_DIR)

# ---8<--- CELL md_fit
"""
## Multi-peak fitting

Each half-cycle is fitted as a sum of pseudo-Voigt components on a polynomial
baseline, seeded from that cycle's own detected peaks.

**The model setup comes from the profile class, and it matters more than any
other fitting parameter:**

| profile | centre tolerance | sigma | baseline |
|---|---|---|---|
| sharp (LTO, LFP) | 30 mV | 3–30 mV | linear |
| moderate | 70 mV | 5–100 mV | quadratic |
| broad (layered oxides) | 70 mV | 5–200 mV | quadratic |

A sharp peak sits on a flat background, so a wide sigma bound would let a
component inflate until it *is* the background. A broad one sits on a curved
background that a straight line cannot follow — fit a broad dQ/dV with a
linear baseline and R² falls from 0.54 to 0.27 on the same data.

### Parallelism

`fit_many` measures before it commits: it times a few half-cycles serially,
estimates the total, and only spawns worker processes if the estimate clears
60 seconds. A process pool costs 5–8 s to start on Windows and a forty-second
job does not repay it. Every branch says which way it went and why.

The workers return plain dictionaries, never lmfit `ModelResult` objects — a
`ModelResult` cannot cross a process boundary through the standard library's
pickle, and that single constraint blocked parallel fitting in 1.8.x.

### Reproducibility, and what it depends on

**On one machine, a run repeats exactly.** Re-running the same build on the
same file returns bit-identical fitted parameters.

**Across machines it depends entirely on whether the fits converged**, and the
difference is stark. The same build was run on two computers — Windows and
Linux, different numpy/scipy/lmfit builds — on the same two files:

| dataset | fits converged | peak centres agree to | areas agree to |
|---|---|---|---|
| sharp, closure determined | all | 10⁻¹¹ V | 10⁻⁶ mAh g⁻¹ |
| broad, closure not determined | 13% | 2 mV typical, 40 mV worst | 2 mAh g⁻¹ typical |

On the broad dataset three half-cycles in thirty-six even ended with a
*different number of components*, one machine keeping a peak the other dropped
as degenerate.

This is not a numerical-hygiene problem, and tightening tolerances will not
touch it. A converged fit sits at a minimum, and both machines find the same
minimum to machine precision. A fit that stopped at the iteration ceiling sits
wherever the optimiser gave up, and where it gives up depends on the last bits
of the arithmetic — which differ between BLAS builds. **The non-convergence is
the reproducibility problem**; the same quantity that makes a fit slow makes it
machine-dependent.

Two consequences. Every coherence verdict was identical on both machines, so
the *verdicts* travel even where the numbers do not — which is the argument for
reporting verdicts rather than bare numbers. And `run_manifest.json` records
the platform, the Python version and the numpy, scipy and lmfit versions for
every run, because on an undetermined dataset those are part of the result.
"""

# ---8<--- CELL fit
# CELL 9 — MULTI-PEAK FITTING
# =============================================================================
# Pseudo-Voigt components on a polynomial baseline, with the baseline degree
# and sigma bounds taken from each dataset's own profile class:
#
#   sharp     (LTO, LFP)          sigma 3-30 mV,  linear baseline
#   moderate                      sigma 5-100 mV, quadratic baseline
#   broad     (layered oxides)    sigma 5-200 mV, cubic baseline
#
# A sharp peak sits on a flat background, so a wide sigma bound would let a
# component inflate until it IS the background. A broad one sits on a curved
# background that a straight line cannot follow.
#
# `fit_many` TIMES a few half-cycles before deciding whether to spawn workers:
# a pool costs 5-8 s to start on Windows and a forty-second job does not repay
# it. It says which way it went and why.
#
# It also asks whether the machine can AFFORD the workers. Each one is a fresh
# interpreter that re-imports numpy, scipy and lmfit and holds that footprint
# — measured at 181 MB, and more on Windows — while the job it is sent is 5
# KiB. Sizing the pool at `cpu_count - 1` on a busy machine is what killed the
# kernel here twice: the fits were fine, the memory was not there. The pool is
# now held to whichever is smaller of the cores, the free memory and
# PARALLEL_MAX_WORKERS, and the console says which of the three decided.
# TWO STAGES, and the console says which is which. Cell 9 fits each half-cycle
# ONCE at its profile's baseline degree; Cell 10 refits a sample at three
# degrees to ask how much the answer depended on that choice. Both print
# "fitting N half-cycles", so both are now labelled.
fit_results, fit_jobs, shape, resolvability = {}, {}, {}, {}
band_sets = {}

# --- STAGE 0: is there anything here to decompose? -------------------------
# Asked on the REFERENCE half-cycle only, before the run commits to fitting
# every cycle three times over. Six fits, against about six hundred.
#
# The pipeline has always been able to answer this — Cell 10 does, after the
# work. On a solid-solution layered oxide it says NOT DETERMINED, withholds
# the capacity attribution on nearly every cycle, and finds no peak that moves
# like a redox feature. Correct, and an hour late. A curve with no resolved
# peaks does not become decomposable because the optimiser tries harder.
#
# The verdict does not stop the run. It sets expectations, and it is written
# into the reports, so a reader is told in the first minute which of three
# situations they are in rather than inferring it from a page of blanks.
if RUN_PEAK_FITTING:
    print(rule("IS THERE ANYTHING HERE TO DECOMPOSE?"))
    for name in datasets:
        det = detections[name]
        _ref_jobs, _n_sh, _n_pk = [], 0, 0
        for step in ("Charge", "Discharge"):
            _k = (det.reference_cycle, step)
            _s, _pk = signals[name].get(_k), det.peaks.get(_k)
            if _s is None or _s.voltage.size == 0 or _pk is None or _pk.empty:
                continue
            _n_pk += len(_pk)
            if "is_shoulder" in _pk:
                _n_sh += int(_pk["is_shoulder"].fillna(False).sum())
            _ref_jobs.append((_s.voltage, _s.dqdv,
                              ft.spec_for_profile(_pk, profiles[name]),
                              _k))
        print("\n" + heading(pl._get_display_name(
            name, user_parameters.get(name, {}), user_parameters)))
        resolvability[name] = ql.assess_resolvability(
            _ref_jobs,
            shoulder_fraction=(_n_sh / _n_pk) if _n_pk else None,
            n_primaries=(_n_pk - _n_sh) if _n_pk else None,
            n_components=(_n_pk // max(len(_ref_jobs), 1)) if _n_pk else None,
            verbose=True)
    # ONE MATERIAL, ONE MODEL. A mechanism is classified per dataset from one
    # reference cycle; replicates of the same material must not end up fitted
    # with different models, because pooling them is what replicates are for.
    # See `quality.reconcile_mechanisms` for why this takes the most
    # permissive call rather than a majority.
    resolvability = ql.reconcile_mechanisms(
        resolvability,
        {n: str((user_parameters.get(n) or {}).get("composition") or n)
         for n in resolvability},
        verbose=True)
    _unres = [n for n, a in resolvability.items()
              if a.get("verdict") == ql.RESOLVABILITY_UNRESOLVED]
    if _unres and not FIT_UNRESOLVED:
        print()
        print(verdict("caution", f"{len(_unres)} dataset(s) will NOT be "
                                 f"decomposed — FIT_UNRESOLVED is off"))
        print(bullet("Peak positions and the dQ/dV envelope are still "
                     "reported; the decomposition into per-peak areas is "
                     "not, because the reference cycle says the data does "
                     "not decide it. Set FIT_UNRESOLVED = True in Cell 2 to "
                     "fit anyway and see for yourself."))
    print("\n" + rule())

# ONE branch, not two. There were an `if not RUN_PEAK_FITTING:` block at the
# top AND a trailing `else:`, so switching fitting off printed both — one
# saying "everything from here to Cell 13", the other "skipping Cells 9 to
# 12". Two messages, two different ranges, both from the same condition.
if RUN_PEAK_FITTING:
    print(rule("Cell 9 — fitting"))
    # --- WHERE DO THE PEAKS FALL SHORT? One pass over every dataset before
    # any of them is fitted, so the regions can be pooled across the
    # replicates of a material. A sample can miss a region a longer look
    # would find, and a pair fitted with different band sets is the same
    # not-comparing-like-with-like the mechanism reconciliation exists to
    # stop. Costs nothing extra: the per-half-cycle discovery it replaces was
    # already a second fit per half-cycle.
    for name in datasets:
        det = detections[name]
        _jobs0, _limit0 = [], fit_limit.get(name)
        if (not FIT_UNRESOLVED
                and resolvability.get(name, {}).get("verdict")
                == ql.RESOLVABILITY_UNRESOLVED):
            continue
        _mm0 = (resolvability.get(name, {}) or {}).get("model") or {}
        for k in sorted(signals[name]):
            s, pk = signals[name][k], det.peaks.get(k)
            if s.voltage.size == 0 or pk is None or pk.empty:
                continue
            if _limit0 is not None and k[0] > _limit0:
                continue
            _jobs0.append((s.voltage, s.dqdv, ft.spec_for_profile(
                pk, profiles[name],
                band_ceiling_span_fraction=_mm0.get(
                    "band_ceiling_span_fraction", 0.0),
                primaries_only=bool(_mm0.get("primaries_only", False))), k))
        band_sets[name] = ft.band_regions(_jobs0, verbose=False)
    band_sets = ft.reconcile_band_sets(
        band_sets,
        {n: str((user_parameters.get(n) or {}).get("composition") or n)
         for n in band_sets},
        verbose=True)

    for name in datasets:
        det = detections[name]
        jobs = []
        limit = fit_limit.get(name)
        if (not FIT_UNRESOLVED
                and resolvability.get(name, {}).get("verdict")
                == ql.RESOLVABILITY_UNRESOLVED):
            # Nothing is hidden: the verdict, its two numbers and its reason
            # were printed above, and the positions and envelope are already
            # in the run. What is skipped is a decomposition whose per-peak
            # areas Cell 11 would have withheld anyway.
            fit_results[name], fit_jobs[name] = [], []
            continue
        for k in sorted(signals[name]):
            s, pk = signals[name][k], det.peaks.get(k)
            if s.voltage.size == 0 or pk is None or pk.empty:
                continue
            if limit is not None and k[0] > limit:
                continue          # the cell is flat; there is nothing to fit
            if k in not_measurements.get(name, ()):
                continue          # caught mid-flight, or ended on something
                                  # other than its cut-off voltage

            # `spec_for_profile`, NOT a bare FitSpec: a broad layered-oxide
            # dQ/dV needs a cubic baseline and a sharp two-phase one needs a
            # tight sigma bound. Getting this wrong is what a visibly bad
            # fit looks like.
            # The DETECTED PEAKS FRAME, not just its centres: `is_shoulder`
            # is what lets `spec_for_profile` tie each shoulder's width to
            # its parent's. Pass the centres alone and every component is
            # refined free, which is how a shoulder inflates into its parent
            # and reports 136% area retention on a cell holding 99% of its
            # capacity.
            # THE MECHANISM CHOOSES THE MODEL, not the shape class. A
            # two-phase transition and a series of transitions both want
            # pseudo-Voigts; a solid solution wants bands; NMC-like data
            # wants both, because a transition sits on the envelope.
            _mm = (resolvability.get(name, {}) or {}).get("model") or {}
            jobs.append((s.voltage, s.dqdv,
                         ft.spec_for_profile(
                             pk, profiles[name],
                             band_ceiling_span_fraction=_mm.get(
                                 "band_ceiling_span_fraction", 0.0),
                             primaries_only=bool(
                                 _mm.get("primaries_only", False))), k))
        # --- MEASURE THE PEAK SHAPE ONCE, THEN HOLD IT ------------------
        # The mixing fraction is a property of the MEASUREMENT — voltage
        # resolution, rebin width, smoothing — not of the redox process, and
        # none of those change from cycle to cycle. Refined per cycle it is
        # free to absorb area: on LTO cell A it wandered 0.65 -> 0.36 -> 0.52
        # across ten cycles and carried the fitted peak area from 61 to 85
        # mAh/g — 37% growth on a cell that had lost 1.7% of its capacity,
        # with R2 between 0.995 and 0.998 the whole way. Every fit was
        # excellent; the trend they formed was fiction. Same argument for the
        # shoulder width ratio.
        # THE NAME FIRST. The calibration below prints several lines, and
        # with the header after them they read as belonging to the PREVIOUS
        # dataset — which is exactly what made Cells 9 and 10 hard to tell
        # apart in the console.
        print("\n" + heading(pl._get_display_name(
            name, user_parameters.get(name, {}), user_parameters)))
        # --- ONE SET OF BANDS FOR THE DATASET ---------------------------
        # Discovered per half-cycle, a band comes and goes and the component
        # set changes identity from cycle to cycle, which is what put every
        # NMC111 feature at `not assessable` in the coherence audit. Establish
        # the regions once, from where the peaks fall short across a sample,
        # and fit them everywhere. Costs nothing extra: the per-half-cycle
        # discovery was already a second fit. Returns nothing at all where the
        # mechanism permits no band, so LTO is untouched.
        print(section("  Step 1 of 3 — where do the peaks fall short?"))
        # Regions were established for EVERY dataset before this loop, and
        # pooled across the replicates of each material, so both cells of a
        # pair are fitted with the same set. See `fitting.reconcile_band_sets`.
        for _r in ft._describe_band_set(band_sets.get(name) or {}):
            print(_r)
        _bs = band_sets.get(name) or {}
        if any(_bs.values()):
            jobs = [(v, y, sp.replace(band_seeds=[
                        (r["centre"], r["span_mV"])
                        for r in _bs.get(str(k[1]), [])]), k)
                    for (v, y, sp, k) in jobs]
        print(section("  Step 2 of 3 — calibrate the peak shape"))
        shape[name] = ft.calibrate_shape(jobs, verbose=True)
        jobs = [(v, y, sp.replace(fraction=shape[name]["fraction"],
                                  sigma_ratio=shape[name]["sigma_ratio"]), k)
                for (v, y, sp, k) in jobs]
        print(section("  Step 3 of 3 — fit every half-cycle"))
        t0 = time.perf_counter()
        fit_results[name] = ft.fit_many(jobs, verbose=True, label="fitting")
        fit_jobs[name] = jobs
        # "CONVERGED" HAS TO MEAN CONVERGED. Until 1.9.0.26 this counted
        # `r["success"]`, which `fit_half_cycle` set to True for every fit
        # that did not raise an exception — so the NNM triplicate printed
        # "converged 200 of 200" on a dataset where 57% of the fits ran to
        # the 20,000-evaluation ceiling and lmfit flagged them as failures.
        # The two are now counted separately: `fitted` is what returned a
        # result, `converged` is what the optimiser was satisfied with.
        _res = fit_results[name]
        ok = sum(1 for r in _res if r["success"])
        _conv = sum(1 for r in _res
                    if r["success"] and r.get("converged", True))
        _capped = [r for r in _res if r.get("hit_iteration_cap")]
        print(entry("fitted", f"{ok} of {len(jobs)}",
                    f"in {time.perf_counter() - t0:.0f} s"))
        print(entry("converged", f"{_conv} of {ok}",
                    "the optimiser was satisfied"
                    if _conv == ok else
                    f"{ok - _conv} stopped without converging"))
        if _capped:
            _nf = _capped[0].get("max_nfev", 0)
            print(verdict("caution", f"{len(_capped)} fit(s) ran to the "
                                     f"{_nf:,}-evaluation ceiling and "
                                     f"stopped"))
            print(bullet("Those parameters are where the optimiser ran out "
                         "of evaluations, not necessarily where it settled. "
                         "They are kept, and — unlike in 1.9.0.43 — they are "
                         "NOT demoted for it: measured on the NNM "
                         "triplicate, the fits that ran out of budget had "
                         "the HIGHER median R2, because running out while "
                         "still descending is not a failure. What decides "
                         "whether a component is a measurement is the "
                         "component: whether its area and centre are "
                         "determined, whether it was inferred, whether it "
                         "sits on a bound. This line is a fact about the "
                         "optimiser, and it is reported as one."))
    # THE POOL IS NOT RELEASED HERE, and 1.9.0.43 was wrong to do it.
    # Cell 10 fits again immediately, so releasing at the end of Cell 9 paid a
    # full teardown and a fresh set of Windows process spawns to hand back
    # memory that was wanted back a second later. Measured, the teardown and
    # respawn cost ~420 ms a pass on Linux and 5-8 s per worker on Windows,
    # for nothing — and shutting a loky executor down and immediately
    # rebuilding one is the pattern most likely to hang. Cell 10 releases it,
    # once, when nothing is going to fit again.
    print("\n" + rule())
else:
    print(rule("PEAK FITTING IS OFF"))
    print(verdict("caution", "Cells 9 to 12 will do nothing"))
    print(bullet("No fitted peaks, no tracking, no polarisation, no capacity "
                 "attribution, and no 5_peak_fitting or 6_descriptors "
                 "folders. The cycling analysis in Cells 6a-6c is unaffected "
                 "and complete."))
    print(bullet("To turn it on: answer 'yes' to 'Run full dQ/dV peak "
                 "fitting?' in Cell 3b, or set RUN_PEAK_FITTING = True in "
                 "Cell 2 — then re-run from Cell 9."))
    print(rule())

# ---8<--- CELL md_quality
"""
## Does the answer mean anything?

Two checks run in this cell, on two different things. The quickest way to see
what they are is to follow one half-cycle through.

### A worked example: LTO, cycle 5, charge

Three numbers describe the same half-cycle at three stages of the pipeline:

| stage | number |
|---|---|
| the cycler's own coulomb count | 129.1 mAh g⁻¹ |
| the area under the dQ/dV curve built from it, ∫(dQ/dV)dV | 128.4 mAh g⁻¹ |
| the one fitted peak on that curve (1.546 V), its area | 123.9 mAh g⁻¹ |

Each check is one ratio of a consecutive pair:

**Integral fidelity = 128.4 / 129.1 = 0.99.** Did anything get lost turning
the raw record into a curve? Here, no — the curve carries 99% of the charge
the cycler counted. Binning, smoothing and the ±50 mV edge exclusion together
cost 1%.

**Capacity closure = 123.9 / 128.4 = 0.96.** Of the curve that survived, how
much did the fitted peak actually claim? 96%; the other 4% went into the
baseline.

Closure is measured against the **curve**, not against the cycler, and that is
deliberate. Divide by the cycler's number instead and a preprocessing loss
would be charged to the fit — one bad number, and no way to tell which stage
produced it.

### Why closure is reported as an interval

The LTO peak above is about 9 mV wide on a 1.3 V window. Nothing a polynomial
baseline can do looks like that, so the choice of baseline barely matters:
refit the same half-cycle with a linear, a quadratic and a cubic baseline and
closure comes back 0.96, 0.96, 0.96. The split between "peak" and "background"
is a property of the data.

Now take a broad layered-oxide curve, where one component can be 100 mV wide
on a 2 V window. Over that span a wide pseudo-Voigt and a cubic are nearly the
same shape, and the fit has no basis on which to prefer either. The same three
refits can give 0.41, 0.45 and 0.48 — seven points of the curve's area moving
between "peak" and "background" on nothing but the baseline degree somebody
picked.

So the interval is reported, not a single value:

```
   interval width  =  max(closure) − min(closure)   over baseline degrees 1, 2, 3
```

Below **0.15** the split is determined by the data, and capacity shares are
reported. Above it the fitted areas still go to the CSVs — they remain the best
description of the curve the fit found — but the *share of capacity* is
withheld for that half-cycle, because at that width the share is a fact about
the baseline rather than about the material. The threshold is applied to the
width of the interval; no threshold is placed on the closure value itself.

### Reading the two together

They fail independently, which is the whole reason for keeping them apart:

| fidelity | closure | what that combination means |
|---|---|---|
| high | high | both stages sound — the fitted areas are capacities |
| high | low | the curve is right but the peak/background split is not; a broad, unresolved profile |
| low | high | the fit describes the curve well, but charge was lost upstream — check the bin width and the edge exclusion |
| low | low | do not read areas from this dataset |

A wide interval also carries physical meaning. A split that survives a change
of baseline describes a feature no polynomial can mimic — narrow, first-order,
two-phase. A split that collapses describes a solid-solution envelope, where
the peak was never a separate thing from its surroundings to begin with.
"""

# ---8<--- CELL quality
# CELL 10 — DOES THE ANSWER MEAN ANYTHING?
# =============================================================================
# Cell 9 FITTED the curves. This cell asks whether the numbers that came out
# mean anything, and it asks two questions that are deliberately independent:
#
#   closure             sum(component areas) / integral(dQ/dV) dV
#                       "do the fitted peaks account for the CURVE?"
#   integral fidelity   integral(dQ/dV) dV / the counter's capacity
#                       "does the curve account for the CELL?"
#
# A dataset can pass one completely and fail the other. LTO scores 0.98-1.00
# on closure and 0.58-0.68 on fidelity: the fits are excellent descriptions of
# a curve that is missing 40% of the charge. Using the counter's capacity as
# closure's denominator would have hidden that inside a fitting number.
#
# Closure is reported as an INTERVAL across baseline degree, because a broad
# pseudo-Voigt and a cubic over a 1.4 V window are nearly the same function.
# Where the interval is wide the split is not decided by the data, and Cell 11
# withholds the capacity SHARE for that cycle.
#
# THIS CELL REFITS. Each sampled half-cycle is fitted once per baseline degree
# — three fits each — so it is the most expensive cell in the run for its
# size. CLOSURE_SAMPLE bounds how many are measured; None measures every
# half-cycle, which on a 200-cycle cell is 600 fits and takes longer than the
# fitting in Cell 9 did.
closure_intervals, fidelity, unattributed = {}, {}, {}
# One branch, not two. The same duplicated `if not X:` / `if X:` pair that
# printed two contradictory skip messages in Cell 9 was still here.
if RUN_PEAK_FITTING:
    print(rule("DOES THE ANSWER MEAN ANYTHING?"))
    for name in datasets:
        jobs = fit_jobs[name]
        keys = [j[3] for j in jobs]
        if CLOSURE_SAMPLE:
            sample = set(ql.sample_half_cycles(keys, n=CLOSURE_SAMPLE))
            batch = [j for j in jobs if j[3] in sample]
        else:
            batch = jobs
        print("\n" + heading(pl._get_display_name(
            name, user_parameters.get(name, {}), user_parameters)))
        # How many fits this actually is depends on whether there is a
        # baseline to sweep. With none there is one fit per half-cycle and
        # saying "x 3 baseline degrees" would be a lie about the cost.
        _ndeg = len(ql.degrees_for(batch[0][2])) if batch else 1
        print(entry("closure sample", f"{len(batch)} of {len(jobs)}",
                    (f"half-cycles × {_ndeg} baseline degrees = "
                     f"{len(batch) * _ndeg} fits") if _ndeg > 1 else
                    (f"half-cycles, one fit each — no free background to "
                     f"sweep, so the split has nothing to depend on")))
        results = ql.assess_closure(batch, verbose=True)
        closure_intervals[name] = {r["key"]: (r["lo"], r["hi"])
                                   for r in results}
        # From 1.9.0.56 there is no free background, so the interval above is
        # zero by construction and cannot withhold anything. The charge the
        # model could not NAME is what carries that duty now — see
        # `quality.UNATTRIBUTED_QUALIFIED_ABOVE`.
        unattributed[name] = {r["key"]: r.get("unattributed", float("nan"))
                              for r in results}
        print(ql.describe_partition(results))

        f = {}
        for (cyc, step), s in signals[name].items():
            if s.voltage.size:
                f[(cyc, step)] = ql.integral_fidelity(s.voltage, s.dqdv,
                                                      s.capacity)
        fidelity[name] = f
        print(ql.describe_fidelity(f))
    # THE ONE PLACE THE POOL IS RELEASED. This is the last cell that fits
    # anything, so from here the workers are pure cost: each holds its whole
    # import footprint — measured at ~181 MB on Linux, more on Windows — for
    # the life of the kernel, through every figure, every export, and however
    # long the notebook then stays open. Releasing here hands that back and
    # costs nothing, because nothing needs a worker again.
    ft.release_workers()
    print("\n" + rule())
else:
    print(rule("QUALITY ASSESSMENT SKIPPED"))
    print(verdict("caution", "peak fitting is off, so there is no fit to "
                             "assess"))
    print(rule())

# ---8<--- CELL md_analyse
"""
## Tracking, polarisation and capacity attribution

**Tracking** matches each cycle's fitted components to the reference peak list
by voltage proximity, one-to-one, by optimal assignment — primaries matched
before shoulders, so that when a primary and its shoulder merge into one
component it is the shoulder recorded as disappeared and the primary's centre
history stays continuous. Drift and area retention are measured from the
**reference cycle**, not cycle 1, so a peak that behaves differently during
formation is not given an artefactual retention.

A peak whose reference-cycle area is already near zero is a **ghost** — the
fitter kept a collapsed component — and retention is not reported for it at
all, rather than reported as a ratio of two meaningless numbers.

A peak that vanishes mid-life is a **discontinuity**. It counts as a *failure*
only if the peak was established first (reliably tracked for at least 15
cycles); a feature present only for the first few cycles and then gone was
never established, and its loss is reported as a transient.

**ΔV** pairs charge and discharge peaks by globally optimal assignment with an
expected-sign constraint that follows the electrode. Polarisation growth is
sigmoidal, not linear, so the trend is reported as a net change over the
leading coherent window rather than a fitted slope.

**Capacity attribution** gives each peak's area as a fraction of a fixed basis
— the summed fitted area at the reference cycle. A per-cycle denominator
shrinks as peaks drop out, which redistributes lost capacity onto the
survivors; a fixed one lets the stack fall below 100%, which is what actually
happened.

> **Attribution is withheld where the split is not determined.** Where the
> closure interval from the previous cell is wider than 0.15, the per-peak
> *fraction* is set to NaN and the reason recorded. The fitted areas are kept:
> withholding a share is not deleting a number. On NMC111 this suppresses the
> whole dataset, which is the correct answer; on real data it suppresses
> nothing.

**The coherence audit** asks whether each peak moves like a redox feature. At
C/10 a centre should drift a few mV per cycle and hold its area. The verdict is
driven by the median drift, not by the tail fractions — the tails are a noisy
statistic on a few dozen pairs and the median is not. Below eight consecutive
pairs it declines to judge and says so.
"""

# ---8<--- CELL analyse
# CELL 11 — TRACK, PAIR, ATTRIBUTE
# =============================================================================
parameters, tracking, deltav, attribution, coherence = {}, {}, {}, {}, {}
if RUN_PEAK_FITTING:
    print(rule("TRACK, PAIR, ATTRIBUTE"))
    for name, ds in datasets.items():
        print("\n" + heading(pl._get_display_name(
            name, user_parameters.get(name, {}), user_parameters)))
        det = detections[name]
        # A dataset skipped as UNRESOLVED has no fits, and everything below
        # this point describes fits. It is not an error and it is not a gap
        # in the output: the verdict, its two measurements and its reason
        # were printed in Cell 9, and the peak POSITIONS and the dQ/dV
        # envelope — the quantities such a curve can actually support — are
        # already in the run.
        if not fit_results.get(name):
            print(verdict("caution", "not decomposed — the reference cycle "
                                     "says the peak/background split is not "
                                     "decided by the data"))
            print(bullet("Positions and the dQ/dV envelope stand. There is "
                         "no per-peak area to track, pair or attribute, so "
                         "this section is empty by decision rather than by "
                         "failure."))
            parameters[name] = pd.DataFrame()
            continue
        # THE INTEGRITY VERDICT REACHES THE FIT. `cell_integrity` banded
        # these half-cycles two cells ago and nothing asked; see the note in
        # `parameters_frame`. A half-cycle that passed more charge than the
        # material can hold still gets fitted, tracked and drawn — it is data,
        # and the figure is where you see what happened — but its components
        # are marked and the trends leave them out.
        P = an.parameters_frame(fit_results[name], det, name=name,
                                integrity=integrity.get(name))
        parameters[name] = P
        # 80 mV is a judgement, not a constant: it varies with peak spacing,
        # and a crowded layered-oxide cathode needs it narrower.
        _an = analysis_overrides(user_parameters.get(name, {}))
        # verbose=False, then FLAG, then print: the summary carries the
        # fidelity and charge-balance warnings, and printing it before they
        # are set would show the numbers without the reasons to doubt them.
        tracking[name] = an.track_peaks(
            P, det, verbose=False,
            **({"tolerance_mV": _an["tracking_tolerance_mV"]}
               if "tracking_tolerance_mV" in _an else {}))
        # IS AN AREA A CAPACITY HERE AT ALL? A fitted peak area is a share
        # of the charge that appears in the dQ/dV CURVE, and integral
        # fidelity — measured in the previous cell — is exactly how much of
        # the cell's charge that curve accounts for. On a flat two-phase
        # plateau the true dV between records falls below the instrument's
        # voltage resolution and most of the charge is delivered in an
        # interval the derivative cannot resolve; on the LTO triplicate the
        # CYCLER'S OWN dQ/dV column recovers 43-68% of the CYCLER'S OWN
        # capacity. No model fixes that. Peak POSITIONS and drift are
        # unaffected and remain the honest headline.
        an.flag_low_fidelity(tracking[name], fidelity.get(name, {}))
        # THE CELL'S OWN CHARGE BALANCE, used as a bound on the fit. A peak
        # cannot grow while the cell it lives in shrinks; where it appears to,
        # the decomposition is wrong, and neither R2 nor the standard errors
        # will say so. Flagged, never deleted.
        # NEEDS CELL 6a. `capacity_retention_pct(None, ...)` returns NaN,
        # and a NaN bound silently stops bounding anything — the same
        # NaN-disables-a-guard hazard closed in Cell 3b. Said out loud
        # rather than left to be inferred from an absent warning.
        _ct6a = all_cycle_tables.get(name)
        if _ct6a is None or _ct6a.empty:
            print(verdict("caution", "no cycle table from Cell 6a — the "
                                     "area-growth guard is not bounded"))
            print(bullet("A fitted peak cannot grow while the cell it lives "
                         "in shrinks. Without Cell 6a's capacity retention "
                         "there is nothing to test that against. Run Cell 6a "
                         "first."))
        an.flag_area_growth(
            tracking[name],
            an.capacity_retention_pct(_ct6a, det.reference_cycle))
        print("\n" + tracking[name].summary_text())
        # The reference cycle IS the measured end of formation since
        # 1.9.0.18, so the polarisation trend now starts where the peak-drift
        # trend does instead of at cycle 2.
        deltav[name] = an.delta_v(tracking[name], is_anode=ds.labels_swapped,
                                  first_cycle=det.reference_cycle,
                                  verbose=True)
        attribution[name] = an.capacity_attribution(
            tracking[name], closure_intervals=closure_intervals.get(name),
            unattributed=unattributed.get(name), verbose=True)
        coherence[name] = an.coherence_audit(
            P, det, profile=profiles[name]["class"], verbose=True,
            rate_protocol=user_parameters.get(name, {}).get("rate_protocol"))
    print("\n" + rule())
else:
    # Was: "there is nothing to peak tracking, polarisation." A word missing
    # and the list unfinished.
    print(rule("TRACKING SKIPPED"))
    print(verdict("caution", "peak fitting is off, so there is nothing to "
                             "track"))
    print(bullet("No peak tracking, no polarisation, no capacity "
                 "attribution and no coherence audit. Cells 6a-6c are "
                 "unaffected."))
    print(rule())

# ---8<--- CELL md_fit_figures
"""
## What the fitting found

Four figures, and the only ones in the run that show the fitted model rather
than the data. Each prints a suggested caption.

1. **Peak fits** — the model against the data for a handful of cycles, with
   the components filled and the residual beneath. This is where you decide
   whether to believe anything that follows.
2. **Peak trends** — each tracked peak's centre, area and width against cycle
   number, one figure per step. Filled markers passed the reliability test;
   open ones did not.
3. **Polarisation** — ΔV between the paired charge and discharge peaks.
   A widening |ΔV| is rising internal resistance.
4. **Capacity attribution** — how much of the reference cycle's capacity each
   peak still accounts for, as areas and as a stack.

Every band is ±1 standard error on the fitted parameter, straight from the
least-squares fit. Where a band is wider than the trend it draws, the fit is
telling you that number is not determined by your data — which is the most
useful thing a fit can say.

**Nothing here runs unless peak fitting is on.** If Cell 9 said SKIPPED, so
will this.
"""

# ---8<--- CELL fit_figures
# CELL 12 — FIT, TRACKING AND DESCRIPTOR FIGURES
# =============================================================================
# The model, not the data: fits, tracked trends, polarisation, attribution.
# Every one is written to RUN_DIR and prints a caption you can paste.
if RUN_PEAK_FITTING:
    print(rule("FIT, TRACKING AND DESCRIPTOR FIGURES"))
    _n_fig = 0
    for name in datasets:
        print("\n" + heading(pl._get_display_name(
            name, user_parameters.get(name, {}), user_parameters)))
        # A DATASET THAT WAS NOT DECOMPOSED IS NOT A REASON TO STOP.
        # Cell 11's skip path sets `parameters[name]` to an empty frame and
        # `continue`s WITHOUT setting `tracking`, `deltav`, `attribution` or
        # `coherence` — correctly, there is nothing to put in them. This loop
        # then did `tracking[name]` and raised KeyError, which is not caught
        # anywhere, so ONE undecomposed dataset destroyed every remaining
        # dataset's fit, trend, delta-V and attribution figures, and Cell 13's
        # export with them. The trigger needs no switch: any dataset whose
        # every half-cycle falls past the fit limit reaches it. A dataset with
        # nothing to draw is skipped; the others are drawn.
        if name not in tracking or not fit_results.get(name):
            print(verdict("caution", "no fitted model for this dataset, so "
                                     "there are no fit or descriptor figures "
                                     "to draw"))
            print(bullet("Cell 11 said why. The cycling figures, the dQ/dV "
                         "figures and the detected-peak positions for this "
                         "dataset are unaffected and are already in the run."))
            continue
        FR = pl.as_fit_results(fit_results[name], signals[name],
                               parameters[name], name=name)
        TR = pl.as_tracked(tracking[name])
        pl.plot_fit_quality(processed_dqdv, detected_peaks, FR,
                            user_parameters, save_location=RUN_DIR)
        pl.plot_tracked_trends(TR, user_parameters, save_location=RUN_DIR)
        if name in deltav:
            dv = deltav[name]
            # `pairs` and `delta_v_windows` are packed here and read by
            # nothing: `plot_delta_v` takes `delta_v_df` and
            # `delta_v_changes`. Passing a value that has no reader invites
            # the belief that the figure used it.
            pl.plot_delta_v({name: dict(delta_v_df=dv.df,
                                        delta_v_changes=dv.changes)},
                            user_parameters, save_location=RUN_DIR)
        if name in attribution:
            pl.plot_capacity_attribution({name: attribution[name]}, TR,
                                         user_parameters,
                                         save_location=RUN_DIR)
        _n_fig += 1
    print("\n" + rule())
    print(entry("figures drawn", f"{_n_fig} dataset(s)",
                "see 5_peak_fitting and 6_descriptors"))
else:
    print(rule("FIT FIGURES SKIPPED"))
    print(verdict("caution", "peak fitting is off, so there is no fitted "
                             "model to draw"))
    print(rule())

# ---8<--- CELL md_export
"""
## Export, and closing the run

Every run writes to its own timestamped folder, and the manifest records what
produced it: the input file checksums, the package versions, the parameters for
each dataset, and every switch in force. With the version number deliberately
held across a series of behaviour changes, those switches are the only thing
distinguishing one run from another.

`finalise_run` sorts the outputs into numbered folders per dataset, checksums
everything written, and closes the manifest. A run that has not been finalised
has no record of what produced it.

```
   OUTPUT_BASE\runs\2026-08-31_143012_v1.9.0\
       run_manifest.json
       <composition>_cell<id>\
           1_cycling\   2_voltage_profiles\   3_energy_power\
           4_dqdv\      5_peak_fitting\       6_descriptors\   7_summary\
           dataset_info.txt
```
"""

# ---8<--- CELL export
# CELL 13 — EXPORT
# =============================================================================
# The fitted model, as CSVs, one set per dataset. The cycling tables and the
# dQ/dV curves were already written by Cells 6a and 7; this is everything that
# only exists because the peaks were fitted.
#
# `closure_interval_width` is NaN wherever the closure interval was NOT
# MEASURED — Cell 10 samples CLOSURE_SAMPLE half-cycles rather than all of
# them, so on a 200-cycle cell that is 40 rows measured and 400 blank. A blank
# there means "not sampled", not "the fit failed", and the column beside it
# now says which.
if RUN_PEAK_FITTING:
    print(rule("EXPORT"))
    _written = 0
    for name in datasets:
        # SAME GUARD AS THE FIGURE CELL, SAME REASON. An undecomposed dataset
        # has an empty `parameters` frame and no entry in `tracking`,
        # `deltav`, `attribution` or `coherence`, and this loop would raise
        # KeyError on the first of them — losing the exports of every dataset
        # after it in the list as well as its own.
        P = parameters.get(name)
        if P is None or P.empty or name not in tracking:
            print(bullet(f"{name}: nothing fitted, so no fitted-parameter, "
                         f"tracking or attribution table is written"))
            continue
        P = P.copy()
        iv = closure_intervals.get(name, {})
        P["closure_interval_width"] = [
            (iv[(c, s)][1] - iv[(c, s)][0]) if (c, s) in iv else np.nan
            for c, s in zip(P["cycle"], P["step"])]
        # Says WHY a width is blank. Without it a reader opening a P3 export
        # sees 400 empty cells in a quality column and has no way to tell an
        # unsampled half-cycle from a failed one.
        P["closure_interval_measured"] = [(c, s) in iv
                                          for c, s in zip(P["cycle"],
                                                          P["step"])]
        P["integral_fidelity"] = [fidelity[name].get((c, s), np.nan)
                                  for c, s in zip(P["cycle"], P["step"])]
        P.to_csv(os.path.join(RUN_DIR, f"{name}_fitted_parameters.csv"),
                 index=False)
        tracking[name].tracked_df.to_csv(
            os.path.join(RUN_DIR, f"{name}_tracked_peaks.csv"), index=False)
        _ts = pd.DataFrame(tracking[name].summary).T
        _ts.index.name = "peak"          # was an unnamed index column
        _ts.to_csv(os.path.join(RUN_DIR,
                                f"{name}_tracked_peaks_summary.csv"))
        if name in deltav and not deltav[name].df.empty:
            deltav[name].df.to_csv(
                os.path.join(RUN_DIR, f"{name}_delta_v.csv"), index=False)
        for step, A in (attribution.get(name) or {}).items():
            A.to_csv(os.path.join(
                RUN_DIR, f"{name}_capacity_attribution_{step}.csv"), index=False)
        if name in coherence:
            coherence[name].to_csv(
                os.path.join(RUN_DIR, f"{name}_fit_coherence.csv"), index=False)
        _written += 1
    _n_meas = sum(len(closure_intervals.get(n, {})) for n in datasets)
    _n_rows = sum(len(parameters[n]) for n in datasets)
    print(entry("exported", f"{_written} dataset(s)",
                "fitted parameters, tracking, polarisation, attribution "
                "and coherence"))
    if _n_rows:
        print(entry("closure measured on", f"{_n_meas} of {_n_rows}",
                    "half-cycle rows; the rest are marked not measured"))
    print(rule())
else:
    # Was outside the `if`, so a run with fitting off announced "Written to
    # <run folder>" having written nothing at all.
    print(rule("EXPORT SKIPPED"))
    print(verdict("caution", "peak fitting is off, so there is no fitted "
                             "model to export"))
    print(bullet("The cycling tables from Cell 6a and the dQ/dV curves from "
                 "Cell 7 are already written and are unaffected."))
    print(rule())

# ---8<--- CELL close
# CELL 14 — CLOSE THE RUN
# =============================================================================
# Sorts the outputs into numbered folders, checksums everything written, and
# closes the manifest. Nothing downstream depends on this — but a run that has
# not been finalised has no record of what produced it.
# WHAT THE PIPELINE DECIDED, per dataset, written into each cell's
# dataset_info.txt beside what the operator asked for. Until 1.9.0.11 that
# file recorded only the request — the mass, the window, the theoretical
# capacity — and none of the measured choices that actually determined the
# result: which profile class was read off the curve, which reference cycle
# was chosen and why, what peak shape was calibrated, and how much of the
# cell's charge the dQ/dV curve accounted for. Same rule as the manifest:
# record what ran, never what was offered.
_decided = {}
for name in datasets:
    d = {}
    if name in profiles:
        d["dQ/dV profile class"] = profiles[name]["class"]
        d["Profile class chosen because"] = profiles[name]["description"]
    if name in preprocess_params:
        _pp = preprocess_params[name]
        d["dQ/dV computed by"] = _pp.get("dqdv_method")
        if _pp.get("dqdv_method") == "histogram":
            # The width ASKED FOR and the widths actually USED. They differ
            # on 354 of P3 cell A's 364 half-cycles, and recording only the
            # request described 3% of the data.
            d["Histogram bin requested (mV)"] = _pp.get("histogram_bin_mV")
            _w = [sg_.bin_width_mV for sg_ in signals.get(name, {}).values()
                  if sg_.voltage.size and np.isfinite(sg_.bin_width_mV)]
            if _w:
                d["Histogram bin used (mV)"] = (
                    f"{min(_w):g}" if max(_w) - min(_w) < 1e-9 else
                    f"{np.median(_w):.3g} median, {min(_w):g}-{max(_w):.3g} "
                    f"(widened on {sum(1 for x in _w if x > min(_w) + 1e-9)} "
                    f"of {len(_w)} half-cycles)")
            _e = sum(sg_.n_empty_bins for sg_ in signals.get(name, {}).values())
            _b = sum(sg_.voltage.size for sg_ in signals.get(name, {}).values())
            if _b:
                d["Bins with no charge (%)"] = round(100.0 * _e / _b, 1)
            # CHARGE THE ANALYSIS WINDOW LEFT OUT. Computed per half-cycle
            # since the histogram rewrite and never recorded anywhere. It is
            # the operator-actionable half of a low integral fidelity: charge
            # that fell outside the voltage range chosen for analysis, as
            # opposed to charge a dV integral cannot represent at all.
            # THE REACHABLE-VOLTAGE ENVELOPE. How far the cell actually got,
            # per half-cycle, per step. The dQ/dV heatmap draws it; nothing
            # said it. On LTO cell A the charge step's furthest voltage falls
            # 622 mV over ten cycles while capacity retention is 99% — a
            # window collapsing under an unchanged capacity, which is a
            # polarisation statement and not a capacity one, and it was
            # visible in no number anywhere in the run.
            # THE SAME HALF-CYCLES THE FIGURE BINS, or the sentence and the
            # line are two measurements of one quantity over two populations —
            # which is the fault this whole audit was about. `plot_dqdv_heatmap`
            # drops half-cycles whose voltage span is a small fraction of the
            # median (`_detect_short_halfcycles`), so the partial final
            # half-cycle is not in the figure. Measured over ALL half-cycles,
            # LTO cell B's delithiation envelope reads 914 mV — and every
            # millivolt of that comes from cycle 11, which the export caught
            # mid-flight and which the page elsewhere says is not a measurement
            # yet. The figure correctly drew no line; the prose announced a
            # collapse that had not happened.
            _short = {}
            _pd = (processed_dqdv.get(name) or {}).get("data") or {}
            for _st in ("Charge", "Discharge"):
                try:
                    _short[_st] = set(pl._detect_short_halfcycles(_pd, _st)[1])
                except Exception:
                    _short[_st] = set()
            _env = {}
            for _st in ("Charge", "Discharge"):
                # SORTED BY CYCLE. `hi_first`/`hi_last` are the ends of a
                # trend, so they cannot come out of a dict in insertion order.
                _ks = sorted((k for k in signals.get(name, {})
                              if k[1] == _st
                              and np.size(signals[name][k].voltage)
                              and k[0] not in _short.get(_st, ())
                              and k not in not_measurements.get(name, ())),
                             key=lambda k: k[0])
                _hi = [float(np.nanmax(signals[name][k].voltage)) for k in _ks]
                _lo = [float(np.nanmin(signals[name][k].voltage)) for k in _ks]
                if len(_hi) >= 3:
                    # ONE GATE, NOT TWO. The figure decides whether the
                    # envelope is worth drawing from the bin width and the
                    # panel span; the sentence had its own absolute
                    # millivolt threshold, and on LTO cell C's delithiation
                    # (66 mV, against a 62 mV panel gate and a 100 mV prose
                    # gate) the line was drawn and the page said nothing
                    # about it. Two thresholds for one quantity is how a page
                    # ends up contradicting its own figure. The decision is
                    # made HERE, once, with the plotting module's own
                    # constants, and `drawn` is what the report reads — so
                    # the sentence is literally a description of the line.
                    _spread_V = max(max(_hi) - min(_hi), max(_lo) - min(_lo))
                    _panel_V = max(_hi) - min(_lo)
                    _bws = [s.bin_width_mV for k, s in signals[name].items()
                            if k[1] == _st and np.isfinite(s.bin_width_mV)]
                    _bw_V = (float(np.median(_bws)) / 1000.0) if _bws else 0.0
                    _drawn = bool(
                        _spread_V > pl.HEATMAP_ENVELOPE_MIN_BINS * _bw_V
                        and _panel_V > 0
                        and _spread_V / _panel_V
                        > pl.HEATMAP_ENVELOPE_MIN_FRACTION)
                    _env[_st] = dict(
                        hi_spread_mV=1000.0 * (max(_hi) - min(_hi)),
                        lo_spread_mV=1000.0 * (max(_lo) - min(_lo)),
                        hi_first=_hi[0], hi_last=_hi[-1],
                        lo_first=_lo[0], lo_last=_lo[-1], n=len(_hi),
                        drawn=_drawn)
            if _env:
                user_parameters.setdefault(name, {})["voltage_envelope"] = _env
            _ow = [float(sg_.charge_outside_window)
                   for sg_ in signals.get(name, {}).values()
                   if np.isfinite(getattr(sg_, "charge_outside_window",
                                          np.nan))]
            if _ow:
                d["Charge outside the analysed window (mAh/g)"] = (
                    f"{np.median(_ow):.2f} median per half-cycle, "
                    f"worst {max(_ow):.2f}")
        else:
            d["Smoothing window (points)"] = _pp.get("smoothing_window")
            d["Rebin width (mV)"] = _pp.get("rebin_width_mV")
            d["Spike removal"] = _pp.get("spike_removal")
    if reconstruction.get(name):
        _r = reconstruction[name]
        # ROUNDED, like the RMSE beside it. The histogram path reconstructs
        # to floating-point exactness, and the raw value wrote itself into
        # the record as "1.063e-12" — which reads as a measurement of
        # something, precise to thirteen figures, rather than as zero.
        _ape = float(np.nanmedian([x["ape_pct"] for x in _r]))
        d["Reconstruction APE (%)"] = (
            "< 0.001" if _ape < 1e-3 else round(_ape, 3))
        d["Reconstruction RMSE (mV)"] = round(
            1000.0 * float(np.nanmedian([x["rmse_V"] for x in _r])), 2)
    if name in windows:
        d["Analysed window (V)"] = (f"{windows[name][0]:.4f} - "
                                    f"{windows[name][1]:.4f}")
    for _st, _tv in sorted((trims.get(name) or {}).items()):
        if max(_tv) > 0:
            d[f"Cut-off trim, {_st.lower()} (mV)"] = (
                f"{1000 * _tv[0]:.0f} off the bottom, "
                f"{1000 * _tv[1]:.0f} off the top")
    if in_progress.get(name):
        d["Caught mid-flight"] = ", ".join(f"cycle {c} {st}"
                                           for c, st in in_progress[name])
    if not early_stops.get(name, pd.DataFrame()).empty:
        d["Ended early, not on voltage"] = ", ".join(
            f"cycle {int(r.cycle)} {r.step} ({r.short_mV:.0f} mV short, "
            f"{r.termination_class})"
            for r in early_stops[name].itertuples())
    if fit_limit.get(name) is not None:
        d["Fitting stopped at cycle"] = fit_limit[name]
    if name in detections:
        d["Reference cycle"] = detections[name].reference_cycle
        d["Reference cycle chosen by"] = detections[name].reference_reason
    if RUN_PEAK_FITTING and name in shape:
        _sh = shape[name]
        d["Mixing fraction eta"] = (
            f"{_sh['fraction']:.3f} (held for every fit)"
            if _sh.get("fraction") is not None else
            f"refined per half-cycle; median {_sh['fraction_median']:.3f}, "
            f"10-90 spread {_sh['fraction_spread']:.3f} too wide to hold"
            if _sh.get("fraction_median") is not None else "not measurable")
        if _sh.get("sigma_ratio") is not None:
            d["Shoulder width ratio k"] = f"{_sh['sigma_ratio']:.3f} (held)"
    for _step, _f in sorted((tracking[name].integral_fidelity
                             if RUN_PEAK_FITTING and name in tracking
                             else {}).items()):
        d[f"Integral fidelity ({_step})"] = (
            f"{_f:.2f}" + ("  *** areas are not capacities ***"
                           if _f < an.INTEGRAL_FIDELITY_FLOOR else ""))
    _decided[name] = d

# `detection=` so the reference cycle each dataset was measured against
# reaches the manifest. It was read from globals() and was always empty.
rn.finalise_run(RUN_DIR, MANIFEST, user_parameters=user_parameters,
                verbose=True, decided=_decided,
                detection=detections if "detections" in dir() else None)

# ---8<--- CELL md_report
"""
## START HERE — the way in

A finished run is forty-six files across seven folders. That is the right way
to store the output and the wrong way to hand it to somebody.

This cell writes two more files at the top of each dataset's folder, above the
numbered directories:

| file | for |
|---|---|
| `START_HERE.html` | reading. Images are embedded, so it can be moved or emailed on its own |
| `START_HERE.md` | pasting into a report, a wiki or a supervision record |
| `RUN_SUMMARY.md` | all the cells side by side, and whether they agree |

Both say the same four things, in this order: **what the cell did**, **what
went wrong and on which cycles**, **what Ratatosk declined to tell you and
why**, and **four figures with what to look for in each**.

The third of those is the one that matters most for a newcomer. A capacity
share left blank because the closure interval was 0.46 wide is a *finding*.
Found as a gap in a spreadsheet three weeks later, it is a bug report.

`RUN_SUMMARY.md` is the triplicate view. It reports the **spread** first, names
an outlier only when there is one, and **declines to nominate a representative
cell when the cells disagree** — picking the one nearest the median would be
choosing a number rather than measuring one.

Nothing is moved or removed — this is a way in, not a replacement.
"""

# ---8<--- CELL report
# CELL 15 — START HERE, AND THE RUN SUMMARY
# =============================================================================
# Written after finalise_run has sorted the outputs, so the figures are in
# their folders and can be found and embedded.
#
#   <cell folder>/START_HERE.html   one cell, four figures, what to look for
#   <cell folder>/START_HERE.md     the same, to paste into a report
#   RUN_SUMMARY.md                  all the cells side by side, and whether
#                                   they agree
# Resolved for ALL datasets at once: two cells sharing a composition and a
# cell id get X and X_2 from `organise_run`, and asking one at a time gave
# both reports the name X, so the second overwrote the first.
print(rule("START HERE"))
_folders = dataset_folders(user_parameters, list(datasets))
_report_facts = {}
for name in datasets:
    _folder = os.path.join(RUN_DIR, _folders[name])
    if not os.path.isdir(_folder):
        _folder = RUN_DIR
    _ct = None
    if isinstance(all_cycle_tables, dict):
        _ct = all_cycle_tables.get(name)
    elif isinstance(all_cycle_tables, pd.DataFrame):
        _ct = all_cycle_tables
    _h, _m, _f = write_report(
        _folder, name,
        params=user_parameters.get(name, {}),
        integrity=integrity.get(name),
        detection=detections.get(name),
        tracking=tracking.get(name) if RUN_PEAK_FITTING else None,
        attribution=attribution.get(name) if RUN_PEAK_FITTING else None,
        coherence=coherence.get(name) if RUN_PEAK_FITTING else None,
        cycle_table=_ct,
        fit_limit=fit_limit.get(name),
        profile=profiles.get(name),
        # THE MECHANISM VERDICT REACHES THE PAGE. Cell 9 computes it, prints
        # it, and chooses the model from it; until now it went no further, so
        # START_HERE and RUN_SUMMARY described a fit without saying which
        # model had been fitted.
        resolvability=resolvability.get(name) if RUN_PEAK_FITTING else None,
        # The fit-quality numbers live on the parameter table, one row
        # per component; the page reads the per-half-cycle medians.
        parameters=parameters.get(name) if RUN_PEAK_FITTING else None,
        file_format=user_parameters.get(name, {}).get("file_format", "png"),
        in_progress=not_measurements.get(name),
        run_id=os.path.basename(RUN_DIR))
    _report_facts[name] = _f
    print(entry(pl._get_display_name(name, user_parameters.get(name, {}),
                                     user_parameters),
                os.path.relpath(_h, RUN_DIR),
                os.path.relpath(_m, RUN_DIR), value_width=26))

_summary = write_run_summary(RUN_DIR, _report_facts,
                             run_id=os.path.basename(RUN_DIR),
                             n_files=len(_all))
print(entry("run summary", os.path.relpath(_summary, RUN_DIR),
            "all the cells side by side", value_width=26))
# The summary is PRINTED as well as written. It is the one thing a reader
# should not have to open a file to see, and the file is there for when they
# want to send it.
print("\n" + rule("RUN SUMMARY"))
print(open(_summary, encoding="utf-8").read())

# ---8<--- CELL md_appendix_1
"""
---

# Appendix — the science, and what this pipeline can and cannot tell you

*Everything below is reference material. It is at the END on purpose: Jupyter
cannot collapse all markdown at once, and in 1.8.x the explanations were
interleaved with the code and made the notebook unnavigable. Nothing here is
executed and nothing above depends on it.*

*Each section is self-contained and titled, so it can be lifted directly into
a help file or a tooltip.*

---

## A1. What a dQ/dV curve is

A galvanostatic cycle gives you charge **Q** and voltage **V**. Differentiating
one against the other, **dQ/dV**, converts a voltage plateau into a peak — and
plateaus are where the interesting electrochemistry is, because a plateau means
the potential is being *held* by something.

At constant current there is an identity worth keeping in mind, because most of
the artefacts in this pipeline come from it:

```
    dQ/dV  =  I / (dV/dt)          so at constant current,
    sign(dQ/dV) = sign(dV/dt)
```

The derivative is therefore only as good as the voltage record. Where the cell
sits on a flat plateau, dV between consecutive records is small; where it is
smaller than the instrument's voltage resolution, dQ/dV is not a measurement of
anything. This is the single largest limitation of the technique and §A4
returns to it.

**Three properties of a peak, and they are not equally trustworthy:**

| Property | What it means | How much to trust it |
|---|---|---|
| **Position** (V) | The potential of a redox process. Shifts as polarisation grows. | **Robust.** Does not involve the integral at all. |
| **Area** | Charge associated with that process — *if* the curve accounts for the charge. | **Conditional.** See §A4 (does the curve account for the cell?) and §A5 (do the peaks account for the curve?). |
| **Width** (FWHM) | Homogeneity and kinetics of the process; a broader peak is a less well-defined transition or a slower one. | Moderate. Correlated with amplitude in any fit. |

### How the curve is computed, and why that is not a detail

There is **no widely agreed method** for computing an IC curve — one review
found nineteen studies with nineteen different workflows. Two families exist:

**Numerical differentiation** (the conventional method; Ratatosk offers it,
but it is *not* the default). Finite differences on the voltage array, with
Savitzky–Golay smoothing before differentiation. Because ΔV sits in the
denominator, flat plateaus give very large IC values, so smoothing is
essential — and its parameters are usually chosen by trial and error until the
curve *looks* right. That makes curves hard to compare between studies, and
the smoothing itself introduces drifts, oscillations and boundary overshoots.
Ratatosk at least chooses the parameters from a measured profile class rather
than by eye, and records every one of them; that does not escape the
underlying fragility, which is why it is not the path taken.

**Voltage histograms** (derivative-free — **what Ratatosk does**,
`DQDV_COMPUTATION = "histogram"` in Cell 2). Bin the records by voltage and
**sum the charge that passed inside each bin**, then divide by the bin width.
That is the IC curve, and nothing is ever differentiated. One parameter, the
bin size, which means exactly what it says: the voltage resolution of the
result.

A note on that, because the textbook statement of the method is weaker than
the implementation. The usual formulation *counts* the records that land in
each bin, which is proportional to the charge only if capacity is sampled at
uniform intervals — a condition real cycler files do not always meet.
Ratatosk passes the charge itself as the histogram weight
(`np.histogram(..., weights=dq)`), so the bin value is the charge that passed
there whether or not the sampling was uniform, and the assumption is not
needed. §A4 measures what this buys.

**The objective test between them is voltage reconstruction.** A derivative is
reversible, so the cumulative integral of the IC curve, plotted against V,
should give back the original voltage curve. Two metrics quantify how well:
the absolute percentage error in maximum cumulative capacity (APE) and the
voltage RMSE over the overlapping interval. Many parameter choices give a
visually satisfying curve; few reconstruct the voltage. Ratatosk's
`integral_fidelity` is the scalar special case of the capacity half of this
test — see §A4, where it matters a great deal.

**Broad features, or none at all, are not a failure.** A material undergoing a
continuous solid solution reaction has no distinct phase transition to hold the
potential, so it gives broad humps. Overlapping reactions merge. High rates
flatten and broaden everything. Coarse voltage sampling hides fine structure. A
featureless dQ/dV curve is a result about the material, not a problem with the
measurement.

> **Tuning.** The bin width and smoothing half-width are the two knobs on this
> section, both set from the measured profile class. If your material is
> broader or sharper than the classifier decided, correct the class first — it
> moves several parameters coherently. §A11 has the table, and the entries for
> *"curve is sparse"*, *"fine structure smeared"* and *"noisy and spiky"*.
"""

# ---8<--- CELL md_appendix_2
"""
## A2. The central idea: coherence, not magnitude

This is the part worth slowing down for, and it is why the pipeline tracks
peaks at all rather than just reporting capacity.

There are two things a redox feature can do as a cell ages.

**Coherent evolution.** The peak drifts gradually, loses area slowly, broadens
steadily, and stays trackable throughout. This is ordinary ageing: the reaction
is still happening, with growing polarisation and slowly declining accessible
capacity. Large changes are not alarming on their own, provided they are
smooth.

**Discontinuity.** The peak jumps, swaps identity with a neighbour, collapses,
or disappears and does not return. This is instability or failure — the process
is not evolving, it is breaking.

**Capacity retention cannot tell these apart.** Two cells can fade to the same
capacity over the same number of cycles, one by coherent ageing and one by
failure, and their capacity curves will look alike. What separates them is
whether the descriptors stayed continuous.

That is the claim the whole pipeline exists to support, and it is the reason
`discontinuity_is_failure` distinguishes a peak that broke *after* being
established from one that was never established at all. Only the first is a
finding about the cell.

> **Tuning.** What counts as a discontinuity is `DISCONTINUITY_STEP_FLOOR_MV`
> (80 mV) and `DISCONTINUITY_STEP_K` (4× the peak's own step scatter),
> whichever is larger, and `DISCONTINUITY_ESTABLISH_MIN` (15 cycles) decides
> whether a peak was ever established. On runs much shorter than 15 cycles no
> peak can be "established", so every break is reported as transient — lower
> it deliberately for short runs rather than being puzzled by the silence.

---

## A3. Polarisation (ΔV) — the most reliable degradation descriptor here

A redox couple appears twice: once on charge at a higher voltage, once on
discharge at a lower one. The gap **ΔV** is the polarisation — the extra
voltage needed over the thermodynamic potential to actually drive the reaction.
It is set by kinetics: charge-transfer resistance at the interface, ohmic drop
through electrode and electrolyte, and how fast ions reach the reaction front.

A gradual, continuous rise in ΔV is the ordinary signature of ageing: internal
resistance building, the interface becoming sluggish, the diffusion path
degrading. Both the value and its **rate of change** are worth reporting — a
couple that starts more polarised and one that polarises faster are telling you
different things.

Pairing is done as a single optimal assignment across all peaks at once, and it
enforces one physical rule: **ΔV must be positive**, because a couple cannot
discharge above the voltage at which it charged. A negative ΔV is not a
measurement, it is a mis-pairing, and the assignment refuses it.

Because ΔV is a difference of two *positions*, it inherits none of the
integral's problems. On a material where the areas cannot be trusted at all,
ΔV and drift are still measurements.

> **Tuning.** `PAIR_MAX_SEPARATION_MV` (200 mV) is how far apart a charge and
> discharge peak may be and still be called the same couple. Raise it for a
> heavily polarised system — a high-rate or low-temperature cell can exceed
> 200 mV honestly — and lower it if unrelated peaks are being paired. Also
> `EXCLUDE_FORMATION_FROM_DELTAV` (True): the trend starts at the measured end
> of formation, because including formation absorbs a step change into what is
> reported as a rate.
"""

# ---8<--- CELL md_appendix_3
"""
## A4. When a peak area is NOT a capacity

This is the most important limitation in the pipeline and the least obvious.

A fitted peak's area is a share of the area under the **dQ/dV curve**. Whether
that is a share of the cell's **charge** depends on whether the curve accounts
for the charge, and that is a separate, measurable quantity:

```
    integral fidelity  =  ∫(dQ/dV) dV  /  the counter's delivered capacity
```

On a first-order two-phase material this can fail badly, for a reason that is
physics rather than software. A two-phase transition holds the potential
essentially invariant, so nearly all the charge is delivered within a few
millivolts. Where the true dV between consecutive records falls below the
instrument's voltage resolution, that charge is delivered in an interval the
derivative cannot resolve — and it cannot appear in ∫(dQ/dV)dV.

**Measured on a flat two-phase anode (Li₄Ti₅O₁₂):** the *cycler's own* dQ/dV
column, integrated over its *own* voltage axis, recovers only **43–68%** of the
*cycler's own* delivered capacity, and the shortfall swings by ten points from
cycle to cycle. No choice of fitting model recovers it. Fitting that curve
beautifully — R² 0.995–0.998, closure 0.98–1.00 — still gives peak areas that
are shares of the 60% that survived, which is how one cell reported **141% area
retention while holding 99% of its capacity**.

The pipeline therefore gates on fidelity, and the gate is **two-sided**: `INTEGRAL_FIDELITY_FLOOR` (0.80) and `INTEGRAL_FIDELITY_CEILING`
(1.20). Outside that band, area trends are marked untrustworthy and capacity
attribution is withheld. **Peak positions and drift are unaffected and remain
reportable.**

The ceiling closes a gap that a one-sided test leaves open.
`integral_fidelity`'s own docstring promises that "fabricated area shows up as
an excess, lost features as a deficit" — and only the deficit was ever tested.
The excess is the more damning of the two, because a deficit is charge the
curve never saw while an excess is charge the *cell never delivered*, and
nothing physical invents it. The 4.199 V constant-voltage artefact this
project spent time chasing is an excess, and a floor-only gate would pass it. The ceiling is set from measurement rather than symmetry:
differencing a voltage record quantised at 0.1–5 mV overshoots to at most
1.047 on the synthetic cases, so anything below about 1.10 would fire on
ordinary data.

### This limit belonged to the METHOD, not to the material — and it is fixed

That distinction matters, and it was settled by measurement. Recomputing the
same half-cycles as **voltage histograms** — the derivative-free path,
now the default (`DQDV_COMPUTATION`) — instead of from the cycler's dQ/dV
column:

| | derivative (cycler column, smoothed) | histogram |
|---|---|---|
| integral fidelity | 0.62 – 0.71 | **0.995 – 1.000** |
| capacity error (APE) | 28 – 38% | **0.001 – 0.05%** |
| voltage RMSE | 234 – 427 mV | **6 – 97 mV** |
| **tracked area retention** | 89% and **141%** | **98% and 100%** |
| peak positions | 1.5253 / 1.5855 V | 1.5230 / 1.5830 V |

The charge was never missing from the *data*. The derivative was losing it,
and a method that never differentiates recovers essentially all of it — at
every bin width from 0.5 to 5 mV. **A cell holding 99% of its capacity reports 100% area retention instead of
141%.** The physical bound check of
§A6 has nothing left to flag on this dataset, because the areas are finally
capacities.

### And on a broad layered oxide, where the problem looked different

A layered oxide never has the two-phase material's catastrophic fidelity — 0.91/0.97 on the
derivative path. It had a different symptom, and the same cure:

| tracked peak area retention, layered oxide, 10 cycles | derivative | histogram |
|---|---|---|
| charge | **152%**, 83%, **170%**, 70%, 54% | 61%, 95%, 98%, 102%, 71%, 50% |
| discharge | 85%, 95%, 105%, 100%, 100% | 43%, 65%, 106%, 89%, 24% |
| median fit R² | 0.971 | **0.991** |

**Two peaks over 150% become none over 106%.** A redox feature taking 70% more
charge at cycle 10 than at cycle 2, in a cell that lost a few per cent, was
never a measurement — it was the derivative's noise being partitioned between
components. The histogram removes it without any change to the fitting.

Note R² moved the *other way* here, 0.971 → 0.991. Between the two chemistries
R² goes up and down while the areas get right both times, which is as clean a
demonstration as this project has produced that **R² tracks how smooth the
curve is, not whether the answer is true.**

**Two pieces of honesty about that table.**

*Integral fidelity means something different on the histogram path.* The curve
is built by adding up the charge each record carried, so within the analysed
window it integrates back to that charge **by arithmetic**. A fidelity of
0.995 is not evidence that the method is right; it is the method's definition.

That does not make the number useless — it changes what it detects. Fidelity
below 1 on the histogram path means charge that is genuinely **not in the
curve**: a constant-voltage hold (charge passed at one voltage, which no dV
integral can represent), or charge outside the analysed voltage window. A
CCCV charge half-cycle sits at 0.95-0.96 for exactly that reason. So read it as
*"how much of the cell's charge this curve is about"*, and read the **voltage
RMSE** for the question fidelity used to stand in for: is the charge at the
right voltages?

*R² gets worse on the two-phase material, and that is fine.* The median fit R² falls from 0.996
to 0.934, because the histogram is a raw binned curve with real bin-to-bin
scatter where the old one had been heavily smoothed. The model now has genuine
noise to sit in. The **areas became correct while R² fell** — which is §A6's
argument, demonstrated by accident. (On a broad profile R² goes the other
way, 0.971 → 0.991, which is the same point from the other side: R² tracks how
smooth the curve is, not whether the answer is right.)

### The two parameters, and why they are not the old problem

The histogram path has a bin width and a smoothing half-width, both chosen
from the measured profile class exactly as the old smoothing parameters were:

| profile | bin | smoothing | why |
|---|---|---|---|
| sharp (two-phase) | 1 mV | 1 bin | FWHM ≈ 15 mV; the peak towers over the noise |
| moderate | 2 mV | 3 bins | |
| broad (layered oxides) | 5 mV | 6 bins | FWHM 60 mV+; features are shallow |

A bin narrower than the records themselves cannot be filled, so the width is
widened automatically where the data are sparse and the width **actually used**
is recorded in `dataset_info.txt`.

It is fair to ask whether this smuggles back the trial-and-error smoothing the
method exists to avoid. It does not, for a reason that is arithmetic rather
than rhetorical: **this smoothing is applied to the result, with a binomial
kernel that sums to one.** It cannot move a record's charge into a different
bin, and it conserves the total area exactly. The old smoothing was applied to
the *voltage* before differentiating, where it changed the derivative and the
integral together and could not be undone. Across a sweep of smoothing widths
from 1 to 8 bins on a layered oxide, integral fidelity moves 0.9403 to 0.9379 — a
quarter of a percent, and that is edge effect from the zero-padded
convolution, not lost charge.

What the smoothing *is* for: peak DETECTION runs on the curve, and a
histogram's bin-to-bin scatter is counting noise. Unsmoothed, detection found
13 peaks per half-cycle on a layered oxide where the derivative path found 5. At 6 bins it
finds 6. That is the whole reason the parameter exists, and it is set by
matching detection to the smoothed path rather than by eye.

### The related artefact: non-monotonic voltage, and what it actually is

On the same flat plateau the recorded voltage can move *backwards* between
records while the cell is still charging. There are **two causes and they are
easily conflated**:

1. **Instrument resolution.** The true voltage change is below the cycler's
   least significant bit, so the recorded value dithers.
2. **Real physics.** Local maxima and minima in the voltage–capacity curve are
   a genuine feature of first-order phase transitions, driven by
   lithium–vacancy interactions in the host. They are not noise.

Either way the consequence for IC is the same and it is severe: the instrument
divides a positive dQ by a negative dV and reports a wrong-sign,
large-magnitude value; sorting by voltage interleaves those with the honest
records; smoothing averages the two. That is the up-and-down pattern on a first
cycle, and on a flat plateau an *inverted* peak. Worse, a ΔV that oscillates
between negative, zero and positive makes the voltage reconstruction of §A1
undefined — which is precisely why fidelity collapses.

`signal.orient_dqdv` corrects the sign of exactly those records, before the
sort, and only where the current has not reversed and charge is still
accumulating. **Be clear about what that is:** it forces the curve to be
sign-definite so the integral is well posed. Where cause (1) dominates it
repairs an instrument artefact; where cause (2) dominates it *discards real
information* — deliberately, because IC assumes a one-to-one relation between
voltage and capacity and simply cannot represent a non-monotonic curve. The
literature's advice is the same in substance: approximate the non-monotonic
region with a smooth monotonic IC, and characterise it separately by
**differential voltage analysis (dV/dQ)**, which does not have this problem. A
high `n_oriented` count is a flat plateau, and a flag that dV/dQ would tell you
something this curve cannot.

---

## A5. Closure, and why attribution is sometimes withheld

Two orthogonal questions, deliberately never combined:

```
    closure            Σ(component areas) / ∫(dQ/dV) dV
                       "do the fitted peaks account for the CURVE?"

    integral fidelity  ∫(dQ/dV) dV / the counter's capacity
                       "does the curve account for the CELL?"
```

A dataset can pass one completely and fail the other, and a flat two-phase
material does exactly that. Using the counter's capacity as closure's denominator would hide a
preprocessing failure inside a fitting number.

**Closure is reported as an interval, not a value.** A pseudo-Voigt of σ ≈ 100
mV and a cubic across a 1.4 V window are nearly the same function. Where that
is true, the split between "peak" and "background" is not determined by the
data, and any single closure value is an artefact of the baseline degree
somebody chose. So the same data is refitted at several baseline degrees and
the **spread** is reported. Where the spread exceeds
`PARTITION_DETERMINED_BELOW`, the per-peak capacity *share* is set to NaN and
the reason recorded — the fitted areas are kept, because withholding a share is
not deleting a number.

> **Tuning.** `PARTITION_DETERMINED_BELOW` (0.15) and `CLOSURE_SAMPLE` (40
> half-cycles). Widening the first to make attribution appear is the one
> change in this appendix most likely to produce a number that cannot be
> defended: the spread *is* the evidence that the split is undetermined. If
> attribution is withheld often, the productive move is usually a lower
> baseline degree or a narrower analysed window, not a looser threshold.
"""

# ---8<--- CELL md_appendix_4
"""
## A6. Reading a fit: what good and bad look like

**Residuals** are the primary diagnostic, exactly as in Rietveld refinement.
Flat and featureless is good; structured residuals mean the model is missing
something real.

**R² is not a check on anything.** It cannot see the failure modes that
actually matter here. On a two-phase anode, refining the mixing fraction per
cycle
carried the fitted peak area from 61 to 85 mAh g⁻¹ — 37% growth on a cell that
had lost 1.5% of its capacity — with R² between 0.995 and 0.998 the whole way.
Every fit was excellent; the trend they formed was fiction. Adding free
parameters always lowers the residual. That is what free parameters do.

**What to look for instead:**

- A component that has inflated to span the whole voltage range — it has become
  the background.
- A component pinned at its σ bound (`sigma_max_fitted`).
- Area retention exceeding the cell's own capacity retention — a redox feature
  cannot take more charge than the cell delivers, so where this appears the
  decomposition is wrong. Flagged, never deleted.
- Two components collapsed onto one feature; the smaller is dropped and the
  half-cycle refitted once, recorded as `dropped_degenerate`.

**Constrain, don't fix, and don't free.** This is the crystallographic
instinct and it applies directly. Nobody refines an independent profile width
for every reflection in a Rietveld fit; widths are tied to a few physically
motivated parameters and released only when the data demand it. Here:

- A **shoulder's width is tied to its parent's** by a bounded ratio,
  σ_shoulder = k·σ_parent with 0.3 ≤ k ≤ 1, one k shared per half-cycle.
- The **mixing fraction η is a property of the measurement**, not of the redox
  process — it is set by voltage resolution, rebin width and smoothing, none of
  which change from cycle to cycle. It is measured once per dataset on a sample
  and then held.
- Both are **measured, not assumed**, and the calibration *declines* to hold
  them when the spread across the sample is too wide. A shape the data says is
  not constant is not asserted to be one.

> **Tuning.** `FIT_SIGMA_MAX_MV` (200 mV) is the width bound worth raising for
> a genuinely broad material; `SHOULDER_SIGMA_RATIO_MIN/MAX` (0.30–1.00) is
> the shoulder tie, and `SIGMA_RATIO_SPREAD_MAX` (0.30) is the spread at which
> the calibration gives up and refuses to hold a shape. If components keep
> pinning at the σ bound, raise the bound *or* reduce the baseline degree —
> a component spanning the window is trying to be the background.

---

## A7. How many peaks should there be? Ask the thermodynamics first

A worked example from this project, because the lesson generalises.

An early cycle of a two-phase anode appeared to show a **doublet** where one
peak was
expected. The evidence offered for it was that the pair survived a change of
bin width, and that R² improved from 0.937 to 0.999 when a second component was
added.

Both arguments are worthless.

- **Bin-width stability is necessary, not sufficient.** A reproducible
  processing artefact is reproducible.
- **An R² gain from 0.937 to 0.999 on one added component is what overfitting
  looks like**, not evidence of a second process.

The test that settled it was the **thermodynamics**. Li₄Ti₅O₁₂ → Li₇Ti₅O₁₂ is a
first-order two-phase transition. By the Gibbs phase rule a two-phase field in
a binary system at fixed T and P is invariant, so the potential is fixed while
both phases coexist — which means **one** flat plateau and therefore **one**
dQ/dV peak. There is no second process available to make a second peak.

The processing-free confirmation was **V(Q)**: Q is a monotonic integral and V
is a directly quantised measurement, so V(Q) shows a second plateau if there is
one. There was none. The "flattest point" sits at 1.546 ± 1 mV across cycles
3–10; the claimed pair appears in cycle 2 only, and not at all in a replicate
cell.

**The rule:** before adding a component, ask what process it would correspond
to. If the phase diagram does not offer one, the component is describing noise
or a baseline, and the fit will happily accommodate it.

### Checked against the literature, including the awkward paper

The claim above was tested against the work that most threatens it — a 2024
study reporting a **three-phase** α/β/γ transition in Li₄Ti₅O₁₂ — and it
survives, for a reason worth stating precisely rather than hedging:

- The third phase (γ, quasi-rock-salt) is reached only on discharge to
  **ultralow potential**. Its plateau sits at **ca. 0.53–0.63 V**, and the
  study's window is 2.0–0.3 V. A cell cycled **1.2–2.5 V never reaches it.**
- Within the ordinary window the α/β transition is exactly as described: a flat
  plateau at ca. 1.55 V on discharge and ca. 1.58 V on charge, with a GITT
  equilibrium potential of **E(α/β) = 1.565 V**.
- What the study *does* add for wide-window work is an asymmetry — discharge
  through α/γ, charge through α/β — plus the observation that the balance
  between the two discharge plateaus is tunable by particle density, current
  and temperature. None of that splits the 1.55 V plateau.

Departures from two-phase behaviour that **are** documented, and their
conditions: **nanosizing** (simultaneous 16c/8a site occupation near the
surface, giving a curved voltage profile and extra low-voltage capacity, much
like nano-LiFePO₄); **very low rate at room temperature**, which can reach an
equilibrium solid solution — note this is the opposite way round from the usual
intuition, since *fast* intercalation kinetically gives the two-phase reaction;
and **temperature**, which moves the system through a solid-solution →
nanodomain → true two-phase coexistence sequence. Sub-nanometre phase
coexistence can even *look* like a solid solution while remaining a first-order
transition.

None of these predicts a **resolved doublet on the main plateau** for
micron-scale powder at C/10 over 1.2–2.5 V, which is the case at hand.

### An independent check on the pipeline's peak positions

Worth recording, because it validates the quantity §A1 calls the robust one.
Across the triplicate, the tracked reference positions are:

```
    charge     1.548, 1.546, 1.550 V        mean 1.5480 V
    discharge  1.579, 1.582, 1.578 V        mean 1.5797 V
    midpoint (the polarisation-free estimate)     1.5638 V
```

The GITT equilibrium potential for the α/β transition is **1.565 V**. The
pipeline's midpoint agrees to **1.2 mV**, from ordinary C/10 galvanostatic
data, with no calibration against it.

*Where the reference cycle sits changes these numbers, and that is itself a
result.* Anchoring on cycle 2 — still inside formation on these cells — gives
1.533 / 1.590 V, a midpoint of 1.562 V and a half-gap of 28 mV. Choosing the
reference by **measured CE stabilisation** moves it out of formation, and the
polarisation drops to ΔV/2 ≈ **16 mV** while the midpoint moves *towards* the
equilibrium potential, from 3 mV out to 1.2 mV. A formation cycle is more
polarised than a settled one, so both movements are in the direction the
physics requires, and neither was tuned for.

16 mV sits well below the ~85 mV reported for a dense single-particle
microelectrode, which is what a porous composite electrode at C/10 should
give: less current per particle and a much shorter effective diffusion path.
**Positions are strong.** That is the whole argument of §A1's table, measured
on a material whose *areas* this same pipeline once refused to report.
"""

# ---8<--- CELL md_appendix_5
"""
## A8. Coulombic efficiency — and a caution the older literature does not give

CE is Q_discharge / Q_charge **for the same cycle**, and it is the most
precision-critical number in the field: distinguishing cells that will survive
500 cycles needs it read at the fourth decimal place, and ultra-high-precision
instruments quote 1 ppm.

Two consequences the pipeline enforces:

- **CE is NaN, never 0, when either half-cycle is absent.** A spurious 0%
  asserts that the cell passed charge and returned none, which is a different
  physical claim from "we could not measure it" — and in a series read at the
  fourth decimal place it is not a small error.
- **CE and capacity fade are not the same quantity.** The conventional
  inference — coulombic inefficiency accumulates into capacity loss — is a
  *systematic overestimation*. Recent work shows the measured coulombic
  inefficiency is far larger than the fractional capacity fade per cycle in
  good cells, so only part of the parasitic charge consumption contributes to
  fade. Report CE as CE. Do not convert it into a predicted lifetime without
  saying you have done so.

Voltage efficiency (VE) decomposes the energy loss alongside it: EE ≈ CE × VE /
100, with CE reflecting charge accounting and VE reflecting polarisation.

---

## A9. Replicates: report mean ± SD, not a representative cell

Published reproducibility practice for replicate cells is **mean ± standard
deviation across the replicates, with n stated**, and the individual cells
shown.

Nominating one cell as "representative" is a *selection step*, and selection
steps are where irreproducibility enters — it is the same move as choosing the
prettiest diffraction pattern.

So:

- The reported number for a group is the **mean ± SD** (sample SD, ddof = 1;
  three cells are a sample, and the population SD understates a triplicate's
  spread by 18%).
- A representative cell is nominated **for figures only**, and labelled as
  such: *"cell B shown; n = 3, retention 98.6 ± 0.4%"*. (The cell letter is the
only thing a caption should name.)
- **The representative cell's number is never the reported number.**
- A single cell shows its value with no ± at all. One measurement has no
  spread, and quoting 0 would claim a precision nothing established.

---

## A10. Known limits — read this before quoting anything

Measured, not speculated. Each was established against synthetic data with a
known answer (`synthetic.make_series`) or against the real triplicates.

**The ±80 mV tracking window is a PER-CYCLE step limit, not a lifetime
allowance.**

If every cycle were matched against the *reference cycle's* fitted positions, a peak drifting 2 mV/cycle exhausted the window in forty cycles
and was then matched to whichever component was nearest — on a crowded curve,
a different peak. The tolerance was therefore a ceiling on the drift the
tracker could measure, which is the one quantity ICA is most often read for.

Instead the expectation moves with the peak: each reference id carries a
running centre, updated every time it is matched, walking outward from the reference
cycle in both directions. A peak missing for some cycles keeps its last
matched position rather than reverting. Measured on synthetic data with a known trajectory, same fits, only the
matching rule changed:

| 2 mV/cycle | fixed reference | drifting reference |
|---|---|---|
| 100 cycles, true drift 192 mV | **−53 mV of a true +172 mV** | **192.21, 191.95, 131.74 mV** (err ≤ 0.3 mV) |
| 50 cycles, worst centre rms | 67.05 mV | **0.18 mV** |
| 50 cycles, worst drift error | −138.30 mV | **+0.21 mV** |
| tracking rate | 78–100% | **100%** |

The hazard of chaining is real — an error in one cycle is inherited by the
next — and it is bounded two ways: no single cycle may move further than the
window, and a single-cycle step that *does* exceed it is a discontinuity,
counted as one, and reported. `drift_exceeds_tolerance` changed meaning with
the rule: total drift is no longer a warning, it is the measurement, and the
flag now tests the per-cycle step. `TRACK_AGAINST_PREVIOUS_CYCLE = False`
restores the old behaviour.

A fixed window also COMPRESSES the drift it does report, by about 13% over 50
cycles, because it acts asymmetrically once a peak has crossed most of it. On
data whose drift stays inside the window the two rules agree exactly, which is
the test that matters: identical where a fixed reference is valid, correct
where it is not.

**Areas remain the weak quantity, and this is now the only open limit of the
three.** On synthetic data with a known answer, per-cycle fitted area is
recovered with a *bias* of 0.25–9.9% but an **rms of 10.7–59%**. It is
scatter, not bias — which is why `area_retention_pct` is computed from medians
over endpoint windows rather than single cycles, exactly as drift is, and why
a single cycle's area should not be compared with another single cycle's. The
suite's `TOL_AREA_PCT = 8` is an aspiration rather than a measured capability
and has deliberately **not** been relaxed to make the tests pass.

A caution about measuring this: two components 20 mV apart, one three times
the other's width, are not separable by any method, and scoring such a merged
doublet against either component alone reports a catastrophic error that is an
artefact of the scoring. Against their SUM the same peak's area bias is 0.25%.

**Integral fidelity below 0.80 is a property of the derivative path, not of
two-phase materials.** On the derivative-free histogram — the default — the
same data measures **0.99–1.00**. §A4 has the head-to-head.

---

## A11. Tuning: what to change, when, and how

Every default here was set on two chemistries — a sharp two-phase spinel (LTO)
and a broad layered oxide. **They are starting points, not constants of
nature.** This section is the one to read when the pipeline is applied to a
system it has not seen: it is organised by the *symptom you observe*, because
that is how the question actually arrives.

Three rules before any of the specifics:

1. **Change one thing, re-run, and look at the same figure.** Every parameter
   below is recorded in `run_manifest.json`, so two runs can be diffed. A
   change nobody can attribute is a change nobody can defend.
2. **Prefer the profile class to a hard-coded value.** Most of these are set
   per profile (`sharp` / `moderate` / `broad`) from the dataset's own curve.
   If the automatic classification is wrong for your material, fixing *that*
   fixes several parameters at once and stays honest about why.
3. **A parameter that makes the picture prettier has not made the answer more
   true.** R² in particular will improve for changes that make the result
   worse — see §A6. Judge a change on residual *structure*, on voltage
   reconstruction, and on whether the physical bounds stop complaining.

### Where they are set

Three places, and it matters which you use:

- **Cell 2** — run-level switches: `DQDV_COMPUTATION`, `DQDV_BIN_MV`,
  `MAX_CYCLE`, `RUN_PEAK_FITTING`, `CLOSURE_SAMPLE`.
- **Cell 3b, per dataset** — the operator overrides: `peak_min_width_mV`,
  `peak_min_distance_mV`, `peak_prominence_fraction`, `histogram_bin_mV`,
  `histogram_smooth_bins`. An override belonging to the dQ/dV path that is
  *not* running is reported as doing nothing rather than silently ignored.
- **Module constants** — everything else in the table below. These are
  deliberately not exposed per dataset: they are decisions about the method,
  not about a cell, and changing one should be a considered act recorded in
  the manifest.

### The parameters, by symptom

| Symptom | Parameter | Default | Which way, and why |
|---|---|---|---|
| **Curve is noisy and spiky; detection finds a peak per bump** | `histogram_smooth_bins` (per profile: sharp 1, moderate 3, broad 6) | by profile | **Up.** Binomial kernel, applied to the result, conserves area exactly — so this is safe in a way that pre-differentiation smoothing never was (§A4). Raise until detection count stabilises, not until the curve looks nice. |
| **Curve is sparse; many empty bins** | `DQDV_BIN_MV` / `histogram_bin_mV` (sharp 1, moderate 2, broad 5 mV) | by profile | **Up.** A bin narrower than the voltage spacing of the records cannot be filled. The width actually used is widened automatically and recorded in `dataset_info.txt` — if that says it was widened, the request was too fine. |
| **Fine structure is being smeared together** | same | | **Down**, but check `bins with no charge` afterwards: past ~90% empty the curve is mostly interpolation. |
| **Fits do not converge / the run is slow** | `PROFILE_SPECS[...]["baseline_degree"]` (sharp 1, moderate 2, broad 2) | | **Down.** This is the single biggest lever on a broad noisy curve. A cubic can carry an inflection, and an inflection is what lets a baseline impersonate a peak — the optimiser then crawls along that degenerate direction to the iteration ceiling. Measured on a layered oxide: cubic 40% of fits converging at 20,000 evaluations, quadratic 66-89% at a few hundred, for 0.004 of R². |
| **Still not converging on a broad curve** | `TERMINAL_TRIM` (off), `TERMINAL_TRIM_FIXED_MV` (75 mV) | | **On, deliberately.** Removes a fixed span at each half-cycle's TERMINATING end — high for charge, low for discharge — where the cell is approaching its cut-off and dQ/dV climbs for protocol reasons. Worth 66% → 87% convergence on a layered oxide with the quadratic. **Look at your curves before setting it**: it removes charge the cell really delivered, so integral fidelity falls by roughly the fraction removed, and automatic detection of the right span does NOT work (see below). |
| **A real peak is never detected** | `peak_min_width_mV` (5 mV), `peak_prominence_fraction` (0.05) | | **Down.** Both admit more peaks. Measured on LTO: dropping min width to 2.5 mV does find the discharge peak — and admits 2–3 spurious charge peaks per cycle. That trade was measured and rejected; make it deliberately, and check the spurious count. |
| **Too many peaks; components fighting over one feature** | `peak_prominence_fraction` (0.05), `peak_min_distance_mV` (30 mV) | | **Up.** `min_distance` is the blunter and safer of the two: it says how far apart two features must be to be two features, which is a statement about your material you can defend. |
| **Two peaks merge and swap identity** | `min_distance_mV`, or accept the merge | 30 mV | Components closer than roughly the wider one's σ are **not separable by any method** (§A10). Better to fit one feature and say so than to fit two and report their ratio. |
| **A tracked peak is lost partway through the run** | `TRACKING_TOLERANCE_MV` | 80 mV | **Up.** This is a *per-cycle* step limit, not a lifetime budget, so it no longer caps total drift. Raise it only if a feature genuinely moves >80 mV **between consecutive cycles**; if it does, suspect the fit before the cell. |
| **`drift_exceeds_tolerance` fires** | same | | Do **not** raise it to silence the flag. It now means a single-cycle jump, which is a discontinuity — look at the fit for those two cycles. |
| **Areas marked "not capacities"** | `INTEGRAL_FIDELITY_FLOOR` (0.80), `INTEGRAL_FIDELITY_CEILING` (1.20) | | **Usually neither.** First check `DQDV_COMPUTATION` is `"histogram"` — on the derivative path a flat plateau fails this routinely and correctly (§A4). On the histogram path a deficit means charge outside the analysed window, typically a CV hold, and the honest fix is to widen the window or accept that the areas exclude the hold. |
| **Capacity attribution withheld** | `PARTITION_DETERMINED_BELOW` | 0.15 | **Up only with an argument.** This is the spread in closure across baseline degrees; a wide spread means the peak/background split is genuinely undetermined, and raising the threshold asserts a split the data does not support. |
| **A peak "grows" past the cell's capacity** | `AREA_GROWTH_HEADROOM_PCT` | 15 pts | **Rarely.** A process can take a larger *share* as another fades, which is what the headroom allows. Consistent large excesses mean the decomposition is wrong, not that the bound is tight. |
| **Fit will not converge / σ pinned at the bound** | `FIT_SIGMA_MAX_MV` (200), `SHOULDER_SIGMA_RATIO_MIN/MAX` (0.30–1.00) | | **Up** for a genuinely broad material — a solid-solution cathode can exceed 200 mV honestly. Check `sigma_max_fitted` in the output: a component pinned at the bound is being asked to be the background. |
| **Shoulder ratio calibration declines to hold** | `SIGMA_RATIO_SPREAD_MAX` | 0.30 | Leave it. Declining is the correct behaviour when the shape is not constant across the sample; forcing it asserts a constancy the data denies. |
| **Reference cycle looks wrong (still in formation)** | `CE_SETTLED_TOLERANCE_PP` (0.1 pp), `CE_SETTLED_RUN` (3), `REFERENCE_CYCLE_FLOOR` (2), `REFERENCE_CYCLE_FALLBACK` (6) | | Formation end is **measured** from CE stabilisation, not assumed. A noisy CE series may never settle, in which case the fallback (cycle 6) is used and says so. Tighten the tolerance for high-precision data; loosen it for a noisy cycler. This choice moves the polarisation and drift numbers materially — see §A7. |
| **Retention quoted against the wrong baseline** | `RETENTION_REFERENCE_CYCLE` | 2 | Cycle 1 includes the first-cycle irreversible loss; cycle 2 does not. Both are reported in the headline metrics, so this only sets which one the *caption* names. |
| **Drift number is noisy** | `DRIFT_ENDPOINT_CYCLES` | 3 | **Up** for long runs. Two single cycles carry √2 times the per-cycle centre scatter; medians of 3 were enough to turn 90 mV of true drift from 79 into 90. |
| **Closure sampling too slow / too sparse** | `CLOSURE_SAMPLE` | 40 half-cycles | Cost is 3 fits per sampled half-cycle. Rows not sampled are marked `closure_interval_measured = False` rather than left ambiguously blank. |

### Trimming the cut-off approach, and why it is not automatic

A galvanostatic half-cycle ends on a voltage. As the cell reaches its cut-off
dV/dQ collapses and dQ/dV climbs — on a layered oxide to 1.5-2.1x the
interior of the curve, extending 200 mV in. That rise is protocol, not
chemistry, and left in it is fitted as a peak.

Removing it works: an extra 50-100 mV at the terminating end took one layered
oxide from 66%
of fits converging to 87-89%, and removed one spurious component per
half-cycle, for 0.003 of R².

**Measuring the right span automatically does not work, and the failure is
worth knowing about.** A rule that walks in from each end while the curve
stands above the interior gives a BIMODAL answer across a full run: half the
half-cycles want nothing, most of the rest saturate at the cap, and there is
no pattern in cycle number (median trim by 20-cycle band on charge: 180, 0, 0,
190, 0 mV). A 30-cycle sample can look clean and not be. So the span is an
operator setting with a default of 75 mV, not a measurement.

**The cost is real and is reported.** Trimming removes charge the cell
delivered, so integral fidelity falls by roughly the fraction removed — on a
layered oxide
about 7-9% on a layered oxide. That is the honest outcome rather than a penalty: the charge near
the cut-off *is* delivered and *is not* attributable to a resolvable feature,
and untrimmed it is silently absorbed into a fake peak and a straining
baseline. But it moves a headline number, so turn it on deliberately.

**It does nothing on a sharp two-phase profile**, which shows no terminal rise
at any threshold tested, on either step.

### When to change the *method* rather than a parameter

- **A CCCV protocol.** Charge passed during a constant-voltage hold happens at
  one voltage and cannot appear in any dV integral. Expect fidelity below 1 on
  that half-cycle; it is not an error, and the number to read is *how much of
  the cell's charge this curve is about*.
- **A strongly non-monotonic voltage curve.** If `n_oriented` is high, IC is
  being asked to represent something it structurally cannot (§A4). Use
  **differential voltage analysis (dV/dQ)** for that region instead — it has
  no such assumption.
- **A featureless material.** A continuous solid solution has no plateau to
  hold the potential and gives broad humps or nothing. That is a result about
  the material (§A1), not a parameter to tune your way out of.

---

## A12. Sources for the science in this appendix

The claims above that are not measurements from this project are drawn from:

- **E. Flores and S. Clark**, *Simple and Comparable Computation of Incremental
  Capacity Curves*, J. Electrochem. Soc. **173**, 120520 (2026), open access —
  §A1 (derivative vs histogram, voltage reconstruction, APE/RMSE) and §A4
  (sign-definite ΔV, non-monotonic voltage curves, IC as a one-to-one
  assumption).
- **Y. Ren, X. Lu, Y. Han, D. Li, Y. Chen**, *Three-Phase Transition of Spinel
  Li₄Ti₅O₁₂ with a Dense Single-Particle Microelectrode*, Energy Fuels **38**,
  16976 (2024) — §A7 (the γ phase below ca. 0.6 V, E(α/β) = 1.565 V by GITT,
  the discharge/charge asymmetry).
- **C. Zhang et al.**, *Li₄Ti₅O₁₂ spinel anode: fundamentals and advances in
  rechargeable batteries*, InfoMat **4**, e12228 (2022) — §A7 (conditions for
  solid-solution vs two-phase behaviour: nanosizing, rate, temperature;
  sub-nanometre coexistence).
- **Nature Communications 16 (2025)**, *Deciphering coulombic loss in
  lithium-ion batteries and beyond* — §A8 (coulombic inefficiency as a
  systematic overestimate of capacity fade).
- **Imperial College / J. Energy Storage**, peak-tracking to quantify
  degradation modes — §A2, §A10 (the coherence framing and what a tracking
  tolerance should be quoted as).

Everything else — the fidelity measurements, the doublet analysis, the
free-mixing-fraction demonstration, the synthetic recovery figures — was
measured in this project on the data in hand, and the numbers are reproducible
from the runs in the output folder.

---

## A13. Provenance

Every run writes `run_manifest.json` (every module constant that was in force,
input checksums, package versions, an inventory of every file written with
checksums) and a per-cell `dataset_info.txt` carrying two blocks: what the
operator **asked for**, and what the pipeline **measured and then used** —
profile class, analysed window, reference cycle and the reason for it,
calibrated peak shape, and integral fidelity per step.

The rule throughout: **the record describes what ran, never what was offered.**
A record field that disagrees with what actually happened is worse than an
absent one, because it reads as an assurance.
"""
