"""Run unit tests and produce stdlib line-coverage reports without extra packages."""

from pathlib import Path
import sys
import trace
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    return unittest.TextTestRunner(verbosity=1).run(suite)


if __name__ == "__main__":
    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.base_prefix])
    result = tracer.runfunc(run)
    coverage = tracer.results()
    coverage.counts = {key: count for key, count in coverage.counts.items()
                       if any(Path(key[0]).is_relative_to(ROOT / package) for package in ("war_research", "war_writer", "war_reviewer"))}
    coverage.write_results(show_missing=True, summary=True, coverdir=str(ROOT / "output" / "coverage"))
    raise SystemExit(0 if result.wasSuccessful() else 1)
