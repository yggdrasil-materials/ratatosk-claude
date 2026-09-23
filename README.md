# **THIS REPOSITORY CONTAINS CODE FOR THE RATATOSK PROJECT THAT WAS COMPOSED BY CLAUDE CODE**

It serves as a snapshot of the code under version control (via Git) and serves as a basis for refactoring the code and tests.

- It is _not_ possible to clone and install this package it is missing a `pyproject.toml` that defines the metadata and
  package structure.
- Whilst there are unit-tests in the `tests/` directory they do not follow the formal structure of the
  [unittest](https://docs.python.org/3/library/unittest.html) or [pytest](https://docs.pytest.org/en/stable/) frameworks and
  refactoring these tests will also be undertaken.

# Ratatosk 1.9.0 — how to run it

## What changed

1.8.x was 69 notebook cells sharing implicit global state. 1.9.0 is a Python
package plus a **14-cell notebook**. The analysis lives in `ratatosk/`; the
notebook loads, runs and exports. You edit Cell 2 and press run.

Nothing about the figures changed — the plotting code is 1.8.7's, ported
unedited.

## Folder layout

Put the notebook and the package folder in the **same directory** — any
directory; nothing below depends on where. The path shown is an example:

```
<wherever you keep it>\Ratatosk_1_9_0\
    Ratatosk 1.9.0.ipynb          <- open this
    README.md
    ARCHITECTURE.md               <- why it is built this way
    ratatosk\
        __init__.py  io.py  signal.py  detect.py  fitting.py
        quality.py   analyse.py  plots.py  cycling.py
        synthetic.py run.py
    tests\
        test_foundation.py  test_port_fidelity.py  test_detect.py
        test_detect_fidelity.py  test_analyse.py
        test_analyse_end_to_end.py  test_presentation.py
```

Cell 1 puts the notebook's own directory on `sys.path`, so `import ratatosk`
finds the package with no installation step. If you keep the package somewhere
else, point `PACKAGE_DIR` at the folder that *contains* `ratatosk`.

## Dependencies

From Anaconda Prompt, in the environment you use for Ratatosk:

```
conda install -c conda-forge numpy pandas scipy matplotlib seaborn lmfit joblib openpyxl python-calamine jupyterlab
```

`python-calamine` is optional but reads these Excel exports 5–7× faster than
openpyxl, with a maximum numeric difference of exactly zero. `seaborn` is used
by one figure (key-cycle voltage profiles). Everything else is required.

## Running

```
cd /d "<wherever you keep it>\Ratatosk_1_9_0"
jupyter lab
```

Open `Ratatosk 1.9.0.ipynb` and run the cells in order.

### Where the data is

**You do not have to edit a path.** `DATA_DIR` in Cell 2 is blank by default
and the folder is searched for: cloud drives on every mounted letter, the home
folder, `Documents`, and the working directory, looking for a folder named
`Example Battery Data` (or `Battery Data`, or `Python Scripting\Example
Battery Data`) that actually contains files matching `PATTERN`. A folder that
exists but holds no matching file is not accepted, so the search does not stop
at the first `Documents` it meets. Cell 2 prints which folder it chose and why.

To be explicit, in the order they win:

1. **`RATATOSK_DATA_DIR`** — set this environment variable before starting
   Jupyter. Use this one if you work on more than one machine, run the
   notebook on a schedule, or are handing it to somebody else:

   ```
   set RATATOSK_DATA_DIR=D:\Cycling\Exports          (Windows, cmd)
   $env:RATATOSK_DATA_DIR = "D:\Cycling\Exports"     (PowerShell)
   export RATATOSK_DATA_DIR=/data/cycling             (macOS, Linux)
   ```

2. **`DATA_DIR` in Cell 2** — put the path on that line.
3. **Leave it blank** and let the search find it.

If nothing is found the error names every place it looked and both ways out.
`OUTPUT_BASE` is written relative to whoever is logged in, so it needs no
editing either.

**Cell 2 is the only one you normally edit,** and usually only to set one
`dict(...)` per cell in `DATASETS`. The field that matters most is
`electrode_type`: `"Negative"` swaps the step labels and the sign of dQ/dV so
that the useful half-cycle reads as *Discharge* for both polarities.

While you are setting a run up, `MAX_CYCLE = 20` and `CLOSURE_SAMPLE = 4` make
the whole notebook run in a couple of minutes. Set them back before the real
run.

## What each cell does

| cell | what it does |
|---|---|
| 1 | imports, version check |
| 2 | **what to analyse** — the only cell you edit |
| 3 | load the exports, open the run folder, write the opening manifest |
| 4 | Q, V, I, t → dQ/dV, with preprocessing chosen from each dataset's own profile |
| 5 | cycle integrity — where the charge went |
| 6 | cycling performance: capacity, CE, retention, fade, energy, power, voltage, efficiency, rate |
| 7 | dQ/dV figures: overlay, key cycles, waterfall, heatmap, QC |
| 8 | peak detection, and the reference cycle chosen on integrity |
| 9 | multi-peak fitting (parallel where it pays) |
| 10 | closure interval and integral fidelity — does the answer mean anything |
| 11 | tracking, ΔV, capacity attribution, coherence audit |
| 12 | fit, tracking and descriptor figures |
| 13 | export the CSVs |
| 14 | close the run: sort the outputs, checksum them, finalise the manifest |

Cells 9–13 are skipped if you set `RUN_PEAK_FITTING = False`; the cycling
analysis does not need them.

## Where the output goes

Every run gets its own folder:

```
OUTPUT_BASE\runs\2026-08-30_143012_v1.9.0\
    run_manifest.json
    NNM_cellA\
        1_cycling\  2_voltage_profiles\  3_energy_power\
        4_dqdv\     5_peak_fitting\      6_descriptors\  7_summary\
```

`run_manifest.json` records the input file checksums, the package versions, and
every switch in force — which is what lets you tell two runs apart when the
version number has not moved.

## Three things 1.9.0 tells you that 1.8.x did not

**The reference cycle is chosen, not assumed.** Its peak list is fitted and
tracked in *every* cycle, so a bad reference cycle is not a bad cycle — it is a
bad dataset. Cell 8 picks the lowest cycle at or above 2 whose half-cycles both
pass Cell 5's integrity check, and says why. Pass `reference_cycle=N` to
`detect_all` to choose it yourself; it will be honoured, checked, and warned
about.

**Reversed charge is classified, not counted.** `f_wrong_sign` conflated a
two-phase plateau at 100% coulombic efficiency with a parasitic current at 20%.
Cell 5 asks where on the curve each backwards run sat — on a plateau, at the
voltage limit with the current tapering, or at full current with no redox
process to account for it — and only the last is a fault. Measured against the
half-cycle's own capacity, never against a population.

**Capacity attribution is withheld where the split is not determined.** A broad
pseudo-Voigt and a cubic baseline over a 1.4 V window are nearly the same
function. Cell 10 refits at several baseline degrees and reports the spread; if
that interval is wide, Cell 11 sets the per-peak *share* to NaN and says so.
The fitted areas are kept — withholding a share is not deleting a number.

## Tests

From Anaconda Prompt, in the package directory:

```
python tests\test_foundation.py
python tests\test_detect.py
python tests\test_analyse.py
```

Those three need no data. The other four (`test_port_fidelity`,
`test_detect_fidelity`, `test_analyse_end_to_end`, `test_presentation`) check
1.9.0 against 1.8.7's own output and expect the example cells and a 1.8.7 run
folder; edit the paths at the top of each before running them.

## START HERE

A finished run is forty-six files across seven folders. Cell 13b writes two
more at the top of each dataset's folder:

| file | for |
|---|---|
| `START_HERE.html` | reading. Images embedded, so it can be moved or emailed alone |
| `START_HERE.md` | pasting into a report, a wiki or a supervision record |

Both say the same four things: what the cell did, what went wrong and on which
cycles, **what Ratatosk declined to tell you and why**, and four figures with
what to look for in each. Nothing is moved or removed.

The third section is the one that matters for a newcomer. A capacity share left
blank because the closure interval was 0.46 wide is a finding; found as a gap
in a spreadsheet three weeks later it is a bug report.

## What is still missing from 1.8.6

Restoring the analysis spine left 8,278 lines of 1.8.6 behind. This release
brings back the loading, parameters and documentation; the rest is listed here
so the gap is visible rather than discovered.

| lines | 1.8.6 cell | status |
|---|---|---|
| 1,540 | Triplicate analysis and representative-cell selection | **missing** |
| 1,246 | Results at a Glance | **missing** |
| 1,017 | Module 6b, descriptor trend shapes | **missing** |
| 763 | Meeting-ready PDF summary | **missing** |
| 638 | Module 2b, comparative dQ/dV | **missing** |
| 478 | Cumulative CSV summary | **missing** |
| 350 | Module 7, fit diagnostics | **missing** |
| 312 | Validation suite | **missing** |
| 309 | Module 3c, dataset competence report | **missing** |
| 284 | Module 7b, single-cycle fit inspector | **missing** |
| 186 | Module 2a, custom heatmaps | **missing** |
| 1,155 | Cell 3, sample parameters | **restored** (`params.collect_parameters`) |
| 418 | Cell 2, metadata extraction | **restored** (`params.extract_neware_metadata`) |
| 1,228 | 28 markdown documentation cells | **restored**, rewritten for this layout |

Rate capability, energy and power density, average discharge voltage and
round-trip efficiency were never lost — they are in `cycling.py` and run in
Cell 6.

## Known gaps

- **Shoulder-to-parent sigma coupling is not ported.** 1.8.7 ties each
  shoulder component's width to its parent primary's, which stops a shoulder
  inflating and stealing its parent's area between cycles. 1.9.0 does not do
  this yet. R² will not show its absence; area retention and a primary/shoulder
  swap will. Next on the list.

- **Tracking, ΔV and attribution have no bit-identity regression.** 1.8.7 never
  wrote a tracking CSV, so there is nothing to diff against. The functions that
  determine those values were extracted from 1.8.7 rather than retyped, and the
  orchestration is unit-tested, but the equivalence check has to be done by
  running both versions on the same cell.
- **The figures are checked by eye.** `tests/test_presentation.py` proves all
  24 draw; it cannot prove a pixel has not moved.
- **Deferred to 2.0:** a fixed model across a dataset, monotonic segmentation,
  reconstructing dQ/dV from Q and V, and rebinning keyed to record spacing. All
  four change every fitted value, and none can be judged without the
  measurements 1.9.0 adds.
