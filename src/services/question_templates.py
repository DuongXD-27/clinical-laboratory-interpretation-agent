"""Sinh câu hỏi gợi ý bệnh nhân mang đi hỏi bác sĩ.

Sinh bằng **tra cứu bộ câu mẫu** theo cặp (analyte_id, status), không bằng LLM.
Lý do khớp nguyên tắc xuyên suốt của dự án (ADR-008): nội dung y khoa do tra cứu
quyết định, LLM chỉ diễn đạt lại. Cụ thể ở đây:

- Câu mẫu duyệt trước được, đúng cách các bài giải thích đang được duyệt.
- Không bao giờ vượt ranh giới nội dung, vì câu chữ là cố định.
- Test cố định được — đầu ra ngẫu nhiên thì không kiểm được, mà tiêu chí nghiệm
  thu của chức năng này đòi hỏi test cố định.

Chỗ cắm LLM về sau: ``paraphrase_hook`` trong :func:`generate_questions`. Một
bước diễn đạt lại chỉ được phép đổi câu chữ của ``text``, không được thêm dữ
kiện và không được đổi ``analyte_id`` / ``priority`` / thứ tự. Guardrail vẫn
chạy sau như lớp cuối cùng, vì câu mẫu vẫn có thể bị sửa sai về sau.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Tối đa 5 câu cho toàn bộ phiếu, kể cả khi có nhiều chỉ số bất thường cùng lúc.
# Một danh sách 12 câu mang vào phòng khám 5 phút sẽ dẫn tới việc không hỏi được
# câu nào.
MAX_QUESTIONS = 5

# Chỉ số `unknown` có ngân sách riêng, KHÔNG cạnh tranh suất với chỉ số thật sự
# bất thường. Nếu để chung, một phiếu có 4 chỉ số nguy kịch + 2 chỉ số unknown sẽ
# hoặc đánh mất câu hỏi về unknown, hoặc chiếm mất suất của một chỉ số nguy kịch.
# Mỗi chỉ số unknown một câu riêng có nêu tên, vì một câu gộp chung sẽ khiến bác
# sĩ không biết đang nói về dòng nào trên phiếu.
MAX_UNKNOWN_QUESTIONS = 2

PRIORITY_CRITICAL = "critical"
PRIORITY_ABNORMAL = "abnormal"
PRIORITY_UNKNOWN = "unknown"
PRIORITY_FALLBACK = "fallback"

_CRITICAL_STATUSES = frozenset({"critical_low", "critical_high"})
_ABNORMAL_STATUSES = frozenset({"low", "high"})
_LOW_STATUSES = frozenset({"low", "critical_low"})
_HIGH_STATUSES = frozenset({"high", "critical_high"})

_TEMPLATE_PATH = Path("data/reference/question_templates.json")


@dataclass(frozen=True)
class GeneratedQuestion:
    """Một câu hỏi gợi ý kèm đủ metadata để lưu vào phiếu."""

    text: str
    priority: str
    display_order: int
    analyte_id: str | None = None
    # Tên đúng như bệnh nhân nhìn thấy trên phiếu của họ. Dùng để nối câu hỏi
    # trở lại đúng dòng chỉ số khi lưu vào DB.
    indicator_name: str | None = None


@dataclass(frozen=True)
class QuestionTemplateLibrary:
    unknown_indicator: str
    generic: Mapping[str, str]
    analytes: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def template_for(self, analyte_id: str | None, status: str) -> str | None:
        """Mẫu riêng của chỉ số nếu có, nếu không thì mẫu chung theo status."""

        if analyte_id:
            per_analyte = self.analytes.get(analyte_id)
            if per_analyte and per_analyte.get(status):
                return per_analyte[status]

        return self.generic.get(status)


def _defaults() -> QuestionTemplateLibrary:
    """Bộ mẫu tối thiểu khi file cấu hình lỗi.

    Vẫn phải sinh được câu hỏi an toàn: chức năng này là phần bổ sung giá trị,
    một file JSON hỏng không được làm bệnh nhân mất luôn kết quả phân tích.
    """

    return QuestionTemplateLibrary(
        unknown_indicator=(
            "Chỉ số {name} ({value} {unit}) chưa có trong dữ liệu đối chiếu của "
            "ứng dụng. Bác sĩ đọc giúp tôi chỉ số này với ạ?"
        ),
        generic={
            "low": (
                "Chỉ số {name} của tôi là {value} {unit}, thấp hơn khoảng tham "
                "chiếu. Mức này có ý nghĩa gì với tình trạng của tôi ạ?"
            ),
            "high": (
                "Chỉ số {name} của tôi là {value} {unit}, cao hơn khoảng tham "
                "chiếu. Mức này có ý nghĩa gì với tình trạng của tôi ạ?"
            ),
            "critical_low": (
                "Chỉ số {name} của tôi là {value} {unit}, thấp hơn nhiều so với "
                "khoảng tham chiếu. Tôi cần làm gì ngay bây giờ ạ?"
            ),
            "critical_high": (
                "Chỉ số {name} của tôi là {value} {unit}, cao hơn nhiều so với "
                "khoảng tham chiếu. Tôi cần làm gì ngay bây giờ ạ?"
            ),
        },
        analytes={},
    )


@lru_cache(maxsize=1)
def load_question_templates() -> QuestionTemplateLibrary:
    try:
        with open(_TEMPLATE_PATH, encoding="utf-8") as file:
            payload = json.load(file)

        unknown = str(payload["unknown_indicator"]).strip()
        generic = {
            str(status): str(text).strip()
            for status, text in payload["generic"].items()
            if str(text).strip()
        }

        if not unknown or not generic:
            raise ValueError("unknown_indicator và generic không được rỗng")

        analytes = {
            str(analyte_id): {
                str(status): str(text).strip()
                for status, text in per_status.items()
                if str(text).strip()
            }
            for analyte_id, per_status in payload.get("analytes", {}).items()
        }

        return QuestionTemplateLibrary(
            unknown_indicator=unknown,
            generic=generic,
            analytes=analytes,
        )
    except Exception as exc:
        logger.error(
            "Lỗi khi đọc %s: %s. Dùng bộ câu mẫu mặc định.",
            _TEMPLATE_PATH,
            exc,
        )
        return _defaults()


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def relative_deviation(indicator: Mapping[str, Any]) -> float:
    """Mức lệch khỏi khoảng tham chiếu, đã chuẩn hoá để so được giữa các chỉ số.

    Tài liệu nghiệp vụ yêu cầu ưu tiên "chỉ số lệch xa khoảng tham chiếu nhất"
    nhưng không định nghĩa cách đo. So sánh trực tiếp mmol/L với 10^9/L là vô
    nghĩa, nên ở đây quy về **tỉ lệ so với độ rộng khoảng tham chiếu**: lệch một
    lần độ rộng khoảng thì bằng 1.0, bất kể đơn vị.

    Thoái lui khi không tính được độ rộng: chia cho chính biên bị vượt; nếu biên
    bằng 0 thì trả về khoảng cách thô. Trả 0.0 khi thiếu dữ liệu — chỉ số như vậy
    xếp cuối trong cùng mức ưu tiên chứ không làm hỏng phép sắp xếp.
    """

    status = str(indicator.get("status") or "")
    value = _as_float(indicator.get("value"))
    low = _as_float(indicator.get("reference_low"))
    high = _as_float(indicator.get("reference_high"))

    if value is None:
        return 0.0

    if status in _LOW_STATUSES and low is not None:
        distance = low - value
        bound = low
    elif status in _HIGH_STATUSES and high is not None:
        distance = value - high
        bound = high
    else:
        return 0.0

    if distance <= 0:
        return 0.0

    if low is not None and high is not None and high > low:
        return distance / (high - low)

    if bound:
        return distance / abs(bound)

    return distance


def _sort_key(indicator: Mapping[str, Any]) -> tuple:
    """Nguy kịch trước, rồi lệch xa nhất, rồi thứ tự cố định để test được.

    Tie-break bằng analyte_id sau đó tên hiển thị: hai chỉ số cùng mức nguy kịch
    hoặc lệch xa bằng nhau phải luôn ra cùng một thứ tự giữa các lần chạy, nếu
    không thì không kiểm được bằng test.
    """

    status = str(indicator.get("status") or "")
    is_critical = bool(indicator.get("is_critical")) or (status in _CRITICAL_STATUSES)

    return (
        0 if is_critical else 1,
        -relative_deviation(indicator),
        str(indicator.get("analyte_id") or ""),
        str(indicator.get("name") or ""),
    )


def _render(template: str, indicator: Mapping[str, Any]) -> str:
    """Điền tên chỉ số **đúng như bệnh nhân nhập trên phiếu**.

    Một người nhập "Đường huyết" mà nhận lại câu hỏi về "Fasting plasma glucose"
    sẽ không nhận ra đó là chỉ số của mình. Mã chuẩn (analyte_id) chỉ dùng để
    chọn mẫu câu ở bên trong.
    """

    value = indicator.get("value")
    unit = str(indicator.get("unit") or "").strip()

    return " ".join(
        template.format(
            name=str(indicator.get("name") or "").strip(),
            value="" if value is None else value,
            unit=unit,
        ).split()
    )


def generate_questions(
    indicators: Sequence[Mapping[str, Any]],
    *,
    templates: QuestionTemplateLibrary | None = None,
    paraphrase_hook: Callable[[list[GeneratedQuestion]], list[GeneratedQuestion]] | None = None,
) -> list[GeneratedQuestion]:
    """Sinh danh sách câu hỏi cho một phiếu đã được đối chiếu khoảng tham chiếu.

    Quy tắc nghiệp vụ:

    - Chỉ sinh cho chỉ số bất thường hoặc nguy kịch. Chỉ số **bình thường không
      sinh câu hỏi**: một người đọc thấy câu hỏi về chỉ số đang bình thường sẽ
      nghĩ chỉ số đó có vấn đề gì mà mình chưa nhận ra.
    - Toàn bộ chỉ số bình thường thì trả về danh sách rỗng, **không dùng câu dự
      phòng**. Bộ dự phòng chỉ dành cho trường hợp guardrail chặn nội dung, không
      phải cho trường hợp không có gì để hỏi.
    - Chỉ số ``unknown`` được một câu trung tính riêng, ngân sách tách biệt.

    ``paraphrase_hook`` là chỗ cắm bước diễn đạt lại bằng LLM ở version sau.
    """

    library = templates or load_question_templates()

    needs_question: list[Mapping[str, Any]] = []
    unknown_indicators: list[Mapping[str, Any]] = []

    for indicator in indicators:
        status = str(indicator.get("status") or "")
        is_critical = bool(indicator.get("is_critical", False))
        is_abnormal = bool(indicator.get("is_abnormal", False))

        if is_critical or is_abnormal or status in _CRITICAL_STATUSES or status in _ABNORMAL_STATUSES:
            needs_question.append(indicator)
        elif status == "unknown":
            unknown_indicators.append(indicator)

    questions: list[GeneratedQuestion] = []
    order = 0

    for indicator in sorted(needs_question, key=_sort_key)[:MAX_QUESTIONS]:
        status = str(indicator.get("status") or "")
        is_critical = bool(indicator.get("is_critical", False))
        critical_status = str(indicator.get("critical_status") or "")
        effective_status = critical_status if (is_critical and critical_status) else status

        template = library.template_for(indicator.get("analyte_id"), effective_status)
        if not template and effective_status != status:
            template = library.template_for(indicator.get("analyte_id"), status)

        if not template:
            continue

        questions.append(
            GeneratedQuestion(
                text=_render(template, indicator),
                priority=(
                    PRIORITY_CRITICAL
                    if is_critical or status in _CRITICAL_STATUSES
                    else PRIORITY_ABNORMAL
                ),
                display_order=order,
                analyte_id=indicator.get("analyte_id") or None,
                indicator_name=str(indicator.get("name") or "") or None,
            )
        )
        order += 1

    unknown_sorted = sorted(
        unknown_indicators,
        key=lambda item: (
            str(item.get("analyte_id") or ""),
            str(item.get("name") or ""),
        ),
    )

    for indicator in unknown_sorted[:MAX_UNKNOWN_QUESTIONS]:
        questions.append(
            GeneratedQuestion(
                text=_render(library.unknown_indicator, indicator),
                priority=PRIORITY_UNKNOWN,
                display_order=order,
                analyte_id=indicator.get("analyte_id") or None,
                indicator_name=str(indicator.get("name") or "") or None,
            )
        )
        order += 1

    if paraphrase_hook is not None and questions:
        questions = paraphrase_hook(questions)

    return questions


def reconcile_after_guardrail(
    final_texts: Iterable[str],
    generated: Sequence[GeneratedQuestion],
) -> list[GeneratedQuestion]:
    """Ghép danh sách câu hỏi sau guardrail trở lại với metadata lúc sinh.

    Guardrail có thể viết lại từng câu (giữ nguyên số lượng và thứ tự) hoặc thay
    cả bộ bằng câu dự phòng của Template Library (số lượng khác). Khi số lượng
    khác, **không đoán** câu nào ứng với chỉ số nào: gán hết thành
    ``priority="fallback"`` không nối chỉ số. Mất liên kết chỉ số còn hơn nối một
    câu hỏi vào sai dòng trên phiếu của bệnh nhân.
    """

    texts = [str(text).strip() for text in final_texts if str(text).strip()]

    if len(texts) == len(generated):
        return [
            GeneratedQuestion(
                text=text,
                priority=meta.priority,
                display_order=index,
                analyte_id=meta.analyte_id,
                indicator_name=meta.indicator_name,
            )
            for index, (text, meta) in enumerate(zip(texts, generated))
        ]

    return [
        GeneratedQuestion(
            text=text,
            priority=PRIORITY_FALLBACK,
            display_order=index,
        )
        for index, text in enumerate(texts)
    ]
