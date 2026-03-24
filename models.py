"""
models.py — Pydantic schemas for the deed validator.

WHY PYDANTIC?
-------------
When an LLM returns data, we can't trust it's the right shape.
Pydantic validates every field — wrong type, missing field, or
out-of-range value raises an immediate error before anything
reaches the validation layer.

This is the typed contract between the LLM output and our code.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class DeedStatus(str, Enum):
    PRELIMINARY = "PRELIMINARY"
    FINAL = "FINAL"
    RECORDED = "RECORDED"
    REJECTED = "REJECTED"


class ExtractedDeed(BaseModel):
    """
    Raw structured data extracted by the LLM from OCR text.
    Every field the LLM must identify and return.
    """
    doc_id: str = Field(description="Document identifier e.g. DEED-TRUST-0042")
    county_raw: str = Field(description="County as written in document e.g. 'S. Clara'")
    state: str = Field(description="Two-letter state code e.g. 'CA'")
    date_signed: str = Field(description="Date signed in YYYY-MM-DD format")
    date_recorded: str = Field(description="Date recorded in YYYY-MM-DD format")
    grantor: str = Field(description="Entity transferring the property")
    grantee: str = Field(description="Entity receiving the property")
    amount_numeric: float = Field(description="Dollar amount as number e.g. 1250000.00")
    amount_words: str = Field(description="Dollar amount as written in words")
    apn: str = Field(description="Assessor Parcel Number e.g. 992-001-XA")
    status: str = Field(description="Document status e.g. PRELIMINARY")


class CountyMatch(BaseModel):
    """Result of fuzzy county matching."""
    raw_input: str
    matched_name: str
    tax_rate: float
    confidence_score: float


class ValidationError(BaseModel):
    """A single validation failure — code-detected, never LLM."""
    error_code: str
    field: str
    message: str
    severity: str  # CRITICAL or WARNING


class DeedValidationResult(BaseModel):
    """
    Final output of the full pipeline.
    Contains extracted data, county match, closing costs,
    and all validation errors found by deterministic code.
    """
    # Input
    doc_id: str
    raw_text: str

    # LLM extracted
    extracted: ExtractedDeed

    # County match
    county: Optional[CountyMatch] = None

    # Closing costs (calculated deterministically)
    closing_costs: Optional[float] = None

    # Validation
    is_valid: bool
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    def summary(self) -> str:
        """Clean summary string for display."""
        lines = [
            f"Document  : {self.doc_id}",
            f"Grantor   : {self.extracted.grantor}",
            f"Grantee   : {self.extracted.grantee}",
            f"Amount    : ${self.extracted.amount_numeric:,.2f}",
            f"County    : {self.county.matched_name if self.county else 'Unknown'} "
            f"(matched from '{self.extracted.county_raw}')",
            f"Tax Rate  : {self.county.tax_rate:.1%}" if self.county else "",
            f"Closing   : ${self.closing_costs:,.2f}" if self.closing_costs else "",
            f"Valid     : {'✅ YES' if self.is_valid else '❌ NO'}",
        ]
        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  ❌ [{e.error_code}] {e.message}")
        if self.warnings:
            lines.append(f"\nWarnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  ⚠️  [{w.error_code}] {w.message}")
        return "\n".join(l for l in lines if l)


if __name__ == "__main__":
    print("Testing models...\n")

    deed = ExtractedDeed(
        doc_id="DEED-TRUST-0042",
        county_raw="S. Clara",
        state="CA",
        date_signed="2024-01-15",
        date_recorded="2024-01-10",
        grantor="T.E.S.L.A. Holdings LLC",
        grantee="John & Sarah Connor",
        amount_numeric=1250000.00,
        amount_words="One Million Two Hundred Thousand Dollars",
        apn="992-001-XA",
        status="PRELIMINARY"
    )

    print(f"Doc ID   : {deed.doc_id}")
    print(f"County   : {deed.county_raw}")
    print(f"Amount   : ${deed.amount_numeric:,.2f}")
    print(f"Signed   : {deed.date_signed}")
    print(f"Recorded : {deed.date_recorded}")
    print("\n✅ Models working correctly!")