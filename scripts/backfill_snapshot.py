"""스냅샷 tar.gz 의 공고 JSON 을 PostgreSQL 에 적재한다(전체가 한 트랜잭션).

  python scripts/backfill_snapshot.py --archive data/data-archive/data_snapshot_20260803.tar.gz
  python scripts/backfill_snapshot.py --archive ... --delete   # 이 적재 표시를 되돌린다
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.connection import connection, reset_pool  # noqa: E402
from src.db.ingest import delete_ingest_source, ingest_documents  # noqa: E402
from src.db.renormalize import renormalize_doc  # noqa: E402

DEFAULT_SOURCE = "backfill:20260803"


def iter_records(root: Path):
    for path in sorted((root / "data" / "job_postings").rglob("*.json")):
        if path.name.startswith("._"):  # macOS AppleDouble 메타 파일
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for rec in data if isinstance(data, list) else [data]:
            if isinstance(rec, dict):
                yield rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--ingest-source", default=DEFAULT_SOURCE)
    ap.add_argument("--delete", action="store_true", help="해당 ingest-source 적재를 되돌린다")
    args = ap.parse_args(argv)

    with connection() as conn:
        if args.delete:
            print(f"deleted_postings={delete_ingest_source(conn, args.ingest_source)}")
            return 0
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(args.archive) as tar:
                tar.extractall(tmp, filter="data")
            docs = (renormalize_doc(r) for r in iter_records(Path(tmp)))
            result = ingest_documents(conn, docs, ingest_source=args.ingest_source)
        print(
            f"inserted={result.inserted} updated={result.updated} "
            f"unchanged={result.unchanged} skipped={result.skipped} "
            f"observations={result.observations}"
        )
        n_post = conn.execute("SELECT count(*) AS n FROM postings").fetchone()["n"]
        stats = conn.execute(
            "SELECT count(*) AS n, min(observed_on) AS lo, max(observed_on) AS hi "
            "FROM posting_observations"
        ).fetchone()
        print(f"postings={n_post} observations={stats['n']}")
        print(f"observed_on min={stats['lo']} max={stats['hi']}")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        reset_pool()
    raise SystemExit(code)
