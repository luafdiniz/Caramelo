"""
Local test: parse the 3 sample receipts and show extraction quality.

Doesn't write to Sheets — just runs Gemini + matcher and prints results.

Usage:
    cd bot
    pip install -r requirements.txt
    export GEMINI_API_KEY=...
    export SPREADSHEET_ID=1hV9zTIMyX3wlULkWAYN_-nBeNeM6adfL0Zz6MIvwFXE
    export GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json
    python tests/test_parser.py
"""

import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import gemini, sheets, matcher, orchestrator


RECEIPTS = [
    "/Users/luafdiniz/Downloads/IMG_0834.heic",
    "/Users/luafdiniz/Downloads/IMG_0835.heic",
    "/Users/luafdiniz/Downloads/IMG_0836.heic",
]


def heic_to_jpg_bytes(heic_path: str) -> bytes:
    """Convert HEIC to JPG using macOS sips, return JPG bytes."""
    tmp = f"/tmp/_receipt_{os.path.basename(heic_path)}.jpg"
    subprocess.run(
        ["sips", "-s", "format", "jpeg", heic_path, "--out", tmp],
        check=True, capture_output=True,
    )
    with open(tmp, "rb") as f:
        return f.read()


def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set")
        sys.exit(1)

    # Load reference data
    use_sheets = bool(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
    if use_sheets:
        spreadsheet_id = os.environ["SPREADSHEET_ID"]
        produtos = sheets.get_produtos(spreadsheet_id)
        fornecedores = sheets.get_fornecedores(spreadsheet_id)
        print(f"Loaded {len(produtos)} produtos and {len(fornecedores)} fornecedores from Sheets\n")
    else:
        print("No GOOGLE_SERVICE_ACCOUNT_JSON — matching will be skipped\n")
        produtos = []
        fornecedores = []

    for i, heic in enumerate(RECEIPTS, 1):
        print("=" * 70)
        print(f"NOTA {i}: {os.path.basename(heic)}")
        print("=" * 70)

        # Convert HEIC → JPG (Gemini supports both, but JPG is more universal)
        try:
            img_bytes = heic_to_jpg_bytes(heic)
        except Exception as e:
            print(f"  Error converting: {e}")
            continue

        try:
            receipt = gemini.parse_receipt(img_bytes)
        except Exception as e:
            print(f"  Gemini error: {e}")
            continue

        print("\n--- RAW GEMINI OUTPUT ---")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))

        if produtos:
            enriched = matcher.enrich_receipt(receipt, produtos, fornecedores)
            print("\n--- AFTER MATCHING (Telegram preview) ---")
            print(orchestrator.format_receipt_summary(enriched))
        print()


if __name__ == "__main__":
    main()
