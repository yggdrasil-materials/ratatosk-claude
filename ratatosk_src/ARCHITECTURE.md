# Ratatosk 1.9.0 — structure

## Why a package, not more cells

1.8.x is 69 notebook cells sharing implicit global state. That made three
things impossible, all of which cost us this week:

- **testing** — nothing could be checked except by running the whole pipeline
  and reading the output;
- **parallelism** — a `ModelResult` cannot cross a process boundary through
  stdlib pickle, which forced `loky`, which forced worrying about which
  notebook globals were statically referenced;
- **editing** — every change meant pasting 300–1200 lines, and twice this week
  a paste landed on the wrong cell and destroyed Module 2.

Every stage becomes a function that takes data and returns data. The notebook
stays — it is how you work — but shrinks to a short orchestration layer.

```
    ratatosk/
      io.py          read a cycler export; dataset metadata; run provenance  [built]
      signal.py      Q, V, I, t  ->  a dQ/dV curve, and whether to trust it   [built]
      detect.py      find features; choose the reference cycle         [built]
      fitting.py     build the model; run it, in parallel where that pays   [built]
      quality.py     does the answer mean anything?                         [built]
      analyse.py     track; delta-V; attribution; mechanism           [built]
      plots.py       waterfall, heatmap, key cycles — unchanged output  [built]
      cycling.py     capacity, retention, fade, energy/power, rate   [built]
      synthetic.py   data with a known right answer                         [built]
      run.py         run folders, manifest, provenance                      [built]

    tests/
      test_foundation.py     metrics against known ground truth            [built]
      test_port_fidelity.py  the ported path against the 1.8.7 output      [built]
      test_detect.py         detection behaviour, on synthetic data        [built]
      test_detect_fidelity.py  detected peak lists against 1.8.7           [built]
      test_analyse.py          analysis logic, on constructed data         [built]
      test_analyse_end_to_end.py  the whole pipeline on three real cells   [built]
      test_presentation.py     all 24 figures draw, through the adapters   [built]
      test_fit_fidelity.py     fit quality against 1.8.7's own R2          [built]
```

Data flows one way: `io -> signal -> detect -> fitting -> analyse -> plots`.
`quality` is consulted by all of them and depends on none of them.

Ten modules for ~18,000 lines is enough structure. Deeper nesting would be
decoration.

---

## What is kept, and what is cut

**Kept as-is, ported not rewritten.** The waterfall, the heatmaps, the
key-cycle overlays and the split charge/discharge panels are the best part of
the tool and their output does not change. `plots.py` is a port, and the
1.9.0 regression requires the figures to be byte-identical apart from any new
annotation.

Also kept: the competence gate (points per free parameter), the reliability
guard, the relative area floor, reference-cycle selection on integrity,
Module 3c/7c reporting, the CV-hold exclusion, provenance, and all of the
cycling analysis (capacity, retention, fade, energy/power, rate capability).

**Cut.**

| removed | why |
|---|---|
| Module 3b, Plan B seeding | proved never to have contributed a result — every seeded fit was discarded on a missing `peak_id`, and the "rescues" it appeared to make were one component each, all discarded by the reliability guard |
| `f_wrong_sign` as a gate | conflated a two-phase plateau at 100% coulombic efficiency with a parasitic current at 20%. Kept as a reported diagnostic only |
| the `suspect` band threshold | replaced by the closure interval, which needs no threshold |
| notebook-global state | the reason for all of the above |

**Deferred to 2.0.** The fixed model across a dataset, monotonic segmentation,
and reconstructing dQ/dV from Q and V. All three change every fitted value, and
none of them can be judged without the measurements 1.9.0 adds.

---

## What is built and tested now

`synthetic.py`, `fitting.py`, `quality.py`, `tests/test_foundation.py`.

Four synthetic cases with analytically known areas — an LTO analogue, an
NMC111 analogue, a P3 analogue, and one built specifically to defeat the
metric. Ground truth is defined by integration, not by the fitting model, so
recovering it is not circular.

```
  1. generator produces self-consistent ground truth        4/4 PASS
  2. fitting recovers known peak areas                      within 3.4%
  3. closure interval separates determined from not
         two_phase        true 0.98   0.88-0.89   width 0.01
         mixed            true 0.62   0.61-0.62   width 0.01
         solid_solution   true 0.50   0.19-0.52   width 0.33
         degenerate       true 0.72   0.15-0.96   width 0.81
  4. integral fidelity catches a fabricated peak            1.283
  5. parallel == serial, bit for bit                        0.00e+00
  6. the scheduler refuses a pool it cannot repay           serial
```

