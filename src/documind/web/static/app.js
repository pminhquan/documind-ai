/* DocuMind AI web frontend — vanilla JS, no build step. */
"use strict";

const state = {
  file: null,
  imageUrl: null,
  naturalWidth: 0,
  naturalHeight: 0,
  machine: null,     // untouched model output (ocr/invoice/tables)
  corrections: {},   // user corrections, keyed by field path
};

const $ = (id) => document.getElementById(id);

/* ---------- upload and preview ---------- */

const fileInput = $("file-input");
const dropZone = $("drop-zone");

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) loadFile(fileInput.files[0]);
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("dragover");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragover");
  if (event.dataTransfer.files.length) loadFile(event.dataTransfer.files[0]);
});
dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

function loadFile(file) {
  if (!/\.(png|jpe?g|bmp|tiff?|webp)$/i.test(file.name)) {
    setStatus("Unsupported file type. Use PNG, JPG, BMP, TIFF or WEBP.", true);
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    setStatus("File exceeds the 10 MB limit.", true);
    return;
  }
  state.file = file;
  state.machine = null;
  state.corrections = {};
  if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
  state.imageUrl = URL.createObjectURL(file);

  const img = $("preview-img");
  img.onload = () => {
    state.naturalWidth = img.naturalWidth;
    state.naturalHeight = img.naturalHeight;
  };
  img.src = state.imageUrl;
  $("preview-wrap").classList.remove("hidden");
  $("results").classList.add("hidden");
  clearOverlay();
  $("run-btn").disabled = false;
  setStatus(`Loaded ${file.name} (${(file.size / 1024).toFixed(0)} KB). Choose a workflow and run.`);
}

function setStatus(message, isError = false) {
  const status = $("status");
  status.textContent = message;
  status.classList.toggle("error", isError);
}

/* ---------- processing ---------- */

$("run-btn").addEventListener("click", async () => {
  if (!state.file) return;
  const workflow = $("workflow").value;
  $("run-btn").disabled = true;
  setStatus("Processing… (first run may download OCR models)");
  try {
    const form = new FormData();
    form.append("upload", state.file, state.file.name);
    form.append("workflow", workflow);
    const response = await fetch("/api/process", { method: "POST", body: form });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    state.machine = await response.json();
    state.corrections = {};
    renderResults(workflow);
    setStatus("Done. Machine output shown — edit fields to add corrections.");
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  } finally {
    $("run-btn").disabled = false;
  }
});

function renderResults(workflow) {
  const data = state.machine;
  $("results").classList.remove("hidden");
  $("ocr-panel").classList.toggle("hidden", !data.ocr);
  $("invoice-panel").classList.toggle("hidden", !data.invoice);
  $("tables-panel").classList.toggle("hidden", !data.tables);
  if (data.ocr) renderOcr(data.ocr);
  if (data.invoice) renderInvoice(data.invoice);
  if (data.tables) renderTables(data.tables);
}

/* ---------- OCR panel + bounding boxes ---------- */

function renderOcr(ocr) {
  const list = $("ocr-list");
  list.innerHTML = "";
  clearOverlay();
  ocr.items.forEach((item, index) => {
    const li = document.createElement("li");
    li.textContent = item.text;
    li.tabIndex = 0;
    const conf = document.createElement("span");
    conf.className = "conf";
    conf.textContent = `${(item.confidence * 100).toFixed(1)}%`;
    li.appendChild(conf);
    li.addEventListener("mouseenter", () => highlightBox(index));
    li.addEventListener("focus", () => highlightBox(index));
    list.appendChild(li);
    addBox(item.box, index);
  });
}

function clearOverlay() {
  $("box-overlay").innerHTML = "";
}

function addBox(box, index) {
  if (!box || box.length !== 4) return;
  const overlay = $("box-overlay");
  const xs = box.map((p) => p[0]);
  const ys = box.map((p) => p[1]);
  const left = Math.min(...xs) / state.naturalWidth * 100;
  const top = Math.min(...ys) / state.naturalHeight * 100;
  const width = (Math.max(...xs) - Math.min(...xs)) / state.naturalWidth * 100;
  const height = (Math.max(...ys) - Math.min(...ys)) / state.naturalHeight * 100;
  const div = document.createElement("div");
  div.className = "box";
  div.dataset.index = String(index);
  div.style.left = `${left}%`;
  div.style.top = `${top}%`;
  div.style.width = `${width}%`;
  div.style.height = `${height}%`;
  overlay.appendChild(div);
}

function highlightBox(index) {
  document.querySelectorAll("#box-overlay .box").forEach((box) => {
    box.classList.toggle("highlight", box.dataset.index === String(index));
  });
}

/* ---------- invoice panel (human-in-the-loop) ---------- */

const INVOICE_FIELDS = [
  "supplier", "invoice_number", "invoice_date", "currency",
  "subtotal", "tax", "discount", "total", "payment_amount", "change_amount",
];

