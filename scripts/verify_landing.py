"""Non-model verification of the new landing page, chat move, and memory split."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.app import app


def main() -> int:
    with TestClient(app) as c:
        print("--- landing page (/) ---")
        r = c.get("/")
        assert r.status_code == 200
        body = r.text
        for frag in [
            '<h1>pywf</h1>',
            '<section class="card">',
            '>Chat</h2>',
            '>Characters</h2>',
            '>Memory</h2>',
            'href="/chat"',
            'href="/characters/new"',
            'href="/characters"',
            'href="/memory"',
        ]:
            assert frag in body, f"missing in landing: {frag!r}"
        # Character count rendered as a number.
        assert "character(s) in the database" in body
        print(f"ok  GET / -> 200 ({len(body)} bytes), all three cards + required links present")

        print()
        print("--- chat moved to /chat ---")
        r = c.get("/chat")
        assert r.status_code == 200
        chat_body = r.text
        assert 'id="f"' in chat_body
        assert 'id="roster"' in chat_body
        assert "Back to home" in chat_body
        # Chat page should NOT include the shared _NAV links to Characters/Memory.
        # (Back link is the only navigation.)
        assert '>Characters</a>' not in chat_body
        assert '>Memory</a>' not in chat_body
        print(f"ok  GET /chat -> 200 ({len(chat_body)} bytes), has form + back link, no _NAV")

        # POST /chat still works for routing (even though we won't run a model).
        r = c.post("/chat", json={"dm": ""})
        assert r.status_code == 400
        print("ok  POST /chat still enforces empty-dm 400")

        print()
        print("--- memory split: HTML / JSON ---")
        r = c.get("/memory")
        assert r.status_code == 200
        mem_body = r.text
        assert "<table>" in mem_body
        for col in ["thread rounds", "thread msgs", "rounds until archive", "episodes", "chronicle", "archived rounds"]:
            assert col in mem_body, f"missing column header: {col!r}"
        print(f"ok  GET /memory -> 200 HTML ({len(mem_body)} bytes)")

        r = c.get("/api/memory")
        assert r.status_code == 200
        data = r.json()
        assert "party" in data and isinstance(data["party"], list)
        # Shape check: each entry has the same keys previous /memory produced.
        if data["party"]:
            expected = {
                "character_id", "name", "thread_rounds", "thread_messages",
                "rounds_until_archive", "episodes", "has_chronicle", "archived_rounds",
            }
            actual = set(data["party"][0].keys())
            missing = expected - actual
            assert not missing, f"api/memory lost keys: {missing}"
        print(f"ok  GET /api/memory -> 200 JSON (shape preserved)")

        # Old JSON route must be gone (now HTML).
        r = c.get("/memory", headers={"Accept": "application/json"})
        # We're not content-negotiating; /memory is HTML regardless of Accept.
        assert r.headers["content-type"].startswith("text/html")
        print("ok  /memory is HTML regardless of Accept header")

        print()
        print("--- nav parity ---")
        for path in ["/characters", "/memory", "/"]:
            body = c.get(path).text
            for nav_link in ['href="/"', 'href="/chat"', 'href="/characters"', 'href="/memory"']:
                assert nav_link in body, f"{path} missing nav link {nav_link!r}"
            print(f"ok  {path} has all four nav links")

        chat_body = c.get("/chat").text
        assert "<nav>" not in chat_body, "chat page should not contain the shared <nav>"
        print("ok  /chat has no <nav> element")

    print()
    print("all landing-page verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
