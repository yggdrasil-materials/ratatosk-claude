"""
Ratatosk — GCPL electrochemical analysis.

Structure, and the reason for it
--------------------------------
The 1.8.x pipeline was 69 notebook cells sharing implicit global state. That
made three things impossible: unit testing, safe parallelism, and editing a
module without pasting 700 lines. This package fixes all three by making every
stage a function that takes data and returns data.

    io          read a cycler export; provenance
    signal      Q, V, I, t  ->  a dQ/dV curve, and whether it is trustworthy
    detect      find features; choose the reference cycle
    fitting     build the model; run it, in parallel where that pays
    quality     does the answer mean anything?   <- new in 1.9.0
    analyse     track, attribute, classify mechanism
    plots       the presentation layer (waterfall, heatmap, key cycles)
    cycling     capacity, retention, fade, energy/power, voltage, rate
    synthetic   data with a known right answer, for testing the above
    run         run folders, the manifest, provenance

Data flows one way: io -> signal -> detect -> fitting -> analyse -> plots.
`quality` is consulted by all of them and depends on none.

The notebook becomes a short orchestration layer that calls this package.
"""

# VERSIONING. The fourth digit is the BUILD COUNTER and it just counts up —
# 1.9.0.9 is followed by 1.9.0.10, then 1.9.0.11. It does not roll over into
# the third digit at 9; only a deliberate decision about the release itself
# moves 1.9.0 to 1.9.1. This build was numbered 1.9.1.0 in error where it
# should have been 1.9.0.10, so the next one is 1.9.0.11. Run folders are
# named <timestamp>_v<version>, timestamp first, so the chronological order of
# a run archive is unaffected by the blip.
__version__ = "1.9.0.75"

# Deliberately no eager imports of the heavy modules — the notebook imports
# what it needs, and a missing optional dependency should not break `import
# ratatosk`.
