"""One-shot: dump the rendered x-data attribute from /characters/new to verify quoting."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.app import app

with TestClient(app) as c:
    r = c.get("/characters/new")
    for line in r.text.splitlines():
        if "x-data" in line:
            print(line[:400])
            break
    print("---")
    # Also dump the Add-class button line to confirm {{...}} escaping
    for line in r.text.splitlines():
        if "Add class" in line:
            print(line[:400])
            break