The synthetic widths match the real cells: NMC111 measured 0.35 against
`solid_solution` 0.33; LTO 0.00–0.01 against `two_phase` 0.01; P3 0.05–0.09
against `mixed` 0.01. The metric behaves the same way on data whose answer we
know and on data whose answer we do not.

**One real finding already.** On `two_phase` the recovered closure is 0.88
against a true 0.98 — a systematic ~10% under-recovery, because a linear
baseline over-absorbs beneath a sharp peak on a flat background. The interval
is narrow, so the metric correctly calls it *determined*; the value is
nonetheless biased low. That is exactly what ground truth is for, and it is on
the list rather than hidden.

---

## Parallelism, and where it actually pays

**The design decision:** a worker returns a plain dictionary, never a
`ModelResult`. The optimiser output anyone uses downstream is a few dozen
floats; returning those makes stdlib pickle work, makes every joblib backend
work, makes the payload small, and makes a fit result something that can be
written to disk and diffed — which is what the 1.9.0 regression needs.

That single change removes the entire `loky`/cloudpickle constraint that
blocked Change 4 for a week.

**Where it pays:** the fits, and only the fits. Half-cycles are independent,
and the closure interval multiplies the count by the number of baseline
degrees, so it is the natural batch. `plan_workers` times a few fits, weights
the estimate by peak count, and **refuses below 60 seconds** — measured, a
worker pool costs 5–8 s to start on Windows, and the test above shows 8 fits
taking 0.5 s serially and 2.9 s on two workers. Refusing is correct behaviour,
not conservatism, and every branch prints which way it went and why.

**Where it does not pay:** loading (calamine already made it 5–7× faster),
preprocessing, detection, tracking, plotting. All are seconds.

---

## Build order from here

```
  [done]  synthetic, fitting, quality, tests
  [done]  io.py + signal.py      port Module 1 + 1b; add integral fidelity
  [done]  detect.py              port Module 3 + reference-cycle selection
  [done]  analyse.py             port Modules 5, 6, 7c; add mechanism +
                                 parasitic charge; withhold attribution where
                                 the closure interval is wide
  [done]  plots.py + cycling.py  port, output unchanged
  [done]  notebook               15 orchestration cells + README
    ->    regression             every CSV bit-identical to 1.8.7 on all six
                                 cells, apart from the new columns
    ->    version bump to 1.9.0  the last act, not the first
```



---

## Detection: what the port changed, and what it did not

`detect.py` ports the four value-determining functions of Module 3 —
`_voltage_to_samples`, `_deduplicate_peaks`, `_assess_truncation`,
`detect_peaks_single` — extracted programmatically, with **exactly one edit**.

**The edit.** 1.8.7 took the sign of the lobe from the step label:
`signal = -dqdv if step == 'Discharge' else dqdv`. Replacing that with the
measured `Dataset.step_direction`, which is what the Module 1b fix taught us to
do, is *wrong here* and was caught by the regression: it inverts every LTO
half-cycle and moves the 1.53 V peak by 30–40 mV. For a negative electrode the
useful half-cycle is the one in which the cell voltage **falls**, and
`io._apply_electrode_convention` has already negated dQ/dV to suit — so after
that convention the label, the direction and the sign of dQ/dV no longer agree,
and only one of the three is a property of the curve.

So the orientation is now measured **from the curve**: the sign of the signed
area under dQ/dV over the half-cycle, which is the net charge passed. Large,
unambiguous, and independent of every label and convention upstream. It
reproduces 1.8.7 exactly wherever 1.8.7's label was right, and is right where
a label would not have been. `tests/test_detect.py` checks the invariance
directly — negating a curve must not move a peak.

**Detection fidelity against 1.8.7** (`tests/test_detect_fidelity.py`, target:
the `detected_voltage` column of each run's `fitted_parameters.csv`, which is
the peak list Module 3 handed to Module 4 for every half-cycle, to 0.1 mV):

```
  P3 cell A   242 of 246 peak lists identical
              4 differ, every one of them on a half-cycle whose processed
              curve changed under the stable sort
  LTO cell A   19 of  19 peak lists identical

  reference peaks, 1.9.0 against 1.8.7
    P3  cell A  Charge     3.220, 3.301, 3.643, 3.700 V     identical
                Discharge  3.160, 3.237, 3.542, 3.573, 4.106 V  identical
    LTO cell A  Charge     1.529 V                          identical
                Discharge  1.590 V                          identical
```

