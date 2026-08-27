"""Evidence for RETRIEVAL_MIN_SCORE: does the gate actually catch junk?

`retrieval_param_sweep.py` showed the threshold never binds on the real
curated corpus (every genuine candidate scores >= 0.76) — there is no bad
content in that corpus for a threshold to catch, so no min_score value can be
"proven best" from it alone.

This script closes that gap the other way: inject deliberately bad synthetic
candidates (real embedding calls, not mocked) alongside genuine corpus
content for THREE different analyte/status pairs, and see what min_score
actually separates junk from genuine content — generalizing beyond a single
indicator so the conclusion isn't an artifact of one domain. This simulates
the failure mode the metadata semantic cross-check (see
medical_knowledge_retriever.py) exists to catch: a chunk that is correctly
labeled (right analyte_id + note_type) but wrong/off-topic/low-quality — e.g.
from a future bulk/automated ingestion with less curation than the current
hand-written explanations.json.

Run: python -m eval.rag.adversarial_threshold_test

See docs/audit/evidence/retrieval-min-score-evidence.md for the resulting
determination and how to re-derive it.
"""

from __future__ import annotations

from src.config import get_settings
from src.services.embedding_provider import get_embedding_provider
from src.services.medical_knowledge_retriever import ChromaMedicalKnowledgeRetriever
from src.services.vector_store import VectorStore

# Three analyte/status pairs spanning different domains (hematology,
# nephrology, endocrinology) so the conclusion generalizes instead of being
# an artifact of one indicator's vocabulary.
CASES = [
    {
        "analyte_id": "wbc",
        "status": "high",
        "query": "Bạch cầu",
        "junk": {
            "off_topic": (
                "Hôm nay thời tiết đẹp, thích hợp để đi dã ngoại cùng gia đình "
                "và bạn bè vào cuối tuần này tại các công viên trong thành phố."
            ),
            "wrong_indicator": (
                "Creatinine tăng cao có thể do suy giảm chức năng thận, mất "
                "nước hoặc chế độ ăn nhiều protein trong thời gian dài."
            ),
            "vague_filler": (
                "Chỉ số xét nghiệm này có thể tăng hoặc giảm tùy theo nhiều "
                "yếu tố khác nhau trong cơ thể con người tùy từng trường hợp "
                "cụ thể của mỗi người bệnh khác nhau, không có quy luật chung."
            ),
            "wrong_status_mislabeled": (
                "Khi WBC giảm thấp hơn mức bình thường, tình trạng này có thể "
                "gặp khi nhiễm virus, thiếu máu bất sản, hoặc do tác dụng phụ "
                "của hóa trị liệu làm suy giảm tủy xương."
            ),
            "keyword_stuffed": (
                "WBC tăng cao. WBC tăng cao là gì. Ý nghĩa WBC tăng cao. WBC "
                "tăng cao nguyên nhân. Tìm hiểu WBC tăng cao. WBC tăng cao "
                "chi tiết."
            ),
            "marketing_spam": (
                "Đến ngay phòng khám ABC để xét nghiệm WBC với giá ưu đãi chỉ "
                "199.000đ, đội ngũ bác sĩ giàu kinh nghiệm, kết quả nhanh "
                "trong 30 phút, đặt lịch hotline 1900-xxxx ngay hôm nay."
            ),
            "contradictory_dangerous": (
                "WBC tăng cao là dấu hiệu hoàn toàn bình thường, không cần lo "
                "lắng hay theo dõi gì thêm, cơ thể sẽ tự điều chỉnh cân bằng."
            ),
            "garbled_ocr": (
                "W8C t4ng c4o | Ynghia: kh0ng r5 || xem them tai lieu "
                "***error*** chi so xet nghiem #WBC# (P.2 - muc 4.1) [scan loi]"
            ),
            "mixed_half_good": (
                "WBC cao hơn mức bình thường có thể phản ánh tình trạng viêm "
                "nhiễm trong cơ thể. Ngoài ra, giá xăng tuần này tăng nhẹ so "
                "với tuần trước do ảnh hưởng từ thị trường thế giới."
            ),
        },
    },
    {
        "analyte_id": "creatinine",
        "status": "low",
        "query": "Creatinine",
        "junk": {
            "off_topic": (
                "Cuối tuần này có chương trình khuyến mãi lớn tại trung tâm "
                "thương mại, giảm giá đến 50% cho các mặt hàng thời trang."
            ),
            "wrong_indicator": (
                "WBC giảm thấp có thể gặp khi nhiễm virus hoặc do tác dụng phụ của hóa trị liệu làm suy giảm tủy xương."
            ),
            "vague_filler": (
                "Kết quả xét nghiệm có thể thay đổi tùy theo nhiều yếu tố như "
                "chế độ ăn, vận động, tình trạng sức khỏe tổng quát của mỗi "
                "người, không có một quy luật cố định áp dụng cho tất cả."
            ),
            "keyword_stuffed": (
                "Creatinine giảm thấp. Creatinine giảm thấp là gì. Ý nghĩa "
                "Creatinine giảm thấp. Creatinine giảm thấp nguyên nhân."
            ),
            "contradictory_dangerous": (
                "Creatinine giảm thấp là dấu hiệu hoàn toàn bình thường, "
                "không liên quan gì đến khối lượng cơ hay chức năng thận."
            ),
        },
    },
    {
        "analyte_id": "hba1c",
        "status": "critical_high",
        "query": "HbA1c",
        "junk": {
            "off_topic": (
                "Đội tuyển bóng đá quốc gia vừa giành chiến thắng trong trận "
                "đấu giao hữu quốc tế tối qua trước sự cổ vũ của khán giả."
            ),
            "wrong_indicator": (
                "LDL Cholesterol tăng cao làm tăng nguy cơ xơ vữa động mạch "
                "và các bệnh lý tim mạch liên quan trong dài hạn."
            ),
            "vague_filler": (
                "Mỗi người có cơ địa khác nhau nên kết quả xét nghiệm cần "
                "được xem xét trong bối cảnh tổng thể của từng trường hợp "
                "riêng biệt, không thể áp dụng chung một cách máy móc."
            ),
            "keyword_stuffed": (
                "HbA1c tăng nguy kịch. HbA1c cao là gì. Ý nghĩa HbA1c tăng "
                "cao nguy kịch. Tìm hiểu về HbA1c tăng cao nguy kịch."
            ),
            "contradictory_dangerous": (
                "HbA1c ở mức nguy kịch không cần can thiệp y tế ngay, có thể "
                "tự theo dõi tại nhà mà không cần thăm khám bác sĩ."
            ),
        },
    },
]

