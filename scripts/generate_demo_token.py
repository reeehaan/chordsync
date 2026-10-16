"""Generate demo bearer tokens and the verifier document for SSM.

    python scripts/generate_demo_token.py --id tester-1 [--id tester-2 ...]

Each token is printed once to stderr; give it to that tester. The verifier
document (SHA-256 hashes only) goes to stdout. Store it as the SecureString
SSM parameter. This script never talks to AWS. Don't commit or log the tokens.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.app.auth import token_sha256  # noqa: E402


def generate(ids: list[str]) -> tuple[dict[str, str], str]:
    tokens = {label: secrets.token_urlsafe(32) for label in ids}  # 256 bits each
    document = json.dumps(
        {
            "version": 1,
            "tokens": [{"id": label, "sha256": token_sha256(token)} for label, token in tokens.items()],
        },
        indent=2,
    )
    return tokens, document


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--id", dest="ids", action="append", required=True, help="token label")
    arguments = parser.parse_args(argv)
    tokens, document = generate(arguments.ids)
    print("Tokens (shown once; give each to its tester):", file=sys.stderr)
    for label, token in tokens.items():
        print(f"  {label}: {token}", file=sys.stderr)
    print(document)


if __name__ == "__main__":
    main()