**The selector takes the integrity check as an argument.** 1.8.7 reached into
notebook globals for `integrity_band`, so it could not be tested without a
notebook; and its sibling test for an explicit reference cycle had to infer
intent from a parameters dict that Cell 3 populates with defaults for every
dataset, which is why the first version of that cell was inert on every real
run. In 1.9.0 an explicit reference cycle is an explicit argument. There is
nothing left to infer.

**A limitation found while testing, not fixed here.** `_assess_truncation`
fires only when scipy's `peak_widths` clamps a half-maximum crossing at the
array end. On a smooth flank it does not clamp: truncating the array raises the
right-hand prominence base, which lowers the half-prominence level, which
returns a narrower *symmetric* width — so there is no asymmetry left to judge.
Measured on the real runs the flag fires 3 times in 893 fitted rows for P3
cell A and once in 468 for the NNM triplicate. What actually protects the fit
is `find_peaks`: a feature cut at or past its centre has its maximum at the
array end, is not a local maximum, and is never detected at all. The flag is
therefore an annotation, not a guard, and should be replaced in 2.0 by an
explicit test on the fitted half-widths.


---

## Analysis: the measurement that replaces `f_wrong_sign`

`analyse.py` ports Modules 5, 6 and 7c — `_flag_reliable_peaks`,
`_coherent_drift_rate`, `_coherent_net_change`, `_discontinuity_events`,
`_auto_pair_peaks` and `_attribution_basis` extracted programmatically, the
orchestration around them rewritten as functions returning data. Two things in
it are new, and both are answers to questions this project has been circling
for a fortnight.

### 1. What the reversed charge actually is

1.8.x had one number, `f_wrong_sign`, and used it as a gate. It conflated three
unrelated things, and no threshold on it transferred — not between the three
cells of one triplicate, not between chemistries. `signal.reversals` already
inventories each backwards run; `analyse` asks where on the curve it sat:

| mechanism | test | what it is |
|---|---|---|
| `plateau` | full current, and \|dQ/dV\| there is ≥5% of this half-cycle's own maximum | a two-phase equilibrium pinning the potential — real, intended charge |
| `cv_hold` | current below the constant-current value, within 50 mV of the window edge | protocol, not chemistry |
| `parasitic` | full current, \|dQ/dV\| small, away from the limit | charge passed with no redox process to account for it |

Every term is measured against the half-cycle **itself** — its own peak
\|dQ/dV\|, its own current, its own capacity. That is the whole reason it
transfers, and it is exactly what the two pooled thresholds could not do.

The plateau test reads the curve, **not a peak list**. That matters twice
over. It is why LTO passes: a peak-proximity test with a 100 mV tolerance calls
almost every voltage "at a peak" on a six-peak P3 half-cycle, and a test on the
peaks' own half-maximum bands calls half of LTO's healthy half-cycles parasitic,
because LTO's two-phase plateau is many times wider than its peak's FWHM. And
it is why the pipeline stays a straight line: integrity does not depend on
detection, so `integrity_report` can return the callable that
`detect.choose_reference_cycle` takes.

**Measured on all six reference cells, 1,384 half-cycles:**

```
  CE band        n      mean parasitic charge      max parasitic fraction
   0-20%        22            5.97 mAh/g                  11.1%
  20-40%        82            1.87                        11.3%
  40-60%       138            0.41                        13.1%
  60-80%       178            0.00                         0.0%
  80-95%       550            0.00                         0.4%
  95-105%      100            0.13                         5.4%
   >105%       288            0.00                         0.0%

  cell     n     clean  suspect  ANOMALOUS  too few    plateau   cv  parasitic
  P3  A   440      254        5          5      176        598  140        172
  P3  B   440      282        4          2      152        175   69         39
  P3  C   440      354        5          4       77        468  137        129
  LTO A    21       21        0          0        0        222    0          0
  LTO B    22       21        0          1        0        216    0          7
  LTO C    21       20        0          1        0        201    0          6
```

Eleven of the thirteen ANOMALOUS half-cycles are P3, and every one of them sits
in a cycle whose coulombic efficiency is between 18% and 52%. Above CE 60%,
nothing anywhere carries more than 0.4% of its capacity backwards. This is not
a correlation dressed as a diagnostic: the quantity *is* the charge that went
in and did not come back, localised to where on the curve it went.

