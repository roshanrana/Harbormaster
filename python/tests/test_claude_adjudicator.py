"""The live adjudicator, exercised against a stub transport.

No network. What is under test is the handling around the model: validation,
fallback, cost accounting and prompt construction. The one test that does hit
the API is opt-in and lives in tests/live.
"""

from __future__ import annotations

from typing import Any

import pytest

from inspector.mapping.tier3 import AdjudicationRequest, DeterministicFake
from inspector.mapping.tier3_llm import ClaudeAdjudicator, build_adjudicator


class Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class Usage:
    def __init__(self) -> None:
        self.input_tokens = 120
        self.output_tokens = 45
        self.cache_read_input_tokens = 80


class Response:
    def __init__(self, text: str) -> None:
        self.content = [Block(text)]
        self.usage = Usage()


class StubClient:
    """Records what was sent and returns scripted responses."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0) if self.responses else Response("{}")
        if isinstance(item, Exception):
            raise item
        return item


def request(headers: list[str] | None = None, **kw: Any) -> AdjudicationRequest:
    base: dict[str, Any] = {
        "client_id": "CLNT004",
        "client_name": "Meridian Capital Partners",
        "source_hint": "CME",
        "domain": "TRADE",
        "template_fingerprint": "tf_x",
        "unresolved_headers": ["Px_Sett"] if headers is None else headers,
        "samples": {"Px_Sett": ["99.50", "99.50"]},
    }
    base.update(kw)
    return AdjudicationRequest(**base)


def adjudicator(*responses: Any) -> tuple[ClaudeAdjudicator, StubClient]:
    client = StubClient(*responses)
    return ClaudeAdjudicator(client=client, api_key="test"), client


def test_valid_response_is_accepted() -> None:
    a, _ = adjudicator(
        Response(
            '{"fields":[{"source_field":"Px_Sett","canonical_field":"settlement_price",'
            '"confidence":0.8,"rationale":"repeats per instrument"}]}'
        )
    )
    result = a.adjudicate(request())
    field = result.as_map()["Px_Sett"]
    assert field.canonical_field == "settlement_price"
    assert field.rationale == "repeats per instrument"


def test_invented_canonical_field_is_discarded() -> None:
    # The failure mode of a mapping layer is not a crash, it is a silently
    # wrong reconciliation. A field that does not exist must not propagate.
    a, _ = adjudicator(
        Response(
            '{"fields":[{"source_field":"Px_Sett","canonical_field":"settlement_pricee",'
            '"confidence":0.95,"rationale":"looks right"}]}'
        )
    )
    field = a.adjudicate(request()).as_map()["Px_Sett"]
    assert field.canonical_field is None
    assert "unknown canonical field" in field.rationale


def test_field_already_taken_is_refused() -> None:
    a, _ = adjudicator(
        Response(
            '{"fields":[{"source_field":"Px_Sett","canonical_field":"quantity",'
            '"confidence":0.9,"rationale":"sure"}]}'
        )
    )
    result = a.adjudicate(request(resolved={"Qty": "quantity"}))
    field = result.as_map()["Px_Sett"]
    assert field.canonical_field is None
    assert "already assigned" in field.rationale


def test_column_nobody_asked_about_is_ignored() -> None:
    a, _ = adjudicator(
        Response(
            '{"fields":[{"source_field":"SomethingElse","canonical_field":"quantity",'
            '"confidence":0.9,"rationale":"x"},'
            '{"source_field":"Px_Sett","canonical_field":"settlement_price",'
            '"confidence":0.8,"rationale":"y"}]}'
        )
    )
    result = a.adjudicate(request())
    assert "SomethingElse" not in result.as_map()
    assert result.as_map()["Px_Sett"].canonical_field == "settlement_price"


def test_unaddressed_column_still_gets_an_answer() -> None:
    # Every column needs a recorded outcome, or provenance has a hole in it.
    a, _ = adjudicator(
        Response(
            '{"fields":[{"source_field":"Px_Sett","canonical_field":"settlement_price",'
            '"confidence":0.8,"rationale":"y"}]}'
        )
    )
    result = a.adjudicate(request(headers=["Px_Sett", "Mystery"]))
    assert result.as_map()["Mystery"].canonical_field is None
    assert result.as_map()["Mystery"].rationale


def test_confidence_never_reaches_dictionary_level() -> None:
    a, _ = adjudicator(
        Response(
            '{"fields":[{"source_field":"Px_Sett","canonical_field":"settlement_price",'
            '"confidence":1.0,"rationale":"certain"}]}'
        )
    )
    assert a.adjudicate(request()).as_map()["Px_Sett"].confidence <= 0.85


def test_markdown_fenced_json_is_tolerated() -> None:
    a, _ = adjudicator(
        Response(
            '```json\n{"fields":[{"source_field":"Px_Sett",'
            '"canonical_field":"settlement_price","confidence":0.8,"rationale":"y"}]}\n```'
        )
    )
    assert a.adjudicate(request()).as_map()["Px_Sett"].canonical_field == "settlement_price"


def test_malformed_output_retries_then_declines() -> None:
    a, client = adjudicator(Response("not json at all"), Response("still not json"))
    result = a.adjudicate(request())
    assert len(client.calls) == 2
    assert result.as_map()["Px_Sett"].canonical_field is None
    assert "validation" in result.as_map()["Px_Sett"].rationale


def test_transport_failure_falls_back_cleanly() -> None:
    # A pipeline that blocks waiting for a model becomes an outage; an
    # unresolved column becomes a review item.
    a, _ = adjudicator(RuntimeError("connection reset"), RuntimeError("connection reset"))
    result = a.adjudicate(request())
    assert result.as_map()["Px_Sett"].canonical_field is None
    assert a.usage.failures == 2


def test_transient_failure_recovers_on_retry() -> None:
    a, client = adjudicator(
        RuntimeError("timeout"),
        Response(
            '{"fields":[{"source_field":"Px_Sett",'
            '"canonical_field":"settlement_price","confidence":0.8,"rationale":"y"}]}'
        ),
    )
    assert a.adjudicate(request()).as_map()["Px_Sett"].canonical_field == "settlement_price"
    assert len(client.calls) == 2


def test_no_call_is_made_when_there_is_nothing_to_resolve() -> None:
    a, client = adjudicator()
    assert a.adjudicate(request(headers=[])).fields == []
    assert client.calls == []


def test_prompt_carries_samples_and_already_mapped_context() -> None:
    a, client = adjudicator(Response('{"fields":[]}'))
    a.adjudicate(request(resolved={"Qty": "quantity"}))
    prompt = client.calls[0]["messages"][0]["content"]
    assert "Meridian Capital Partners" in prompt
    assert "CME" in prompt
    assert "'99.50'" in prompt
    assert "Qty -> quantity" in prompt
    assert "do not reuse" in prompt


def test_system_prompt_is_marked_for_caching() -> None:
    # The instructions are identical on every call, so only the per-file
    # portion should be charged in full.
    a, client = adjudicator(Response('{"fields":[]}'))
    a.adjudicate(request())
    system = client.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_token_usage_is_accumulated() -> None:
    # NFR-8 is measured, not asserted.
    a, _ = adjudicator(
        Response(
            '{"fields":[{"source_field":"Px_Sett","canonical_field":"settlement_price",'
            '"confidence":0.8,"rationale":"y"}]}'
        ),
    )
    a.adjudicate(request())
    assert a.usage.calls == 1
    assert a.usage.input_tokens == 120
    assert a.usage.cache_read_tokens == 80
    assert a.usage.mean_latency_ms >= 0


def test_missing_api_key_is_a_clear_error() -> None:
    a = ClaudeAdjudicator(api_key="")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        a.adjudicate(request())


def test_default_selection_is_the_offline_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    # A misconfigured deployment should run without a model rather than fail
    # to start. Enabling the live tier is an explicit act.
    monkeypatch.delenv("HM_ADJUDICATOR", raising=False)
    assert isinstance(build_adjudicator(), DeterministicFake)
    assert isinstance(build_adjudicator("claude"), ClaudeAdjudicator)
