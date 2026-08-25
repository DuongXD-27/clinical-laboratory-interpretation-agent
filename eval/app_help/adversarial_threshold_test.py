"""Evidence script for APP_HELP_RETRIEVAL_MIN_SCORE=0.70.

Mirrors eval/rag/adversarial_threshold_test.py's purpose for medical_kb_v4:
measure the genuine-question score floor vs. the adjacent-but-unsupported/
off-topic-question score ceiling, so the threshold is picked from evidence
rather than guessed. Re-run whenever the App Help corpus changes.

Requires APP_HELP_RAG_ENABLED=true and a real embedding provider (this
hits the live Gemini embedding API — same as eval/rag/*).
"""

from __future__ import annotations

from src.services.app_help_retriever import get_app_help_retriever

GENUINE = [
    ("Làm sao tải phiếu xét nghiệm?", "upload-analysis"),
    ("tôi tải phiếu xét nghiệm ở đâu?", "upload-analysis"),
    ("Tại sao tôi không tải được phiếu xét nghiệm?", "upload-analysis"),
    ("Tôi xem lịch sử ở đâu?", "history"),
    ("Làm sao xem xu hướng WBC?", "trends"),
    ("Làm sao xem xu hướng HbA1c?", "trends"),
    ("Tại sao phải xác nhận OCR?", "ocr-review"),
    ("hướng dẫn tôi dùng OCR", "ocr-review"),
    ("Chức năng OCR của ứng dụng dùng để làm gì?", "ocr-review"),
    ("Tôi sửa hồ sơ ở đâu?", "profile"),
    ("Cảnh báo khẩn cấp nghĩa là gì?", "critical-alerts"),
]

# Off-topic (no app relation at all) and adjacent-but-unsupported (app-shaped
# question, no matching capability in the corpus) — both must fail closed.
ADVERSARIAL = [
    "Hướng dẫn viết Python",
    "Hôm nay thời tiết thế nào?",
    "Làm sao nấu phở bò ngon?",
    "Xuất phiếu ra file PDF ký số ở đâu?",
    "Ứng dụng có xuất được báo cáo PDF không?",
    "App có tính năng nhắc uống thuốc không?",
]


def main() -> None:
    retriever = get_app_help_retriever()

    print(f"min_score = {retriever._min_score}\n")

    print("=== GENUINE (must match expected feature) ===")
    genuine_scores: list[float] = []
    all_correct = True
    for question, expected_feature in GENUINE:
        result = retriever.retrieve(question)
        top = result.matches[0] if result.matches else None
        correct = top is not None and top.feature == expected_feature
        all_correct = all_correct and correct
        score = top.score if top else 0.0
        genuine_scores.append(score)
        print(f"{'OK ' if correct else 'FAIL'}  score={score:.4f}  feature={top.feature if top else '-':18s}  {question}")

    print("\n=== ADVERSARIAL (must fail closed, has_match=False) ===")
    adversarial_scores: list[float] = []
    all_closed = True
    for question in ADVERSARIAL:
        result = retriever.retrieve(question)
        closed = not result.has_match
        all_closed = all_closed and closed
        # Peek at the raw top-1 score (pre-threshold) for the ceiling
        # measurement, bypassing the retriever's own cutoff.
        raw = retriever._vector_store.search(question, k=1)
        raw_dist = raw["distances"][0][0] if raw["distances"][0] else None
        raw_score = 1.0 - raw_dist if raw_dist is not None else 0.0
        adversarial_scores.append(raw_score)
        print(f"{'OK ' if closed else 'FAIL'}  fail_closed={closed}  raw_top1_score={raw_score:.4f}  {question}")

    genuine_floor = min(genuine_scores)
    adversarial_ceiling = max(adversarial_scores)
    print(f"\nGenuine score floor:      {genuine_floor:.4f}")
    print(f"Adversarial score ceiling: {adversarial_ceiling:.4f}")
    print(f"Margin at min_score={retriever._min_score}: floor - ceiling = {genuine_floor - adversarial_ceiling:.4f}")
    print(f"\nALL GENUINE CORRECT: {all_correct}")
    print(f"ALL ADVERSARIAL FAIL-CLOSED: {all_closed}")


if __name__ == "__main__":
    main()