**The two exceptions are worth naming rather than tuning away.** LTO cells B
and C each flag their **cycle 1 charge** — 6.8 and 5.8 mAh/g of ~130, at CE 98%
and 99%. That is formation, and formation is precisely when charge legitimately
goes to irreversible processes. The rule is reporting something true; the
reader has to know it is cycle 1. Lowering or raising the 2% band to make them
disappear would be the third repetition of the mistake this project has already
made twice, so it is not done. `choose_reference_cycle` starts at cycle 2 in any
case, so nothing downstream pays for it.

The `too few records` population is not a judgement either. On P3 cell A it is
176 half-cycles with 5–19 records and 0.00–0.04 mAh/g — the cell is dead and the
record is still running. The 20-record floor sits inside a clean gap: 168
half-cycles have 5–20 records, 257 have more than 200, and six lie in between.

### 2. Attribution is withheld where the split is not determined

`capacity_attribution` now takes the closure intervals and sets the per-peak
**fraction** to NaN wherever the interval is wider than 0.15, recording the
width and an `attribution_withheld` flag. The fitted **areas** are kept — the
fit found them, and withholding a share is not the same as deleting a number.

That 0.15 is the one threshold in 1.9.0's reporting, and it sits inside a
measured gap: LTO 0.00–0.01, P3 0.00–0.09, NMC111 0.35–0.40, the synthetic
`degenerate` case 0.81. Nothing observed lies between 0.09 and 0.35. It is
reported next to every value it suppresses, so it can be argued with. One
caution already visible: on the first thirty cycles of P3 cell A the sampled
widths reached 0.14, which is closer to the line than the earlier 0.09 suggested
— and on P3 cell C they reached 0.46, so attribution is genuinely withheld on
part of that dataset.

### What is verified, and what is not yet

`tests/test_analyse.py` — 28 checks on constructed data: mechanism assignment,
banding against a half-cycle's own capacity, drift measured from the reference
cycle, transient loss versus established failure, electrode-aware pairing,
global assignment resisting a stolen partner, withholding, and the coherence
verdict resting on the median rather than the tails.

`tests/test_analyse_end_to_end.py` — the whole pipeline on P3 cells A and C and
LTO cell A, checking the claims made about those cells during development:

```
  P3  cell C   cycle 2 charge found ANOMALOUS   16.9 mAh/g of 580.9 (2.9%)
               reference cycle moves to 3       "cycle 2 failed the integrity
                                                 check; 3 is the first at or
                                                 above it that passes"
  LTO cell A   plateau 222 mAh/g, parasitic 0.0 — the case that broke every
               previous rule
  all three    no half-cycle banded clean carries any unaccounted charge
               delta-V sign follows the electrode (+82, +76, -48 mV)
```

**Not yet verified:** tracking, ΔV and attribution have no bit-identity
regression, because 1.8.7 shipped no tracking CSV to compare against. The
value-determining functions are extracted rather than retyped, and the
orchestration is unit-tested, but the equivalence gate arrives with the notebook,
when both versions can write their CSVs side by side on the same run.


---

## The presentation layer: ported, not rewritten

The waterfall, the heatmaps, the key-cycle overlays and the split panels are
the best part of the tool, so `plots.py` and `cycling.py` contain 1.8.7's
drawing code, extracted programmatically and unedited.

`plots.py` — fourteen functions from Modules 2, 3, 4, 5 and 6, plus the shared
`_get_display_name`, `_force_integer_cycles`, `_charge_label`,
`_discharge_label` and `_apply_pub_style`.

`cycling.py` — Cells 5 to 13. Those were top-level scripts, not functions, so
the port was mechanical: each cell's statements were wrapped in a function whose
parameters are exactly the globals it read, imports dropped, constants hoisted.
Nothing inside a body was rewritten.

**The adapters go the other way round.** Rewriting fourteen tested plotting
functions against `Dataset`, `HalfCycleSignal`, `Detection` and `Tracking` is
precisely how figures stop being identical. So `as_processed_dqdv`,
`as_detected_peaks`, `as_fit_results`, `as_tracked` and `as_user_parameters`
build the 1.8.7 dictionaries from the 1.9.0 objects. They are the only new code
in the module, and they are tested.

