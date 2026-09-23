"""Where the data is must not be one machine's drive letter.

1.9.0.73 and earlier hard-coded `G:\\My Drive\\...` in Cell 2. The notebook ran
on exactly one computer and raised NotADirectoryError on every other, which
for a tool being handed to somebody else is a defect, not an inconvenience.
"""
import os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ratatosk.params import (find_data_dir, validate_run_settings,
                             DATA_DIR_ENV)

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}   {detail}")
    if not cond:
        fails.append(name)


print("=" * 70)
print("FINDING THE DATA FOLDER")
print("=" * 70)

_saved = os.environ.pop(DATA_DIR_ENV, None)
tmp = tempfile.mkdtemp()
try:
    # --- the environment variable wins, and wins first ------------------
    withdata = os.path.join(tmp, "withdata")
    os.makedirs(withdata)
    open(os.path.join(withdata, "cell_A.xlsx"), "w").close()
    os.environ[DATA_DIR_ENV] = withdata
    got = find_data_dir(verbose=False)
    check("$" + DATA_DIR_ENV + " is honoured", got == withdata, got)

    # --- a folder with no matching file is NOT the data folder ----------
    nodata = os.path.join(tmp, "nodata")
    os.makedirs(nodata)
    open(os.path.join(nodata, "notes.txt"), "w").close()
    os.environ[DATA_DIR_ENV] = nodata
    got = find_data_dir(verbose=False)
    check("an empty folder is refused", got == "", repr(got))
    check("...and remembered as a fallback to report",
          nodata in (find_data_dir.empty or []))

    # --- `extra` is searched after the env var, before the guesses ------
    os.environ.pop(DATA_DIR_ENV, None)
    got = find_data_dir(extra=[nodata, withdata], verbose=False)
    check("`extra` is searched in order", got == withdata, got)

    # --- a missing env var does not crash -------------------------------
    got = find_data_dir(extra=[os.path.join(tmp, "nope")], verbose=False)
    check("a missing folder is skipped, not raised",
          isinstance(got, str))

    # --- the pattern is honoured ----------------------------------------
    # A suffix nothing on any machine will have, so the guessed roots cannot
    # rescue the search and only `extra` is in play.
    got = find_data_dir(pattern="*.nomatchxyz", extra=[withdata],
                        verbose=False)
    check("pattern is honoured", got == "", repr(got))

    # --- a NAMED folder beats a stray spreadsheet in a bare root --------
    # Root-major search order tried `G:\My Drive` itself before
    # `~/Documents/Example Battery Data`, so one unrelated .xlsx at the top
    # of a cloud drive would win. The sweep is leaf-major for that reason.
    named = os.path.join(tmp, "root", "Example Battery Data")
    os.makedirs(named)
    open(os.path.join(named, "cell_A.xlsx"), "w").close()
    stray = os.path.join(tmp, "root")
    open(os.path.join(stray, "budget.xlsx"), "w").close()
    import ratatosk.params as _pm
    _real = _pm._candidate_roots
    _pm._candidate_roots = lambda: [stray]
    try:
        got = find_data_dir(verbose=False)
        check("a named folder beats a stray file in the root",
              got == named, got)
    finally:
        _pm._candidate_roots = _real

    # --- searched list is populated for the error message ---------------
    check("`searched` records what was tried",
          len(find_data_dir.searched or []) > 0,
          f"{len(find_data_dir.searched or [])} location(s)")

    print()
    print("=" * 70)
    print("THE ERROR WHEN NOTHING IS FOUND")
    print("=" * 70)
    # An empty DATA_DIR must NOT say "you forgot to set it" — Cell 2 leaves
    # it blank on purpose. It must name the environment variable.
    find_data_dir(extra=[nodata], verbose=False)
    try:
        validate_run_settings(
            data_dir="", output_base=tmp, files=[], pattern="*.xlsx",
            parameter_mode="ask", parameters={}, max_cycle=None,
            dqdv_computation="histogram", dqdv_bin_mV=None,
            closure_sample=10, run_peak_fitting=True, verbose=False)
        check("an empty DATA_DIR is refused", False, "no exception raised")
    except ValueError as e:
        msg = str(e)
        check("an empty DATA_DIR is refused", True)
        check("the error names the environment variable",
              DATA_DIR_ENV in msg)
        check("the error lists what was searched",
              nodata in msg or "searched" in msg)
        check("the error does not just say 'set it'",
              "no data folder was found" in msg)

    # A DATA_DIR that was typed and is wrong still gets the old error, plus
    # the way out.
    try:
        validate_run_settings(
            data_dir=os.path.join(tmp, "definitely-not-here"),
            output_base=tmp, files=[], pattern="*.xlsx",
            parameter_mode="ask", parameters={}, max_cycle=None,
            dqdv_computation="histogram", dqdv_bin_mV=None,
            closure_sample=10, run_peak_fitting=True, verbose=False)
        check("a wrong DATA_DIR is refused", False, "no exception raised")
    except NotADirectoryError as e:
        check("a wrong DATA_DIR is refused", True)
        check("...and that error offers the env var too",
              DATA_DIR_ENV in str(e))

    # A GOOD run of the real thing: settings validate when the folder is real
    got = validate_run_settings(
        data_dir=withdata, output_base=tmp, files=[], pattern="*.xlsx",
        parameter_mode="ask", parameters={}, max_cycle=None,
        dqdv_computation="histogram", dqdv_bin_mV=None,
        closure_sample=10, run_peak_fitting=True, verbose=False)
    check("a real folder validates", got["data_dir"] == withdata)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    os.environ.pop(DATA_DIR_ENV, None)
    if _saved is not None:
        os.environ[DATA_DIR_ENV] = _saved

print()
print("ALL PASS" if not fails else f"{len(fails)} FAILURE(S): {fails}")
sys.exit(1 if fails else 0)
