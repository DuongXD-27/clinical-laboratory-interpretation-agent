from __future__ import annotations

import logging
import re
import textwrap
import unicodedata
from collections.abc import Sequence

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    BlockedPayload,
    DataPayload,
    DataType,
    DoctorQuestionsPayload,
    ExplanationDataPayload,
    IntentEnum,
    NeedsInputPayload,
    OrchestratorResponse,
    ReasonCode,
    ResponseStatus,
    SuggestedAction,
    TrendDataPayload,
)
from src.services.llm import get_llm
from src.services.medical_safety_validator import MedicalSafetyValidator

logger = logging.getLogger(__name__)


class ComposedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=600)


_ACTION_ADAPTER = TypeAdapter(SuggestedAction)


_TREND_ASSESSMENT_LABELS = {
    "low": "THẤP",
    "normal": "BÌNH THƯỜNG",
    "high": "CAO",
    "unknown": "CHƯA XÁC ĐỊNH (UNKNOWN)",
}


def _format_trend_measurement(value: float, unit: str) -> str:
    separator = "" if unit == "%" else " "
    return f"{value}{separator}{unit}".rstrip()


def _compose_trend_message(data: TrendDataPayload) -> str:
    trend = data.trend
    points = sorted(trend.points, key=lambda point: point.test_date)
    analyte_name = trend.display_name or trend.analyte_canonical
    lines = [f"Xu hướng {analyte_name} của bạn qua {len(points)} lần xét nghiệm:"]

    for point in points:
        measurement = _format_trend_measurement(point.value, trend.canonical_unit)
        lines.append(f"- {point.test_date.strftime('%d/%m/%Y')}: {measurement}")

    if trend.observed_direction == "increasing":
        lines.append("\nCác giá trị tăng qua các lần đo được ghi nhận.")
    elif trend.observed_direction == "decreasing":
        lines.append("\nCác giá trị giảm qua các lần đo được ghi nhận.")

    latest = points[-1]
    latest_measurement = _format_trend_measurement(latest.value, trend.canonical_unit)
    latest_assessment = _TREND_ASSESSMENT_LABELS.get(
        latest.assessment.casefold(),
        latest.assessment.upper(),
    )
    lines.append(
        f"Giá trị gần nhất là {latest_measurement} và được đánh dấu {latest_assessment}."
    )

    if trend.critical_alert is not None:
        lines.append(f"\n⚠️ CẢNH BÁO: {trend.critical_alert.message}")

    return "\n".join(lines)


def _compose_doctor_questions_message(data: DoctorQuestionsPayload) -> str:
    questions = sorted(data.questions, key=lambda question: question.display_order)
    if not questions:
        return "Hiện chưa có câu hỏi gợi ý phù hợp cho phiếu hoặc chỉ số này."

    lines = ["Bạn có thể trao đổi với bác sĩ các câu hỏi sau:"]
    for index, question in enumerate(questions, start=1):
        lines.append(f"{index}. {question.text}")
    return "\n".join(lines)


