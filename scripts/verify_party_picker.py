"""Non-model verification of the party-picker: build_party kwarg, POST /api/party, chat page markup."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.app import app
from engine.core import Initiative, parse_dm_line


def main() -> int:
    with TestClient(app) as c:
        # --- Baseline: env default party is loaded.
        print("--- baseline party ---")
        r = c.get("/party")
        assert r.status_code == 200
        initial = [p["id"] for p in r.json()["party"]]
        assert initial, f"startup party should be non-empty from env default, got {initial}"
        print(f"ok  initial party from env: {initial}")

        try:
            # --- POST /api/party with a smaller valid party.
            print()
            print("--- POST /api/party happy path ---")
            r = c.post("/api/party", json={"character_ids": ["thorin"]})
            assert r.status_code == 200, f"{r.status_code} {r.text}"
            assert [p["id"] for p in r.json()["party"]] == ["thorin"]
            # The ctx actually swapped: /party now reflects the new roster.
            assert [p["id"] for p in c.get("/party").json()["party"]] == ["thorin"]
            print("ok  POST /api/party shrinks party to ['thorin'], /party reflects")

            # --- Validation errors.
            print()
            print("--- validation ---")
            r = c.post("/api/party", json={"character_ids": []})
            assert r.status_code == 400 and r.json()["detail"]["error"] == "empty party"
            print("ok  empty list -> 400 'empty party'")

            r = c.post("/api/party", json={"character_ids": ["ghost"]})
            assert r.status_code == 400
            d = r.json()["detail"]
            assert d["error"] == "unknown character(s)" and d["missing"] == ["ghost"]
            print("ok  unknown id -> 400 with missing list")

            # --- POST /chat on an empty-party ctx would 400; but we can't easily force empty here.
            # Instead ensure the current (thorin-only) party still accepts dm payload shape.
            r = c.post("/chat", json={"dm": ""})
            assert r.status_code == 400
            print("ok  POST /chat empty dm still 400 (unchanged)")

            # --- Chat page markup: picker is present.
            print()
            print("--- chat page markup ---")
            body = c.get("/chat").text
            for frag in [
                '<section id="picker">',
                'id="roster-choices"',
                'id="start"',
                'id="change-party"',
                '/api/characters',
                '/api/party',
                'id="change-party-wrap"',
                '<form id="f" hidden>',
                "/characters/' + encodeURIComponent(t.character_id) + '/edit",
                'target="_blank"',
                '/characters/${encodeURIComponent(p.id)}/edit',
                '<section id="initiative"',
                'id="init-list"',
                'id="init-enabled"',
                'sortablejs',
                'openInitiative',
            ]:
                assert frag in body, f"missing in /chat body: {frag!r}"
            print(f"ok  /chat page contains picker + initiative markup ({len(body)} bytes)")

            # --- Agent cache reuse: same party selected twice reuses the agent instances.
            print()
            print("--- agent cache ---")
            r = c.post("/api/party", json={"character_ids": initial})
            assert r.status_code == 200
            # Peer names (not ids) are baked into the cache key, mirroring the system prompt.
            names_by_id = {p["id"]: p["name"] for p in r.json()["party"]}
            peer_key = lambda cid: frozenset(names_by_id[o] for o in initial if o != cid)
            first_agents = {cid: id(app.state.agent_cache[(cid, peer_key(cid))]) for cid in initial}
            r = c.post("/api/party", json={"character_ids": initial})
            assert r.status_code == 200
            second_agents = {cid: id(app.state.agent_cache[(cid, peer_key(cid))]) for cid in initial}
            assert first_agents == second_agents, (first_agents, second_agents)
            # The live ctx must also be using the cached agent instances, not fresh ones.
            for cid in initial:
                assert id(app.state.ctx.agents[cid]) == first_agents[cid]
            print(f"ok  repeat POST /api/party reuses cached agents (ids: {first_agents})")

            if len(initial) >= 2:
                singleton = [initial[0]]
                r = c.post("/api/party", json={"character_ids": singleton})
                assert r.status_code == 200
                assert (singleton[0], frozenset()) in app.state.agent_cache
                print("ok  distinct composition populates a new cache entry")

            # --- Initiative order
            print()
            print("--- initiative order ---")
            # Make sure the full initial party is loaded for this section.
            c.post("/api/party", json={"character_ids": initial})

            # Engine-level: parse_dm_line respects Initiative(enabled=True) and @id override.
            parsed = parse_dm_line("hello", initial, initiative=Initiative(True, list(reversed(initial))))
            assert parsed.order == list(reversed(initial)), parsed.order
            parsed = parse_dm_line(f"@{initial[0]} hi", initial, initiative=Initiative(True, initial))
            assert parsed.order == [initial[0]], parsed.order
            print("ok  parse_dm_line honours Initiative + @id override")

            # Baseline: seeded from current party, disabled.
            r = c.get("/api/initiative")
            assert r.status_code == 200
            state = r.json()
            assert state["enabled"] is False, state
            assert set(state["order"]) == set(initial), state
            print(f"ok  GET /api/initiative baseline (enabled={state['enabled']}, order={state['order']})")

            # POST valid: reversed order enforced.
            reversed_party = list(reversed(initial))
            r = c.post("/api/initiative", json={"enabled": True, "order": reversed_party})
            assert r.status_code == 200, r.text
            assert r.json()["order"] == reversed_party and r.json()["enabled"] is True
            print(f"ok  POST /api/initiative saves {reversed_party} enabled")

            # Validation: unknown id.
            r = c.post("/api/initiative", json={"enabled": True, "order": initial + ["ghost"]})
            assert r.status_code == 400 and r.json()["detail"]["error"] == "unknown character(s)"
            print("ok  unknown id -> 400")

            # Validation: missing a party member.
            if len(initial) >= 2:
                r = c.post("/api/initiative", json={"enabled": True, "order": [initial[0]]})
                assert r.status_code == 400 and r.json()["detail"]["error"].startswith("order must include")
                print("ok  missing member -> 400")

            # Validation: duplicate.
            r = c.post("/api/initiative", json={"enabled": True, "order": [initial[0], initial[0]]})
            assert r.status_code == 400 and r.json()["detail"]["error"] == "duplicate ids in order"
            print("ok  duplicate id -> 400")

            # Reconcile on party-swap: shrink then expand.
            if len(initial) >= 2:
                c.post("/api/party", json={"character_ids": [initial[0]]})
                after_shrink = c.get("/api/initiative").json()
                assert after_shrink["order"] == [initial[0]], after_shrink
                assert after_shrink["enabled"] is True, after_shrink
                c.post("/api/party", json={"character_ids": initial})
                after_expand = c.get("/api/initiative").json()
                assert after_expand["order"][0] == initial[0], after_expand
                assert set(after_expand["order"]) == set(initial), after_expand
                print(f"ok  reconcile on party change (shrink={after_shrink['order']}, expand={after_expand['order']})")
        finally:
            # Restore the env default for subsequent runs/suites.
            if initial:
                c.post("/api/party", json={"character_ids": initial})

    print()
    print("all party-picker verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
