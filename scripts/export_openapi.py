"""Export the actual FastAPI schema; no credentials or external calls required."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app

target = Path("docs/openapi.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(target)