def _format_whole_report_deterministic_summary(data: AnalysisDataPayload) -> str:
    critical_names = {alert.indicator_name for alert in data.critical_alerts}
    for ind in data.indicators:
        if getattr(ind, "is_critical", False) or getattr(ind, "critical_status", None):
            critical_names.add(ind.name)
            if ind.analyte_canonical:
                critical_names.add(ind.analyte_canonical)

    critical_indicators = [
        ind for ind in data.indicators
        if ind.name in critical_names or (ind.analyte_canonical and ind.analyte_canonical in critical_names)
        or getattr(ind, "is_critical", False) or getattr(ind, "critical_status", None)
    ]
    critical_ind_names = {ind.name for ind in critical_indicators} | {ind.analyte_canonical for ind in critical_indicators if ind.analyte_canonical}

    abnormal_indicators = [
        ind for ind in data.indicators
        if str(ind.status).casefold() in {"high", "low"}
        and ind.name not in critical_ind_names
        and (not ind.analyte_canonical or ind.analyte_canonical not in critical_ind_names)
        and not getattr(ind, "is_critical", False)
        and not getattr(ind, "critical_status", None)
    ]

    unknown_indicators = [
        ind for ind in data.indicators
        if str(ind.status).casefold() == "unknown"
        and ind.name not in critical_ind_names
        and (not ind.analyte_canonical or ind.analyte_canonical not in critical_ind_names)
    ]

    normal_count = sum(
        1 for ind in data.indicators
        if str(ind.status).casefold() == "normal"
        and ind.name not in critical_ind_names
        and (not ind.analyte_canonical or ind.analyte_canonical not in critical_ind_names)
    )

    lines = ["Dưới đây là tổng hợp kết quả xét nghiệm của bạn:"]

    if data.critical_alerts or critical_indicators:
        lines.append("\n⚠️ CHỈ SỐ NGUY KỊCH:")
        if data.critical_alerts:
            for alert in data.critical_alerts:
                lines.append(f"- {alert.indicator_name}: {alert.value} {alert.unit} - {alert.message}")
        else:
            for ind in critical_indicators:
                name = ind.analyte_canonical or ind.name
                lines.append(f"- {name}: {ind.value} {ind.unit} (NGUY KỊCH)")

    if abnormal_indicators:
        lines.append("\nCác chỉ số nằm ngoài khoảng tham chiếu:")
        for ind in abnormal_indicators:
            name = ind.analyte_canonical or ind.name
            status_str = "CAO" if str(ind.status).casefold() == "high" else "THẤP"
            ref_str = f" (tham chiếu: {ind.reference_low} - {ind.reference_high} {ind.unit})" if ind.reference_low is not None and ind.reference_high is not None else ""
            lines.append(f"- {name}: {ind.value} {ind.unit}{ref_str} [{status_str}]")

    if unknown_indicators:
        lines.append("\nCác chỉ số chưa xác định khoảng tham chiếu:")
        for ind in unknown_indicators:
            name = ind.analyte_canonical or ind.name
            lines.append(f"- {name}: {ind.value} {ind.unit}")

    if normal_count > 0:
        lines.append(f"\nCó {normal_count} chỉ số nằm trong khoảng tham chiếu thông thường.")

    if not critical_indicators and not abnormal_indicators and not unknown_indicators and normal_count > 0:
        lines = ["Tất cả các chỉ số xét nghiệm đã phân tích đều nằm trong khoảng tham chiếu thông thường."]

    if abnormal_indicators or critical_indicators:
        first_notable = (critical_indicators + abnormal_indicators)[0]
        name = first_notable.analyte_canonical or first_notable.name
        lines.append(f"\nBạn có thể hỏi thêm về chỉ số cụ thể (ví dụ: 'Giải thích kỹ hơn {name}') nếu cần.")

    return "\n".join(lines)


_EXPLANATION_STATUS_LABELS = {
    "low": "THẤP",
    "normal": "BÌNH THƯỜNG",
    "high": "CAO",
    "unknown": "CHƯA XÁC ĐỊNH (UNKNOWN)",
}

_CRITICAL_SIDE_LABELS = {
    "critical_high": "NGUY KỊCH (CAO)",
    "critical_low": "NGUY KỊCH (THẤP)",
}


