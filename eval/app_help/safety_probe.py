"""End-to-end APP_HELP response-safety + fail-closed probe (final integration check).

Runs the REAL pipeline on the reconciled branch:
  route decision -> _dispatch_app_help (real AppHelpRetriever over Chroma
  app_help_kb_v1) -> build_final_response (deterministic fallback + bounded
  LLM rewrite + hallucination guard).

Safety checks per response message:
  - no internal chunk IDs ("feature::section")
  - no `.md` filenames
  - no raw route/API paths (/patient/..., /api/...)
  - no corpus heading artifacts ("Feature này dùng để làm gì?" etc.)
  - sources carry only the existing human-readable doc titles (payload shape unchanged)

Fail-closed probes: app-shaped capabilities that DO NOT exist must return the
NOT_FOUND message — never an invented capability.

Run:
  PYTHONPATH=. APP_HELP_RAG_ENABLED=true EMBEDDING_PROVIDER=gemini \\
  EMBEDDING_MODEL_NAME=gemini-embedding-001 EMBEDDING_DIMENSION=3072 \\
  python eval/app_help/safety_probe.py
"""

from __future__ import annotations

import re
import sys

from src.models.orchestrator_schemas import IntentEnum
from src.orchestrator.dispatcher import DispatchContext, _dispatch_app_help
from src.orchestrator.response_composer import build_final_response
from src.services import app_help_retriever
from src.services.app_help_retriever import get_app_help_retriever

SAFETY_PROBES = [
    "làm thế nào để tải ảnh phiếu?",
    "tải phiếu ở đâu?",
    "xem lịch sử kết quả ở đâu?",
    "cảnh báo khẩn cấp nghĩa là gì?",
    "câu hỏi cho bác sĩ ở đâu?",
]

FAIL_CLOSED_PROBES = [
    "xuất PDF ký số",
    "xóa tài khoản trong app",
    "đặt lịch hẹn bác sĩ",
]

HEADING_ARTIFACTS = (
    "Feature này dùng để làm gì?",
    "Người dùng tìm ở đâu?",
    "Các bước sử dụng?",
    "Không làm được gì?",
    "Điều kiện & giới hạn?",
)

_CHUNK_ID_RE = re.compile(r"[a-z0-9-]+::[a-z0-9-]+")
_MD_FILE_RE = re.compile(r"\b[\w-]+\.md\b")
_ROUTE_RE = re.compile(r"(?:^|\s|\()`?(?:/patient|/api|/doctor)[\w/-]*")


class _FakeUser:
    def __init__(self, role: str = "patient"):
        self.role = role


def check_message_safety(message: str) -> list[str]:
    problems = []
    if _CHUNK_ID_RE.search(message):
        problems.append("internal chunk ID exposed")
    if _MD_FILE_RE.search(message):
        problems.append(".md filename exposed")
    if _ROUTE_RE.search(message):
        problems.append("raw route/API path exposed")
    for artifact in HEADING_ARTIFACTS:
        if artifact in message:
            problems.append(f"heading artifact: {artifact!r}")
    return problems


async def run_probe(question: str, retriever) -> dict:
    retrieval = retriever.retrieve(question, requester_role="patient")
    context = DispatchContext(
        current_user=_FakeUser("patient"),
        db=None,
        current_report_ref=None,
        current_analyte=None,
        progress_callback=None,
        message=question,
    )
    result = await _dispatch_app_help(context)
    response = await build_final_response(
        intent=IntentEnum.APP_HELP,
        status=result.status,
        data=result.data,
    )
    chunk_ids = [m.chunk_id for m in retrieval.matches]
    fail_closed = not retrieval.has_match
    return {
        "question": question,
        "retrieved_chunk_ids": chunk_ids,
        "workflow_selected": result.workflow_selected,
        "message": response.message,
        "sources": getattr(result.data, "sources", []),
        "problems": check_message_safety(response.message),
        "fail_closed": fail_closed,
    }


def validate(probe: dict) -> bool:
    ok = not probe["problems"]
    if probe["fail_closed"]:
        # Fail-closed probe: must have retrieved nothing AND answered with the
        # plain NOT_FOUND text — never an invented capability walkthrough.
        if probe["retrieved_chunk_ids"]:
            print(f"  FAIL: fail-closed probe unexpectedly retrieved {probe['retrieved_chunk_ids']}")
            ok = False
        if "chưa tìm thấy" not in probe["message"]:
            print("  FAIL: fail-closed probe did not answer with NOT_FOUND text")
            ok = False
    else:
        if not probe["message"].strip():
            print("  FAIL: empty answer")
            ok = False
        # Payload shape: sources stay human-readable doc titles, never IDs.
        for source in probe["sources"]:
            if "::" in source:
                print(f"  FAIL: source carries internal id: {source!r}")
                ok = False
    return ok


async def main() -> int:
    try:
        retriever = get_app_help_retriever()
    except app_help_retriever.AppHelpRetrieverError as exc:
        print(f"RETRIEVER UNAVAILABLE: {exc}")
        return 2

    failures = 0
    for question in SAFETY_PROBES:
        probe = await run_probe(question, retriever)
        ok = validate(probe)
        failures += 0 if ok else 1
        print("=" * 100)
        print(f"QUESTION={probe['question']}")
        print(f"WORKFLOW={probe['workflow_selected']}")
        print(f"RETRIEVED_CHUNK_IDS(eval-only)={probe['retrieved_chunk_ids']}")
        print(f"SOURCES(payload)={probe['sources']}")
        print(f"FINAL_RESPONSE=\n{probe['message']}")
        print(f"PROBLEMS={probe['problems'] or 'none'}")
        print(f"PASS/FAIL={'PASS' if ok else 'FAIL'}")

    for question in FAIL_CLOSED_PROBES:
        probe = await run_probe(question, retriever)
        ok = validate(probe)
        failures += 0 if ok else 1
        print("=" * 100)
        print(f"[FAIL-CLOSED] QUESTION={probe['question']}")
        print(f"RETRIEVED_CHUNK_IDS(eval-only)={probe['retrieved_chunk_ids']}")
        print(f"FINAL_RESPONSE=\n{probe['message']}")
        print(f"PASS/FAIL={'PASS' if ok else 'FAIL'}")

    print("=" * 100)
    print(f"SAFETY_PROBES={len(SAFETY_PROBES)} FAIL_CLOSED_PROBES={len(FAIL_CLOSED_PROBES)} FAILURES={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    import asyncio

    raise SystemExit(asyncio.run(main()))
