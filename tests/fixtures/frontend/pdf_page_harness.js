/*
 * Node harness for the PDF page-level frontend behavior (D-18).
 *
 * Executes the real static/app.js inside a small deterministic DOM so the
 * tests can drive page tabs, edit invoice/table inputs, press Reset, and
 * collect export payloads without a browser. Every scenario is isolated:
 * a crash in one scenario is reported as an error, not a harness failure.
 *
 * Usage: node pdf_page_harness.js <path-to-app.js>
 * Prints one JSON document on stdout: { "scenarios": { "A": {...}, ... } }
 */
"use strict";

const fs = require("fs");
const vm = require("vm");

const appPath = process.argv[2];
if (!appPath) {
  console.error("usage: node pdf_page_harness.js <app.js>");
  process.exit(2);
}

/* ---------- minimal deterministic DOM ---------- */

class FakeClassList {
  constructor() {
    this.names = new Set();
  }
  add(...names) {
    names.forEach((name) => this.names.add(name));
  }
  remove(...names) {
    names.forEach((name) => this.names.delete(name));
  }
  toggle(name, force) {
    if (force === undefined) {
      this.names.has(name) ? this.names.delete(name) : this.names.add(name);
      return;
    }
    force ? this.names.add(name) : this.names.delete(name);
  }
  contains(name) {
    return this.names.has(name);
  }
}

class FakeElement {
  constructor(tagName, owner) {
    this.tagName = String(tagName).toUpperCase();
    this.ownerDocument = owner;
    this.children = [];
    this.parentElement = null;
    this.classList = new FakeClassList();
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this.handlers = {};
    this.text = "";
    this.html = "";
    this.value = "";
    this.id = "";
    this.disabled = false;
    this.tabIndex = 0;
    this.files = [];
  }
  get className() {
    return Array.from(this.classList.names).join(" ");
  }
  set className(value) {
    this.classList.names = new Set(
      String(value).split(/\s+/).filter(Boolean));
  }
  get textContent() {
    return this.text;
  }
  set textContent(value) {
    this.text = String(value);
    this.children = [];
  }
  get innerHTML() {
    return this.html;
  }
  set innerHTML(value) {
    this.html = String(value);
    this.children = [];
  }
  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
  remove() {
    if (!this.parentElement) return;
    const index = this.parentElement.children.indexOf(this);
    if (index >= 0) this.parentElement.children.splice(index, 1);
    this.parentElement = null;
  }
  addEventListener(type, handler) {
    (this.handlers[type] || (this.handlers[type] = [])).push(handler);
  }
  removeEventListener(type, handler) {
    const list = this.handlers[type] || [];
    const index = list.indexOf(handler);
    if (index >= 0) list.splice(index, 1);
  }
  dispatch(type, event = {}) {
    (this.handlers[type] || []).forEach((handler) =>
      handler(Object.assign({ target: this, preventDefault() {} }, event)));
  }
  click() {
    this.dispatch("click");
  }
  focus() {
    this.dispatch("focus");
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name] : null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
  }
  descendantElements() {
    const found = [];
    const walk = (node) => {
      node.children.forEach((child) => {
        found.push(child);
        walk(child);
      });
    };
    walk(this);
    return found;
  }
  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
  querySelectorAll(selector) {
    return queryAll(this, selector);
  }
}

