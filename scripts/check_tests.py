"""Run functional checks and report memory without requiring a recent kernel."""
import resource
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
print(f'PROCESS_PEAK_RSS_KIB={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}', flush=True)
for name in ('memory.current', 'memory.peak', 'memory.events', 'memory.max', 'memory.swap.max'):
    path = Path('/sys/fs/cgroup') / name
    if path.exists():
        print(f'{name}: {path.read_text().strip()}', flush=True)
raise SystemExit(not result.wasSuccessful())