**The one thing that could not be adapted directly.** `plot_fit_quality` asks
its fit for `.best_fit` and `.eval_components(x=...)` — a live lmfit
`ModelResult`, which 1.9.0 deliberately does not keep, because carrying one
would undo the decision that made parallel fitting possible. Rather than edit
the plotting code, `as_fit_results` supplies a `_FitView` answering both from
the new `fitting.evaluate`, which rebuilds the component curves analytically
from the stored parameters through lmfit's own model classes. No refit;
verified against the data to 3e-7. The plotting function is untouched.

### Four defects this port surfaced

Each lived in a code path the notebook never took in this order.

| where | what |
|---|---|
| adapter | `plot_fit_quality` picks its worst-converged half-cycle from a column named `success`; the adapter wrote `fit_success` |
| `fitting.py` | 1.9.0 prefixed its baseline `bkg_`, and `plot_fit_quality` identifies the baseline by testing `'bg_' in name` — the baseline would have been drawn as a filled peak. Prefix is now `bg_` throughout, matching 1.8.7. Renaming it also exposed a live bug: the `peak_total` filter still tested `startswith("bkg")`, which would have folded the baseline into `component_area_sum` and inflated every closure value |
| Cell 9b | `palette` used but never assigned — in the notebook it resolved to whatever an earlier cell had left in globals |
| Cell 12 | `is_anode` read in the >100%-efficiency notice but assigned later in the same loop: undefined on the first dataset, the previous dataset's value on every one after |

The last two are the implicit-shared-state failure this package exists to
remove, and neither could have been found without putting the code in
functions. Both fixes are one line, marked in place with the reasoning.

Two constants are deliberately **not** hoisted: `MARKER_SIZE` is 7 in Cells 7-9
and 6 in Cells 9b, 11 and 12, and `YAXIS_MIN` is 0 in Cell 9 and 40 in Cell 12
(likewise `YAXIS_MAX` and `VISUAL_OUTLIER_THRESHOLD`). Hoisting any of them
would have quietly changed a figure.

### Verified

`tests/test_presentation.py` runs all 24 entry points on two real P3 cells
through the adapters — 13 dQ/dV figures and 11 cycling figures, 43 files — and
checks that `_FitView`'s components sum to its `best_fit` and that the baseline
comes back under the `bg_` prefix. It is what found all four defects above.

What it cannot check is that a pixel has not moved. That is the notebook's
regression: run 1.8.7 and 1.9.0 on the same cell and diff the PNGs.


---

## The defaults bug, and the test that should have existed

The first 1.9.0 run on a real cell produced visibly bad fits. Not a porting
error — a **defaults** error, in the one layer that was written fresh.

1.8.7's Module 4 chose its fitting parameters from the dataset's profile class:

```
  sharp     (LTO, LFP)        centre_tol 30 mV   sigma  3-30 mV   baseline 1
  moderate                    centre_tol 50 mV   sigma 5-100 mV   baseline 3
  broad     (layered oxides)  centre_tol 50 mV   sigma 5-200 mV   baseline 3
```

`FitSpec` defaulted to `baseline_degree=1`, and the notebook used the bare
default. A broad layered-oxide dQ/dV sits on a curved background that a
straight line cannot follow:

```
  P3 cell A, charge      1.8.7      linear     cubic
    cycle 2              0.4924     0.2736     0.5404
    cycle 3              0.7837     0.6929     0.8021
    cycle 4              0.9644     0.9584     0.9690
```

Worth recording what was NOT the cause. 1.8.7 initialises every baseline
coefficient to zero; 1.9.0 called `PolynomialModel.guess`, which least-squares
fits the whole curve *including the peaks* and therefore starts the baseline
threaded through the peak tops. That looked like the obvious culprit and it is
worth nothing at all — measured, the two initialisations converge to the same
answer to four decimal places on every half-cycle tested. The degree was the
whole of it.

The fix is `fitting.spec_for_profile(centres, profile)`, reproducing 1.8.7's
table, and `FitSpec`'s default is now 3.

**The test that should have existed.** `test_detect_fidelity.py` proved 1.9.0
finds the same peaks and nothing proved it then fitted them as well — the gap
the bug walked through. `test_fit_fidelity.py` now compares against the
`r_squared` column of 1.8.7's own `fitted_parameters.csv`:

```
  P3 cell A   21 half-cycles   median R2  1.8.7 0.9861  1.9.0 0.9832
              worst delta -0.0067, best +0.0480, 1.9.0 better on 15/21
  LTO cell A  19 half-cycles   median R2  1.8.7 0.9965  1.9.0 0.9971
              worst delta +0.0004, 1.9.0 better on 19/19
```

