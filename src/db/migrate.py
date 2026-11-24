"""SQL 마이그레이션 실행기. `python -m src.db.migrate` 로 DATABASE_URL 의 DB 에 적용한다."""
from __future__ import annotations

from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_LOCK_KEY = 7_340_001


def apply_migrations(conn: psycopg.Connection) -> list[str]:
    """아직 적용 안 된 마이그레이션을 파일 이름 순으로 적용하고 그 버전 이름을 돌려준다.

    commit 은 호출한 쪽이 한다.
    """
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    applied = {row[0] if not isinstance(row, dict) else row["version"]
               for row in conn.execute("SELECT version FROM schema_migrations")}
    done: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.stem in applied:
            continue
        conn.execute(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
        done.append(path.stem)
    return done


def main() -> None:
    from src.db.connection import get_database_url

    with psycopg.connect(get_database_url(), connect_timeout=3) as conn:
        done = apply_migrations(conn)
    print(f"applied: {', '.join(done)}" if done else "no pending migrations")


if __name__ == "__main__":
    main()