def _compose_explanation_message(data: ExplanationDataPayload) -> str:
    """ORCH-V1.4C deterministic single-analyte composition.

    One canonical path:
        ExplanationDataPayload with structured facts,
        deterministic single-analyte composer,
        final response.

    Output = DETERMINISTIC FACT BLOCK + EXISTING APPROVED EXPLANATION PROSE.
    The general composer LLM is never invoked for this path, so it can never
    rewrite value, unit, reference status, range or critical facts. Numeric
    and unit formatting reuses the existing conventions (no rounding, no
    invented operators); the two-sided range is rendered ONLY when both
    authoritative bounds are available.
    """
    facts = data.facts
    if facts is None:  # pragma: no cover - callers guarantee facts
        return ""
    if facts.critical_status is not None:
        status_label = _CRITICAL_SIDE_LABELS.get(facts.critical_status, facts.critical_status.upper())
    else:
        status_key = str(facts.status).casefold()
        status_label = _EXPLANATION_STATUS_LABELS.get(status_key, str(facts.status).upper())
    fact_lines = [
        f"Kết quả {facts.analyte_name} của bạn:",
    ]
    if data.presentation_mode == "status_first":
        fact_lines.extend((
            f"- Trạng thái: {status_label}",
            f"- Giá trị: {facts.value} {facts.unit}",
        ))
    else:
        fact_lines.extend((
            f"- Giá trị: {facts.value} {facts.unit}",
            f"- Trạng thái: {status_label}",
        ))
    if facts.has_two_sided_reference_range:
        fact_lines.append(f"- Khoảng tham chiếu: {facts.reference_low} - {facts.reference_high} {facts.unit}")
    if facts.critical_status == "critical_high":
        fact_lines.append(f"\n⚠️ CẢNH BÁO: {facts.analyte_name} tăng tới ngưỡng nguy kịch. Yêu cầu can thiệp y tế.")
    elif facts.critical_status == "critical_low":
        fact_lines.append(f"\n⚠️ CẢNH BÁO: {facts.analyte_name} giảm tới ngưỡng nguy kịch. Yêu cầu can thiệp y tế.")
    elif facts.approved_critical_message:
        # Approved existing critical warning, preserved verbatim.
        fact_lines.append(f"\n⚠️ {facts.approved_critical_message}")
    approved_explanation = data.explanation.strip()
    if data.presentation_mode == "education_first" and approved_explanation:
        lines = [approved_explanation, "", *fact_lines]
    else:
        lines = fact_lines
        if approved_explanation:
            lines.extend(("", approved_explanation))
    return "\n".join(lines)


def _compose_doctor_questions_message(data: DoctorQuestionsPayload) -> str:
    if not data.questions:
        return "Hiện chưa có câu hỏi phù hợp cho chỉ số hoặc phiếu xét nghiệm này."
    lines = ["Đây là các câu hỏi gợi ý để trao đổi với bác sĩ:"]
    lines.extend(f"{index}. {question.text}" for index, question in enumerate(data.questions, start=1))
    return "\n".join(lines)


