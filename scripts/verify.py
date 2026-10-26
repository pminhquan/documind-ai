"""Fast local verification: lint + full test suite.

Usage:
    python scripts/verify.py

Exits nonzero on the first failing stage. This is the pre-commit /
pre-push gate; CI runs the same checks.
"""

import subprocess
import sys

STEPS = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]),
    ("frontend-gate", [sys.executable, "scripts/check_browser_js.py"]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
]


def main() -> int:
    for name, command in STEPS:
        print(f"==> {name}")
        result = subprocess.run(command)
        if result.returncode != 0:
            print(f"FAILED: {name}", file=sys.stderr)
            return result.returncode
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
