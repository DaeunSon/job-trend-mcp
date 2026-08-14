"""
MCP 서버 실행 진입 헬퍼 — transport 선택 (stdio / streamable-http).

보안 기본:
  - HTTP 모드는 기본 host=127.0.0.1 (로컬만)
  - 0.0.0.0 / :: 바인딩은 거부 (외부 노출은 ngrok 등 터널로만)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Literal

logger = logging.getLogger(__name__)

TransportName = Literal["stdio", "streamable-http"]

_BLOCKED_HOSTS = frozenset({"0.0.0.0", "::", "[::]"})
_HOST_WILDCARD_PATCHED = False


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="job-trend-mcp 서버 실행 (stdio 또는 Streamable HTTP)",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=None,
        help="전송 방식. 생략 시 MCP_TRANSPORT 환경변수, 없으면 stdio.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="HTTP 바인딩 주소 (기본: 127.0.0.1). 0.0.0.0 은 거부.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP 포트 (기본: 8000, 또는 MCP_PORT).",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Streamable HTTP 경로 (기본: /mcp).",
    )
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=None,
        metavar="HOST",
        help=(
            "터널/공개 Host 허용 (DNS rebinding 보호 allowlist). "
            "예: example.ngrok-free.dev 또는 *.ngrok-free.dev. "
            "여러 번 지정 가능. 환경변수 MCP_ALLOWED_HOSTS(쉼표 구분)와 합쳐짐."
        ),
    )
    return parser.parse_args(argv)


def _split_host_port(value: str) -> tuple[str, str | None]:
    """Host 헤더/패턴에서 (hostname, port|None)를 분리한다. IPv6([::1]:port) 지원."""
    raw = value.strip().lower()
    if raw.startswith("["):
        if "]:" in raw:
            name, port = raw.rsplit("]:", 1)
            return name + "]", port
        return raw, None
    if raw.count(":") == 1:
        name, port = raw.split(":", 1)
        if port.isdigit() or port == "*":
            return name, port
    return raw, None


def match_allowed_host(host: str, pattern: str) -> bool:
    """
    Host 헤더가 allowlist 패턴과 맞는지 확인.

    지원 패턴:
      - 정확 일치: ``abc.ngrok-free.dev``
      - 포트 와일드카드: ``localhost:*``
      - DNS 와일드카드: ``*.ngrok-free.dev``
      - 조합: ``*.ngrok-free.dev:*``
    """
    host_l = (host or "").strip().lower()
    pattern_l = (pattern or "").strip().lower()
    if not host_l or not pattern_l:
        return False
    if host_l == pattern_l:
        return True

    port_wildcard = pattern_l.endswith(":*")
    base_pattern = pattern_l[:-2] if port_wildcard else pattern_l
    host_name, host_port = _split_host_port(host_l)
    pat_name, pat_port = _split_host_port(base_pattern)

    if port_wildcard:
        # 포트 유무 모두 허용 (ngrok Host는 보통 포트 없음)
        pass
    elif pat_port is not None:
        if host_port != pat_port:
            return False
    else:
        # 패턴에 포트 없음 → 호스트명만 비교 (포트 있어도 hostname 일치하면 OK)
        pass

    if pat_name.startswith("*."):
        suffix = pat_name[1:]  # ".ngrok-free.dev"
        return host_name.endswith(suffix) and len(host_name) > len(suffix)

    if port_wildcard:
        return host_name == pat_name
    # 정확 호스트명 (포트는 위에서 검사했거나 무시)
    if pat_port is not None:
        return host_name == pat_name
    return host_name == pat_name


def _patch_transport_security_dns_wildcards() -> None:
    """
    MCP SDK TransportSecurityMiddleware는 ``host:*`` 포트 와일드카드만 지원한다.
    ``*.ngrok-free.dev`` 같은 DNS 와일드카드는 여기서 보강한다 (421 Invalid Host 방지).
    """
    global _HOST_WILDCARD_PATCHED
    if _HOST_WILDCARD_PATCHED:
        return

    from mcp.server.transport_security import TransportSecurityMiddleware

    def _validate_host(self, host: str | None) -> bool:  # noqa: ANN001
        if not host:
            logger.warning("Missing Host header in request")
            return False
        for allowed in self.settings.allowed_hosts:
            if match_allowed_host(host, allowed):
                return True
        logger.warning("Invalid Host header: %s", host)
        return False

    TransportSecurityMiddleware._validate_host = _validate_host  # type: ignore[method-assign]
    _HOST_WILDCARD_PATCHED = True
    logger.debug("Patched TransportSecurityMiddleware for DNS host wildcards")


def _resolve_allowed_hosts(cli_hosts: list[str] | None) -> list[str]:
    hosts: list[str] = []
    for item in cli_hosts or []:
        hosts.append(item.strip())
    env = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    if env:
        hosts.extend(h.strip() for h in env.split(",") if h.strip())

    # localhost 기본 + 터널 호스트. 포트 유무 둘 다 허용 패턴 추가
    expanded: list[str] = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "[::1]",
        "[::1]:*",
    ]
    for h in hosts:
        if not h:
            continue
        expanded.append(h)
        # "*.ngrok-free.dev" / "abc.example.com" → 포트 와일드카드도 추가
        # (이미 :* 이거나 명시 포트가 있으면 건너뜀)
        bare = h.strip("[]")
        if not bare.endswith(":*") and ":" not in bare:
            expanded.append(f"{h}:*")
    # 중복 제거 (순서 유지)
    seen: set[str] = set()
    out: list[str] = []
    for h in expanded:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def resolve_run_config(argv: list[str] | None = None) -> dict:
    """CLI + 환경변수로 run() 인자를 조립한다."""
    args = _parse_args(argv)

    transport_raw = (
        args.transport
        or os.environ.get("MCP_TRANSPORT")
        or "stdio"
    ).strip().lower()
    if transport_raw in ("http", "streamable_http", "streamable-http"):
        transport: TransportName = "streamable-http"
    elif transport_raw == "stdio":
        transport = "stdio"
    else:
        raise SystemExit(
            f"Unsupported transport {transport_raw!r}. "
            "Use 'stdio' or 'streamable-http'."
        )

    if transport == "stdio":
        return {"transport": "stdio"}

    host = (args.host or os.environ.get("MCP_HOST") or "127.0.0.1").strip()
    if host in _BLOCKED_HOSTS:
        raise SystemExit(
            f"Refusing to bind host={host!r}. "
            "Use 127.0.0.1 and expose via a temporary tunnel (e.g. ngrok) if needed."
        )

    port_raw = args.port if args.port is not None else os.environ.get("MCP_PORT", "8000")
    try:
        port = int(port_raw)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid port: {port_raw!r}") from exc

    path = (args.path or os.environ.get("MCP_PATH") or "/mcp").strip()
    if not path.startswith("/"):
        path = "/" + path

    allowed_hosts = _resolve_allowed_hosts(args.allowed_host)
    # CLI/ENV에 터널 호스트가 있을 때만 커스텀 allowlist를 넘긴다.
    # (없으면 SDK 기본 localhost allowlist 유지)
    has_extra = bool(args.allowed_host) or bool(
        os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    )

    return {
        "transport": "streamable-http",
        "host": host,
        "port": port,
        "streamable_http_path": path,
        "allowed_hosts": allowed_hosts if has_extra else None,
    }


def main(argv: list[str] | None = None) -> None:
    from mcp.server.transport_security import TransportSecuritySettings

    from src.mcp_server.server import mcp

    config = resolve_run_config(argv)
    transport = config["transport"]
    if transport == "stdio":
        logger.info("Starting MCP server transport=stdio")
        mcp.run(transport="stdio")
        return

    logger.info(
        "Starting MCP server transport=streamable-http host=%s port=%s path=%s",
        config["host"],
        config["port"],
        config["streamable_http_path"],
    )
    # stderr에만 안내 — stdio 프로토콜과 무관 (HTTP 모드)
    print(
        f"Streamable HTTP listening on "
        f"http://{config['host']}:{config['port']}{config['streamable_http_path']}",
        file=sys.stderr,
    )

    run_kwargs: dict = {
        "transport": "streamable-http",
        "host": config["host"],
        "port": config["port"],
        "streamable_http_path": config["streamable_http_path"],
    }
    if config.get("allowed_hosts"):
        # SDK 기본은 포트 :* 만 지원 → *.ngrok-free.dev DNS 와일드카드 보강
        _patch_transport_security_dns_wildcards()
        logger.info("DNS-rebinding allowlist hosts=%s", config["allowed_hosts"])
        run_kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=config["allowed_hosts"],
        )
    mcp.run(**run_kwargs)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    main()
