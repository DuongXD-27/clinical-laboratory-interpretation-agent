import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from src.adapters.vision_adapter import close_vision_clients
from src.api.admin_routes import router as admin_router
from src.api.auth_routes import router as auth_router
from src.api.doctor_routes import router as doctor_router
from src.api.history_routes import router as history_router
from src.api.ocr_routes import router as ocr_router
from src.api.orchestrator_routes import router as orchestrator_router
from src.api.patient_routes import router as patient_router
from src.api.routes import router
from src.config import get_settings
from src.models.db import SessionLocal, get_db, init_db
from src.services import langfuse_tracing, trace_repository
from src.services.demo_patient_data import seed_demo_patient_reports
from src.services.doctor_review_service import backfill_review_flags
from src.services.history_repository import backfill_legacy_canonical_indicators
from src.services.logging_config import configure_logging
from src.services.medical_knowledge_retriever import get_rag_readiness
from src.services.request_timing import (
    RequestTiming,
    reset_current_timing,
    set_current_timing,
)

# Áp trước khi tạo logger nào, nếu không thì mọi logger.info() của app bị nuốt:
# uvicorn chỉ cấu hình logger của riêng nó, `src.*` rơi về mặc định WARNING.
_log_level = configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "startup",
        extra={
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "log_level": _log_level,
            # Chỉ ghi loại DB, tuyệt đối không ghi DATABASE_URL vì nó chứa mật khẩu.
            "db_dialect": settings.database_url.split("://", 1)[0],
        },
    )
    init_db()

    # Don trace cu ngay luc khoi dong thay vi theo lich: bang nay chi lon len,
    # va khong ai di soi do tre cua hai tuan truoc. Chay o day thay vi trong
    # middleware de khong request nao phai ganh chi phi don dep.
    if settings.trace_persistence_enabled:
        with SessionLocal() as db:
            trace_repository.prune_older_than(db, days=settings.trace_retention_days)

    if settings.app_env == "development":
        with SessionLocal() as db:
            seed_demo_patient_reports(db)
            changed = backfill_review_flags(db)
            if changed:
                logger.info("doctor_review_backfill", extra={"reports_changed": changed})
            
            backfill_metrics = backfill_legacy_canonical_indicators(db)
            if backfill_metrics and backfill_metrics.get("PARTIAL_ROWS_COMPLETED", 0) > 0:
                logger.info("legacy_trend_backfill", extra=backfill_metrics)
    try:
        yield
    finally:
        await close_vision_clients()
        # Langfuse gui theo lo o luong nen. Container bi kill ma khong flush thi
        # mat dung lo cuoi — tuc la nhung request ngay truoc su co, lo dang xem
        # nhat.
        await run_in_threadpool(langfuse_tracing.flush)
        logger.info("shutdown")