def deterministic_message_for(status: ResponseStatus, reason_code: ReasonCode | None, intent: IntentEnum, data: DataPayload | None = None) -> str:
    if reason_code == ReasonCode.OUT_OF_SCOPE:
        from src.orchestrator.service import OUT_OF_SCOPE_MESSAGE
        return OUT_OF_SCOPE_MESSAGE
    if reason_code == ReasonCode.SENSITIVE_SYSTEM_REQUEST:
        from src.orchestrator.service import SENSITIVE_SYSTEM_MESSAGE
        return SENSITIVE_SYSTEM_MESSAGE
    if reason_code == ReasonCode.UNSUPPORTED_ANALYTE:
        return "Chỉ số này chưa nằm trong phạm vi hỗ trợ an toàn của hệ thống."
    if reason_code == ReasonCode.UNSUPPORTED_CAPABILITY:
        return "Chức năng này chưa được hỗ trợ cho phiên hiện tại."
    if reason_code == ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED:
        return "Hiện mình chưa thấy phiếu xét nghiệm nào trong tài khoản của bạn. Bạn có thể gửi ảnh phiếu xét nghiệm hoặc nhập kết quả để mình hỗ trợ."
    if reason_code == ReasonCode.TREND_INSUFFICIENT_POINTS:
        return "Chưa đủ dữ liệu để tạo xu hướng cho chỉ số này."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.VIEW_HISTORY:
        return "Đây là phiếu xét nghiệm gần nhất trong lịch sử của bạn."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.ANALYZE_TREND:
        if (
            isinstance(data, TrendDataPayload)
            and data.trend.trend_available
            and len(data.trend.points) >= 3
        ):
            return _compose_trend_message(data)
        return "Đây là xu hướng của chỉ số đã chọn."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.GET_DOCTOR_QUESTIONS:
        if isinstance(data, DoctorQuestionsPayload):
            return _compose_doctor_questions_message(data)
        return "Hiện chưa có câu hỏi phù hợp cho phiếu xét nghiệm này."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.EXPLAIN_CURRENT_RESULT:
        if isinstance(data, AnalysisDataPayload):
            return _format_whole_report_deterministic_summary(data)
        if isinstance(data, ExplanationDataPayload):
            if data.facts is not None:
                return _compose_explanation_message(data)
            # 0e128c5 contract: approved bare prose (no fact block) surfaces
            # VERBATIM in the deterministic path — never swapped for a
            # generic placeholder. A later refactor in the same PR range
            # dropped this branch; restored.
            return data.explanation or "Đây là phần giải thích đã được tạo cho chỉ số hiện tại."
        return "Đây là phần giải thích đã được tạo cho chỉ số hiện tại."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.APP_HELP:
        # The dispatcher already put the exact (verbatim, grounded) answer
        # in data.explanation — this function must surface it as-is, not
        # fall through to the generic AnalysisDataPayload-shaped message
        # below (which ignores ExplanationDataPayload entirely).
        if isinstance(data, ExplanationDataPayload):
            return data.explanation
        return "Tôi chưa tìm thấy hướng dẫn phù hợp cho câu hỏi này."
    if status == ResponseStatus.SUCCESS:
        if isinstance(data, AnalysisDataPayload):
            return _format_whole_report_deterministic_summary(data)
        return "Đây là kết quả phân tích hiện có."
    return "Tôi cần thêm thông tin để tiếp tục an toàn."


def _safety_refusal_message(reason_code: ReasonCode | None) -> str:
    if reason_code == ReasonCode.MEDICAL_DIAGNOSIS_REQUEST:
        return (
            "Mình không thể đưa ra chẩn đoán bệnh hoặc khẳng định tình trạng bệnh lý của bạn. "
            "Bạn nên trao đổi trực tiếp với bác sĩ chuyên khoa để được thăm khám chính xác. "
            "Mình có thể hỗ trợ giải thích ý nghĩa các chỉ số xét nghiệm hoặc gợi ý câu hỏi để bạn trao đổi cùng bác sĩ."
        )
    if reason_code == ReasonCode.MEDICAL_CAUSE_REQUEST:
        return (
            "Mình không thể xác định nguyên nhân cá nhân dẫn đến kết quả này. "
            "Để hiểu rõ nguyên nhân, bác sĩ cần thăm khám kết hợp với các triệu chứng lâm sàng và tiền sử bệnh của bạn. "
            "Mình có thể hỗ trợ giải thích ý nghĩa tổng quan của chỉ số hoặc gợi ý câu hỏi cho bác sĩ."
        )
    if reason_code == ReasonCode.TREATMENT_REQUEST:
        return (
            "Mình không thể hướng dẫn phương pháp điều trị hay tư vấn sử dụng thuốc. "
            "Bạn nên tham khảo ý kiến bác sĩ để có kế hoạch chăm sóc và điều trị phù hợp và an toàn nhất."
        )
    return "Tôi không thể hỗ trợ yêu cầu này an toàn."