1.9.0 is slightly better, and that is expected rather than reassuring: 1.8.7
couples each shoulder's sigma to its parent primary's, which costs a little R2
and buys protection against a shoulder inflating and stealing its parent's
area. **1.9.0 has not ported that coupling.** R2 will not show its absence —
area retention and the primary/shoulder swap will. It is the next thing to
port, before the six-cell regression.


---

## Two versions, and how they stay the same

`Ratatosk 1.9.0 inline.ipynb` is the whole pipeline in one notebook — 27 cells,
no imports beyond the scientific stack. It exists because a package you cannot
walk someone through is a package that cannot be handed over, and this code is
going to a research software engineering team.

**It is generated from the package, not maintained beside it.** A script reads
the module sources, strips the package-relative imports and the `__all__`
blocks, splits `plots` and `cycling` at function boundaries into cells of a
size a reader can hold, and emits the notebook. Nothing is retyped, so the two
cannot drift apart by transcription. Verified on P3 cell A with matched
settings: **13 of 13 CSVs identical, 31 of 31 PNGs byte-identical.**

Flattening is safe because the modules share no names — checked
programmatically before doing it, and it came back zero collisions across all
nine.

Two things the flat namespace needed rewriting rather than copying:
`plots._ft.evaluate` becomes `evaluate`, and `run.default_flags()` scans
`globals()` for ALL-CAPS constants instead of asking each module for its own.
The second is actually closer to 1.8.7 — and better than it, because 1.8.7 read
a *hardcoded list* of names and noted in its own docstring that a flag defined
in Module 4 could not be seen from Cell 3b. Taking everything means the manifest
cannot fall behind the code.

### What the comparison caught

The first inline-versus-package diff came back with every fitted parameter
different, which looked like a flattening bug and was not. The package test
script had been generated before `spec_for_profile` existed and was still
building a bare `FitSpec`, so it fitted with `sigma_min` 3 mV where the inline
used 5. Chasing that down surfaced a real error in `PROFILE_SPECS`: I had
`centre_tol` at 50 mV for the moderate and broad profiles where 1.8.7's
`FIT_CENTRE_TOLERANCE_MV` is **70**. Now read off the source rather than
recalled, and noted in the code as such.

Fit fidelity after the correction:

```
  P3 cell A   21 half-cycles   median R2  1.8.7 0.9861  1.9.0 0.9832
                               worst -0.0067, best +0.0495, better on 15/21
  LTO cell A  19 half-cycles   median R2  1.8.7 0.9965  1.9.0 0.9971
                               worst +0.0004, better on 19/19
```


---

## The missed peak, and the two deeper problems behind it

Reported from a run: cycle 10 discharge on P3 cell A fitted two components where
the eye sees four. Measuring it found three separate faults.

### 1. One dominant peak sets the detection floor for the whole half-cycle

A peak's prominence has to clear 5% of the half-cycle's **full range**. On cycle
10 discharge the 3.539 V two-phase feature is 2075 mAh/V/g, so the floor is 104,
and the 3.156 V feature — prominence 44.5, a peak this cell tracks for a hundred
cycles — is invisible. The same cycle's CHARGE has a range of 383, a floor of
19, and finds all four of its peaks. One half-cycle and not the other, for no
reason to do with the chemistry.

**1.8.7 has the same bug, and it flickers**: it found 3.148 V on cycle 9 and
3.151 V on cycle 11 and missed it on cycle 10. A feature appearing and
disappearing between consecutive cycles is exactly what corrupts tracking.

**The fix** (`LOCAL_PROMINENCE`, on by default): a peak is also kept if it is a
distinct feature *on its own scale* — prominence at least 25% of its own height,
and height at least 2% of the largest. Both are ratios, so neither can be
dominated by an unrelated feature elsewhere in the window. Cycle 10 discharge
now finds 3.156, 3.231, 3.539 and 3.563.

Cost: 1.1× on fitting time. Across 60 cycles of P3 cell A it lifts the 3.2 V
discharge band from 74 sightings to 81 and tightens peaks-per-cycle from 2–5 to
3–5. It also adds a persistent 2.27–2.37 V charge feature seen in 37 of 60
cycles, drifting ~3 mV/cycle — the same rate as the accepted peaks, so it is
left in for the coherence audit to judge rather than excluded by fiat.

