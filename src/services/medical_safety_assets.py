"""Shared medical-safety assets for generation and guardrail nodes.

Centralizes the safety contract, status qualifiers and the reference-qualification
helper so the analyzer, guardrail and future callers use one authoritative set
of safety wording instead of duplicating it per node.
"""

from __future__ import annotations

import unicodedata

GENERATION_SAFETY_CONTRACT = """\
Hợp đồng an toàn bắt buộc:
- NORMAL chỉ có nghĩa là giá trị nằm trong khoảng tham chiếu được hệ thống sử dụng. Không được suy ra cơ thể/sức khỏe/chức năng cơ quan bình thường, miễn dịch ổn định, không có bệnh, viêm, nhiễm trùng hoặc vấn đề y khoa.
- Khi trạng thái là NORMAL: TUYỆT ĐỐI KHÔNG suy diễn rằng "bình thường thì không gây triệu chứng/không ảnh hưởng gì", và KHÔNG liệt kê rủi ro khi tăng/giảm nếu context không nói rõ về trạng thái bình thường. Nếu context chỉ mô tả khi tăng cao/giảm thấp mà không có nội dung trực tiếp về mức bình thường, lời giải thích CHỈ ĐƯỢC nêu giá trị, đơn vị và xác nhận giá trị nằm trong khoảng tham chiếu được hệ thống sử dụng; bỏ toàn bộ phần tăng/giảm.
- LOW/HIGH chỉ có nghĩa là giá trị thấp/cao so với khoảng tham chiếu được hệ thống sử dụng; đây không phải chẩn đoán.
- CRITICAL_LOW/CRITICAL_HIGH chỉ có nghĩa là giá trị vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình; cảnh báo xác định của hệ thống là có thẩm quyền và đây không phải chẩn đoán.
- Không gọi giá trị là "mức tối ưu" và không khẳng định tim, gan, thận, miễn dịch hay chức năng khác hoạt động bình thường từ một kết quả xét nghiệm đơn lẻ.
- Ngoài giá trị, đơn vị, trạng thái xác định, khoảng tham chiếu và cảnh báo xác định: mọi triệu chứng, ảnh hưởng, liên hệ hoặc nội dung y khoa phải được nêu trực tiếp trong context cho đúng trạng thái đó. Context không nêu thì phải bỏ, không dùng kiến thức sẵn có của mô hình để bổ sung hay suy diễn ngược từ trạng thái khác.
- Giữ nguyên ngôn ngữ điều kiện của context như "có thể" hoặc "có thể gặp"; không đổi thành khẳng định về bệnh nhân như "bệnh nhân đang", "điều này cho thấy" hoặc "điều này chứng minh".
- Khi context không đủ hoặc không trực tiếp hỗ trợ cho trạng thái hiện tại, ưu tiên lời giải thích tối giản (chỉ nêu giá trị, đơn vị và xác nhận giá trị nằm trong khoảng tham chiếu) thay vì suy diễn.
"""

STATUS_QUALIFIERS = {
    "normal": "Giá trị này nằm trong khoảng tham chiếu được hệ thống sử dụng.",
    "low": "Giá trị này thấp so với khoảng tham chiếu được hệ thống sử dụng.",
    "high": "Giá trị này cao so với khoảng tham chiếu được hệ thống sử dụng.",
    "critical_low": "Giá trị này vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình.",
    "critical_high": "Giá trị này vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình.",
    "desirable": "Giá trị này thuộc mức 'mong muốn' theo hệ thống phân loại đang được áp dụng.",
    "borderline_high": "Giá trị này thuộc mức 'ranh giới cao' theo hệ thống phân loại đang được áp dụng.",
    "very_high": "Giá trị này thuộc mức 'rất cao' theo hệ thống phân loại đang được áp dụng.",
    "optimal": "Giá trị này thuộc mức 'tối ưu' theo hệ thống phân loại đang được áp dụng.",
    "near_optimal": "Giá trị này thuộc mức 'gần tối ưu' theo hệ thống phân loại đang được áp dụng.",
    "intermediate": "Giá trị này thuộc mức 'trung gian' theo hệ thống phân loại đang được áp dụng.",
    "impaired_fasting_glucose": "Giá trị này nằm trong khoảng phân loại rối loạn đường huyết lúc đói theo ngưỡng đang được áp dụng.",
    "prediabetes": "Giá trị này nằm trong khoảng xét nghiệm được phân loại là tiền đái tháo đường theo ngưỡng đang được áp dụng.",
    "provisional_diabetes": "Giá trị này đạt ngưỡng xét nghiệm được sử dụng trong tiêu chuẩn chẩn đoán đái tháo đường; một kết quả đơn lẻ không tự xác lập chẩn đoán trong đa số trường hợp.",
    "unknown": "Hệ thống chưa đủ cơ sở để phân loại giá trị này.",
}


def _normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def ensure_reference_qualification(
    explanation: str,
    status: str,
    critical_status: str | None = None,
    is_critical: bool = False,
) -> str:
    """Guarantee a generic status boundary without replacing generated content."""
    effective_status = critical_status if (is_critical and critical_status) else status
    qualifier = STATUS_QUALIFIERS.get(effective_status)
    if not qualifier:
        return explanation

    normalized = _normalized_text(explanation)
    is_qualified = (
        "khoang tham chieu" in normalized
        if effective_status in {"normal", "low", "high"}
        else "nguong canh bao nguy kich" in normalized
    )
    return explanation if is_qualified else f"{qualifier} {explanation}".strip()
