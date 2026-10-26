"""Browser-script regression gate for the web frontend.

``node --check`` only proves syntax. Classic browser scripts can also die
at load time on runtime errors (e.g. a top-level ``ReferenceError`` from a
misplaced ``return``/block), which silently breaks the entire UI. This
gate EXECUTES ``static/app.js`` in Node with minimal DOM stubs so any
top-level runtime error fails loudly.

Usage:
    python scripts/check_browser_js.py [path-to-app.js]

Exits nonzero when Node is unavailable (CI must install it) or when the
script fails to parse/execute.
"""

import subprocess
import sys
from pathlib import Path

# Minimal DOM stubs: every element lookup returns a permissive proxy so
# top-level wiring code runs; only REAL runtime errors (ReferenceError,
# SyntaxError, TypeError from app logic) fail the gate.
NODE_PRELUDE = r"""
function makeElement() {
  const target = {
    addEventListener() {}, removeEventListener() {},
    appendChild() { return makeElement(); }, remove() {},
    querySelector() { return makeElement(); },
    querySelectorAll() { return []; },
    classList: { add() {}, remove() {}, toggle() {},
               contains() { return false; } },
    dataset: {}, style: {},
    setAttribute() {}, getAttribute() { return null; },
    textContent: "", value: "", innerHTML: "",
    click() {}, focus() {}, disabled: false, files: [],
  };
  return new Proxy(target, {
    get(obj, key) {
      if (key in obj) return obj[key];
      return makeElement();
    },
    set(obj, key, value) { obj[key] = value; return true; },
  });
}
globalThis.document = {
  getElementById: () => makeElement(),
  createElement: () => makeElement(),
  querySelector: () => makeElement(),
  querySelectorAll: () => [],
  addEventListener() {},
  body: makeElement(),
};
globalThis.window = { addEventListener() {}, location: { href: "" } };
globalThis.URL = { createObjectURL: () => "stub:", revokeObjectURL() {} };
globalThis.fetch = () => Promise.resolve({
  ok: true, json: async () => ({}), blob: async () => ({}),
  headers: { get() { return null; } },
});
globalThis.FormData = class {};
globalThis.Blob = class {};
"""

RUNNER = r"""
const fs = require("fs");
const vm = require("vm");
const stubs = fs.readFileSync(process.argv[2], "utf8");
const app = fs.readFileSync(process.argv[3], "utf8");
try {
  vm.runInThisContext(stubs + "\n;\n" + app, { filename: "app.js" });
  console.log("app.js executed without top-level errors");
} catch (error) {
  console.error("FRONTEND RUNTIME ERROR:", error.message);
  process.exit(1);
}
"""


def check(app_js: Path) -> tuple[bool, str]:
    """Parse + execute app.js under Node; returns (ok, output)."""
    harness = Path(app_js).parent / "_browser_gate_runner.js"
    stub_file = Path(app_js).parent / "_browser_gate_stubs.js"
    try:
        stub_file.write_text(NODE_PRELUDE, encoding="utf-8")
        harness.write_text(RUNNER, encoding="utf-8")
        result = subprocess.run(
            ["node", str(harness), str(stub_file), str(app_js)],
            capture_output=True, text=True,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    finally:
        harness.unlink(missing_ok=True)
        stub_file.unlink(missing_ok=True)


def main() -> int:
    app_js = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path("src/documind/web/static/app.js")
    if not app_js.exists():
        print(f"missing {app_js}", file=sys.stderr)
        return 2
    ok, output = check(app_js)
    print(output)
    if not ok:
        print("FAILED: frontend script has load-time errors", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
