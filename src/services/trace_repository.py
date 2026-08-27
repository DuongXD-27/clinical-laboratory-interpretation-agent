"""Ghi và đọc `request_traces` — nguồn dữ liệu cho màn hình admin.

Tách khỏi `history_repository` có chủ ý: hai bảng trả lời hai câu hỏi khác nhau
và có quy tắc bảo mật ngược nhau. `history_repository` luôn nhận `patient_id`
tường minh để không route nào lỡ quên `WHERE` mà lộ bệnh án; ở đây thì ngược
lại, dữ liệu cố tình không gắn với bệnh nhân nào cả, nên không có gì để giới
hạn phạm vi.

Nguyên tắc của module: **ghi trace hỏng thì im lặng, không bao giờ làm hỏng
request đang phục vụ người dùng.** Một dòng đo lường mất đi là chuyện nhỏ; một
request 500 vì log không ghi được là chuyện lớn.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.db import RequestTrace
from src.services import trace_metrics

logger = logging.getLogger(__name__)

# Đường dẫn không lưu trace. `/health` và `/ready` bị uptime checker gọi liên
# tục; lưu chúng thì bảng toàn nhiễu và mỗi lần probe lại tốn thêm một INSERT
# ra Neon — DB nằm ngoài mạng nên đó là chi phí thật, không phải chi phí giấy.
_SKIPPED_PATHS = frozenset({"/health", "/ready", "/favicon.ico", "/openapi.json", "/docs", "/redoc"})


def should_persist(path: str) -> bool:
    return path not in _SKIPPED_PATHS


def record_trace(
    db: Session,
    *,
    fields: dict[str, Any],
    server_timing: str | None = None,
    user_role: str | None = None,
) -> RequestTrace | None:
    """Lưu một dòng trace. Trả `None` nếu bỏ qua hoặc ghi hỏng.

    `fields` chính là dict `RequestTiming.as_log_fields()` trả ra, dùng lại
    nguyên vẹn để dòng trong DB và dòng trong log JSON không bao giờ lệch nhau
    — hai nguồn số liệu nói khác nhau còn tệ hơn chỉ có một nguồn.
    """

    path = str(fields.get("path", ""))
    if not should_persist(path):
        return None

    def _num(key: str) -> float:
        """`as_log_fields()` tra None cho llm_ms khi request khong goi LLM nao.

        `dict.get(key, 0.0)` KHONG cuu duoc truong hop nay: khoa co ton tai, gia
        tri cua no moi la None. Phai ep rieng.
        """

        value = fields.get(key)
        return float(value) if value is not None else 0.0

    try:
        trace = RequestTrace(
            request_id=str(fields.get("request_id", ""))[:64],
            method=str(fields.get("method", ""))[:10],
            path=path[:255],
            status_code=int(_num("status_code")),
            duration_ms=_num("duration_ms"),
            db_query_count=int(_num("db_query_count")),
            db_ms=_num("db_ms"),
            llm_call_count=int(_num("llm_call_count")),
            llm_ms=_num("llm_ms"),
            llm_error_count=int(_num("llm_error_count")),
            llm_input_tokens=int(_num("llm_input_tokens")),
            llm_output_tokens=int(_num("llm_output_tokens")),
            # KHONG dung `_num` cho chi phi: `_num` doi None thanh 0.0, ma o day
            # `None` mang thong tin — "chua tinh duoc gia". Ep ve 0.0 la bien
            # "khong biet" thanh "mien phi".
            llm_cost_usd=(
                float(fields["llm_cost_usd"])
                if fields.get("llm_cost_usd") is not None
                else None
            ),
            llm_unpriced_call_count=int(_num("llm_unpriced_call_count")),
            user_role=user_role,
            server_timing=server_timing,
        )
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return trace
    except Exception:
        # Nuốt có chủ ý — xem docstring module. Rollback để session còn dùng
        # được nếu caller chưa đóng.
        logger.warning("trace_persist_failed", extra={"path": path}, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def list_traces(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    path_contains: str | None = None,
    min_duration_ms: float | None = None,
    status_code: int | None = None,
    only_llm_errors: bool = False,
    since: datetime | None = None,
) -> tuple[Sequence[RequestTrace], int]:
    """Danh sách trace, mới nhất trước, kèm tổng số dòng khớp bộ lọc.

    Bộ lọc được chọn theo đúng ba câu hỏi hay phải trả lời nhất, và chúng là ba
    câu `jq` mà CLAUDE.md đã ghi sẵn: cái gì chậm (`min_duration_ms`), cái gì
    hỏng (`status_code`), LLM có đang âm thầm hỏng không (`only_llm_errors`).
    Câu thứ ba quan trọng nhất vì response vẫn trả 200 khi LLM hỏng.
    """

    query = select(RequestTrace)
    count_query = select(func.count()).select_from(RequestTrace)

    conditions = []
    if path_contains:
        conditions.append(RequestTrace.path.contains(path_contains))
    if min_duration_ms is not None:
        conditions.append(RequestTrace.duration_ms >= min_duration_ms)
    if status_code is not None:
        conditions.append(RequestTrace.status_code == status_code)
    if only_llm_errors:
        conditions.append(RequestTrace.llm_error_count > 0)
    if since is not None:
        conditions.append(RequestTrace.created_at >= since)

    for condition in conditions:
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = int(db.execute(count_query).scalar_one())
    rows = (
        db.execute(
            query.order_by(RequestTrace.created_at.desc(), RequestTrace.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return rows, total


def get_trace(db: Session, request_id: str) -> RequestTrace | None:
    """Một trace theo `request_id` — chính là id người dùng đọc được từ màn lỗi."""

    return (
        db.execute(
            select(RequestTrace)
            .where(RequestTrace.request_id == request_id)
            .order_by(RequestTrace.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def summarise(db: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Vài con số tổng hợp cho đầu màn admin.

    Cố ý KHÔNG kèm ngưỡng cảnh báo. Ngưỡng phải chọn từ số đo thật chứ không
    phải đoán; đặt bừa một con số rồi tô đỏ theo nó chỉ dạy người xem bỏ qua
    màu đỏ.
    """

    query = select(
        func.count(RequestTrace.id),
        func.avg(RequestTrace.duration_ms),
        func.max(RequestTrace.duration_ms),
        func.sum(RequestTrace.llm_call_count),
        func.sum(RequestTrace.llm_error_count),
    )
    if since is not None:
        query = query.where(RequestTrace.created_at >= since)

    total, avg_ms, max_ms, llm_calls, llm_errors = db.execute(query).one()

    error_query = select(func.count(RequestTrace.id)).where(RequestTrace.status_code >= 500)
    if since is not None:
        error_query = error_query.where(RequestTrace.created_at >= since)
    server_errors = int(db.execute(error_query).scalar_one())

    return {
        "request_count": int(total or 0),
        "avg_duration_ms": round(float(avg_ms), 1) if avg_ms is not None else 0.0,
        "max_duration_ms": round(float(max_ms), 1) if max_ms is not None else 0.0,
        "llm_call_count": int(llm_calls or 0),
        "llm_error_count": int(llm_errors or 0),
        "server_error_count": server_errors,
    }


