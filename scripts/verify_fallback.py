"""Non-model verification of fallback middleware + cooldown + graceful run_round failure."""
import logging
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core import cooldown as cd
from agent.core.fallback import LoggingModelFallbackMiddleware
from engine.core import PartyContext, run_round
from settings.settings import Settings


class _CapturingHandler(logging.Handler):
    """Collect LogRecords by level so the test can assert the right ones were emitted."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def levels(self) -> list[int]:
        return [r.levelno for r in self.records]

    def messages(self) -> list[str]:
        return [r.getMessage() for r in self.records]


class _FakeRequest:
    """Mock of langchain's ModelRequest with just enough API: `.override(model=...)` returns self."""

    def __init__(self, model: str = "primary") -> None:
        self.model = model

    def override(self, *, model):
        return _FakeRequest(model=model)


def _attach_capture() -> _CapturingHandler:
    logger = logging.getLogger("pywf.fallback")
    logger.setLevel(logging.DEBUG)
    handler = _CapturingHandler()
    logger.addHandler(handler)
    return handler


def _detach(handler: _CapturingHandler) -> None:
    logging.getLogger("pywf.fallback").removeHandler(handler)


def verify_settings_default() -> None:
    print("--- settings ---")
    s = Settings()
    assert s.model_timeout_s == 30, s.model_timeout_s
    print(f"ok  model_timeout_s default is 30s")


def verify_primary_success() -> None:
    print()
    print("--- primary succeeds, no logs ---")
    captured = _attach_capture()
    try:
        mw = LoggingModelFallbackMiddleware("thorin", [])
        sentinel = object()
        got = mw.wrap_model_call(_FakeRequest(), lambda req: sentinel)
        assert got is sentinel
        # No warning or error should have been emitted on the happy path.
        bad = [r for r in captured.records if r.levelno >= logging.WARNING]
        assert not bad, [r.getMessage() for r in bad]
        print("ok  primary success passes through with no fallback logs")
    finally:
        _detach(captured)


def verify_fallback_fires_on_exception() -> None:
    print()
    print("--- primary raises, fallback succeeds ---")
    captured = _attach_capture()
    try:
        fallback_model = types.SimpleNamespace(_name="fake-fallback")
        mw = LoggingModelFallbackMiddleware("thorin", [fallback_model])
        sentinel = object()

        def handler(req: _FakeRequest):
            if req.model == "primary":
                raise RuntimeError("503 UNAVAILABLE (simulated)")
            return sentinel

        got = mw.wrap_model_call(_FakeRequest(), handler)
        assert got is sentinel
        msgs = captured.messages()
        assert any("primary failed" in m and "RuntimeError" in m for m in msgs), msgs
        assert any("trying fallback[0]" in m for m in msgs), msgs
        print("ok  primary RuntimeError -> warning log + fallback invoked")
    finally:
        _detach(captured)


def verify_all_fail_raises_last() -> None:
    print()
    print("--- all models fail -> last exception reraised ---")
    captured = _attach_capture()
    try:
        mw = LoggingModelFallbackMiddleware(
            "thorin",
            [types.SimpleNamespace(_name="f0"), types.SimpleNamespace(_name="f1")],
        )

        def handler(req: _FakeRequest):
            raise RuntimeError(f"fail-{req.model}")

        raised: Exception | None = None
        try:
            mw.wrap_model_call(_FakeRequest(), handler)
        except Exception as e:
            raised = e
        assert raised is not None
        # Last attempt was fallback[1] = SimpleNamespace f1 → model is that object; str() renders generically.
        msgs = captured.messages()
        assert any("exhausted 3 candidate(s)" in m for m in msgs), msgs
        assert any(r.levelno == logging.ERROR for r in captured.records)
        print(f"ok  all-fail raised {type(raised).__name__}: {raised}; error log emitted")
    finally:
        _detach(captured)