function renderInvoice(invoice) {
  const tbody = $("invoice-fields").querySelector("tbody");
  tbody.innerHTML = "";
  const data = invoice.invoice;
  INVOICE_FIELDS.forEach((field) => {
    const row = document.createElement("tr");
    const label = document.createElement("td");
    label.textContent = field;
    const cell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "text";
    input.value = data[field] === null || data[field] === undefined ? "" : data[field];
    input.id = `invoice-${field}`;
    input.setAttribute("aria-label", `Invoice field ${field}`);
    input.addEventListener("input", () => {
      recordCorrection(`invoice.${field}`, input.value === "" ? null : input.value);
      markEdited(input, field);
    });
    cell.appendChild(input);
    row.appendChild(label);
    row.appendChild(cell);
    tbody.appendChild(row);
  });

  const itemsBody = $("line-items-table").querySelector("tbody");
  itemsBody.innerHTML = "";
  data.line_items.forEach((item, index) => {
    const row = document.createElement("tr");
    ["description", "quantity", "unit_price", "line_total"].forEach((key) => {
      const cell = document.createElement("td");
      const input = document.createElement("input");
      input.type = "text";
      input.value = item[key] === null || item[key] === undefined ? "" : item[key];
      input.setAttribute("aria-label", `Line item ${index} ${key}`);
      input.addEventListener("input", () => {
        recordCorrection(`invoice.line_items[${index}].${key}`,
                         input.value === "" ? null : input.value);
        markEdited(input, `item ${index} ${key}`);
      });
      cell.appendChild(input);
      row.appendChild(cell);
    });
    itemsBody.appendChild(row);
  });
}

function recordCorrection(path, value) {
  state.corrections[path] = value;
}

function markEdited(input, label) {
  let marker = input.parentElement.querySelector(".edited-marker");
  if (!marker) {
    marker = document.createElement("span");
    marker.className = "edited-marker";
    marker.textContent = "edited";
    input.parentElement.appendChild(marker);
  }
  marker.setAttribute("aria-label", `Corrected ${label}`);
}

$("invoice-reset").addEventListener("click", () => {
  state.corrections = Object.fromEntries(
    Object.entries(state.corrections).filter(([key]) => !key.startsWith("invoice.")));
  renderInvoice(state.machine.invoice);
});
$("tables-reset").addEventListener("click", () => {
  state.corrections = Object.fromEntries(
    Object.entries(state.corrections).filter(([key]) => !key.startsWith("tables.")));
  renderTables(state.machine.tables);
});

/* ---------- tables panel (human-in-the-loop) ---------- */

function renderTables(tablesResponse) {
  const tabs = $("table-tabs");
  const grids = $("tables-grids");
  tabs.innerHTML = "";
  grids.innerHTML = "";
  tablesResponse.tables.forEach((table, tableIndex) => {
    const tab = document.createElement("button");
    tab.className = "tab";
    tab.textContent = table.table_id;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", tableIndex === 0 ? "true" : "false");
    tab.addEventListener("click", () => {
      tabs.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", "false"));
      tab.setAttribute("aria-selected", "true");
      grids.querySelectorAll(".grid-wrap").forEach((g) => g.classList.add("hidden"));
      grids.querySelector(`[data-table="${tableIndex}"]`).classList.remove("hidden");
    });
    tabs.appendChild(tab);

    const wrap = document.createElement("div");
    wrap.className = "grid-wrap";
    wrap.dataset.table = String(tableIndex);
    if (tableIndex > 0) wrap.classList.add("hidden");

    const grid = document.createElement("table");
    grid.className = "grid";
    const body = document.createElement("tbody");
    for (let r = 0; r < table.rows; r += 1) {
      const row = document.createElement("tr");
      for (let c = 0; c < table.columns; c += 1) {
        const cell = table.cells.find(
          (x) => x.row_index === r && x.column_index === c);
        const td = document.createElement("td");
        const input = document.createElement("input");
        input.type = "text";
        input.value = cell ? cell.text : "";
        input.setAttribute("aria-label",
          `${table.table_id} cell ${r},${c}`);
        input.addEventListener("input", () => {
          recordCorrection(`tables[${tableIndex}].cells[${r}][${c}]`,
                           input.value);
          markEdited(input, `${table.table_id} ${r},${c}`);
        });
        td.appendChild(input);
        row.appendChild(td);
      }
      body.appendChild(row);
    }
    grid.appendChild(body);
    wrap.appendChild(grid);
    grids.appendChild(wrap);
  });
  if (!tablesResponse.tables.length) {
    grids.innerHTML = "<p class='hint'>No ruled tables detected in this document.</p>";
  }
}

/* ---------- exports ---------- */

document.querySelectorAll("[data-export]").forEach((button) => {
  button.addEventListener("click", async () => {
    const kind = button.dataset.export;
    const payload = buildExportPayload(kind);
    try {
      const response = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const name = (response.headers.get("Content-Disposition") || "")
        .match(/filename="([^"]+)"/)?.[1] || "export";
      downloadBlob(blob, name);
      setStatus(`Exported ${name}`);
    } catch (error) {
      setStatus(`Export failed: ${error.message}`, true);
    }
  });
});

function buildExportPayload(kind) {
  const machine = state.machine || {};
  if (kind === "ocr-json") {
    return { kind, data: machine.ocr || {}, filename: "ocr-result.json" };
  }
  if (kind === "invoice-json") {
    return {
      kind,
      data: applyCorrections({
        machine_output: machine.invoice || null,
        user_corrections: pickCorrections("invoice."),
      }),
      filename: "invoice-result.json",
    };
  }
  const tablesPayload = {
    machine_output: machine.tables || null,
    user_corrections: pickCorrections("tables."),
  };
  return { kind, data: tablesPayload, filename: "tables-result" };
}

function pickCorrections(prefix) {
  const picked = {};
  Object.entries(state.corrections).forEach(([key, value]) => {
    if (key.startsWith(prefix)) picked[key.slice(prefix.length)] = value;
  });
  return picked;
}

function applyCorrections(payload) {
  return payload;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
