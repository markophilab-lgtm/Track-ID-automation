"""Run every test_*.py file in this directory."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

failures = 0
total = 0

for test_file in sorted(HERE.glob("test_*.py")):
    name = test_file.stem
    spec = importlib.util.spec_from_file_location(name, test_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tests = [getattr(mod, n) for n in dir(mod) if n.startswith("test_") and callable(getattr(mod, n))]
    print(f"\n{name}:")
    for t in tests:
        total += 1
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")

print(f"\n{total - failures}/{total} passed.")
sys.exit(0 if failures == 0 else 1)
