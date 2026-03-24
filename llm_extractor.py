"""
llm_extractor.py — LLM-powered structured data extraction.

THE ONLY JOB OF THIS FILE:
--------------------------
Take messy OCR text → return a clean ExtractedDeed object.

That's it. The LLM does NOT validate. The LLM does NOT calculate.
The LLM does NOT make decisions about whether the deed is valid.

It reads messy text and fills in a structured form. Like a very
smart copy-paste.

WHY GROQ (LLAMA 3.3 70B)?
--------------------------
- Free tier with generous rate limits
- Llama 3.3 70B is production-quality for structured extraction
- Fast inference (~1-2 seconds)
- Model-agnostic design — swap to GPT-4o or Claude in one line

WHY JSON STRUCTURED OUTPUT?
----------------------------
We instruct the LLM to return ONLY valid JSON matching our schema.
We parse and validate it with Pydantic immediately.
If the LLM returns malformed JSON or missing fields — we catch it
and raise a clear error rather than letting bad data propagate.
"""

import json
import os
import re
import ssl
import certifi
from dotenv import load_dotenv
from groq import Groq
from models import ExtractedDeed

ssl._create_default_https_context = ssl.create_default_context
os.environ['SSL_CERT_FILE'] = certifi.where()

load_dotenv()

# The exact OCR text from the task
RAW_DEED_TEXT = """
*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara | State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-10
Grantor: T.E.S.L.A. Holdings LLC
Grantee: John & Sarah Connor
Amount: $1,250,000.00 (One Million Two Hundred Thousand Dollars)
APN: 992-001-XA
Status: PRELIMINARY
*** END ***
"""

SYSTEM_PROMPT = """You are a precise document parser for real estate deeds.
Your ONLY job is to extract structured data from messy OCR text and return it as JSON.

RULES:
- Return ONLY valid JSON — no explanation, no markdown, no preamble
- Extract dates in YYYY-MM-DD format exactly as written
- Extract the numeric dollar amount as a float (digits only, no commas)
- Extract the written dollar amount exactly as it appears in words
- Do NOT fix errors — if dates look wrong, extract them anyway
- Do NOT validate — just extract what is written
- If a field is missing, use null"""

EXTRACTION_PROMPT = """Extract all fields from this deed document and return as JSON:

{deed_text}

Return this exact JSON structure:
{{
  "doc_id": "document identifier",
  "county_raw": "county as written",
  "state": "two letter state code",
  "date_signed": "YYYY-MM-DD",
  "date_recorded": "YYYY-MM-DD",
  "grantor": "entity transferring property",
  "grantee": "entity receiving property",
  "amount_numeric": 0.00,
  "amount_words": "amount written in words",
  "apn": "assessor parcel number",
  "status": "document status"
}}

Return ONLY the JSON object. No other text."""


def clean_json_response(raw: str) -> str:
    """
    Cleans LLM response to extract valid JSON.
    Handles markdown code blocks and extra whitespace.
    """
    # Strip markdown code blocks if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            if "{" in part:
                raw = part
                if raw.startswith("json"):
                    raw = raw[4:]
                break

    # Find JSON object boundaries
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    return raw.strip()


def extract_deed(raw_text: str = None) -> ExtractedDeed:
    """
    Uses Groq LLM to extract structured data from raw OCR deed text.

    Args:
        raw_text: OCR text to parse. Uses default task text if None.

    Returns:
        ExtractedDeed — validated Pydantic object

    Raises:
        ValueError: If LLM returns unparseable JSON
        ValidationError: If extracted data fails Pydantic validation
    """
    if raw_text is None:
        raw_text = RAW_DEED_TEXT

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    print("   🤖 Calling LLM for extraction...")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": EXTRACTION_PROMPT.format(
                deed_text=raw_text
            )}
        ],
        temperature=0.0,   # zero temp — extraction should be deterministic
        max_tokens=500
    )

    raw_json = response.choices[0].message.content.strip()
    print(f"   ✅ LLM response received ({len(raw_json)} chars)")

    # Clean and parse
    cleaned = clean_json_response(raw_json)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON: {e}\n"
            f"Raw response: {raw_json[:200]}"
        )

    # Validate with Pydantic — this catches missing/wrong-type fields
    try:
        deed = ExtractedDeed(**data)
    except Exception as e:
        raise ValueError(
            f"Extracted data failed schema validation: {e}\n"
            f"Data: {data}"
        )

    return deed


if __name__ == "__main__":
    print("Testing LLM Extractor...\n")
    print("=" * 55)
    print("Raw OCR input:")
    print("=" * 55)
    print(RAW_DEED_TEXT)

    print("=" * 55)
    print("Extracting with LLM...")
    print("=" * 55)

    deed = extract_deed(RAW_DEED_TEXT)

    print(f"\nExtracted fields:")
    print(f"   Doc ID         : {deed.doc_id}")
    print(f"   County (raw)   : {deed.county_raw}")
    print(f"   State          : {deed.state}")
    print(f"   Date Signed    : {deed.date_signed}")
    print(f"   Date Recorded  : {deed.date_recorded}")
    print(f"   Grantor        : {deed.grantor}")
    print(f"   Grantee        : {deed.grantee}")
    print(f"   Amount (num)   : ${deed.amount_numeric:,.2f}")
    print(f"   Amount (words) : {deed.amount_words}")
    print(f"   APN            : {deed.apn}")
    print(f"   Status         : {deed.status}")

    print("\n✅ LLM Extractor working correctly!")