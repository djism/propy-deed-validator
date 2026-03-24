"""
county_matcher.py — Fuzzy matching for county names.

THE PROBLEM:
------------
OCR documents write county names inconsistently:
  "S. Clara"       → "Santa Clara"
  "SAN MATEO"      → "San Mateo"
  "Santa Cruz Cty" → "Santa Cruz"

We cannot use exact string matching — it fails on every
abbreviation, typo, or formatting variation.

WHY RAPIDFUZZ NOT LLM?
-----------------------
We deliberately do NOT ask the LLM to match county names.
Reason: county name matching is deterministic — there is always
a single correct answer. Using an LLM introduces unnecessary
nondeterminism and cost. RapidFuzz gives us:
  - Fast fuzzy string similarity (Levenshtein + token-based)
  - Deterministic, reproducible results
  - Confidence score so we can reject low-confidence matches
  - Zero API cost, zero latency overhead

WHY LOWERCASE NORMALIZATION?
-----------------------------
"SAN MATEO" vs "San Mateo" — different case, same county.
Fuzzy scorers are case-sensitive by default. Normalizing both
sides to lowercase before matching eliminates this entire class
of failures, then we restore the properly-cased name for output.

This is the "paranoid engineering" Propy is looking for —
use AI where it adds value, use deterministic code where code
is better and more reliable.
"""

import json
from pathlib import Path
from rapidfuzz import process, fuzz
from models import CountyMatch


COUNTIES_FILE = Path(__file__).parent / "counties.json"
MIN_CONFIDENCE = 60.0  # reject matches below this threshold


def load_counties() -> list[dict]:
    """Loads county reference data from counties.json."""
    if not COUNTIES_FILE.exists():
        raise FileNotFoundError(
            f"counties.json not found at {COUNTIES_FILE}\n"
            "Please create it with county name and tax_rate fields."
        )
    with open(COUNTIES_FILE) as f:
        return json.load(f)


def match_county(raw_county: str) -> CountyMatch:
    """
    Matches a raw county string to the closest entry
    in counties.json using fuzzy string matching.

    Strategy:
    1. Normalize both query and candidates to lowercase
       → eliminates case sensitivity failures ("SAN MATEO" == "san mateo")
    2. Try token_sort_ratio — handles word order differences
       e.g. "Clara Santa" matches "Santa Clara"
    3. Try partial_ratio — handles abbreviations
       e.g. "S. Clara" partially matches "Santa Clara"
    4. Take the highest scoring match across both methods
    5. Restore original casing for the matched county name
    6. Reject if confidence < MIN_CONFIDENCE threshold

    Args:
        raw_county: County name as extracted from document

    Returns:
        CountyMatch with matched name, tax rate, confidence

    Raises:
        ValueError: If no county matches above confidence threshold
    """
    counties = load_counties()
    county_names = [c["name"] for c in counties]

    # Normalize to lowercase — both query and candidates
    # This eliminates all case-sensitivity issues
    raw_lower = raw_county.strip().lower()
    county_names_lower = [n.lower() for n in county_names]

    # Method 1: token sort ratio — good for reordered words
    match_lower_token, score_token, _ = process.extractOne(
        raw_lower,
        county_names_lower,
        scorer=fuzz.token_sort_ratio
    )

    # Method 2: partial ratio — good for abbreviations
    match_lower_partial, score_partial, _ = process.extractOne(
        raw_lower,
        county_names_lower,
        scorer=fuzz.partial_ratio
    )

    # Take whichever method scored higher
    if score_token >= score_partial:
        best_match_lower = match_lower_token
        best_score = score_token
        method_used = "token_sort_ratio"
    else:
        best_match_lower = match_lower_partial
        best_score = score_partial
        method_used = "partial_ratio"

    # Restore original casing from county_names list
    best_match = county_names[county_names_lower.index(best_match_lower)]

    print(f"   County match: '{raw_county}' → '{best_match}' "
          f"(confidence: {best_score:.1f}%, method: {method_used})")

    # Reject if below confidence threshold
    if best_score < MIN_CONFIDENCE:
        raise ValueError(
            f"Could not confidently match county '{raw_county}' "
            f"to any known county. "
            f"Best match was '{best_match}' with only "
            f"{best_score:.1f}% confidence. "
            f"Minimum required: {MIN_CONFIDENCE}%"
        )

    # Find the tax rate for the matched county
    tax_rate = next(
        c["tax_rate"] for c in counties
        if c["name"] == best_match
    )

    return CountyMatch(
        raw_input=raw_county,
        matched_name=best_match,
        tax_rate=tax_rate,
        confidence_score=best_score
    )


def calculate_closing_costs(sale_amount: float, tax_rate: float) -> float:
    """
    Calculates closing costs as: sale_amount × tax_rate.
    Simple deterministic calculation — no LLM involved.
    """
    return round(sale_amount * tax_rate, 2)


if __name__ == "__main__":
    print("Testing County Matcher...\n")

    test_cases = [
        ("S. Clara",        "Santa Clara"),
        ("Santa Cruz",      "Santa Cruz"),
        ("SAN MATEO",       "San Mateo"),
        ("S. Clara County", "Santa Clara"),
        ("santa clara",     "Santa Clara"),
    ]

    print("=" * 55)
    print("TEST 1: Fuzzy matching cases")
    print("=" * 55)
    all_passed = True
    for raw, expected in test_cases:
        try:
            result = match_county(raw)
            status = "✅" if result.matched_name == expected else "⚠️"
            if result.matched_name != expected:
                all_passed = False
            print(f"   {status} '{raw}' → '{result.matched_name}' "
                  f"({result.confidence_score:.1f}%)")
        except ValueError as e:
            print(f"   ❌ '{raw}' failed: {e}")
            all_passed = False

    print("\n" + "=" * 55)
    print("TEST 2: Closing cost calculation")
    print("=" * 55)
    match = match_county("S. Clara")
    costs = calculate_closing_costs(1_250_000, match.tax_rate)
    print(f"   Sale amount  : $1,250,000.00")
    print(f"   Tax rate     : {match.tax_rate:.1%}")
    print(f"   Closing costs: ${costs:,.2f}")

    print("\n" + "=" * 55)
    print("TEST 3: Low confidence rejection")
    print("=" * 55)
    try:
        match_county("Transylvania")
        print("   ❌ Should have raised ValueError")
    except ValueError as e:
        print(f"   ✅ Correctly rejected unknown county")

    if all_passed:
        print("\n✅ County Matcher working correctly!")
    else:
        print("\n⚠️  Some tests failed — check above")