function matchesSelector(element, selector) {
  if (!element) return false;
  const simple = selector.trim();
  if (!simple) return false;
  if (simple.startsWith("#")) return element.id === simple.slice(1);
  if (simple.startsWith("[")) {
    const attr = simple.slice(1, -1);
    const equals = attr.indexOf("=");
    if (equals < 0) {
      return Object.prototype.hasOwnProperty.call(element.dataset, attr);
    }
    const key = attr.slice(0, equals);
    const value = attr.slice(equals + 1).replace(/^["']|["']$/g, "");
    return String(element.dataset[key]) === value;
  }
  if (simple.startsWith(".")) {
    return simple.split(".").filter(Boolean)
      .every((name) => element.classList.contains(name));
  }
  return element.tagName === simple.toUpperCase();
}

function queryAll(root, selector) {
  let scope = root;
  let simple = selector.trim();
  if (simple.includes(" ")) {
    const parts = simple.split(/\s+/);
    const anchor = parts.shift();
    if (anchor.startsWith("#")) {
      scope = root.ownerDocument.getElementById(anchor.slice(1));
    } else if (anchor.startsWith(".")) {
      scope = root.querySelector(anchor);
    }
    simple = parts.join(" ");
  }
  if (!scope) return [];
  return scope.descendantElements().filter((element) =>
    matchesSelector(element, simple));
}

class FakeDocument {
  constructor() {
    this.byId = new Map();
    this.created = [];
    this.body = this.createElement("body");
  }
  createElement(tagName) {
    const element = new FakeElement(tagName, this);
    this.created.push(element);
    return element;
  }
  getElementById(id) {
    if (!this.byId.has(id)) {
      this.byId.set(id, this.createElement("div"));
      this.byId.get(id).id = id;
    }
    const generated = this.byId.get(id);
    if (generated.children.length || generated.id === id) {
      const dynamic = this.created.slice().reverse()
        .find((element) => element.id === id);
      return dynamic || generated;
    }
    return generated;
  }
  querySelector(selector) {
    if (selector.startsWith("#") && !selector.includes(" ")) {
      return this.getElementById(selector.slice(1));
    }
    return queryAll(this.body, selector)[0] || null;
  }
  querySelectorAll(selector) {
    return queryAll(this.body, selector);
  }
  addEventListener() {}
  findInputById(id) {
    return this.created.slice().reverse()
      .find((element) => element.tagName === "INPUT" && element.id === id) || null;
  }
  findInputByLabel(label) {
    return this.created.slice().reverse().find((element) =>
      element.tagName === "INPUT"
      && element.getAttribute("aria-label") === label) || null;
  }
}

const document = new FakeDocument();
const window = { addEventListener() {}, location: { href: "" } };
const URLStub = { createObjectURL: () => "blob:stub", revokeObjectURL() {} };
const fetchStub = () => Promise.resolve({
  ok: true, json: async () => ({}), blob: async () => ({}),
  headers: { get: () => null },
});
class FormDataStub {
  append() {}
}
class BlobStub {}

const sandbox = {
  document,
  window,
  URL: URLStub,
  fetch: fetchStub,
  FormData: FormDataStub,
  Blob: BlobStub,
  console,
  setTimeout,
  clearTimeout,
};
const context = vm.createContext(sandbox);
const source = fs.readFileSync(appPath, "utf8") + `
;globalThis.__app = {
  state,
  renderResults,
  buildExportPayload,
  pickCorrections,
  recordCorrection,
  renderInvoice,
  renderTables,
  exportKindFor,
  exportDataFor,
  buildBatchPayload:
    typeof buildBatchPayload === "function" ? buildBatchPayload : null,
  resolveActiveResult:
    typeof resolveActiveResult === "function" ? resolveActiveResult : null,
};
`;
vm.runInContext(source, context, { filename: "app.js" });
const app = context.__app;
const state = app.state;

/* ---------- page fixtures ---------- */

function ocrResponse(label, total) {
  return {
    source: "upload",
    engine: "fake",
    items: [{ text: `${label} TOTAL ${total}`, confidence: 0.99, box: [] }],
    full_text: `${label} TOTAL ${total}`,
  };
}

function invoiceResponse(supplier, total, label) {
  return {
    source: "upload",
    provenance: {},
    invoice: {
      supplier,
      invoice_number: `INV-${label}`,
      invoice_date: "2026-01-01",
      currency: "USD",
      line_items: [{
        description: `Item ${label}`,
        quantity: "1",
        unit_price: total,
        line_total: total,
      }],
      subtotal: total,
      tax: null,
      discount: null,
      total,
      payment_amount: null,
      change_amount: null,
      validation_status: "ok",
      validation_errors: [],
    },
  };
}

function tableResponse(tableId, cellText) {
  return {
    source_image: "upload",
    tables: [{
      table_id: tableId,
      source_image: "upload",
      rows: 1,
      columns: 1,
      cells: [{
        row_index: 0,
        column_index: 0,
        text: cellText,
        bounding_box: [],
        source_ocr_indices: [],
        confidence: 0.9,
      }],
      warnings: [],
    }],
    warnings: [],
  };
}

function pdfPage(pageIndex, label, supplier, total, cellText) {
  return {
    page_index: pageIndex,
    workflows: ["ocr", "invoice", "table"],
    source: `upload#page${pageIndex}`,
    ocr: ocrResponse(label, total),
    invoice: invoiceResponse(supplier, total, label),
    tables: tableResponse("table_0", cellText),
  };
}

function pdfFixture() {
  return {
    kind: "pdf",
    page_count: 2,
    workflows: ["ocr", "invoice", "table"],
    pages: [
      pdfPage(0, "A", "SHOP-A", "10.00", "10"),
      pdfPage(1, "B", "SHOP-B", "20.00", "20"),
    ],
    errors: [],
  };
}

function imageFixture() {
  return {
    workflows: ["ocr", "invoice", "table"],
    source: "upload",
    ocr: ocrResponse("IMG", "9.57"),
    invoice: invoiceResponse("MINIMART", "9.57", "IMG"),
    tables: tableResponse("table_0", "9.57"),
  };
}

/* ---------- harness helpers ---------- */

function resetState(machine, filename) {
  state.machine = machine;
  state.file = { name: filename, size: 1024 };
  state.files = [state.file];
  state.correctionsByDoc = {};
  state.activeDocKey = null;
  state.activePageIndex = null;
  state.batchResults = [];
  state.naturalWidth = 0;
  state.naturalHeight = 0;

  const invoiceTable = document.getElementById("invoice-fields");
  if (!invoiceTable.querySelector("tbody")) {
    invoiceTable.appendChild(document.createElement("tbody"));
  }
  const lineTable = document.getElementById("line-items-table");
  if (!lineTable.querySelector("tbody")) {
    lineTable.appendChild(document.createElement("tbody"));
  }
  const nav = document.getElementById("pages-nav");
  nav.innerHTML = "";
  nav.classList.add("hidden");
}

function setInput(element, value) {
  if (!element) throw new Error("missing input for value " + value);
  element.value = value;
  element.dispatch("input");
}

function pageTabs() {
  return document.getElementById("pages-nav").children
    .filter((element) => element.classList.contains("tab"));
}

function inputValue(id) {
  const input = document.findInputById(id);
  return input ? input.value : null;
}

function cellValue(label) {
  const input = document.findInputByLabel(label);
  return input ? input.value : null;
}

function hasMarker(element) {
  return Boolean(element && element.parentElement
    && element.parentElement.querySelector(".edited-marker"));
}

function markerFor(id) {
  return hasMarker(document.findInputById(id));
}

function cellMarker(label) {
  return hasMarker(document.findInputByLabel(label));
}

function activeInfo() {
  return {
    activeDocKey: state.activeDocKey,
    activePageIndex: state.activePageIndex,
  };
}

function correctionsFor(key) {
  return JSON.parse(JSON.stringify(state.correctionsByDoc[key] || {}));
}

function editBothPages() {
  resetState(pdfFixture(), "document.pdf");
  app.renderResults();
  setInput(document.findInputById("invoice-total"), "100.00");
  setInput(document.findInputByLabel("table_0 cell 0,0"), "Apple");
  pageTabs()[1].click();
  setInput(document.findInputById("invoice-total"), "200.00");
  setInput(document.findInputByLabel("table_0 cell 0,0"), "Orange");
}

function collectPageExports(kind) {
  const payloads = {};
  pageTabs()[0].click();
  payloads.page0 = app.buildExportPayload(kind);
  pageTabs()[1].click();
  payloads.page1 = app.buildExportPayload(kind);
  return payloads;
}

/* ---------- scenarios ---------- */

const scenarios = {};

function scenario(name, fn) {
  try {
    scenarios[name] = { ok: true, data: fn() };
  } catch (error) {
    scenarios[name] = {
      ok: false,
      error: String(error && error.stack ? error.stack : error),
    };
  }
}

scenario("A", () => {
  resetState(pdfFixture(), "document.pdf");
  app.renderResults();
  const initial = {
    total: inputValue("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    tabs: pageTabs().length,
    ...activeInfo(),
  };

  setInput(document.findInputById("invoice-total"), "100.00");
  setInput(document.findInputByLabel("table_0 cell 0,0"), "Apple");

  pageTabs()[1].click();
  const page1 = {
    total: inputValue("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    ...activeInfo(),
  };
  setInput(document.findInputById("invoice-total"), "200.00");
  setInput(document.findInputByLabel("table_0 cell 0,0"), "Orange");

  pageTabs()[0].click();
  const page0Again = {
    total: inputValue("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    totalEdited: markerFor("invoice-total"),
    cellEdited: cellMarker("table_0 cell 0,0"),
    ...activeInfo(),
  };

  pageTabs()[1].click();
  const page1Again = {
    total: inputValue("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    totalEdited: markerFor("invoice-total"),
    cellEdited: cellMarker("table_0 cell 0,0"),
    ...activeInfo(),
  };

  return { initial, page1, page0Again, page1Again,
           corrections: JSON.parse(JSON.stringify(state.correctionsByDoc)) };
});

scenario("B", () => {
  editBothPages();
  return {
    invoiceCsv: collectPageExports("invoice-csv"),
    invoiceXlsx: collectPageExports("invoice-xlsx"),
    invoiceJson: collectPageExports("invoice-json"),
    tableCsv: collectPageExports("table-csv"),
    tableXlsx: collectPageExports("table-xlsx"),
    tableJson: collectPageExports("table-json"),
    ocrJson: collectPageExports("ocr-json"),
    ocrTxt: collectPageExports("ocr-txt"),
  };
});

scenario("C", () => {
  editBothPages();
  pageTabs()[0].click();
  document.getElementById("invoice-reset").click();
  const page0AfterInvoiceReset = {
    total: inputValue("invoice-total"),
    totalEdited: markerFor("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    cellEdited: cellMarker("table_0 cell 0,0"),
    corrections: correctionsFor("document.pdf#0"),
  };

  pageTabs()[1].click();
  const page1AfterPage0Reset = {
    total: inputValue("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    corrections: correctionsFor("document.pdf#1"),
  };

  document.getElementById("tables-reset").click();
  const page1AfterTablesReset = {
    total: inputValue("invoice-total"),
    totalEdited: markerFor("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    cellEdited: cellMarker("table_0 cell 0,0"),
    corrections: correctionsFor("document.pdf#1"),
    invoicePayload: app.buildExportPayload("invoice-csv"),
    tablePayload: app.buildExportPayload("table-csv"),
  };

  pageTabs()[0].click();
  const page0Final = {
    total: inputValue("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    corrections: correctionsFor("document.pdf#0"),
  };

  return { page0AfterInvoiceReset, page1AfterPage0Reset,
           page1AfterTablesReset, page0Final,
           allCorrections: JSON.parse(JSON.stringify(state.correctionsByDoc)) };
});

scenario("D", () => {
  const partial = {
    kind: "pdf",
    page_count: 2,
    workflows: ["ocr", "invoice", "table"],
    errors: ["page 0: boom"],
    pages: [
      { page_index: 0, error: "boom" },
      pdfPage(1, "B", "SHOP-B", "20.00", "20"),
    ],
  };
  resetState(partial, "document.pdf");
  app.renderResults();
  const tabs = pageTabs();
  const info = activeInfo();
  const total = inputValue("invoice-total");
  const invoicePayload = app.buildExportPayload("invoice-csv");

  let batch = null;
  if (app.buildBatchPayload) {
    state.batchResults = [{
      filename: "document.pdf",
      workflow: "auto",
      kind: "ocr-json",
      result: partial,
    }];
    batch = app.buildBatchPayload();
  }
  return {
    tabCount: tabs.length,
    tabLabels: tabs.map((tab) => tab.textContent),
    ...info,
    total,
    invoicePayload,
    batch,
  };
});

scenario("E", () => {
  resetState(imageFixture(), "scan.png");
  state.activeDocKey = "scan.png#0";
  app.renderResults();
  const initial = {
    total: inputValue("invoice-total"),
    cell: cellValue("table_0 cell 0,0"),
    pagesHidden: document.getElementById("pages-nav").classList.contains("hidden"),
    ...activeInfo(),
  };
  setInput(document.findInputById("invoice-total"), "10.00");
  setInput(document.findInputByLabel("table_0 cell 0,0"), "Apple");
  return {
    initial,
    invoiceCsv: app.buildExportPayload("invoice-csv"),
    invoiceJson: app.buildExportPayload("invoice-json"),
    tableCsv: app.buildExportPayload("table-csv"),
    ocrJson: app.buildExportPayload("ocr-json"),
  };
});

scenario("F", () => {
  const machine = pdfFixture();
  resetState(machine, "document.pdf");
  state.correctionsByDoc = {
    "document.pdf#0": {
      "invoice.total": "100.00",
      "tables[0].cells[0][0]": "Apple",
    },
    "document.pdf#1": {
      "invoice.total": "200.00",
      "tables[0].cells[0][0]": "Orange",
    },
  };
  state.batchResults = [
    { filename: "document.pdf", workflow: "auto", kind: "ocr-json",
      result: machine },
    { filename: "scan.png", workflow: "invoice", kind: "invoice-json",
      result: imageFixture() },
    { filename: "broken.png", workflow: "ocr", kind: "ocr-json",
      error: "boom" },
  ];
  if (!app.buildBatchPayload) return { available: false };
  return { available: true, payload: app.buildBatchPayload() };
});

scenario("G", () => {
  const machine = pdfFixture();
  machine.pages[0].invoice.invoice.supplier = "=SUM(A1)";
  machine.pages[0].tables.tables[0].cells[0].text = "=cmd()";
  resetState(machine, "document.pdf");
  state.correctionsByDoc = {
    "document.pdf#0": { "tables[0].cells[0][0]": "=cmd()" },
  };
  app.renderResults();
  return {
    invoiceCsv: app.buildExportPayload("invoice-csv"),
    invoiceXlsx: app.buildExportPayload("invoice-xlsx"),
    tableCsv: app.buildExportPayload("table-csv"),
    tableXlsx: app.buildExportPayload("table-xlsx"),
    active: activeInfo(),
  };
});

scenario("H", () => {
  const ocrOnly = {
    kind: "pdf",
    page_count: 1,
    workflows: ["ocr"],
    errors: [],
    pages: [{
      page_index: 0,
      source: "upload#page0",
      ocr: ocrResponse("A", "1.00"),
    }],
  };
  resetState(ocrOnly, "scan.pdf");
  app.renderResults();
  const attempts = {};
  ["invoice-csv", "table-xlsx"].forEach((kind) => {
    try {
      app.buildExportPayload(kind);
      attempts[kind] = { ok: true };
    } catch (error) {
      attempts[kind] = { ok: false, message: error.message };
    }
  });
  return attempts;
});

scenario("I", () => {
  const page = pdfPage(0, "A", "SHOP-A", "10.00", "10");
  page.tables = {
    source_image: "upload",
    tables: [
      page.tables.tables[0],
      {
        ...page.tables.tables[0],
        table_id: "table_1",
        cells: [{ ...page.tables.tables[0].cells[0], text: "second" }],
      },
    ],
    warnings: [],
  };
  const machine = {
    kind: "pdf",
    page_count: 1,
    workflows: ["table"],
    errors: [],
    pages: [page],
  };
  resetState(machine, "multi.pdf");
  app.renderResults();
  return { tableCsv: app.buildExportPayload("table-csv") };
});

process.stdout.write(JSON.stringify({ scenarios }));
