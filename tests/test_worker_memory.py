"""
Ratatosk 1.9.0.43 — worker-pool sizing. Run: python tests/test_worker_memory.py

Cell 9 killed the kernel twice on a machine that was at 80% RAM before the run
started. The fits were not at fault: `plan_workers` sized the pool from a TIME
estimate alone, spending `cpu_count - 1` fresh interpreters at ~180 MB each on
a machine with nothing to spare.

These tests pin the behaviour that fixes it. They monkey-patch the two
measurements — free memory and the cost of a worker — so that the arithmetic
can be checked on a machine of any size, including this one.
"""
import sys, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, __file__.rsplit("/tests/", 1)[0])

from ratatosk import synthetic as S, fitting as F

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


class fake_machine:
    """Pretend to be a machine with `free_gb` free and `worker_mb` workers.

    Also neutralises the TIME gate. These tests are about memory sizing, and
    `plan_workers` quite correctly refuses a pool for a job it can finish
    serially inside PARALLEL_MIN_SECONDS — which since 1.9.0.44 the fixture
    below can, because `fitting.FIT_TOLERANCE` made the fits about ten times
    faster. Leaving the time gate live made these tests measure the speed of
    the machine running them rather than the sizing logic they exist for.
    """

    def __init__(self, free_gb=None, worker_mb=None):
        self.free_gb, self.worker_mb = free_gb, worker_mb

    def __enter__(self):
        self._a, self._c = F._available_memory_mb, F.measure_worker_cost_mb
        self._cached = F._WORKER_RSS_MB
        self._floor = F.PARALLEL_MIN_SECONDS
        F.PARALLEL_MIN_SECONDS = 0.0
        F._available_memory_mb = lambda: (None if self.free_gb is None
                                          else self.free_gb * 1024.0)
        F.measure_worker_cost_mb = lambda **k: self.worker_mb
        return self

    def __exit__(self, *a):
        F._available_memory_mb, F.measure_worker_cost_mb = self._a, self._c
        F._WORKER_RSS_MB = self._cached
        F.PARALLEL_MIN_SECONDS = self._floor
        return False


def _long_jobs(n=400):
    """Enough jobs that the TIME test always votes for a pool."""
    h = S.make_case("solid_solution", seed=7)
    spec = F.FitSpec([h.voltage.mean()], baseline_degree=2,
                     sigma_min=0.005, sigma_max=0.2)
    return [(h.voltage, h.dqdv, spec, i) for i in range(n)]


# ---------------------------------------------------------------------------


def test_budget_arithmetic():
    print("\n1. The memory budget is arithmetic anyone can check")
    with fake_machine(free_gb=8.0, worker_mb=200.0):
        n, why = F.memory_budget_workers()
        # 8 GB free * 0.5 headroom = 4096 MB;  200 * 1.25 = 250 MB/worker
        check("8 GB free, 200 MB workers -> 16", n == 16, why)
    with fake_machine(free_gb=1.0, worker_mb=200.0):
        n, why = F.memory_budget_workers()
        # 1024 * 0.5 = 512 MB; 512 // 250 = 2
        check("1 GB free -> 2", n == 2, why)
    with fake_machine(free_gb=0.3, worker_mb=200.0):
        n, why = F.memory_budget_workers()
        check("300 MB free -> none affordable", n == 0, why)


def test_the_measurement_is_reported_honestly():
    print("\n2. The reason line says which number was used")
    with fake_machine(free_gb=8.0, worker_mb=200.0):
        _, why = F.memory_budget_workers()
        check("a measured cost says measured", "measured 200 MB" in why, why)
    with fake_machine(free_gb=8.0, worker_mb=None):
        _, why = F.memory_budget_workers()
        check("an unmeasurable cost says assumed", "assumed" in why, why)
        check("and uses the assumed constant",
              f"{F.WORKER_RSS_ASSUMED_MB:.0f} MB" in why, why)
    with fake_machine(free_gb=None, worker_mb=200.0):
        n, why = F.memory_budget_workers()
        check("unreadable memory is None, not unlimited", n is None, why)


def test_plan_workers_respects_memory():
    print("\n3. plan_workers is bound by memory, cores and the ceiling")
    jobs = _long_jobs()

    with fake_machine(free_gb=64.0, worker_mb=200.0):
        w, _, est = F.plan_workers(jobs, n_jobs=64, verbose=False)
        check("plenty of memory -> held at the ceiling",
              w == F.PARALLEL_MAX_WORKERS,
              f"{w} workers, estimate {est:.0f}s")

    with fake_machine(free_gb=1.5, worker_mb=200.0):
        w, _, _ = F.plan_workers(jobs, n_jobs=64, verbose=False)
        # 1536 * 0.5 = 768 MB;  768 // 250 = 3
        check("1.5 GB free -> 3 workers, not the ceiling", w == 3, f"{w}")

    with fake_machine(free_gb=0.2, worker_mb=200.0):
        w, _, _ = F.plan_workers(jobs, n_jobs=64, verbose=False)
        check("no room for one worker -> serial, not a crash", w == 1, f"{w}")

    with fake_machine(free_gb=64.0, worker_mb=200.0):
        w, _, _ = F.plan_workers(jobs, n_jobs=2, verbose=False)
        check("an explicit small n_jobs is still honoured", w == 2, f"{w}")

    with fake_machine(free_gb=None, worker_mb=None):
        w, _, _ = F.plan_workers(jobs, n_jobs=64, verbose=False)
        check("no psutil -> ceiling still applies",
              w == F.PARALLEL_MAX_WORKERS, f"{w}")


def test_release_never_creates_a_pool():
    print("\n4. Releasing workers never starts any")
    import psutil, os
    me = psutil.Process()

    def kids():
        out = 0
        for c in me.children(recursive=True):
            try:
                out += 1 if c.is_running() else 0
            except Exception:
                pass
        return out

    before = kids()
    got = F.release_workers()
    check("no pool -> returns False and spawns nothing",
          got is False and kids() <= before,
          f"{before} children before, {kids()} after")

    # A real pool, then a real release.
    from joblib import Parallel, delayed
    Parallel(n_jobs=2)(delayed(abs)(i) for i in range(4))
    during = kids()
    check("joblib leaves its workers running after Parallel returns",
          during > before, f"{during} children")
    got = F.release_workers()
    after = kids()
    check("release_workers shuts them down", got is True and after < during,
          f"{during} -> {after} children")
    # 1.9.0.45: an executor that has ALREADY been shut down is not something
    # this released. loky leaves the object in place, so the old `is None`
    # check said True every time and claimed memory it had freed once.
    check("...and says False when there was nothing left to release",
          F.release_workers() is False, "no double claim")


def test_probe_measures_something_plausible():
    print("\n5. The probe measures this machine, not a constant")
    F._WORKER_RSS_MB = None
    mb = F.measure_worker_cost_mb()
    F.release_workers()
    if mb is None:
        check("probe unavailable is survivable", True, "fell back to assumed")
    else:
        check("a worker costs between 50 MB and 2 GB", 50.0 < mb < 2048.0,
              f"{mb:.0f} MB measured")
        check("the second call is cached, not re-measured",
              F.measure_worker_cost_mb() == mb, "one probe per session")


for t in (test_budget_arithmetic, test_the_measurement_is_reported_honestly,
          test_plan_workers_respects_memory, test_release_never_creates_a_pool,
          test_probe_measures_something_plausible):
    t()

print("\n" + ("ALL PASS" if not FAILURES else f"FAILED: {FAILURES}"))
sys.exit(1 if FAILURES else 0)