**The fidelity test was measuring the wrong thing.** It compared detected
centres to 4 decimal places, so the rescue's eleven 3–9 mV centre shifts
(3.148 → 3.1515) read as losses. A detected centre is a local maximum on a
smoothed curve and the fit's centre tolerance is 70 mV; the test now separates
"same feature, centre moved" from "genuinely absent". One genuine absence
remains, on a half-cycle whose curve changed under the stable sort.

### 2. Two components converge on the same peak, and one collapses

With the rescue on, cycle 10 discharge fits **two components at 3.538 V**, one
of which ends with zero area. The 3.563 V seed slid 25 mV onto its neighbour —
well inside the 70 mV tolerance — and the optimiser gave it nothing.

The `area_collapsed` guard flags it, so it is not silently wrong, but a seed
that lands on top of another seed is wasted and the pair is not identifiable.
**Not yet fixed.**

### 3. The sharp peak is narrower than the model is allowed to be

This is the visible under-shoot, and it predates everything above. The 3.538 V
component sits with **sigma pinned at the 5 mV floor** and still only reaches a
height of 1530 against a data peak of 2075.

The profile class is decided **per dataset**, and P3 classifies as broad, so its
sigma floor is 5 mV. But sharpness is a property of a **half-cycle**, not of a
dataset: P3's discharge carries one genuinely LTO-like two-phase peak alongside
several broad ones, in the same curve.

The fix is to derive each component's sigma floor from **that peak's own measured
width** — detection already computes `width_V`, the FWHM at half maximum — rather
than from one number for the whole dataset. **Not yet implemented.**


---

## Two tests, because the curve cannot vouch for the total

The mechanism classification reads the CURVE: where on it did the reversed
charge sit — a plateau, a voltage hold, or nothing that accounts for it. That
is a good test and it caught real faults. It also got P3 cell A badly wrong.

The first `START_HERE` report said, reassuringly, that 598 mAh/g of reversed
charge sat on a two-phase plateau and was "a first-order phase transition
holding the potential, not a fault". Measured against the theoretical capacity:

```
  cycle  step      capacity   x theoretical   plateau   parasitic
      1  Charge         681            4.3        149        75.8
     69  Charge         407            2.5         65        38.6
     19  Charge         342            2.1         88        11.6
     13  Charge         294            1.8         54         1.5
     26  Charge         246            1.5         53         4.3
```

**94% of that "plateau" charge is on nine half-cycles delivering 1.3 to 4.3
times the theoretical capacity.** Cycle 1 charge alone puts in 681 mAh/g
against a theoretical 160. On the half-cycles that are physically possible the
plateau charge is **38 mAh/g, not 598**.

Charge above the theoretical capacity is not a phase transition and not a
measurement artefact. It is charge going somewhere other than the material,
and in practice it means something has broken. A dQ/dV shape cannot vouch for
it, because the shape says where the charge went on the voltage axis and says
nothing about how much of it there was.

So `half_cycle_integrity` now applies **two independent tests**, and either can
condemn a half-cycle:

| test | reads | catches |
|---|---|---|
| the curve | where the reversed charge sat | charge with no redox process to account for it |
| the total | capacity against `theoretical_capacity_mAh_g` | more charge than the material can hold, whatever the curve looks like |

`OVER_THEORETICAL_FRACTION = 1.2` rather than 1.0: the first cycle legitimately
exceeds the reversible capacity through SEI formation, and the theoretical
figure is a nominal number for the composition.

On P3 cell A this moves four half-cycles from `suspect` to `ANOMALOUS` and
changes what the report says about the other 559 mAh/g: it is now excluded from
the plateau total and named as what it is.

This is why `theoretical_capacity_mAh_g` is one of the two parameters
`params.parameters_from_dict` refuses to invent. Without it this test cannot
run, and the report says so rather than quietly falling back to the curve alone.


---

## Two bugs in the interactive path, and how they got there

Both were mine, both were introduced by patching a file with string
replacement rather than rebuilding the function, and one of them made the
parameters cell silently useless.

### The loop that ate itself

Adding a headless `input` shadow to `collect_parameters`, I spliced

```python
    if headless:
        def input(prompt=""):
            ...
```

at four-space indent **into the middle of the for-loop** — right after the
electrode-diameter prompt. Four spaces terminates the loop body. So the loop
asked composition, cell id, blend, mass, theoretical capacity and diameter, and
then **started the next dataset**, skipping electrode type, C-rate, key cycles,
separator, electrolyte, palette and the confirmation. Everything after the
splice, including `user_parameters[name] = sample_parameters`, became
unreachable code — so the cell returned an EMPTY parameter set and every cell
downstream ran on nothing.

