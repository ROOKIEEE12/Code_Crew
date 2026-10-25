"""Writes the API's OpenAPI schema to web/openapi.json (input for `npm run gen:api`)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402

(ROOT / "web" / "openapi.json").write_text(json.dumps(server.app.openapi(), indent=1), encoding="utf-8")
print("wrote web/openapi.json")
