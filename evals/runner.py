"""
Claude API 도구 호출 루프. 모델 · 문항 · 반복 한 번마다 호출 기록과 지연 · 토큰을 남긴다.

Tool Runner(beta) 대신 직접 루프를 쓰는 이유: 턴마다 응답시간과 usage 를 따로 재고,
모델이 부른 도구와 인자를 그대로 남기기 위해서다.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import anthropic

from evals.bridge import McpBridge
from evals.cases import Case

# $ / 1M tokens (Anthropic API 정가, 2026-10 기준). 캐시는 쓰지 않으므로 입력 · 출력만 계산한다.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

MAX_TURNS = 8
TOOL_RESULT_CHAR_LIMIT = 30_000


@dataclass
class RunRecord:
    model: str
    case_id: str
    repeat: int
    final_text: str = ""
    stop_reason: str | None = None
    turns: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_sec: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICING.get(model, (0.0, 0.0))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


async def run_case(
    client: anthropic.AsyncAnthropic,
    bridge: McpBridge,
    *,
    model: str,
    system_prompt: str,
    case: Case,
    repeat: int,
    effort: str,
) -> RunRecord:
    rec = RunRecord(model=model, case_id=case.id, repeat=repeat)
    messages: list[dict[str, Any]] = [{"role": "user", "content": case.question}]
    started = time.perf_counter()
    response = None
    try:
        while rec.turns < MAX_TURNS:
            rec.turns += 1
            response = await client.messages.create(
                model=model,
                max_tokens=16000,
                system=system_prompt,
                tools=bridge.tool_defs,
                messages=messages,
                output_config={"effort": effort},
            )
            rec.input_tokens += response.usage.input_tokens
            rec.output_tokens += response.usage.output_tokens
            rec.stop_reason = response.stop_reason
            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                args = dict(block.input) if isinstance(block.input, dict) else {}
                result = await bridge.call(block.name, args)
                rec.tool_calls.append({"name": block.name, "args": args, "result": result})
                payload = json.dumps(result, ensure_ascii=False)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": payload[:TOOL_RESULT_CHAR_LIMIT],
                        "is_error": result.get("status") == "error",
                    }
                )
            # 병렬 호출 결과는 한 user 메시지에 모아 보낸다
            messages.append({"role": "user", "content": tool_results})
        else:
            rec.error = f"{MAX_TURNS}턴 안에 끝나지 않음"
    except anthropic.RateLimitError as exc:
        rec.error = f"rate_limit: {exc.message}"
    except anthropic.APIStatusError as exc:
        rec.error = f"api_{exc.status_code}: {exc.message}"
    except anthropic.APIConnectionError as exc:
        rec.error = f"connection: {exc}"

    rec.latency_sec = round(time.perf_counter() - started, 3)
    if response is not None:
        rec.final_text = "".join(b.text for b in response.content if b.type == "text")
    rec.cost_usd = estimate_cost(model, rec.input_tokens, rec.output_tokens)
    return rec