def verify_build_chat_model() -> None:
    print()
    print("--- build_chat_model ---")
    from agent.core.models import build_chat_model
    from langchain_openai import ChatOpenAI

    m = build_chat_model("openrouter:nvidia/nemotron-3-super-120b-a12b:free", timeout=30)
    assert isinstance(m, ChatOpenAI), type(m)
    base = getattr(m, "openai_api_base", None) or getattr(m, "base_url", None)
    assert str(base) == "https://openrouter.ai/api/v1", base
    model_name = getattr(m, "model_name", None) or getattr(m, "model", "")
    assert str(model_name).startswith("nvidia/nemotron"), model_name
    print(f"ok  openrouter:... spec -> ChatOpenAI base_url={base} model={model_name}")

    g = build_chat_model("google_genai:gemini-3.7-flash", timeout=30)
    assert type(g).__name__ == "ChatGoogleGenerativeAI", type(g)
    print(f"ok  google_genai:... spec -> {type(g).__name__}")


def verify_cooldown_registry() -> None:
    print()
    print("--- cooldown registry ---")

    class Fake: pass
    m1, m2 = Fake(), Fake()
    cd.register_model(m1, "test:a")
    cd.register_model(m2, "test:b")
    assert not cd.is_on_cooldown(m1) and not cd.is_on_cooldown(m2)

    class FakeHeaders:
        def get(self, key):
            return "60" if key.lower() == "retry-after" else None

    class FakeResp:
        headers = FakeHeaders()

    class RateLimitError(Exception):
        response = FakeResp()

    secs = cd.start_cooldown(m1, RateLimitError("429 Too Many Requests"))
    assert secs == 60, secs
    assert cd.is_on_cooldown(m1) and not cd.is_on_cooldown(m2)
    assert cd.spec_for(m1) == "test:a"

    snap = cd.snapshot()
    assert "test:a" in snap and snap["test:a"]["remaining_s"] > 0
    print(f"ok  register / start / is_on_cooldown / snapshot (secs={secs})")

    # Clean up so later tests see a fresh state.
    cd._until.pop("test:a", None)


def verify_cooldown_default_eight_hours() -> None:
    print()
    print("--- cooldown default (no retry hint -> 8h) ---")

    class Fake: pass
    m = Fake()
    cd.register_model(m, "test:no-hint")
    secs = cd.start_cooldown(m, Exception("something generic"))
    assert secs == 8 * 3600, secs
    print(f"ok  no retry hint -> default {secs}s")
    cd._until.pop("test:no-hint", None)


def verify_is_quota_error() -> None:
    print()
    print("--- is_quota_error ---")

    class ResourceExhausted(Exception): pass
    class RateLimitError(Exception): pass
    assert cd.is_quota_error(ResourceExhausted("x"))
    assert cd.is_quota_error(RateLimitError("x"))
    assert cd.is_quota_error(Exception("Got 429 from upstream"))
    assert cd.is_quota_error(Exception("quota exceeded"))
    assert cd.is_quota_error(Exception("Rate Limit hit"))
    assert not cd.is_quota_error(Exception("timeout"))
    assert not cd.is_quota_error(Exception("ServiceUnavailable"))
    print("ok  quota detection covers Resource/RateLimit/429/quota/rate limit; rejects noise")


def verify_middleware_skips_cooldown() -> None:
    print()
    print("--- middleware skips cooled-down candidates ---")
    captured = _attach_capture()
    cooldown_capture = _CapturingHandler()
    logging.getLogger("pywf.cooldown").setLevel(logging.DEBUG)
    logging.getLogger("pywf.cooldown").addHandler(cooldown_capture)
    try:
        primary = types.SimpleNamespace(_n="primary")
        fb0 = types.SimpleNamespace(_n="fb0")
        cd.register_model(primary, "test:primary")
        cd.register_model(fb0, "test:fb0")

        cd._until["test:primary"] = time.monotonic() + 300  # artificially cool
        try:
            mw = LoggingModelFallbackMiddleware("thorin", [fb0])
            seen: list[str] = []

            class Req:
                def __init__(self, model=primary):
                    self.model = model
                def override(self, *, model):
                    return Req(model=model)

            def handler(req):
                seen.append(getattr(req.model, "_n", "?"))
                return "ok"

            got = mw.wrap_model_call(Req(), handler)
            assert got == "ok" and seen == ["fb0"], (got, seen)
            cooldown_msgs = cooldown_capture.messages()
            assert any("skipping primary" in m for m in cooldown_msgs), cooldown_msgs
            print("ok  primary on cooldown is skipped; fallback is called")
        finally:
            cd._until.pop("test:primary", None)
    finally:
        _detach(captured)
        logging.getLogger("pywf.cooldown").removeHandler(cooldown_capture)


