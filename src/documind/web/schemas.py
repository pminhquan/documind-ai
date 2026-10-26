"""Pydantic response schemas — the documented web API contracts."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    engine_loaded: bool
    version: str


class OcrItem(BaseModel):
    text: str
    confidence: float
    box: list[list[float]] = Field(default_factory=list)


class OcrResponse(BaseModel):
    source: str
    engine: str
    items: list[OcrItem]
    full_text: str


class InvoiceLineItem(BaseModel):
    description: str = ""
    quantity: str | None = None
    unit_price: str | None = None
    line_total: str | None = None


class InvoiceData(BaseModel):
    supplier: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    currency: str | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    subtotal: str | None = None
    tax: str | None = None
    discount: str | None = None
    total: str | None = None
    payment_amount: str | None = None
    change_amount: str | None = None
    validation_status: str = "ok"
    validation_errors: list[str] = Field(default_factory=list)


class ProvenanceEntry(BaseModel):
    ocr_index: int
    text: str
    box: list[list[float]] = Field(default_factory=list)


class InvoiceResponse(BaseModel):
    source: str
    invoice: InvoiceData
    provenance: dict[str, ProvenanceEntry] = Field(default_factory=dict)


class TableCellData(BaseModel):
    row_index: int
    column_index: int
    text: str
    bounding_box: list[list[int]] = Field(default_factory=list)
    source_ocr_indices: list[int] = Field(default_factory=list)
    confidence: float | None = None


class TableData(BaseModel):
    table_id: str
    source_image: str
    rows: int
    columns: int
    cells: list[TableCellData] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TableResponse(BaseModel):
    source_image: str
    tables: list[TableData]
    warnings: list[str] = Field(default_factory=list)


class UnifiedResponse(BaseModel):
    workflows: list[str]
    source: str
    ocr: OcrResponse | None = None
    invoice: InvoiceResponse | None = None
    tables: TableResponse | None = None
