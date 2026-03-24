"""
main.py — Run the deed validator as a CLI demo.

This is the quickest way to see the full pipeline in action
without starting the API server.

Usage:
    python main.py              # runs on task deed
    python main.py --api        # starts FastAPI server
"""

import sys
import argparse
from deed_processor import process_deed
from llm_extractor import RAW_DEED_TEXT


def main():
    parser = argparse.ArgumentParser(
        description="Propy Bad Deed Validator"
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Start FastAPI server instead of CLI demo"
    )
    args = parser.parse_args()

    if args.api:
        import uvicorn
        print("\n🚀 Starting Propy Deed Validator API")
        print("   Docs : http://localhost:8000/docs")
        print("   Demo : http://localhost:8000/validate/demo\n")
        uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
        return

    print("=" * 55)
    print("  Propy Bad Deed Validator")
    print("  Processing task deed...")
    print("=" * 55)

    result = process_deed(RAW_DEED_TEXT)

    # Exit code signals validity — useful for scripting
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()