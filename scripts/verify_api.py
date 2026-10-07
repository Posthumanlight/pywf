"""Non-model verification of the FastAPI frontend. Does not call the LLM."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.app import app
from engine.core import ParsedLine, UnknownTargetError, parse_dm_line


def main() -> int:
    print("--- parser parity ---")
    r = parse_dm_line("@thorin hi", ["thorin", "mira"])
    assert r == ParsedLine(order=["thorin"], dm_text="hi"), r
    print("ok  @thorin hi -> order=['thorin'], dm='hi'")

    r = parse_dm_line("hello party", ["thorin", "mira"])
    assert sorted(r.order) == ["mira", "thorin"] and r.dm_text == "hello party", r
    print(f"ok  'hello party' -> shuffled {r.order}, dm='hello party'")

    try:
        parse_dm_line("@ghost hi", ["thorin", "mira"])
        print("FAIL: expected UnknownTargetError")
        return 1
    except UnknownTargetError as exc:
        assert exc.target == "ghost" and exc.party_ids == ["thorin", "mira"]
        print("ok  @ghost hi -> UnknownTargetError(target='ghost')")

    print()
    print("--- API routes via TestClient ---")
    with TestClient(app) as client:
        resp = client.get("/party")
        assert resp.status_code == 200
        data = resp.json()
        print("ok  GET /party ->", data)
        assert {p["id"] for p in data["party"]} == {"thorin", "mira"}

        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "<title>pywf</title>" in html
        assert 'id="roster"' in html
        print(f"ok  GET / -> HTMLResponse ({len(html)} bytes), title + roster present")

        resp = client.post("/chat", json={"dm": "@ghost hi"})
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "unknown party member"
        assert detail["target"] == "ghost"
        assert sorted(detail["party"]) == ["mira", "thorin"]
        print("ok  POST /chat {@ghost hi} -> 400", detail)

        resp = client.post("/chat", json={"dm": ""})
        assert resp.status_code == 400
        print("ok  POST /chat {empty dm} -> 400")

    print()
    print("all non-model verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
