"""Endpoint chỉ dành cho admin — trace vận hành.

Ranh giới quyền của nhóm route này hẹp có chủ ý: admin xem được **dữ liệu vận
hành** (độ trễ, số truy vấn, số lần gọi LLM, mã lỗi) và không xem được bệnh án.
`/history` vẫn chỉ nhận `patient` và `doctor`, `require_roles(ROLE_ADMIN)` ở đây
không mở thêm gì sang phía đó. Người lo hạ tầng không cần, và không nên, đọc
được kết quả xét nghiệm của bệnh nhân.

Đối xứng ở chiều ngược lại: bác sĩ không vào được nhóm route này. Đó không phải
bảo mật chống bác sĩ, mà là giữ cho ma trận phân quyền chỉ có một cách đọc.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, require_roles
from src.config import get_settings
from src.models.db import ROLE_ADMIN, get_db
from src.models.schemas import (
    LatencyGroupSchema,
    LatencyGroupsResponse,
    RequestTraceListResponse,
    RequestTraceSchema,
    TraceSummarySchema,
    TracingStatusSchema,
)
from src.services import langfuse_tracing, trace_metrics, trace_repository

router = APIRouter(prefix="/admin", tags=["admin"])

# Một dependency dùng chung cho cả nhóm, thay vì lặp ở từng route: thêm endpoint
# mới mà quên gắn guard là lỗi im lặng, còn quên gắn dependency chung thì route
# không có `current_user` và hỏng ngay.
_admin_only = require_roles(ROLE_ADMIN)


@router.get("/tracing/status", response_model=TracingStatusSchema)
async def tracing_status(
    current_user: CurrentUser = Depends(_admin_only),
) -> TracingStatusSchema:
    """Langfuse đang bật hay tắt, và có che dữ liệu không.

    Tồn tại vì "không thấy trace nào" có hai nguyên nhân hoàn toàn khác nhau:
    chưa cấu hình key, hay đã cấu hình mà chưa có traffic. Không có endpoint này
    thì phân biệt hai trường hợp đó phải vào đọc biến môi trường trên Railway.

    Trả về trạng thái và host, không bao giờ trả về key.
    """

    settings = get_settings()
    return TracingStatusSchema(
        langfuse_configured=langfuse_tracing.is_configured(),
        langfuse_host=settings.langfuse_host,
        masked=settings.langfuse_mask_payloads,
        trace_persistence_enabled=settings.trace_persistence_enabled,
        retention_days=settings.trace_retention_days,
    )


@router.get("/traces/summary", response_model=TraceSummarySchema)
async def traces_summary(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    current_user: CurrentUser = Depends(_admin_only),
    db: Session = Depends(get_db),
) -> TraceSummarySchema:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=window_hours)
    data = trace_repository.summarise(db, since=since)
    return TraceSummarySchema(**data, window_hours=window_hours)


@router.get("/traces/latency", response_model=LatencyGroupsResponse)
async def traces_latency(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    current_user: CurrentUser = Depends(_admin_only),
    db: Session = Depends(get_db),
) -> LatencyGroupsResponse:
    """Phan vi do tre, tach nhom AI va API thuong.

    Endpoint RIENG chu khong nhoi vao `/traces/summary`: `summary` dang duoc
    giao dien hien tai dung, va doi hop dong cua no la lam hong man hinh dang
    chay. Them mot endpoint thi ban frontend cu tiep tuc song, ban moi doc cai
    nay — cung nguyen tac tuong thich nguoc da ap cho `conversation_id`.

    Dat TRUOC `/traces/{request_id}` trong file nay, neu khong FastAPI se khop
    "latency" thanh mot request_id. Cung cai bay da gap voi `/traces/summary`.
    """

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=window_hours)
    data = trace_repository.summarise_latency_groups(
        db,
        since=since,
        window_minutes=window_hours * 60,
    )
    groups = data["groups"]
    return LatencyGroupsResponse(
        ai=LatencyGroupSchema(**groups[trace_metrics.GROUP_AI]),
        api=LatencyGroupSchema(**groups[trace_metrics.GROUP_API]),
        window_hours=window_hours,
        window_minutes=data["window_minutes"],
    )


@router.get("/traces", response_model=RequestTraceListResponse)
async def list_traces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    path: str | None = Query(default=None, description="Lọc theo đường dẫn chứa chuỗi này"),
    min_duration_ms: float | None = Query(default=None, ge=0),
    status_code: int | None = Query(default=None, ge=100, le=599),
    only_llm_errors: bool = Query(default=False),
    window_hours: int | None = Query(default=None, ge=1, le=24 * 30),
    current_user: CurrentUser = Depends(_admin_only),
    db: Session = Depends(get_db),
) -> RequestTraceListResponse:
    """Danh sách trace, mới nhất trước.

    Ba bộ lọc `min_duration_ms` / `status_code` / `only_llm_errors` là bản UI của
    đúng ba câu `jq` hay phải chạy nhất trên log Railway. Câu thứ ba đáng giá
    nhất: LLM hỏng thì analyzer âm thầm rơi về nội dung dựng sẵn, response vẫn
    200, và chỉ bệnh nhân nhận ra chất lượng đi xuống.
    """

    since = (
        datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=window_hours)
        if window_hours is not None
        else None
    )

    rows, total = trace_repository.list_traces(
        db,
        limit=limit,
        offset=offset,
        path_contains=path,
        min_duration_ms=min_duration_ms,
        status_code=status_code,
        only_llm_errors=only_llm_errors,
        since=since,
    )
    return RequestTraceListResponse(
        total=total,
        items=[RequestTraceSchema.model_validate(row) for row in rows],
    )


@router.get("/traces/{request_id}", response_model=RequestTraceSchema)
async def get_trace(
    request_id: str,
    current_user: CurrentUser = Depends(_admin_only),
    db: Session = Depends(get_db),
) -> RequestTraceSchema:
    """Một trace theo `request_id`.

    Đây là đường đi từ lời than phiền về đúng một dòng: người dùng gặp 500 sẽ
    thấy `request_id` trên màn hình lỗi, đọc lại cho admin, admin dán vào đây.
    Không có nó thì "tôi bấm bị lỗi" không ánh xạ được sang dòng log nào.
    """

    trace = trace_repository.get_trace(db, request_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy trace với request_id này.",
        )
    return RequestTraceSchema.model_validate(trace)
