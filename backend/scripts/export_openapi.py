"""Write the API's OpenAPI schema to a file (or stdout) without starting a server.

The frontend generates its TypeScript API types from this file
(`make api-types`), and CI fails when the committed types drift from the API.

Usage: python -m scripts.export_openapi [path]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    # Importing the app reads settings; the schema does not depend on secrets.
    os.environ.setdefault("JWT_SECRET", "openapi-export-only-not-a-real-secret-000000")
    from app.main import app

    schema = json.dumps(app.openapi(), indent=2, sort_keys=False) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(schema, encoding="utf-8")
    else:
        sys.stdout.write(schema)


if __name__ == "__main__":
    main()
