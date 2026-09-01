"""The live Tier 3 adjudicator.

Implements the same ``MappingAdjudicator`` interface the deterministic fake
implements, so nothing upstream knows or cares which is bound. That seam is
what lets the entire test suite run offline, and it is why this file is the
last thing built rather than the first.

Four things here are about operating a model in a control system rather than
demonstrating that one can be called:

**Structured output, validated before use.** The model returns JSON, and every
proposed field is checked against the canonical schema before it is accepted. A
plausible-sounding field name that does not exist is discarded rather than
propagated, because the failure mode of a mapping layer is not a crash, it is a
silently wrong reconciliation.

**Bounded retries with a hard fallback.** Two attempts, then give up and let the
column stay unresolved. An unresolved column becomes a review item; a pipeline
that blocks waiting for a model becomes an outage.

**Prompt caching on the stable prefix.** The instructions and the canonical
field list are identical on every call, so they are marked for caching and only
the per-file portion is charged at full rate.

**Cost is counted, not estimated.** Token counts come back on every response and
are accumulated, so the two percent target in NFR-8 is measured rather than
asserted.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from inspector.mapping import canonical as c
from inspector.mapping.tier3 import (
    AdjudicatedField,
    AdjudicationRequest,
    AdjudicationResult,
)

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_ATTEMPTS = 2
MAX_TOKENS = 1500

# Confidence ceiling for a model answer. It never reaches dictionary level:
# provenance should make clear that a human has not confirmed this.
MAX_MODEL_CONFIDENCE = 0.85

SYSTEM_PROMPT = """\
You map column headers from financial counterparty reports onto a fixed \
canonical schema used by a reconciliation engine.

Rules:
- Only ever use a canonical field from the provided list. Never invent one.
- Each canonical field may be used at most once.
- If a column does not correspond to any canonical field, return null for it. \
Returning null is correct and expected; a wrong mapping is far worse than none.
- Distinguish an execution price from a settlement or mark price carefully. A \
settlement price is a property of an instrument on a day and repeats across \
rows sharing an instrument; an execution price varies per row.
- Sample values are usually more informative than the header text.

Respond with JSON only, no prose, in exactly this shape:
{"fields": [{"source_field": "...", "canonical_field": "..." or null, \
"confidence": 0.0-1.0, "rationale": "one short sentence"}]}"""


@dataclass(slots=True)
class Usage:
    """Accumulated cost, so NFR-8 is measured rather than asserted."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    failures: int = 0
    latencies_ms: list[int] = field(default_factory=list)

    @property
    def mean_latency_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0