def verify_middleware_all_on_cooldown() -> None:
    print()
    print("--- middleware all-on-cooldown raises ---")
    primary = types.SimpleNamespace(_n="solo")
    cd.register_model(primary, "test:solo")
    cd._until["test:solo"] = time.monotonic() + 300
    try:
        mw = LoggingModelFallbackMiddleware("thorin", [])

        class Req:
            model = primary
            def override(self, *, model):
                return self

        raised: Exception | None = None
        try:
            mw.wrap_model_call(Req(), lambda r: "unreachable")
        except RuntimeError as e:
            raised = e
        assert raised is not None and "cooldown" in str(raised).lower(), raised
        print(f"ok  all-on-cooldown raised: {raised}")
    finally:
        cd._until.pop("test:solo", None)


def verify_quota_triggers_cooldown() -> None:
    print()
    print("--- quota error triggers cooldown ---")
    captured = _attach_capture()
    try:
        primary = types.SimpleNamespace(_n="primary-429")
        fb0 = types.SimpleNamespace(_n="fb0-ok")
        cd.register_model(primary, "test:primary-429")
        cd.register_model(fb0, "test:fb0-ok")

        class ResourceExhausted(Exception):
            pass

        def handler(req):
            if getattr(req.model, "_n", "?") == "primary-429":
                raise ResourceExhausted("429 quota exceeded")
            return "ok"

        class Req:
            def __init__(self, model=primary):
                self.model = model
            def override(self, *, model):
                return Req(model=model)

        mw = LoggingModelFallbackMiddleware("thorin", [fb0])
        got = mw.wrap_model_call(Req(), handler)
        assert got == "ok"
        assert cd.is_on_cooldown(primary)
        assert not cd.is_on_cooldown(fb0)
        msgs = captured.messages()
        assert any("hit quota" in m and "cooling" in m for m in msgs), msgs
        print(f"ok  ResourceExhausted triggered cooldown; snapshot: {cd.snapshot()}")
    finally:
        cd._until.pop("test:primary-429", None)
        _detach(captured)


def verify_run_round_graceful_failure() -> None:
    print()
    print("--- run_round graceful failure ---")
    # Build a fake PartyContext: two agents, the first raises on invoke, the second
    # would succeed. Expected: one error turn, round stopped (second never runs).
    def raiser(*_, **__):
        raise RuntimeError("hard fail")

    def happy(*_, **__):
        return {"messages": [types.SimpleNamespace(content="should not be reached", type="ai")]}

    ctx = PartyContext(
        agents={"bad": types.SimpleNamespace(invoke=raiser), "good": types.SimpleNamespace(invoke=happy)},
        names={"bad": "Bad Guy", "good": "Good Guy"},
        party_ids=["bad", "good"],
        store=None,
    )
    turns = run_round(ctx, "hello", ["bad", "good"])
    assert len(turns) == 1, turns
    assert turns[0]["character_id"] == "bad"
    assert turns[0]["name"] == "Bad Guy"
    assert turns[0]["text"].startswith("[error: RuntimeError: hard fail"), turns[0]["text"]
    print("ok  bad agent emits error turn; good agent is skipped (round stops)")


def main() -> int:
    verify_settings_default()
    verify_primary_success()
    verify_fallback_fires_on_exception()
    verify_all_fail_raises_last()
    verify_cooldown_registry()
    verify_cooldown_default_eight_hours()
    verify_is_quota_error()
    verify_middleware_skips_cooldown()
    verify_middleware_all_on_cooldown()
    verify_quota_triggers_cooldown()
    verify_build_chat_model()
    verify_run_round_graceful_failure()
    print()
    print("all fallback verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
