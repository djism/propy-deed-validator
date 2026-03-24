"""
deed_processor.py — Orchestrates the full validation pipeline.

PIPELINE FLOW:
--------------
Step 1: LLM extracts structured data from messy OCR text
Step 2: Fuzzy match raw county name to known county + tax rate
Step 3: Deterministic validators catch date and money errors
Step 4: Calculate closing costs (only if no CRITICAL errors)
Step 5: Return complete DeedValidationResult

This file is intentionally thin — it just calls the right
functions in the right order. Each concern lives in its own file.
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

from llm_extractor import extract_deed, RAW_DEED_TEXT
from county_matcher import match_county, calculate_closing_costs
from validators import run_all_validations
from models import DeedValidationResult

# The exact OCR text from the Propy task
TASK_DEED_TEXT = RAW_DEED_TEXT


def process_deed(raw_text: str = None) -> DeedValidationResult:
    """
    Full pipeline: OCR text → validated DeedValidationResult.

    Args:
        raw_text: Raw OCR deed text. Uses task text if None.

    Returns:
        DeedValidationResult with all fields populated.
    """
    if raw_text is None:
        raw_text = TASK_DEED_TEXT

    print("\n" + "=" * 55)
    print("  Propy Deed Validator — Processing")
    print("=" * 55)

    # ── Step 1: LLM extraction ────────────────────────────────────────────────
    print("\n[1/4] Extracting structured data with LLM...")
    deed = extract_deed(raw_text)
    print(f"   ✅ Extracted: {deed.doc_id}")

    # ── Step 2: County matching ───────────────────────────────────────────────
    print(f"\n[2/4] Matching county '{deed.county_raw}'...")
    county_match = None
    county_error = None
    try:
        county_match = match_county(deed.county_raw)
        print(f"   ✅ Matched: {county_match.matched_name} "
              f"(tax rate: {county_match.tax_rate:.1%})")
    except ValueError as e:
        county_error = str(e)
        print(f"   ⚠️  County match failed: {county_error}")

    # ── Step 3: Deterministic validation ──────────────────────────────────────
    print(f"\n[3/4] Running validation checks...")
    errors, warnings = run_all_validations(deed)

    print(f"   Errors   : {len(errors)} CRITICAL")
    print(f"   Warnings : {len(warnings)}")
    for e in errors:
        print(f"   ❌ [{e.error_code}] {e.message[:80]}...")
    for w in warnings:
        print(f"   ⚠️  [{w.error_code}] {w.message[:80]}...")

    # ── Step 4: Closing costs (only if no CRITICAL errors) ────────────────────
    print(f"\n[4/4] Calculating closing costs...")
    closing_costs = None
    if not errors and county_match:
        closing_costs = calculate_closing_costs(
            deed.amount_numeric,
            county_match.tax_rate
        )
        print(f"   ✅ Closing costs: ${closing_costs:,.2f}")
    elif errors:
        print(f"   ⏭️  Skipped — CRITICAL errors must be resolved first")
    else:
        print(f"   ⏭️  Skipped — county not matched")

    # ── Assemble result ───────────────────────────────────────────────────────
    is_valid = len(errors) == 0 and county_match is not None
    result = DeedValidationResult(
        doc_id=deed.doc_id,
        raw_text=raw_text.strip(),
        extracted=deed,
        county=county_match,
        closing_costs=closing_costs,
        is_valid=is_valid,
        errors=errors,
        warnings=warnings
    )

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 55}")
    print(f"  RESULT")
    print(f"{'=' * 55}")
    print(result.summary())
    print(f"{'=' * 55}\n")

    return result


if __name__ == "__main__":
    print("Running Propy Bad Deed Validator on task input...\n")
    result = process_deed(TASK_DEED_TEXT)

    # Exit with appropriate code
    if result.is_valid:
        print("✅ Deed is valid — safe to proceed")
        sys.exit(0)
    else:
        print("❌ Deed has errors — do not record")
        sys.exit(1)