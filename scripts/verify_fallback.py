"""Non-model verification of fallback middleware + graceful run_round failure."""
import logging
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
        assert any("exhausted 3 model(s)" in m for m in msgs), msgs
        assert any(r.levelno == logging.ERROR for r in captured.records)
        print(f"ok  all-fail raised {type(raised).__name__}: {raised}; error log emitted")
    finally:
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
    verify_run_round_graceful_failure()
    print()
    print("all fallback verifications passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
