"""
api.py — FastAPI endpoint for the deed validator.

Exposes:
    POST /validate     — validate a deed from raw OCR text
    GET  /validate/demo — run against the exact task input
    GET  /health        — service health check
"""

import os
import sys
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

load_dotenv()

from deed_processor import process_deed
from llm_extractor import RAW_DEED_TEXT

# ── Request / Response schemas ────────────────────────────────────────────────

class ValidateRequest(BaseModel):
    raw_text: Optional[str] = None  # uses task deed if not provided


class ValidationErrorResponse(BaseModel):
    error_code: str
    field: str
    message: str
    severity: str


class ValidateResponse(BaseModel):
    doc_id: str
    is_valid: bool
    grantor: str
    grantee: str
    amount_numeric: float
    county_raw: str
    county_matched: Optional[str]
    county_confidence: Optional[float]
    tax_rate: Optional[float]
    closing_costs: Optional[float]
    errors: list[ValidationErrorResponse]
    warnings: list[ValidationErrorResponse]
    summary: str


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Propy Deed Validator",
    description="""
    Validates real estate deeds using a hybrid approach:
    - **LLM** (Groq Llama 3.3 70B) for structured extraction from messy OCR
    - **Deterministic code** for all validation — dates, amounts, county matching

    Key principle: AI extracts, code validates. Never trust an LLM
    to catch financial or legal errors.
    """,
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model": "groq/llama-3.3-70b-versatile",
        "message": "Deed validator ready"
    }


@app.post("/validate", response_model=ValidateResponse)
async def validate_deed(request: ValidateRequest):
    """
    Validates a deed from raw OCR text.
    If no text provided, uses the task's demo deed.
    """
    try:
        result = process_deed(request.raw_text)

        return ValidateResponse(
            doc_id=result.doc_id,
            is_valid=result.is_valid,
            grantor=result.extracted.grantor,
            grantee=result.extracted.grantee,
            amount_numeric=result.extracted.amount_numeric,
            county_raw=result.extracted.county_raw,
            county_matched=result.county.matched_name if result.county else None,
            county_confidence=result.county.confidence_score if result.county else None,
            tax_rate=result.county.tax_rate if result.county else None,
            closing_costs=result.closing_costs,
            errors=[
                ValidationErrorResponse(
                    error_code=e.error_code,
                    field=e.field,
                    message=e.message,
                    severity=e.severity
                ) for e in result.errors
            ],
            warnings=[
                ValidationErrorResponse(
                    error_code=e.error_code,
                    field=e.field,
                    message=e.message,
                    severity=e.severity
                ) for w in result.warnings
                for e in [w]
            ],
            summary=result.summary()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/validate/demo", response_model=ValidateResponse)
async def validate_demo():
    """
    Runs the validator against the exact task input deed.
    Shows all three issues: county fuzzy match, date error, money mismatch.
    """
    try:
        result = process_deed(RAW_DEED_TEXT)

        return ValidateResponse(
            doc_id=result.doc_id,
            is_valid=result.is_valid,
            grantor=result.extracted.grantor,
            grantee=result.extracted.grantee,
            amount_numeric=result.extracted.amount_numeric,
            county_raw=result.extracted.county_raw,
            county_matched=result.county.matched_name if result.county else None,
            county_confidence=result.county.confidence_score if result.county else None,
            tax_rate=result.county.tax_rate if result.county else None,
            closing_costs=result.closing_costs,
            errors=[
                ValidationErrorResponse(
                    error_code=e.error_code,
                    field=e.field,
                    message=e.message,
                    severity=e.severity
                ) for e in result.errors
            ],
            warnings=[
                ValidationErrorResponse(
                    error_code=w.error_code,
                    field=w.field,
                    message=w.message,
                    severity=w.severity
                ) for w in result.warnings
            ],
            summary=result.summary()
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"\n🚀 Starting Propy Deed Validator API")
    print(f"   Docs    : http://localhost:{port}/docs")
    print(f"   Demo    : http://localhost:{port}/validate/demo")
    print(f"   Health  : http://localhost:{port}/health\n")
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)