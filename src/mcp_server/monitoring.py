"""
MCP tool 호출 품질 모니터링 (경량 파일/콘솔 로그).

새 DB·인프라 없이 JSONL 한 줄씩 기록한다.
기존 tool 로직는 건드리지 않고, 데코레이터/`monitored_call`로만 감싼다.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger("mcp_tool_monitor")

_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
_LOG_PATH: Path | None = None
_FILE_HANDLER_ATTACHED = False


def get_log_path() -> Path:
    """로그 파일 경로. MCP_MONITOR_LOG 환경변수로 덮어쓸 수 있다."""
    global _LOG_PATH
    if _LOG_PATH is not None:
        return _LOG_PATH
    override = os.environ.get("MCP_MONITOR_LOG", "").strip()
    if override:
        _LOG_PATH = Path(override)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        _LOG_PATH = _DEFAULT_LOG_DIR / f"mcp_tool_calls_{stamp}.jsonl"
    return _LOG_PATH


def set_log_path(path: str | Path | None) -> Path:
    """테스트·시뮬레이션용 로그 경로 지정. None이면 기본 경로로 리셋."""
    global _LOG_PATH, _FILE_HANDLER_ATTACHED
    _LOG_PATH = Path(path) if path is not None else None
    _FILE_HANDLER_ATTACHED = False
    return get_log_path()


def _ensure_file_logger() -> Path:
    global _FILE_HANDLER_ATTACHED
    path = get_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _FILE_HANDLER_ATTACHED:
        # 같은 path에 이미 handler가 있으면 중복 추가하지 않음
        abs_path = str(path.resolve())
        for h in logger.handlers:
            if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == abs_path:
                _FILE_HANDLER_ATTACHED = True
                return path
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _FILE_HANDLER_ATTACHED = True
    return path


def extract_result_metrics(result: Any) -> dict[str, Any]:
    """tool 응답 dict에서 건수·상태·안내 여부를 뽑는다."""
    if not isinstance(result, dict):
        return {
            "status": None,
            "result_count": None,
            "is_zero": None,
            "is_unknown_param": False,
            "is_empty": False,
            "is_guidance": False,
        }

    status = result.get("status")
    count: int | None = None
    if isinstance(result.get("count"), int):
        count = result["count"]
    elif isinstance(result.get("matched_postings"), int):
        count = result["matched_postings"]
    elif isinstance(result.get("skills"), list):
        count = len(result["skills"])
    elif isinstance(result.get("salary_data_count"), int):
        count = result["salary_data_count"]
    elif isinstance(result.get("postings"), list):
        count = len(result["postings"])
    elif isinstance(result.get("total_postings"), int):
        count = result["total_postings"]
    elif isinstance(result.get("categories"), list):
        count = len(result["categories"])

    is_unknown = status in ("unknown_param", "unknown_company")
    is_empty = status in ("empty", "no_salary_data")
    is_zero = (count == 0) if count is not None else bool(is_empty or is_unknown)

    return {
        "status": status,
        "result_count": count,
        "is_zero": is_zero,
        "is_unknown_param": is_unknown,
        "is_empty": is_empty,
        "is_guidance": is_unknown or is_empty,
    }


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    """로그용 파라미터 (store 등 비직렬화 객체 제외)."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        if key == "store":
            continue
        try:
            json.dumps(value, ensure_ascii=False)
            out[key] = value
        except (TypeError, ValueError):
            out[key] = repr(value)
    return out


def write_tool_event(
    *,
    tool_name: str,
    params: dict[str, Any],
    duration_ms: float,
    result: Any = None,
    error: BaseException | None = None,
    category: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """한 건의 tool 호출 이벤트를 JSONL로 기록하고 이벤트를 반환한다."""
    metrics = extract_result_metrics(result) if error is None else {
        "status": "error",
        "result_count": 0,
        "is_zero": True,
        "is_unknown_param": False,
        "is_empty": False,
        "is_guidance": False,
    }
    event: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "params": _safe_params(params),
        "duration_ms": round(duration_ms, 2),
        "error": None if error is None else f"{type(error).__name__}: {error}",
        **metrics,
    }
    if category:
        event["sim_category"] = category
    if extra:
        event["extra"] = extra

    path = _ensure_file_logger()
    line = json.dumps(event, ensure_ascii=False)
    logger.info(line)
    # stdout은 MCP stdio 전용 — 요약은 stderr만 (또는 MCP_MONITOR_QUIET=1 이면 생략)
    if os.environ.get("MCP_MONITOR_QUIET", "").strip() not in ("1", "true", "yes"):
        print(
            f"[mcp-monitor] {tool_name} status={event.get('status')} "
            f"count={event.get('result_count')} {event['duration_ms']}ms"
            + (f" err={event['error']}" if event["error"] else ""),
            file=sys.stderr,
            flush=True,
        )
    event["_log_path"] = str(path)
    return event


def monitored_call(
    tool_name: str,
    fn: Callable[..., Any],
    *,
    category: str | None = None,
    **kwargs: Any,
) -> Any:
    """시뮬레이션·직접 호출용. 데코레이터 없이 한 번 감싸서 실행·기록."""
    start = time.perf_counter()
    error: BaseException | None = None
    result: Any = None
    try:
        result = fn(**kwargs)
        return result
    except BaseException as exc:  # noqa: BLE001 — 모니터링이 예외를 삼키지 않음
        error = exc
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        write_tool_event(
            tool_name=tool_name,
            params=kwargs,
            duration_ms=duration_ms,
            result=result,
            error=error,
            category=category,
        )


def monitor_tool(tool_name: str | None = None) -> Callable[[F], F]:
    """tool 함수에 붙여 호출마다 로그를 남긴다. 로직/반환값은 그대로 통과."""

    def decorator(fn: F) -> F:
        name = tool_name or fn.__name__

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # positional은 가능하면 키워드로 합쳐 기록
            params = dict(kwargs)
            if args:
                params["_positional"] = [repr(a) for a in args]
            start = time.perf_counter()
            error: BaseException | None = None
            result: Any = None
            try:
                result = fn(*args, **kwargs)
                return result
            except BaseException as exc:  # noqa: BLE001
                error = exc
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                write_tool_event(
                    tool_name=name,
                    params=params,
                    duration_ms=duration_ms,
                    result=result,
                    error=error,
                )

        return wrapper  # type: ignore[return-value]

    return decorator
