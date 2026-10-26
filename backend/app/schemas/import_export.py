from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class RowValidationError(BaseModel):
    row_number: int
    sku: Optional[str] = None
    field: str
    message: str
    severity: str = "error"  # "error" or "warning"

class ImportSummaryResponse(BaseModel):
    success: bool
    filename: str
    total_rows: int
    imported_count: int
    updated_count: int
    failed_count: int
    warnings_count: int
    errors: List[RowValidationError] = Field(default_factory=list)
    warnings: List[RowValidationError] = Field(default_factory=list)
    categories_detected: List[str] = Field(default_factory=list)
    message: str

class ExportRequest(BaseModel):
    format: str = "xlsx"  # xlsx, csv, json
    category: Optional[str] = None
    search: Optional[str] = None