def summarise_latency_groups(
    db: Session,
    *,
    since: datetime | None = None,
    window_minutes: float | None = None,
) -> dict[str, Any]:
    """Phan vi va ti le loi, TACH RIENG nhom AI va nhom API thuong.

    Thay the `summarise()` cho phan do tre. `summarise()` tra trung binh toan
    he thong, va tren du lieu that no ra 85ms trong khi request AI mat 4-7 giay:
    ~1200 request API thuong de con so do xuong. Trung binh o day khong sai ve
    toan hoc, no chi tra loi mot cau khong ai can hoi.

    Chi tai `duration_ms`, `status_code`, `path`, `method` va hai cot LLM — KHONG
    tai `server_timing` (mot chuoi dai) va khong tai gi khac. Voi vai nghin dong
    moi ngay thi day la mot query nhe, va phan vi duoc tinh trong Python nen
    SQLite va Postgres cho ra CUNG mot con so (`percentile_cont` chi co o
    Postgres — mot duong code chi ton tai o mot dialect la duong bo test khong
    bat duoc).
    """

    query = select(
        RequestTrace.path,
        RequestTrace.method,
        RequestTrace.duration_ms,
        RequestTrace.status_code,
        RequestTrace.llm_call_count,
        RequestTrace.llm_error_count,
        RequestTrace.llm_input_tokens,
        RequestTrace.llm_output_tokens,
        RequestTrace.llm_cost_usd,
        RequestTrace.llm_unpriced_call_count,
    )
    if since is not None:
        query = query.where(RequestTrace.created_at >= since)

    rows = db.execute(query).all()
    groups = trace_metrics.summarise_by_group(rows, window_minutes=window_minutes)
    return {
        "groups": groups,
        "window_minutes": window_minutes,
    }


def prune_older_than(db: Session, *, days: int) -> int:
    """Xoá trace cũ hơn `days` ngày, trả số dòng đã xoá.

    Bảng này ghi mỗi request một dòng nên nó chỉ có lớn lên. Neon free tier có
    hạn mức dung lượng, và không ai đi soi độ trễ của hai tuần trước — cái cần
    là hôm nay hỏng gì.
    """

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    try:
        deleted = (
            db.query(RequestTrace).filter(RequestTrace.created_at < cutoff).delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info("trace_pruned", extra={"deleted": deleted, "older_than_days": days})
        return int(deleted)
    except Exception:
        logger.warning("trace_prune_failed", exc_info=True)
        db.rollback()
        return 0


__all__ = [
    "get_trace",
    "list_traces",
    "prune_older_than",
    "record_trace",
    "should_persist",
    "summarise",
]