def map_needs_input_prompt(missing_fields: list[str], fallback: str) -> str:
    if "current_report_ref" in missing_fields:
        return (
            "Hiện mình chưa thấy phiếu xét nghiệm nào trong tài khoản của bạn.\n\n"
            "Bạn có thể gửi ảnh phiếu xét nghiệm hoặc nhập kết quả để mình hỗ trợ."
        )
    if "current_analyte" in missing_fields:
        return (
            "Bạn muốn xem chỉ số nào?\n\n"
            "Bạn có thể chọn một chỉ số trong phiếu xét nghiệm hoặc nhập tên chỉ số, ví dụ:\n"
            "- WBC\n"
            "- Glucose\n"
            "- HbA1c\n"
            "- Cholesterol"
        )
    if "analysis_input" in missing_fields:
        return "Bạn hãy gửi phiếu xét nghiệm bằng ảnh hoặc nhập kết quả thủ công để mình có thể phân tích."
    return fallback


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _deduplicate(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _sources_from_data(data: DataPayload) -> list[str]:
    if isinstance(data, ExplanationDataPayload):
        return _deduplicate(data.sources)
    if isinstance(data, AnalysisDataPayload):
        sources: list[str] = []
        for indicator in data.indicators:
            sources.extend(indicator.sources)
        return _deduplicate(sources)
    return []


def _payload_summary(data: DataPayload) -> str:
    if isinstance(data, AnalysisDataPayload):
        critical_names = {alert.indicator_name for alert in data.critical_alerts}
        for ind in data.indicators:
            if getattr(ind, "is_critical", False) or getattr(ind, "critical_status", None):
                critical_names.add(ind.name)
                if ind.analyte_canonical:
                    critical_names.add(ind.analyte_canonical)

        critical_list = [
            f"{ind.name}: {ind.value} {ind.unit} (CRITICAL)"
            for ind in data.indicators
            if ind.name in critical_names or getattr(ind, "is_critical", False)
        ]
        abnormal_list = [
            f"{ind.analyte_canonical or ind.name}: {ind.value} {ind.unit} ({ind.status.upper()}, ref: {ind.reference_low}-{ind.reference_high})"
            for ind in data.indicators
            if str(ind.status).casefold() in {"high", "low"} and ind.name not in critical_names and not getattr(ind, "is_critical", False)
        ]
        unknown_list = [
            f"{ind.analyte_canonical or ind.name}: {ind.value} {ind.unit}"
            for ind in data.indicators
            if str(ind.status).casefold() == "unknown" and ind.name not in critical_names
        ]
        normal_count = sum(
            1 for ind in data.indicators
            if str(ind.status).casefold() == "normal" and ind.name not in critical_names
        )
        return (
            f"Payload: whole report analysis. Total indicators: {len(data.indicators)}. "
            f"Critical findings ({len(critical_list)}): {', '.join(critical_list) or 'none'}. "
            f"Abnormal High/Low findings ({len(abnormal_list)}): {', '.join(abnormal_list) or 'none'}. "
            f"Unknown reference findings ({len(unknown_list)}): {', '.join(unknown_list) or 'none'}. "
            f"Normal indicators count: {normal_count}."
        )
    if isinstance(data, ExplanationDataPayload):
        return f"Payload: explanation. Approved explanation: {data.explanation[:800]}"
    if data.data_type == DataType.HISTORY_SUMMARY:
        return "Payload: history summary. Report summary is available to the user."
    if data.data_type == DataType.TREND:
        return "Payload: trend. Deterministic trend data is available to the user."
    if data.data_type == DataType.DOCTOR_QUESTIONS:
        return "Payload: doctor questions. Server-generated questions are available."
    if isinstance(data, NeedsInputPayload):
        return f"Payload: needs input. Missing fields: {', '.join(data.missing_fields)}."
    if isinstance(data, BlockedPayload):
        return f"Payload: blocked. Reason: {data.reason_code}."
    return f"Payload: {data.data_type}."


_APP_HELP_EXTRA_RULES = """
        This is an APP_HELP answer: the "Deterministic fallback message" is a
        verbatim excerpt from the product's own How-To-Use documentation. It
        currently reads like internal docs (repeated section headings,
        `file.md` references) — your job is ONLY to make it read like a
        friendly chat reply, not to add or change what it says.
        Hard rules, no exceptions:
        - Do not mention, rename, or invent ANY route, button label, menu
          item, filename, or app feature that is not already present
          verbatim in the fallback message below.
        - Do not add steps, conditions, or capabilities the fallback message
          does not state. If something is not mentioned, stay silent about
          it — do not guess or fill gaps.
        - You MAY: drop the leading heading line, remove `like_this.md` file
          references, turn a numbered/bulleted list into natural prose or
          keep it as a list (either is fine), and smooth the tone.
        - The user navigates by clicking menu items on screen, not by typing
          a URL — so ALWAYS drop raw route/API paths like `/patient/analysis`
          or `/api/v1/ocr/policy`, and code-ish identifiers like
          `HistoryPanel.tsx` or `getRole() === "patient"`. Keep the visible
          menu/button label (e.g. mục "Phân tích xét nghiệm") — just cut the
          technical path/identifier next to it. This is a subtraction, not
          an invention, so it is always safe to do.
        - If in doubt, prefer copying a sentence unchanged over rephrasing it.
"""


def _composer_prompt(
    *,
    intent: IntentEnum,
    status: ResponseStatus,
    reason_code: ReasonCode | None,
    data: DataPayload,
    fallback_message: str,
) -> str:
    extra_rules = _APP_HELP_EXTRA_RULES if intent == IntentEnum.APP_HELP else ""
    return textwrap.dedent(
        f"""\
        You write one short patient-facing message in Vietnamese.

        You may rewrite or summarize approved canonical information only.
        You may not recalculate medical status, reinterpret reference ranges,
        create diagnoses, infer causes, recommend treatment, invent facts,
        invent sources, invent actions, or change server fields.
        If whole report analysis is provided, summarize findings by highlighting critical/abnormal indicators first, mentioning unknown/unresolved indicators separately, summarizing normal indicators, and offering a safe follow-up question.
        {extra_rules}
        Server-controlled fields:
        intent={intent.value}
        status={status.value}
        reason_code={reason_code.value if reason_code else "none"}

        Canonical bounded context:
        {_payload_summary(data)}

        Deterministic fallback message:
        {fallback_message}

        Return only the message field.
        """
    )


async def compose_message(
    *,
    intent: IntentEnum,
    status: ResponseStatus,
    reason_code: ReasonCode | None,
    data: DataPayload,
    fallback_message: str,
) -> str:
    if status != ResponseStatus.SUCCESS:
        return fallback_message
    if isinstance(data, TrendDataPayload):
        return fallback_message
    if isinstance(data, DoctorQuestionsPayload):
        return fallback_message
    if isinstance(data, ExplanationDataPayload) and data.facts is not None:
        # ORCH-V1.4C: one canonical deterministic path. The general composer
        # LLM must NOT run for fact-bearing single-analyte explanations, so
        # hostile or incorrect rewrites of value/unit/status/range/critical
        # facts can never reach the final response. Restored after the
        # conversation-persistence refactor dropped it: with a live LLM the
        # rewrite reordered the deterministic fact block and destroyed both
        # the ORCH-V1.4C contracts and the G2 education-first ordering
        # ("WBC là gì?" must lead with approved education, "WBC là bao
        # nhiêu?" must lead with the fact block — in BOTH composer modes).
        return fallback_message
    prompt = _composer_prompt(
        intent=intent,
        status=status,
        reason_code=reason_code,
        data=data,
        fallback_message=fallback_message,
    )
    try:
        structured_llm = get_llm().with_structured_output(ComposedMessage)
        raw = await structured_llm.ainvoke([HumanMessage(content=prompt)])
        composed = raw if isinstance(raw, ComposedMessage) else ComposedMessage.model_validate(raw)
    except Exception as exc:
        logger.info("Response composer unavailable; using deterministic fallback: %s", exc)
        return fallback_message
    message = composed.message.strip() or fallback_message
    if intent == IntentEnum.APP_HELP and _app_help_rewrite_introduces_new_label(message, fallback_message):
        # Safety net, not just a prompt instruction: the LLM is asked not to
        # invent routes/button names, but a prompt is a request, not a
        # guarantee (yeu-cau-vu.txt AH-10 needs a guarantee). If the rewrite
        # names a quoted UI label or route that isn't in the source text,
        # discard the rewrite and fall back to the verbatim corpus text.
        logger.info("App Help rewrite introduced an unverified label/route; using verbatim fallback")
        return fallback_message
    if intent == IntentEnum.APP_HELP and _app_help_rewrite_keeps_forbidden_artifact(message):
        # Second, independent net: raw route paths / code filenames / chunk
        # IDs must never reach the chat regardless of whether they existed in
        # the source — the deterministic cleanup already stripped them from
        # the fallback text, so a rewrite still carrying one reintroduced or
        # retained it. Found live during final-integration verification: the
        # model kept doctor-questions.md's inline `/patient/analysis`-style
        # paths verbatim despite _APP_HELP_EXTRA_RULES.
        logger.info("App Help rewrite kept a forbidden artifact; using verbatim fallback")
        return fallback_message
    return message


_QUOTED_LABEL_RE = re.compile(r'"([^"]{2,60})"|\*\*([^*]{2,60})\*\*')
_ROUTE_PATH_RE = re.compile(r"/[a-zA-Z][a-zA-Z0-9/_-]*")
_FORBIDDEN_ARTIFACT_RE = re.compile(
    r"`?/(?:patient|doctor|api)\b"  # raw app/API route path
    r"|[\w.-]+\.(?:tsx|ts|jsx|mjs|py|md)\b"  # code/doc filename
    r"|\w+::[\w-]+"  # internal chunk ID ("feature::section")
)


def _app_help_rewrite_keeps_forbidden_artifact(rewritten: str) -> bool:
    """True if `rewritten` still shows any raw route path, code/doc filename,
    or internal chunk ID — artifacts that must never reach an APP_HELP chat
    message no matter what the source contained."""
    return bool(_FORBIDDEN_ARTIFACT_RE.search(rewritten))


def _extract_labels_and_routes(text: str) -> set[str]:
    found: set[str] = set()
    for match in _QUOTED_LABEL_RE.finditer(text):
        label = (match.group(1) or match.group(2) or "").strip().casefold()
        if label:
            found.add(label)
    for match in _ROUTE_PATH_RE.finditer(text):
        found.add(match.group(0).casefold())
    return found


def _app_help_rewrite_introduces_new_label(rewritten: str, source: str) -> bool:
    """True if `rewritten` names a quoted UI label/button or a route path
    that never appeared in `source` — i.e. the LLM likely invented it."""
    source_labels = _extract_labels_and_routes(source)
    rewritten_labels = _extract_labels_and_routes(rewritten)
    return not rewritten_labels.issubset(source_labels)


def _canonical_statuses(data: DataPayload) -> list[str]:
    if not isinstance(data, AnalysisDataPayload):
        return []
    return [str(indicator.status).casefold() for indicator in data.indicators]


def _message_contradicts_canonical_data(message: str, data: DataPayload) -> bool:
    normalized = _normalize(message)
    if not normalized:
        return False
    if isinstance(data, AnalysisDataPayload) and data.indicators:
        critical_count = len(data.critical_alerts) + sum(
            1 for ind in data.indicators if getattr(ind, "is_critical", False) or getattr(ind, "critical_status", None)
        )
        abnormal_count = sum(
            1 for ind in data.indicators
            if str(ind.status).casefold() in {"high", "low"}
            and not getattr(ind, "is_critical", False)
            and not getattr(ind, "critical_status", None)
        )
        normal_count = sum(
            1 for ind in data.indicators
            if str(ind.status).casefold() == "normal" and not getattr(ind, "is_critical", False)
        )
        total = len(data.indicators)

        if total > 0 and normal_count == total:
            if any(term in normalized for term in ("nguy kich", "critical", "cao", "thap", "bat thuong")):
                return True

        if total > 0 and normal_count == 0 and (abnormal_count > 0 or critical_count > 0):
            if "tat ca binh thuong" in normalized or "hoan toan binh thuong" in normalized or (
                "binh thuong" in normalized and not any(term in normalized for term in ("cao", "thap", "nguy kich", "bat thuong", "ngoai", "ngoai khoang"))
            ):
                return True

        if critical_count > 0:
            if "hoan toan binh thuong" in normalized or "khong co gi bat thuong" in normalized:
                return True

    return False


def _guardrail_blocked_response(intent: IntentEnum, message: str = "Nội dung phản hồi không vượt qua kiểm duyệt an toàn.") -> OrchestratorResponse:
    return OrchestratorResponse(
        intent=intent,
        status=ResponseStatus.BLOCKED,
        message=message,
        data_type=DataType.BLOCKED,
        data=BlockedPayload(
            safety_notice=message,
            disclaimer="Thông tin này chỉ mang tính giáo dục và không thay thế tư vấn y khoa.",
            reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        ),
        reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        suggested_actions=[],
        sources=[],
        safety_notice=message,
    )


def _validate_actions(actions: Sequence[object]) -> list[SuggestedAction]:
    return [_ACTION_ADAPTER.validate_python(action) for action in actions]


def enforce_final_response(response: OrchestratorResponse) -> OrchestratorResponse:
    try:
        validated = OrchestratorResponse.model_validate(response.model_dump())
    except Exception:
        return _guardrail_blocked_response(response.intent)

    validator = MedicalSafetyValidator()
    if validator.validate(validated.message):
        return _guardrail_blocked_response(validated.intent)
    if _message_contradicts_canonical_data(validated.message, validated.data):
        return _guardrail_blocked_response(validated.intent)
    return validated


async def build_final_response(
    *,
    intent: IntentEnum,
    status: ResponseStatus,
    data: DataPayload,
    reason_code: ReasonCode | None = None,
    suggested_actions: Sequence[object] = (),
) -> OrchestratorResponse:
    fallback_message = deterministic_message_for(status, reason_code, intent, data)

    if isinstance(data, NeedsInputPayload):
        friendly_prompt = map_needs_input_prompt(data.missing_fields, fallback_message)
        data = data.model_copy(update={"prompt": friendly_prompt})
        fallback_message = friendly_prompt

    message = await compose_message(
        intent=intent,
        status=status,
        reason_code=reason_code,
        data=data,
        fallback_message=fallback_message,
    )
    try:
        actions = _validate_actions(suggested_actions)
    except Exception:
        return _guardrail_blocked_response(intent)
    response = OrchestratorResponse(
        intent=intent,
        status=status,
        message=message,
        data_type=data.data_type,
        data=data,
        reason_code=reason_code,
        suggested_actions=actions,
        sources=_sources_from_data(data),
        safety_notice=data.safety_notice if isinstance(data, BlockedPayload) else None,
    )
    return enforce_final_response(response)


def build_provenance_response(data: ExplanationDataPayload) -> OrchestratorResponse:
    """CHAT-V1.5-R1-G1: deterministic provenance response assembly.

    The provenance wording rendered by the dispatcher is authoritative and is
    copied verbatim into the final message. The general composer LLM never
    runs on this path, so it can never invent or rewrite a source identity.
    The assembled response still passes the same final safety guardrails as
    every other response.
    """
    return enforce_final_response(
        OrchestratorResponse(
            intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
            status=ResponseStatus.SUCCESS,
            message=data.explanation,
            data_type=data.data_type,
            data=data,
            sources=list(data.sources),
        )
    )


__all__ = [
    "ComposedMessage",
    "build_final_response",
    "build_provenance_response",
    "compose_message",
    "deterministic_message_for",
    "enforce_final_response",
    "map_needs_input_prompt",
]
