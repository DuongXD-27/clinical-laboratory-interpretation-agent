"""Bù cột còn thiếu khi model đi trước DB.

`create_all()` chỉ tạo bảng chưa tồn tại, nó không ALTER bảng đã có. Khi DB còn
bị xoá mỗi lần redeploy thì điều đó vô hại. Từ khi production dùng Postgres
(2026-08-15), DB sống dai hơn code và mỗi lần model thêm cột là production trả
500 `UndefinedColumn` — đã xảy ra thật với `report_indicators.critical_status`.

Bộ test này dựng đúng tình huống đó: tạo bảng thiếu cột rồi chạy migration.
"""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

import src.models.db as db_module


@pytest.fixture
def temp_engine(tmp_path, monkeypatch):
    """Engine riêng trên file tạm, gắn vào module db để migration chạy lên nó."""

    engine = create_engine(
        f"sqlite:///{tmp_path / 'migration.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db_module, "engine", engine)
    yield engine
    engine.dispose()


def columns_of(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def test_adds_a_column_the_model_declares_but_the_table_lacks(temp_engine):
    """Đúng kịch bản đã làm sập production: bảng cũ thiếu critical_status."""

    # Dựng report_indicators theo hình dạng CŨ — thiếu hẳn critical_status và
    # nhóm cột canonical mà đợt audit thêm vào sau.
    old_shape = MetaData()
    Table(
        "report_indicators",
        old_shape,
        Column("id", Integer, primary_key=True),
        Column("report_id", Integer, nullable=False),
        Column("name", String, nullable=False),
    )
    old_shape.create_all(temp_engine)

    before = columns_of(temp_engine, "report_indicators")
    assert "critical_status" not in before

    added = db_module.add_missing_columns()

    after = columns_of(temp_engine, "report_indicators")
    assert "critical_status" in after
    assert "report_indicators.critical_status" in added
    # Nhóm cột canonical cũng phải được bù cùng lượt.
    for column in ("analyte_raw", "analyte_canonical", "canonical_unit"):
        assert column in after, column


def test_reports_every_column_it_added(temp_engine):
    old_shape = MetaData()
    Table(
        "users",
        old_shape,
        Column("id", Integer, primary_key=True),
        Column("username", String, nullable=False),
        Column("password_hash", String, nullable=False),
        Column("role", String, nullable=False),
    )
    old_shape.create_all(temp_engine)

    added = db_module.add_missing_columns()

    user_columns = {name.split(".", 1)[1] for name in added if name.startswith("users.")}
    assert {"full_name", "email", "created_at", "updated_at"} <= user_columns


def test_is_idempotent(temp_engine):
    """Chạy lần hai không được thêm gì, vì init_db() chạy mỗi lần khởi động."""

    db_module.Base.metadata.create_all(bind=temp_engine)

    assert db_module.add_missing_columns() == []
    assert db_module.add_missing_columns() == []


def test_does_nothing_when_the_table_does_not_exist_yet(temp_engine):
    """Bảng chưa có thì để create_all() lo, migration không được tự tạo."""

    added = db_module.add_missing_columns()

    assert added == []
    assert inspect(temp_engine).get_table_names() == []


def test_added_column_is_nullable_even_when_the_model_says_not_null(temp_engine):
    """Bảng đang có dòng cũ thì thêm NOT NULL không default sẽ fail.

    Nhận cột nullable là đánh đổi có chủ đích: ứng dụng vẫn ghi được vì default
    nằm ở tầng Python. Cần chặt hơn thì phải dùng migration tool thật.
    """

    old_shape = MetaData()
    Table(
        "lab_reports",
        old_shape,
        Column("id", Integer, primary_key=True),
        Column("patient_id", Integer, nullable=False),
        Column("has_critical_values", Integer, nullable=False),
    )
    old_shape.create_all(temp_engine)

    with temp_engine.begin() as conn:
        conn.execute(text("INSERT INTO lab_reports (patient_id, has_critical_values) VALUES (1, 0)"))

    added = db_module.add_missing_columns()

    assert any(name.startswith("lab_reports.") for name in added)
    # Dòng cũ vẫn còn — migration không được làm mất dữ liệu.
    with temp_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM lab_reports")).scalar() == 1


def test_backfill_fills_status_left_null_by_the_added_column(temp_engine):
    """Cột `status` vừa thêm sẽ NULL ở dòng cũ, và màn lịch sử hiển thị sai."""

    old_shape = MetaData()
    Table(
        "lab_reports",
        old_shape,
        Column("id", Integer, primary_key=True),
        Column("patient_id", Integer, nullable=False),
        Column("has_critical_values", Integer, nullable=False),
    )
    Table(
        "users",
        old_shape,
        Column("id", Integer, primary_key=True),
        Column("username", String, nullable=False),
        Column("password_hash", String, nullable=False),
        Column("role", String, nullable=False),
    )
    Table(
        "report_indicators",
        old_shape,
        Column("id", Integer, primary_key=True),
        Column("report_id", Integer, nullable=False),
        Column("name", String, nullable=False),
        Column("status", String, nullable=False),
    )
    old_shape.create_all(temp_engine)

    with temp_engine.begin() as conn:
        conn.execute(text("INSERT INTO lab_reports (patient_id, has_critical_values) VALUES (1, 1)"))
        conn.execute(
            text("INSERT INTO report_indicators (report_id, name, status) VALUES (1, 'Kali', 'critical_high')")
        )

    db_module.add_missing_columns()
    db_module.backfill_added_column_defaults()

    with temp_engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM lab_reports")).scalar() == "CRITICAL"
        assert conn.execute(text("SELECT critical_status FROM report_indicators")).scalar() == "critical_high"


def test_model_and_a_fresh_database_agree(temp_engine):
    """Sau create_all() thì không cột nào của model bị thiếu.

    Nếu test này đỏ thì `add_missing_columns()` đang đọc sai metadata, chứ không
    phải DB thiếu cột.
    """

    db_module.Base.metadata.create_all(bind=temp_engine)
    inspector = inspect(temp_engine)

    for table in db_module.Base.metadata.sorted_tables:
        db_columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing = {column.name for column in table.columns} - db_columns
        assert not missing, f"{table.name} thiếu {sorted(missing)}"


def test_picks_up_a_brand_new_model_column_without_any_hand_maintained_list(temp_engine):
    """Tính chất quan trọng nhất: không có danh sách cột viết tay nào cả.

    Bản trước liệt kê cột theo từng bảng trong một dict. Ai thêm cột vào model
    mà quên cập nhật dict đó là migration bỏ sót — đúng cách
    `report_indicators.critical_status` lọt lưới và làm sập production.

    Ở đây thêm một cột chưa từng tồn tại vào metadata lúc chạy, rồi kiểm
    migration có tự bù không. Không sửa gì trong `db.py`.
    """

    db_module.Base.metadata.create_all(bind=temp_engine)
    assert db_module.add_missing_columns() == []

    table = db_module.Base.metadata.tables["report_indicators"]
    new_column = Column("lab_device_serial", String, nullable=True)
    table.append_column(new_column)

    try:
        added = db_module.add_missing_columns()

        assert "report_indicators.lab_device_serial" in added
        assert "lab_device_serial" in columns_of(temp_engine, "report_indicators")
    finally:
        # Metadata dùng chung cả process; trả lại nguyên trạng cho test khác.
        table._columns.remove(new_column)