class ClaudeAdjudicator:
    """Tier 3 backed by the Anthropic API."""

    name = "claude"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        client: Any = None,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self.model = model
        self.max_attempts = max_attempts
        self.usage = Usage()
        self._client = client
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(
                "ClaudeAdjudicator requires ANTHROPIC_API_KEY; "
                "bind DeterministicFake for offline runs"
            )
        from anthropic import Anthropic

        self._client = Anthropic(api_key=self._api_key)
        return self._client

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationResult:
        """Resolve the unresolved headers, or decline cleanly."""
        if not request.unresolved_headers:
            return AdjudicationResult(fields=[], model=self.model)

        client = self._ensure_client()
        prompt = self._build_prompt(request)

        for attempt in range(1, self.max_attempts + 1):
            started = time.monotonic()
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=[
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT,
                            # The instructions are byte-identical on every call,
                            # so only the per-file portion is charged in full.
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception:
                # Any transport failure degrades to an unresolved column rather
                # than crashing the arrival. Broad by intent.
                self.usage.failures += 1
                if attempt == self.max_attempts:
                    return self._declined(request, "model unavailable")
                continue

            self.usage.calls += 1
            self.usage.latencies_ms.append(int((time.monotonic() - started) * 1000))
            self._record_usage(response)

            parsed = self._parse(response, request)
            if parsed is not None:
                return parsed
            if attempt == self.max_attempts:
                return self._declined(request, "model output failed validation")

        return self._declined(request, "exhausted attempts")

    # --- prompt ------------------------------------------------------------

    def _build_prompt(self, request: AdjudicationRequest) -> str:
        lines = [
            f"Client: {request.client_name or request.client_id}",
            f"Venue: {request.source_hint or 'unknown'}",
            f"Report type: {request.domain}",
            "",
            "Canonical fields available:",
            ", ".join(request.candidate_fields),
            "",
        ]
        if request.resolved:
            # Telling the model what is already settled stops it re-litigating
            # decisions the dictionary already made correctly.
            lines += [
                "Already mapped (do not reuse these canonical fields):",
                ", ".join(f"{k} -> {v}" for k, v in sorted(request.resolved.items())),
                "",
            ]
        lines.append("Unresolved columns, with sample values:")
        for header in request.unresolved_headers:
            samples = request.samples.get(header, [])[:5]
            shown = ", ".join(repr(s) for s in samples) if samples else "no samples"
            lines.append(f"- {header}: {shown}")
        return "\n".join(lines)

    # --- response ----------------------------------------------------------

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.usage.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.usage.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.usage.cache_read_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)

    def _parse(self, response: Any, request: AdjudicationRequest) -> AdjudicationResult | None:
        text = self._text(response)
        if not text:
            return None
        payload = self._json(text)
        if payload is None:
            return None

        allowed = set(request.candidate_fields)
        taken = set(request.resolved.values())
        requested = set(request.unresolved_headers)
        out: list[AdjudicatedField] = []

        for item in payload.get("fields", []):
            if not isinstance(item, dict):
                continue
            source = str(item.get("source_field", ""))
            if source not in requested:
                # A column nobody asked about. Discarded rather than trusted.
                continue
            canonical = item.get("canonical_field")
            rationale = str(item.get("rationale", ""))[:300]

            if canonical is None or canonical == "":
                out.append(AdjudicatedField(source, None, 0.0, rationale or "declined"))
                continue

            canonical = str(canonical)
            if canonical not in allowed or canonical not in c.MAPPABLE_FIELDS:
                # A plausible-sounding field that does not exist. This is the
                # failure this validation exists for.
                out.append(
                    AdjudicatedField(
                        source,
                        None,
                        0.0,
                        f"proposed unknown canonical field {canonical!r}; discarded",
                    )
                )
                continue
            if canonical in taken:
                out.append(
                    AdjudicatedField(
                        source,
                        None,
                        0.0,
                        f"proposed {canonical}, which is already assigned",
                    )
                )
                continue

            taken.add(canonical)
            confidence = _clamp(item.get("confidence", 0.7))
            out.append(AdjudicatedField(source, canonical, confidence, rationale))

        if not out:
            return None

        # Columns the model ignored entirely still need an answer on the record.
        answered = {f.source_field for f in out}
        for header in request.unresolved_headers:
            if header not in answered:
                out.append(AdjudicatedField(header, None, 0.0, "not addressed by the model"))

        return AdjudicationResult(
            fields=out,
            model=self.model,
            input_tokens=self.usage.input_tokens,
            output_tokens=self.usage.output_tokens,
        )

    def _text(self, response: Any) -> str:
        blocks = getattr(response, "content", None) or []
        parts = []
        for block in blocks:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", ""))
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()

    def _json(self, text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _declined(self, request: AdjudicationRequest, reason: str) -> AdjudicationResult:
        """Fall back cleanly: every column stays unresolved, with the reason."""
        return AdjudicationResult(
            fields=[AdjudicatedField(h, None, 0.0, reason) for h in request.unresolved_headers],
            model=self.model,
        )


def _clamp(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.7
    return round(max(0.0, min(confidence, MAX_MODEL_CONFIDENCE)), 3)


def build_adjudicator(kind: str | None = None) -> Any:
    """Select the adjudicator from configuration.

    Defaults to the deterministic fake, so a misconfigured deployment runs
    without a model rather than failing to start. Enabling the live tier is an
    explicit act.
    """
    from inspector.mapping.tier3 import DeterministicFake

    choice = (kind or os.environ.get("HM_ADJUDICATOR", "fake")).lower()
    if choice == "claude":
        return ClaudeAdjudicator()
    return DeterministicFake()
