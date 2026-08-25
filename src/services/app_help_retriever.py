"""Dense-only retriever for the App Help knowledge base.

Unlike ``medical_knowledge_retriever.py`` (status/band-aware, tightly
coupled to the 35-locked-analyte schema), App Help queries are stateless
free-text lookups against a small, static markdown corpus — there is no
analyte/status/band concept here, so a single dense (embedding) search
against a dedicated ``VectorStore`` collection is enough.

Fail-closed by design: below ``min_score`` nothing is returned, so callers
must never invent a route/button when the corpus has no real answer for the
question (see yeu-cau-vu.txt AH-10/AH-12 — this is the enforcement point
for that requirement).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import get_settings
from src.services.embedding_provider import get_embedding_provider
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError
from src.services.vector_store import VectorStore


class AppHelpRetrieverError(Exception):
    """Raised when the App Help RAG is disabled or unavailable."""


@dataclass(frozen=True)
class AppHelpChunkMatch:
    chunk_id: str
    text: str
    feature: str
    role: str
    route: str
    heading: str
    source_file: str
    score: float


@dataclass(frozen=True)
class AppHelpRetrievalResult:
    query: str
    matches: list[AppHelpChunkMatch]

    @property
    def has_match(self) -> bool:
        return len(self.matches) > 0


_KNOWN_ROLE_VALUES = {"patient", "doctor"}


def _normalize(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


# Deterministic feature hints for the intent_router's known explicit
# app-help phrases (see app_help_explicit_patterns in intent_router.py).
# Pure dense search alone measurably confuses closely-related sections
# across features here — e.g. "tôi tải phiếu xét nghiệm ở đâu?" scored
# history.md's generic "feature này dùng để làm gì?" section (0.7639)
# slightly above upload-analysis.md's own answer (0.7582). When a query
# unambiguously names a known feature, restrict the dense search to that
# feature's chunks via a metadata filter instead of trusting raw
# similarity across the whole corpus — this only picks WHICH feature,
# dense search still picks the best section within it.
FEATURE_HINTS: dict[str, str] = {
    "tai phieu xet nghiem o dau": "upload-analysis",
    "tai phieu o dau": "upload-analysis",
    "lam sao tai phieu": "upload-analysis",
    "lam sao de tai phieu": "upload-analysis",
    "khong tai duoc phieu": "upload-analysis",
    "huong dan toi tai phieu": "upload-analysis",
    "huong dan tai phieu": "upload-analysis",
    "huong dan xem lich su": "history",
    "huong dan xem xu huong": "trends",
    "huong dan xem ket qua": "analysis-results",
    "huong dan dung ocr": "ocr-review",
    "huong dan toi dung ocr": "ocr-review",
    "chuc nang ocr": "ocr-review",
    "ocr dung de lam gi": "ocr-review",
    "ocr cua ung dung": "ocr-review",
    "tai sao phai xac nhan ocr": "ocr-review",
    "vi sao phai xac nhan ocr": "ocr-review",
    "sua ho so o dau": "profile",
    "sua thong tin ca nhan o dau": "profile",
    "chinh sua ho so o dau": "profile",
    "xem canh bao khan cap o dau": "critical-alerts",
}


def _feature_hint(query: str) -> str | None:
    normalized = _normalize(query)
    for phrase, feature in FEATURE_HINTS.items():
        if phrase in normalized:
            return feature
    return None


def strip_explicit_analyte(message: str) -> str:
    """Remove an explicit analyte name (e.g. "WBC", "HbA1c") from a query
    before embedding it for App Help retrieval.

    A navigational question like "Làm sao xem xu hướng WBC?" and "...
    HbA1c?" should retrieve the SAME trends.md doc — the analyte name is
    noise for "which app feature" but real signal for "which lab value",
    so leaving it in measurably drags the embedding score down toward the
    noise floor (evidence: with the analyte present, the genuine-question
    score floor is ~0.68, overlapping the ~0.68 ceiling of adjacent-but-
    unsupported questions like "xuất phiếu ra PDF ở đâu?"; stripped, the
    genuine floor rises to ~0.73 with a clean margin above that ceiling —
    see docs/version-handoff or the Phase 2 implementation report for the
    measurement). This only runs for the already-classified APP_HELP path,
    so it can never suppress a real medical query elsewhere.
    """
    try:
        repo = ReferenceRepository.from_default_files()
    except ReferenceRepositoryError:
        return message
    aliases = sorted(repo.analyte_aliases.keys(), key=len, reverse=True)
    for alias in aliases:
        pattern = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
        if pattern.search(message):
            return pattern.sub("", message).strip()
    return message


def _matches_role(chunk_role: str, requester_role: str | None) -> bool:
    if requester_role is None or requester_role not in _KNOWN_ROLE_VALUES:
        return True
    allowed = {token.strip() for token in chunk_role.split(",")}
    return requester_role in allowed


class AppHelpRetriever:
    def __init__(self, *, vector_store: VectorStore, min_score: float, top_k: int) -> None:
        self._vector_store = vector_store
        self._min_score = min_score
        self._top_k = top_k

    def retrieve(self, query: str, *, requester_role: str | None = None) -> AppHelpRetrievalResult:
        embed_query = strip_explicit_analyte(query)
        hint_feature = _feature_hint(query)
        search_filter = {"feature": hint_feature} if hint_feature else None
        raw = self._vector_store.search(embed_query, k=self._top_k, filter=search_filter)
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        ids = (raw.get("ids") or [[]])[0]

        matches: list[AppHelpChunkMatch] = []
        for index, document in enumerate(documents):
            score = 1.0 - float(distances[index]) if index < len(distances) else 0.0
            if score < self._min_score:
                continue
            metadata = metadatas[index] if index < len(metadatas) else {}
            matches.append(
                AppHelpChunkMatch(
                    chunk_id=ids[index] if index < len(ids) else "",
                    text=document,
                    feature=str(metadata.get("feature", "")),
                    role=str(metadata.get("role", "")),
                    route=str(metadata.get("route", "")),
                    heading=str(metadata.get("heading", "")),
                    source_file=str(metadata.get("source_file", "")),
                    score=score,
                )
            )

        # Role is a soft signal, not a hard filter: a doctor asking about a
        # patient-only workflow should still get the real answer (with a
        # role-aware caveat composed by the caller), not silence. Only
        # reorder so same-role content ranks first.
        matches.sort(key=lambda match: (not _matches_role(match.role, requester_role), -match.score))
        return AppHelpRetrievalResult(query=query, matches=matches)


def get_app_help_retriever() -> AppHelpRetriever:
    settings = get_settings()
    if not settings.app_help_rag_enabled:
        raise AppHelpRetrieverError("App Help RAG is disabled")
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.app_help_collection_name,
        corpus_version=settings.app_help_corpus_version,
        embedding_provider=get_embedding_provider(),
    )
    return AppHelpRetriever(
        vector_store=store,
        min_score=settings.app_help_retrieval_min_score,
        top_k=settings.app_help_retrieval_top_k,
    )
