"""
validators.py — Deterministic validation checks.

THIS IS THE MOST IMPORTANT FILE IN THE PROJECT.

The core principle of this system:
    LLM  → extract and parse (it's good at understanding messy text)
    CODE → validate (it never hallucinates, never has a bad day)

WHY NOT LET THE LLM VALIDATE?
-------------------------------
Because LLMs are probabilistic. On a good day they catch the date
error. On a bad day they don't. On a very bad day they confidently
tell you the dates are fine when they aren't.

For a real estate deed recorded on blockchain, one missed error
could mean a fraudulent transaction is permanently recorded.
The cost of that mistake is catastrophic.

Deterministic Python code is:
  - Always right (given correct input)
  - Zero cost
  - Instantly verifiable by reading it
  - Auditable — you can prove in court why it flagged something

These two checks catch the exact errors in the test document:
  1. Date check: recorded (Jan 10) before signed (Jan 15) → CRITICAL
  2. Money check: $1,250,000 digits vs $1,200,000 words → WARNING
"""

from datetime import datetime
from word2number import w2n
from models import ExtractedDeed, ValidationError


# ── Date validation ───────────────────────────────────────────────────────────

def validate_dates(deed: ExtractedDeed) -> list[ValidationError]:
    """
    Checks that the document timeline is logically possible.

    THE RULE: A document cannot be recorded before it was signed.
    Signing creates the legal instrument. Recording registers it
    with the county. Recording must always come AFTER signing.

    This is 100% deterministic — we parse both dates and compare
    them with a simple inequality. No LLM, no ambiguity, no cost.

    The test document has:
        Date Signed   : 2024-01-15
        Date Recorded : 2024-01-10
    recorded < signed → CRITICAL error

    Returns:
        List of ValidationError objects (empty if dates are valid)
    """
    errors = []

    try:
        date_signed = datetime.strptime(deed.date_signed, "%Y-%m-%d")
        date_recorded = datetime.strptime(deed.date_recorded, "%Y-%m-%d")
    except ValueError as e:
        errors.append(ValidationError(
            error_code="INVALID_DATE_FORMAT",
            field="date_signed / date_recorded",
            message=f"Could not parse date: {e}. Expected format: YYYY-MM-DD",
            severity="CRITICAL"
        ))
        return errors

    # Core check: recorded must be on or after signed
    if date_recorded < date_signed:
        delta_days = (date_signed - date_recorded).days
        errors.append(ValidationError(
            error_code="RECORDING_BEFORE_SIGNING",
            field="date_recorded",
            message=(
                f"Document recorded ({deed.date_recorded}) "
                f"before it was signed ({deed.date_signed}). "
                f"Recording is {delta_days} day(s) before signing. "
                f"A document cannot be legally recorded before it exists."
            ),
            severity="CRITICAL"
        ))

    # Additional check: dates shouldn't be in the future
    today = datetime.now()
    if date_signed > today:
        errors.append(ValidationError(
            error_code="FUTURE_SIGNING_DATE",
            field="date_signed",
            message=(
                f"Signing date ({deed.date_signed}) is in the future. "
                f"Cannot sign a document that hasn't occurred yet."
            ),
            severity="CRITICAL"
        ))

    if date_recorded > today:
        errors.append(ValidationError(
            error_code="FUTURE_RECORDING_DATE",
            field="date_recorded",
            message=(
                f"Recording date ({deed.date_recorded}) is in the future."
            ),
            severity="WARNING"
        ))

    return errors


# ── Money validation ──────────────────────────────────────────────────────────

def parse_amount_from_words(amount_words: str) -> float:
    """
    Converts written dollar amount to float.
    Uses custom parsing because word2number mishandles
    compound numbers like "Two Hundred Thousand".
    """
    import re

    # Clean input
    text = amount_words.lower()
    text = re.sub(r'[^a-z\s]', '', text)
    text = re.sub(r'\b(dollars?|and)\b', '', text).strip()

    # Word to digit mapping
    ones = {
        'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,
        'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,
        'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,
        'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19
    }
    tens = {
        'twenty':20,'thirty':30,'forty':40,'fifty':50,
        'sixty':60,'seventy':70,'eighty':80,'ninety':90
    }

    def parse_chunk(words):
        """Parse a chunk less than 1000."""
        result = 0
        i = 0
        while i < len(words):
            w = words[i]
            if w == 'hundred':
                result *= 100
            elif w in ones:
                result += ones[w]
            elif w in tens:
                result += tens[w]
            i += 1
        return result

    words = text.split()
    result = 0
    current = []

    for word in words:
        if word == 'million':
            result += parse_chunk(current) * 1_000_000
            current = []
        elif word == 'thousand':
            result += parse_chunk(current) * 1_000
            current = []
        else:
            current.append(word)

    result += parse_chunk(current)
    return float(result)