app = FastAPI(
    title="AI20K Agent",
    description="AI Agent built with LangGraph",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
_cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
if "*" in _cors_origins:
    # allow_credentials=True + "*" là cấu hình sai: trình duyệt từ chối wildcard
    # origin khi có credentials, và một số middleware sẽ "chữa cháy" bằng cách
    # echo lại Origin của request — tức là chấp nhận MỌI domain kèm cookie/JWT,
    # lỏng hơn nhiều so với ý định ban đầu. Chặn ngay lúc khởi động thay vì để
    # lỗi âm thầm lọt ra production.
    raise ValueError(
        "CORS_ORIGINS không được chứa '*' khi allow_credentials=True — "
        "liệt kê rõ từng domain (vd. https://vmec-05.vercel.app)."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Server-Timing", "X-Request-ID"],
)



def _persist_trace(fields: dict, server_timing: str, user_role: str | None) -> None:
    """Ghi mot dong trace, mo session rieng.

    Session cua route da dong khi middleware chay den day, nen phai mo moi.

    Doc session factory qua `app.dependency_overrides` chu khong goi thang
    `SessionLocal()`. Ly do: conftest thay `get_db` bang mot SQLite tam cho tung
    test, va middleware nam NGOAI he thong dependency nen no khong tu duoc thay
    theo. Goi thang SessionLocal() thi moi lan chay suite la trace do vao
    data/app.db that cua may dev — dung loai loi vua phai va o test_corpus.py,
    noi mot test ghi de len file duoc track.

    Moi loi deu bi nuot trong `record_trace`: mot dong do luong mat di la chuyen
    nho, mot request 500 vi log khong ghi duoc la chuyen lon.
    """

    # Bao ca than ham, khong chi tin vao try/except BEN TRONG record_trace.
    # `record_trace` tu nuot loi cua chinh no, nhung neu no hong TRUOC khi vao
    # try — mo session that bai, import loi, hoac ai do doi chu ky ham — thi
    # exception bay len middleware va bien request cua nguoi dung thanh 500.
    # Bo test da bat dung truong hop nay. Phong ve phai o BIEN, khong chi o ruot.
    try:
        dependency = app.dependency_overrides.get(get_db, get_db)
        generator = dependency()
        try:
            db = next(generator)
        except StopIteration:  # pragma: no cover - dependency khong yield gi
            return
        try:
            trace_repository.record_trace(
                db,
                fields=fields,
                server_timing=server_timing,
                user_role=user_role,
            )
        finally:
            generator.close()
    except Exception:
        logger.warning(
            "trace_persist_boundary_failed",
            extra={"path": fields.get("path")},
            exc_info=True,
        )


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """Measure complete HTTP time and correlate detailed stage timings.

    The timer starts before FastAPI parses multipart/JSON bodies or resolves
    dependencies.  Route/service spans use the context variable installed here,
    so one structured log line contains the complete latency breakdown.
    """

    timing = RequestTiming()
    request.state.timing = timing
    token = set_current_timing(timing)
    status_code = 500
    response = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        timing.finish()
        if response is not None:
            response.headers["X-Request-ID"] = timing.request_id
            response.headers["Server-Timing"] = timing.server_timing_header()
            origin = request.headers.get("origin")
            if origin in _cors_origins:
                response.headers["Timing-Allow-Origin"] = origin
        fields = timing.as_log_fields(
            method=request.method,
            path=request.url.path,
            status_code=status_code,
        )
        logger.info("request_timing", extra=fields)

        # Cung mot dict di ca hai duong: dong log JSON va dong trong DB. Neu
        # dung hai nguon so lieu khac nhau thi som muon chung se lech, va hai
        # nguon noi khac nhau con te hon chi co mot nguon.
        if settings.trace_persistence_enabled and trace_repository.should_persist(request.url.path):
            # run_in_threadpool vi SessionLocal la SQLAlchemy dong bo: commit
            # thang trong middleware async se chan event loop, ma DB lai nam
            # ngoai mang (Neon o Frankfurt) nen do khong phai chi phi giay.
            await run_in_threadpool(
                _persist_trace,
                fields,
                timing.server_timing_header(),
                getattr(request.state, "user_role", None),
            )

        reset_current_timing(token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Chặn rò rỉ chi tiết lỗi nội bộ ra client (đã lộ ở V1 — xem state.py).

    Log đầy đủ nội bộ, chỉ trả thông điệp chung ra ngoài.

    Trả kèm `request_id` vì đó là thứ duy nhất nối được lời người dùng ("bấm vào
    bị lỗi") với dòng log tương ứng. Id này là ngẫu nhiên, không mang thông tin
    gì về người dùng hay dữ liệu, nên lộ ra ngoài là vô hại — trong khi thiếu nó
    thì mọi báo lỗi từ người dùng đều không tra được.
    """

    timing = getattr(request.state, "timing", None)
    request_id = timing.request_id if timing is not None else None

    logger.exception(
        "unhandled_exception",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "exception_type": type(exc).__name__,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Hệ thống đang bận, vui lòng thử lại.",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id} if request_id else None,
    )


app.include_router(auth_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
app.include_router(ocr_router, prefix="/api/v1")
app.include_router(orchestrator_router, prefix="/api/v1")
app.include_router(patient_router, prefix="/api/v1")
app.include_router(history_router, prefix="/api/v1")
app.include_router(doctor_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


@app.get("/ready")
async def readiness():
    """Report optional RAG separately without making the core API unavailable."""

    rag = get_rag_readiness()
    return {
        "status": "ok" if rag["status"] in {"ready", "disabled"} else "degraded",
        "env": settings.app_env,
        "components": {
            "api": {"status": "ready"},
            "rag": rag,
        },
    }
