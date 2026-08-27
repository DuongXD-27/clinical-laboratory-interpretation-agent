"""ALTER cac cot context cua bang conversations cho du rong.

## Vi sao can script rieng

`add_missing_columns()` trong `db.py` chi THEM cot con thieu — no khong bao gio
ALTER kieu cua cot da ton tai. Doi `String(64)` thanh `Text` trong model vi vay
KHONG tu dong cap nhat mot DB da song, va production tiep tuc ném
`StringDataRightTruncation` du code da dung.

Repo nay khong dung Alembic (quyet dinh cu, xem CLAUDE.md), nen day la script
mot lan, chay tay, va viet sao cho chay lai nhieu lan van an toan.

## Vi sao an toan

Postgres mo rong varchar hoac doi varchar -> text la thay doi metadata, khong
rewrite bang va khong mat du lieu. Chi thu hep moi nguy hiem, va script nay
khong thu hep gi.

    railway run -s vmec-05-api -e production -- python -m src.scripts.widen_conversation_columns
"""

from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.models.db import engine

# (bang, cot, kieu dich)
CHANGES = [
    ("conversations", "pending_question", "TEXT"),
    ("conversations", "expected_entity", "VARCHAR(255)"),
    ("conversations", "current_analyte", "VARCHAR(255)"),
]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if engine.dialect.name != "postgresql":
        # SQLite khong cuong che do dai VARCHAR nen khong co gi phai sua, va no
        # cung khong ho tro ALTER COLUMN TYPE. Thoat sach thay vi bao loi.
        print(f"dialect={engine.dialect.name} — khong can ALTER, bo qua.")
        return 0

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, target in CHANGES:
            if table not in tables:
                print(f"bo qua {table}.{column}: bang chua ton tai")
                continue

            cols = {c["name"]: c for c in inspector.get_columns(table)}
            if column not in cols:
                print(f"bo qua {table}.{column}: cot chua ton tai")
                continue

            before = str(cols[column]["type"])
            conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE {target}'))
            print(f"{table}.{column}: {before} -> {target}")

    print("xong")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