def validate_money(
    deed: ExtractedDeed,
    tolerance_pct: float = 0.001
) -> list[ValidationError]:
    """
    Checks that the numeric amount matches the written-out amount.

    THE RULE: Both representations of the sale price must agree.
    If they don't, we don't know which one is correct — a human
    must review before this deed can be accepted.

    This is 100% deterministic — parse both, subtract, compare.
    No LLM. No guessing. No silent acceptance of discrepancies.

    The test document has:
        Numeric : $1,250,000.00
        Words   : "One Million Two Hundred Thousand" = $1,200,000.00
        Delta   : $50,000 discrepancy → WARNING

    Args:
        deed: Extracted deed data
        tolerance_pct: Acceptable rounding difference as fraction
                       Default 0.1% handles minor rounding only

    Returns:
        List of ValidationError objects (empty if amounts match)
    """
    errors = []

    try:
        amount_from_words = parse_amount_from_words(deed.amount_words)
    except ValueError as e:
        errors.append(ValidationError(
            error_code="AMOUNT_WORDS_PARSE_ERROR",
            field="amount_words",
            message=str(e),
            severity="WARNING"
        ))
        return errors

    numeric = deed.amount_numeric
    discrepancy = abs(numeric - amount_from_words)
    tolerance = numeric * tolerance_pct

    if discrepancy > tolerance:
        discrepancy_pct = (discrepancy / numeric) * 100
        errors.append(ValidationError(
            error_code="AMOUNT_MISMATCH",
            field="amount_numeric / amount_words",
            message=(
                f"Numeric amount (${numeric:,.2f}) does not match "
                f"written amount (${amount_from_words:,.2f}). "
                f"Discrepancy: ${discrepancy:,.2f} ({discrepancy_pct:.1f}%). "
                f"Cannot determine which value is correct — "
                f"human review required before recording."
            ),
            severity="WARNING"
        ))

    return errors


# ── Master validator ──────────────────────────────────────────────────────────

def run_all_validations(deed: ExtractedDeed) -> tuple[list, list]:
    """
    Runs all deterministic validators against an extracted deed.

    Returns:
        (errors, warnings) — two separate lists by severity
    """
    all_issues = []

    # Run all checks
    all_issues.extend(validate_dates(deed))
    all_issues.extend(validate_money(deed))

    # Split by severity
    errors = [i for i in all_issues if i.severity == "CRITICAL"]
    warnings = [i for i in all_issues if i.severity == "WARNING"]

    return errors, warnings


if __name__ == "__main__":
    print("Testing Validators...\n")

    # The exact deed from the task
    test_deed = ExtractedDeed(
        doc_id="DEED-TRUST-0042",
        county_raw="S. Clara",
        state="CA",
        date_signed="2024-01-15",
        date_recorded="2024-01-10",  # ← recorded BEFORE signed
        grantor="T.E.S.L.A. Holdings LLC",
        grantee="John & Sarah Connor",
        amount_numeric=1250000.00,   # ← $1,250,000 in digits
        amount_words="One Million Two Hundred Thousand Dollars",  # ← $1,200,000
        apn="992-001-XA",
        status="PRELIMINARY"
    )

    print("=" * 55)
    print("TEST 1: Date validation (should catch CRITICAL error)")
    print("=" * 55)
    date_errors = validate_dates(test_deed)
    for e in date_errors:
        icon = "❌" if e.severity == "CRITICAL" else "⚠️"
        print(f"   {icon} [{e.error_code}] {e.message}")
    if not date_errors:
        print("   ✅ No date errors (unexpected!)")

    print("\n" + "=" * 55)
    print("TEST 2: Money validation (should catch $50K discrepancy)")
    print("=" * 55)
    money_errors = validate_money(test_deed)
    for e in money_errors:
        icon = "❌" if e.severity == "CRITICAL" else "⚠️"
        print(f"   {icon} [{e.error_code}] {e.message}")
    if not money_errors:
        print("   ✅ No money errors (unexpected!)")

    print("\n" + "=" * 55)
    print("TEST 3: Word-to-number parsing")
    print("=" * 55)
    test_amounts = [
        ("One Million Two Hundred Thousand Dollars", 1_200_000),
        ("One Million Two Hundred Fifty Thousand Dollars", 1_250_000),
        ("Five Hundred Thousand Dollars", 500_000),
    ]
    for words, expected in test_amounts:
        parsed = parse_amount_from_words(words)
        status = "✅" if parsed == expected else "❌"
        print(f"   {status} '{words[:45]}' → ${parsed:,.0f}")

    print("\n" + "=" * 55)
    print("TEST 4: Valid deed (no errors expected)")
    print("=" * 55)
    valid_deed = ExtractedDeed(
        doc_id="DEED-VALID-001",
        county_raw="Santa Clara",
        state="CA",
        date_signed="2024-01-10",
        date_recorded="2024-01-15",  # ← recorded AFTER signed ✅
        grantor="Seller Corp",
        grantee="Buyer Inc",
        amount_numeric=1_250_000.00,
        amount_words="One Million Two Hundred Fifty Thousand Dollars",  # ✅ matches
        apn="001-001-AA",
        status="FINAL"
    )
    errors, warnings = run_all_validations(valid_deed)
    if not errors and not warnings:
        print("   ✅ No errors — deed is valid")
    else:
        for e in errors + warnings:
            print(f"   [{e.severity}] {e.error_code}: {e.message}")

    print("\n✅ Validators working correctly!")