MIN_SCORE_CANDIDATES = [0.3, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.78, 0.8, 0.85]


def main() -> None:
    settings = get_settings()
    provider = get_embedding_provider()
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.rag_collection_name,
        corpus_version=settings.rag_corpus_version,
        embedding_provider=provider,
    )
    retriever = ChromaMedicalKnowledgeRetriever(store)

    all_genuine: list[float] = []
    all_junk: dict[str, float] = {}

    for case in CASES:
        analyte_id, status, query = case["analyte_id"], case["status"], case["query"]
        status_query = retriever._status_query(query, status)  # noqa: SLF001
        query_embedding = provider.embed_query(status_query)

        print(f"\n=== {analyte_id} / {status} — {status_query!r} ===")

        genuine_chunks = retriever.retrieve(query=query, analyte_id=analyte_id, status=status, limit=10)
        genuine_scores = [c["score"] for c in genuine_chunks]
        all_genuine.extend(genuine_scores)
        print(f"  genuine: n={len(genuine_scores)}, range=[{min(genuine_scores):.3f}, {max(genuine_scores):.3f}]")

        for label, text in case["junk"].items():
            junk_embedding = provider.embed_documents([text])[0]
            score = retriever._metadata_score(  # noqa: SLF001
                text,
                min_chunk_length=settings.metadata_min_chunk_length,
                chunk_embedding=junk_embedding,
                query_embedding=query_embedding,
            )
            key = f"{analyte_id}/{label}"
            all_junk[key] = score
            print(f"    junk score={score:.3f}  [{label}]")

    min_genuine = min(all_genuine)
    print(f"\n=== Global genuine floor across {len(CASES)} domains: {min_genuine:.3f} (n={len(all_genuine)}) ===")

    catchable = {k: v for k, v in all_junk.items() if v < min_genuine}
    uncatchable = {k: v for k, v in all_junk.items() if v >= min_genuine}
    print(f"Junk structurally uncatchable (score >= genuine floor, no threshold can separate it): {uncatchable}")
    if catchable:
        max_catchable = max(catchable.values())
        print(f"Max score among catchable junk: {max_catchable:.3f}")
        print(f"Clean-separation window: ({max_catchable:.3f}, {min_genuine:.3f})")

    print(f"\n{'min_score':>10} | {'junk excluded':>14} | {'genuine kept':>13} | verdict")
    for min_score in MIN_SCORE_CANDIDATES:
        junk_excluded = sum(1 for s in all_junk.values() if s < min_score)
        genuine_kept = sum(1 for s in all_genuine if s >= min_score)
        verdict = (
            "clean separation"
            if genuine_kept == len(all_genuine) and junk_excluded == len(catchable)
            else "kills genuine content"
            if genuine_kept < len(all_genuine)
            else "some catchable junk survives"
        )
        print(
            f"{min_score:>10} | {junk_excluded:>3}/{len(all_junk):<10} | "
            f"{genuine_kept:>3}/{len(all_genuine):<9} | {verdict}"
        )


if __name__ == "__main__":
    main()
