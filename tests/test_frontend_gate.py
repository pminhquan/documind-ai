"""Frontend regression gate: app.js must parse AND execute at load time.

Catches the class of defect where a classic browser script dies at load
(e.g. a misplaced top-level ``return``), which pure syntax checks can
miss when the error is a runtime ReferenceError instead.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

APP_JS = Path(__file__).parent.parent / "src" / "documind" / "web" / "static" / "app.js"
GATE = Path(__file__).parent.parent / "scripts" / "check_browser_js.py"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed")


def test_app_js_parses_and_executes_at_load_time():
    result = subprocess.run(
        [sys.executable, str(GATE), str(APP_JS)], capture_output=True, text=True)
    assert result.returncode == 0, f"frontend gate failed:\n{result.stdout}\n{result.stderr}"


def test_gate_rejects_top_level_return():
    """The gate must fail on a stray top-level return (the Stage 0 defect)."""
    import sys as _sys

    original = APP_JS.read_text(encoding="utf-8")
    try:
        APP_JS.write_text(original + "\nreturn; // simulated defect",
                          encoding="utf-8")
        result = subprocess.run(
            [_sys.executable, str(GATE), str(APP_JS)],
            capture_output=True, text=True)
        assert result.returncode != 0
        assert "Illegal return" in (result.stdout + result.stderr)
    finally:
        APP_JS.write_text(original, encoding="utf-8")


