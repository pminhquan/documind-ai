"""Frontend regression gate: app.js must parse AND execute at load time.

Catches the class of defect where a classic browser script dies at load
(e.g. a misplaced top-level ``return``), which pure syntax checks can
miss when the error is a runtime ReferenceError instead.

Also runs behavioral assertions against the export payload builder in
Node (``buildExportPayload``/``pickCorrections``): the load-time gate
cannot see wrong-shape payloads, which is how the invoice-csv/xlsx and
table-correction export defects shipped.
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

APP_JS = Path(__file__).parent.parent / "src" / "documind" / "web" / "static" / "app.js"
GATE = Path(__file__).parent.parent / "scripts" / "check_browser_js.py"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed")

# Reuse the gate's DOM stubs so both entry points share one prelude.
_gate_spec = importlib.util.spec_from_file_location("check_browser_js", GATE)
_gate_module = importlib.util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(_gate_module)
NODE_PRELUDE = _gate_module.NODE_PRELUDE

BEHAVIORAL_RUNNER = r"""
const fs = require("fs");
const vm = require("vm");
const stubs = fs.readFileSync(process.argv[2], "utf8");
const app = fs.readFileSync(process.argv[3], "utf8");
const expose = `
;globalThis.__documindTest = {
  buildExportPayload,
  pickCorrections,
  setMachine: (machine) => { state.machine = machine; },
  setActiveDoc: (key) => { state.activeDocKey = key; },
  recordCorrection,
};
`;
vm.runInThisContext(stubs + "\n;\n" + app + expose, { filename: "app.js" });
const t = globalThis.__documindTest;
function assertEq(actual, expected, label) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) {
    console.error(`FAIL: ${label}\n  expected: ${e}\n  actual:   ${a}`);
    process.exit(1);
  }
}

t.setActiveDoc("scan.png#0");
t.setMachine({
  ocr: { items: [{ text: "TOTAL 9.57" }] },
  // Realistic InvoiceResponse shape: the server reads data.machine_output.invoice
  invoice: { source: "scan.png", provenance: {},
             invoice: { supplier: "MINIMART", total: "9.57", line_items: [] } },
  tables: { tables: [{ table_id: "table_0", rows: 2, columns: 2, cells: [] }] },
});

t.recordCorrection("invoice.total", "10.00");
const invoiceData = {
  machine_output: { source: "scan.png", provenance: {},
                    invoice: { supplier: "MINIMART", total: "9.57", line_items: [] } },
  user_corrections: { total: "10.00" },
};

// invoice-json keeps the invoice payload; corrections lose the prefix.
assertEq(t.buildExportPayload("invoice-json"), {
  kind: "invoice-json", data: invoiceData, filename: "invoice-result.json",
}, "invoice-json payload");

// Regression: invoice-csv / invoice-xlsx must carry the INVOICE payload,
// not the tables fallthrough (which exported a near-empty invoice).
assertEq(t.buildExportPayload("invoice-csv"), {
  kind: "invoice-csv", data: invoiceData, filename: "invoice-result.csv",
}, "invoice-csv payload");
assertEq(t.buildExportPayload("invoice-xlsx"), {
  kind: "invoice-xlsx", data: invoiceData, filename: "invoice-result.xlsx",
}, "invoice-xlsx payload");

// Regression: table corrections keep their full server-side path
// (tables[T].cells[R][C]); the stripped "[T].cells[R][C]" form is 422.
t.recordCorrection("tables[0].cells[1][1]", "9");
const tablesData = {
  machine_output: { tables: [{ table_id: "table_0", rows: 2, columns: 2, cells: [] }] },
  user_corrections: { "tables[0].cells[1][1]": "9" },
};
assertEq(t.buildExportPayload("table-csv"), {
  kind: "table-csv", data: tablesData, filename: "tables.csv",
}, "table-csv corrections verbatim");
assertEq(t.buildExportPayload("table-json"), {
  kind: "table-json", data: tablesData, filename: "tables-result.json",
}, "table-json corrections verbatim");

// ocr-json passthrough unchanged.
assertEq(t.buildExportPayload("ocr-json").data,
         { items: [{ text: "TOTAL 9.57" }] }, "ocr-json passthrough");

console.log("export payload behavior passed");
"""


def test_app_js_parses_and_executes_at_load_time():
    result = subprocess.run(
        [sys.executable, str(GATE), str(APP_JS)], capture_output=True, text=True)
    assert result.returncode == 0, f"frontend gate failed:\n{result.stdout}\n{result.stderr}"


def test_gate_rejects_top_level_return(tmp_path):
    """The gate must fail on a stray top-level return (the Stage 0 defect)."""
    import sys as _sys

    # Mutate a COPY: the gate must never risk corrupting the real source.
    copy = tmp_path / "app.js"
    copy.write_text(APP_JS.read_text(encoding="utf-8") + "\nreturn; // simulated defect",
                    encoding="utf-8")
    result = subprocess.run(
        [_sys.executable, str(GATE), str(copy)],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "Illegal return" in (result.stdout + result.stderr)


def test_export_payload_behavior(tmp_path):
    """buildExportPayload routes invoice/table kinds to the right data."""
    copy = tmp_path / "app.js"
    shutil.copyfile(APP_JS, copy)
    runner = tmp_path / "_export_behavior_runner.js"
    stubs = tmp_path / "_export_behavior_stubs.js"
    stubs.write_text(NODE_PRELUDE, encoding="utf-8")
    runner.write_text(BEHAVIORAL_RUNNER, encoding="utf-8")
    result = subprocess.run(
        ["node", str(runner), str(stubs), str(copy)],
        capture_output=True, text=True)
    assert result.returncode == 0, (
        f"export payload behavior failed:\n{result.stdout}\n{result.stderr}")
