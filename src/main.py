import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.auth_routes import router as auth_router
from src.api.history_routes import router as history_router
from src.api.ocr_routes import router as ocr_router
from src.api.routes import router
from src.config import get_settings
from src.models.db import init_db
from src.services.medical_knowledge_retriever import get_rag_readiness

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    init_db()
    yield
    print("Shutting down...")


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
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Chặn rò rỉ chi tiết lỗi nội bộ ra client (đã lộ ở V1 — xem state.py).

    Log đầy đủ nội bộ, chỉ trả thông điệp chung ra ngoài.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Hệ thống đang bận, vui lòng thử lại."},
    )


app.include_router(auth_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
app.include_router(ocr_router, prefix="/api/v1")
app.include_router(history_router, prefix="/api/v1")


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