The symptom the user saw was the loop jumping from "Electrode punch diameter"
straight back to "--- Material ---".

A second, related fault in the same function: defining `input` inside
`if headless:` makes the name local to the whole function, so on the
interactive path every one of the eighteen raw `input()` calls raised
`UnboundLocalError` before reaching a person. It is now bound
unconditionally and branches inside.

**The fix was to rebuild the function from the 1.8.6 source rather than patch
it, with a structural assertion in the build:**

```python
loops = [n for n in fn.body if isinstance(n, ast.For)]
d = ast.dump(loops[0])
assert "Are these parameters correct" in d      # the confirmation
assert "sample_parameters" in d                 # the assignment
```

A prompt that falls out of the loop is now a build error, not a run that looks
plausible and returns nothing.

### The guard that was always false

`meta = cycler_metadata.get(name, {}) if 'cycler_metadata' in globals() else {}`

1.8.6 wrote that because Cell 2 might not have run. In a function
`cycler_metadata` is a PARAMETER, so `globals()` never holds it, the guard is
always false, and every metadata default silently vanishes. The visible effect
is a prompt reading `Mass of active material (mg):` with no `[from file: 4.72]`
— and because that prompt sits in a `while True` that rejects a blank answer,
it loops forever.

This one was found, fixed, lost again when the function was rebuilt from
source, and fixed again. It is now marked in place.

## Choosing the files

Loading was `sorted(glob.glob(...))` — every match, no question asked. A folder
of eight files here is three chemistries, and loading all of them puts an LTO
anode and an NMC cathode on the same axes.

`params.choose_files` lists what is there, grouped by the chemistry token in
each filename, and takes numbers, ranges (`1-3`), `all`, or blank for all.
Setting `FILES` explicitly skips the question.

`_suggest_cell_id` also matched only `_A_`, so a hyphenated name like
`JQ-P3-NaNiMnO2-35%-2-4.2V-0.1C-A-20062025` fell through to the numeric branch
and suggested **"3"** — the varying digit of "35%" — for a cell called A. It
now accepts either delimiter and prefers a letter over a digit.

---

## The port, and the one thing it changes

`io.py` and `signal.py` are ported, not rewritten: the six functions that
determine an output value — `classify_dqdv_profile`, `auto_preprocess_params`,
`remove_spikes`, `smooth_dqdv`, `rebin_dqdv`, `strip_cv_hold` — were extracted
from 1.8.7 programmatically rather than retyped. Only the orchestration around
them is new.

```
  LTO cell A     21 of  21 half-cycles identical to 1.8.7
  P3  cell A    306 of 376 identical; 70 differ, all 70 containing tied voltages
```

**The 70 are a fix, and the only knowing difference in 1.9.0.** 1.8.7 sorts by
voltage with pandas' default quicksort, which is not stable, so among records
sharing a voltage the order is decided by the sort's internals rather than by
the data. That is not a rare corner: P3 cell A cycle 1 charge has 483 tied
voltages out of 1434, because the cycler records to 0.1 mV and the cell sits
on a plateau. Despiking and smoothing then run over that arbitrary order —
so **1.8.7's smoothed curve is not a well-defined function of its input**.
Reorder the rows and it changes.

`signal.py` sorts with `kind="mergesort"`, which is stable and therefore
breaks ties by acquisition order — the order the measurements were taken in.
The result is reproducible under any reordering of the input. Median effect
0.24% of a half-cycle's peak value; the 94.5% worst case is inside the +/-4830
quantisation comb of an anomalous cycle that 1.9.0 declines to fit anyway.

LTO shows no difference at all because it is rebinned at 2 mV, which collapses
the ties before anything smooths them — which is a further argument for keying
rebinning to record spacing rather than to profile class, since P3 has 2.4%
duplicate steps and gets no rebinning at all.

### Two other things the port had to get right

**The voltage trim is global to the dataset, not per half-cycle.** 1.8.7 takes
the min and max over the whole cleaned frame and trims 50 mV from each end,
then clips every half-cycle to that one window. Computing it per half-cycle —
the obvious-looking thing — silently removes real data from every one.

**The direction of a half-cycle is measured, never read from its label.** For a
negative electrode the labels are swapped, so an LTO dataset's "Charge" is the
half-cycle where the voltage falls. `Dataset.step_direction()` reads the
recorded voltage. That is the structural fix for a bug that reported all 64 LTO
half-cycles as anomalous at 98-99% coulombic efficiency.
