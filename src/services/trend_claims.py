"""Lớp dữ kiện đã chốt ("claim") cho phần giải thích xu hướng — ADR-010 CRIT-TREND-01/02/04.

Vì sao có module này
--------------------
Kiến trúc cũ là "backend cấp dữ kiện thô → LLM tự phân loại + tự diễn đạt", còn
guardrail chỉ canh được lớp SỐ (``scan_fabricated_numbers``). Mọi lỗi *ngữ nghĩa*
lọt sạch, vì chúng không tạo ra con số mới. Ca thật trên WBC ``[20.0, 8.0, 6.0, 8.0]``
với khoảng tham chiếu ``4.72 - 11.3``:

1. Backend tính ``pct_direction = "tăng"`` (8.0 > 6.0) nhưng model viết
   "đã giảm 33.3%" — số 33.3 nằm trong whitelist nên guardrail báo pass.
2. Backend phân loại 6.0 là ``within_reference`` nhưng model viết "nằm dưới cận
   dưới" — không kèm số nào sai nên guardrail im lặng.
3. ``trend_service._observed_direction`` trả ``None`` cho chuỗi này (không đơn điệu),
   nhưng trường đó chưa bao giờ được đưa vào prompt; prompt lại bảo model TỰ suy
   ra "tăng dần / giảm dần / dao động". Model bịa ra "giảm dần".

Cách sửa: backend chốt sẵn từng nhận định thành một ``TrendClaim`` mang theo (a) câu
tiếng Việt hoàn chỉnh, (b) từ khoá BẮT BUỘC phải xuất hiện nếu model nói về nhận định
đó, (c) từ khoá NGƯỢC NGHĨA bị cấm. LLM chỉ còn nhiệm vụ viết lại cho mượt, và
``validate_claims`` đối chiếu ngược từng câu model viết với claim tương ứng.

Nguyên tắc chống chặn nhầm
--------------------------
File ``trend_explanation_service`` đã một lần hỏng production vì guardrail quá tay
(xem ``tests/test_services/test_trend_explanation_units.py``). Nên ở đây:

- Kiểm ở mức **câu**, và chỉ với câu có chứa *neo* của claim (giá trị/`%` của đúng
  điểm đó) — không quét cả đoạn.
- Chỉ báo lỗi khi **có từ ngược nghĩa VÀ vắng mặt từ bắt buộc**. Nhờ vậy một câu
  nói đúng về nhiều điểm cùng lúc ("ngày 13/08 giá trị 20.0 vượt cận trên 11.3,
  các lần sau nằm trong khoảng tham chiếu") không bị chặn oan.
- Neo số có chặn biên ``(?<![\\d.,]) ... (?![\\d.,])`` để "20 tháng 8" không bị coi
  là nhắc tới giá trị 20.0.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from src.models.schemas import TrendResponse

REFERENCE_NEAR_MARGIN_RATIO = 0.10

# Chuỗi được coi là "ổn định tương đối" khi biên độ nhỏ hơn ngần này lần độ rộng
# khoảng tham chiếu (hoặc giá trị đầu tiên, khi chưa khớp được khoảng tham chiếu).
STABLE_SPREAD_RATIO = 0.10

INSIDE_RELATIONS = frozenset({"within_reference", "near_lower_bound", "near_upper_bound"})


@dataclass(frozen=True)
class TrendPointReferenceFact:
    report_id: int
    test_date: str
    value: float
    lower: float | None
    upper: float | None
    relation: str


@dataclass(frozen=True)
class TrendClaim:
    """Một nhận định backend đã chốt, kèm cách kiểm lại câu của model.

    ``anchors`` rỗng nghĩa là kiểm trên toàn đoạn (dùng cho hình dạng chuỗi ở luồng
    đơn chỉ số, nơi cả đoạn nói về đúng một chỉ số). Có ``anchors`` thì chỉ những câu
    khớp neo mới bị soi.
    """

    kind: str
    required: tuple[str, ...]
    forbidden: tuple[str, ...]
    anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrendClaimSet:
    """``sentences`` để dựng prompt và fallback; ``claims`` để kiểm output."""

    sentences: tuple[str, ...]
    claims: tuple[TrendClaim, ...]


# --- tiện ích số ---------------------------------------------------------------


def decimal_variants(value: float | int) -> set[str]:
    raw = str(value)
    try:
        decimal_value = Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return {raw}
    normalized = format(decimal_value, "f")
    variants = {raw, raw.replace(".", ","), normalized, normalized.replace(".", ",")}
    if "." in normalized:
        variants.add(normalized.rstrip("0").rstrip("."))
        variants.add(normalized.rstrip("0").rstrip(".").replace(".", ","))
    return {item for item in variants if item}


def _alternation(variants: set[str]) -> str:
    # Dài trước ngắn: tránh "0" nuốt mất "0.0" khi khớp.
    ordered = sorted(variants, key=lambda item: (-len(item), item))
    return "|".join(re.escape(item) for item in ordered)


def _number_anchor(value: float) -> str | None:
    """Neo một giá trị xét nghiệm.

    Chỉ nhận các biến thể còn dấu thập phân ("8.0", "8,0") — bỏ dạng trần "8", vì
    "ngày 16 và 20 tháng 8" sẽ vô tình neo vào giá trị 8.0 và gây chặn oan.
    """
    variants = {item for item in decimal_variants(value) if "." in item or "," in item}
    if not variants:
        return None
    return rf"(?<![\d.,])(?:{_alternation(variants)})(?![\d.,])"


def _percent_anchor(value: float) -> str:
    """Neo con số phần trăm — hậu tố ``%`` đủ để phân biệt nên nhận cả dạng trần."""
    return rf"(?<![\d.,])(?:{_alternation(decimal_variants(value))})\s*(?:%|phần trăm|phan tram)"


def _text_anchor(text: str) -> str:
    return re.escape(text)


def _format_date(iso_date: str) -> str:
    try:
        year, month, day = iso_date.split("-")
    except ValueError:
        return iso_date
    return f"{day}/{month}/{year}"


# --- phân loại so với khoảng tham chiếu ---------------------------------------


def classify_reference_position(value: float, lower: float | None, upper: float | None) -> str:
    if lower is None and upper is None:
        return "unknown_reference"
    if lower is not None and value < lower:
        return "below_reference"
    if upper is not None and value > upper:
        return "above_reference"
    if lower is not None and upper is not None and upper > lower:
        margin = (upper - lower) * REFERENCE_NEAR_MARGIN_RATIO
        if value - lower <= margin:
            return "near_lower_bound"
        if upper - value <= margin:
            return "near_upper_bound"
    return "within_reference"


def reference_relation_text(fact: TrendPointReferenceFact, unit: str) -> str:
    if fact.relation == "unknown_reference":
        return "chưa khớp được khoảng tham chiếu cho điểm này"
    if fact.relation == "below_reference":
        return f"nằm dưới cận dưới {fact.lower} {unit}"
    if fact.relation == "above_reference":
        return f"vượt cận trên {fact.upper} {unit}"
    if fact.relation == "near_lower_bound":
        return f"nằm trong khoảng tham chiếu và gần cận dưới {fact.lower} {unit}"
    if fact.relation == "near_upper_bound":
        return f"nằm trong khoảng tham chiếu và gần cận trên {fact.upper} {unit}"
    if fact.lower is not None and fact.upper is not None:
        return f"nằm trong khoảng tham chiếu {fact.lower} - {fact.upper} {unit}"
    if fact.lower is not None:
        return f"nằm trên cận dưới {fact.lower} {unit}"
    if fact.upper is not None:
        return f"nằm dưới cận trên {fact.upper} {unit}"
    return "chưa khớp được khoảng tham chiếu cho điểm này"


def format_point_reference_facts(facts: list[TrendPointReferenceFact], unit: str) -> str:
    if not facts:
        return "Không có dữ kiện khoảng tham chiếu theo từng điểm."
    return "\n".join(
        f"- {fact.test_date}: giá trị {fact.value} {unit}, {reference_relation_text(fact, unit)}."
        for fact in facts
    )


def point_reference_extra_numbers(facts: list[TrendPointReferenceFact]) -> list[float | None]:
    numbers: list[float | None] = []
    for fact in facts:
        numbers.extend([fact.lower, fact.upper])
    return numbers


# ``(bắt buộc, cấm)`` cho từng nhãn vị trí. Từ "bắt buộc" là lối thoát: câu nào đã
# nói đúng nhãn thì các từ ngược nghĩa trong cùng câu là nói về điểm khác.
_RELATION_TERMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "within_reference": (
        ("trong khoảng tham chiếu", "trong ngưỡng tham chiếu", "trong giới hạn tham chiếu", "trong khoảng bình thường"),
        (
            "vượt cận trên",
            "vượt ngưỡng trên",
            "trên cận trên",
            "cao hơn cận trên",
            "dưới cận dưới",
            "dưới ngưỡng dưới",
            "thấp hơn cận dưới",
            "ngoài khoảng tham chiếu",
            "vượt khoảng tham chiếu",
        ),
    ),
    "near_lower_bound": (
        ("trong khoảng tham chiếu", "trong ngưỡng tham chiếu", "gần cận dưới", "gần ngưỡng dưới"),
        (
            "vượt cận trên",
            "vượt ngưỡng trên",
            "dưới cận dưới",
            "dưới ngưỡng dưới",
            "thấp hơn cận dưới",
            "ngoài khoảng tham chiếu",
        ),
    ),
    "near_upper_bound": (
        ("trong khoảng tham chiếu", "trong ngưỡng tham chiếu", "gần cận trên", "gần ngưỡng trên"),
        (
            "vượt cận trên",
            "vượt ngưỡng trên",
            "cao hơn cận trên",
            "dưới cận dưới",
            "dưới ngưỡng dưới",
            "ngoài khoảng tham chiếu",
        ),
    ),
    "above_reference": (
        # "cao nhất"/"mức cao" là lối thoát hợp lệ: gọi một điểm vượt cận trên là
        # "mức cao nhất" không bao giờ sai, mà đó lại là cách diễn đạt tự nhiên nhất
        # khi câu đó đồng thời nói các điểm sau đã về trong khoảng tham chiếu.
        (
            "vượt cận trên",
            "vượt ngưỡng trên",
            "cao hơn cận trên",
            "trên cận trên",
            "vượt khoảng tham chiếu",
            "ngoài khoảng tham chiếu",
            "cao nhất",
            "mức cao",
        ),
        (
            "trong khoảng tham chiếu",
            "trong ngưỡng tham chiếu",
            "dưới cận dưới",
            "dưới ngưỡng dưới",
            "thấp hơn cận dưới",
        ),
    ),
    "below_reference": (
        ("dưới cận dưới", "dưới ngưỡng dưới", "thấp hơn cận dưới", "ngoài khoảng tham chiếu", "thấp nhất", "mức thấp"),
        (
            "trong khoảng tham chiếu",
            "trong ngưỡng tham chiếu",
            "vượt cận trên",
            "vượt ngưỡng trên",
            "cao hơn cận trên",
        ),
    ),
    # Chưa khớp được khoảng tham chiếu: prompt đã cấm nói vị trí, nhưng trước đây
    # không có gì cưỡng chế. Giờ mọi phát biểu vị trí quanh điểm đó đều bị chặn.
    "unknown_reference": (
        (),
        (
            "khoảng tham chiếu",
            "ngưỡng tham chiếu",
            "cận trên",
            "cận dưới",
            "ngưỡng trên",
            "ngưỡng dưới",
        ),
    ),
}


# --- hình dạng chuỗi -----------------------------------------------------------

_MONOTONIC_FORBIDDEN = (
    "tăng dần",
    "giảm dần",
    "tăng liên tục",
    "giảm liên tục",
    "liên tục tăng",
    "liên tục giảm",
)

_SHAPE_FORBIDDEN: dict[str, tuple[str, ...]] = {
    "increasing": ("giảm dần", "giảm liên tục", "liên tục giảm", "xu hướng giảm"),
    "decreasing": ("tăng dần", "tăng liên tục", "liên tục tăng", "xu hướng tăng"),
    "stable": _MONOTONIC_FORBIDDEN,
    "fluctuating": _MONOTONIC_FORBIDDEN,
    "fell_from_high": _MONOTONIC_FORBIDDEN,
}

# Chỉ dùng ở chế độ nhóm — xem ``build_claim_set``.
_SHAPE_REQUIRED: dict[str, tuple[str, ...]] = {
    "increasing": ("tăng dần", "tăng liên tục", "liên tục tăng", "xu hướng tăng", "đi lên"),
    "decreasing": ("giảm dần", "giảm liên tục", "liên tục giảm", "xu hướng giảm", "đi xuống"),
    "stable": ("ổn định", "không đổi", "không thay đổi", "ít thay đổi"),
    "fluctuating": ("dao động", "lên xuống", "biến động"),
    "fell_from_high": ("dao động", "lên xuống", "biến động", "giảm mạnh", "mức cao nhất"),
}


def series_shape(trend: TrendResponse, facts: list[TrendPointReferenceFact]) -> str:
    """Nhãn hình dạng chuỗi, do backend quyết định — không để model tự suy.

    Tái dùng ``trend.observed_direction`` (đơn điệu nghiêm ngặt toàn chuỗi, tính ở
    ``trend_service``) làm nguồn sự thật cho hai nhãn đơn điệu, rồi phân biệt tiếp
    *ổn định* với *dao động* cho phần còn lại.
    """
    values = [point.value for point in trend.points]
    if not values:
        return "fluctuating"
    if trend.observed_direction == "increasing":
        return "increasing"
    if trend.observed_direction == "decreasing":
        return "decreasing"

    spread = max(values) - min(values)
    lower = facts[-1].lower if facts else None
    upper = facts[-1].upper if facts else None
    if lower is not None and upper is not None and upper > lower:
        scale: float | None = upper - lower
    else:
        scale = abs(values[0]) or None
    if scale and spread <= STABLE_SPREAD_RATIO * scale:
        return "stable"

    # Ca thường gặp nhất khi theo dõi hồi phục: một đỉnh ngoài khoảng tham chiếu ở
    # lần đo đầu rồi các lần sau đều về trong khoảng. Gọi nguyên chuỗi là "dao động"
    # thì đúng nhưng bỏ mất thông tin quan trọng nhất.
    if (
        len(facts) == len(values)
        and len(values) >= 2
        and values[0] == max(values)
        and facts[0].relation == "above_reference"
        and all(fact.relation in INSIDE_RELATIONS for fact in facts[1:])
    ):
        return "fell_from_high"
    return "fluctuating"


def _shape_sentence(shape: str, trend: TrendResponse, facts: list[TrendPointReferenceFact]) -> str:
    count = len(trend.points)
    if shape == "increasing":
        return f"Các giá trị tăng dần qua {count} lần đo."
    if shape == "decreasing":
        return f"Các giá trị giảm dần qua {count} lần đo."
    if shape == "stable":
        return f"Các giá trị ổn định tương đối qua {count} lần đo."
    if shape == "fell_from_high":
        peak = max(point.value for point in trend.points)
        return (
            f"Các giá trị giảm mạnh từ mức cao nhất {peak} {trend.canonical_unit} ở lần đo đầu, "
            "sau đó dao động trong khoảng tham chiếu."
        )
    return f"Các giá trị dao động lên xuống qua {count} lần đo."


# --- % biến động ---------------------------------------------------------------


def percent_change(trend: TrendResponse) -> tuple[float | None, str | None]:
    """ADR-010 CRIT-TREND-04: % biến động giữa 2 lần đo gần nhất, tính ở backend.

    Trả về (độ lớn tuyệt đối đã làm tròn 1 chữ số thập phân, hướng "tăng"/"giảm").
    Model chỉ lặp lại số này, không tự tính — nếu để model tự tính, guardrail không
    còn cách nào phân biệt số thật với số bịa.
    """
    if len(trend.points) < 2:
        return None, None
    latest, previous = trend.points[-1].value, trend.points[-2].value
    if previous == 0:
        return None, None
    change = round(abs((latest - previous) / previous * 100), 1)
    direction = "tăng" if latest > previous else "giảm" if latest < previous else "không đổi"
    if direction == "không đổi":
        return 0.0, direction
    return change, direction


# --- dựng claim ----------------------------------------------------------------


def _reference_claims(facts: list[TrendPointReferenceFact]) -> list[TrendClaim]:
    """Một claim cho mỗi giá trị phân biệt.

    Nếu cùng một giá trị lại mang hai nhãn khác nhau (khoảng tham chiếu đổi giữa các
    lần đo vì tuổi bệnh nhân đổi), không thể quy câu của model về đúng điểm nào —
    bỏ qua thay vì đoán mò.
    """
    by_value: dict[float, set[str]] = defaultdict(set)
    for fact in facts:
        by_value[fact.value].add(fact.relation)

    claims: list[TrendClaim] = []
    for value, relations in by_value.items():
        if len(relations) != 1:
            continue
        relation = next(iter(relations))
        terms = _RELATION_TERMS.get(relation)
        anchor = _number_anchor(value)
        if terms is None or anchor is None:
            continue
        required, forbidden = terms
        claims.append(
            TrendClaim(
                kind=f"vị trí so với khoảng tham chiếu ({relation})",
                required=required,
                forbidden=forbidden,
                anchors=(anchor,),
            )
        )
    return claims


def build_claim_set(
    trend: TrendResponse,
    facts: list[TrendPointReferenceFact],
    *,
    shape_anchor: str | None = None,
) -> TrendClaimSet:
    """Chốt toàn bộ nhận định của một chỉ số.

    ``shape_anchor`` dùng cho luồng nhóm chức năng: ở đó "A tăng dần trong khi B dao
    động" là câu hợp lệ, nên nhãn hình dạng phải neo theo tên chỉ số thay vì soi
    toàn đoạn như luồng đơn chỉ số.
    """
    unit = trend.canonical_unit
    sentences: list[str] = []
    claims: list[TrendClaim] = []

    if facts:
        latest = facts[-1]
        sentences.append(f"Giá trị gần nhất {latest.value} {unit} {reference_relation_text(latest, unit)}.")

    pct, direction = percent_change(trend)
    if pct is not None and direction is not None:
        previous = trend.points[-2].value
        latest_value = trend.points[-1].value
        if direction == "không đổi":
            sentences.append(
                f"So với lần đo ngay trước ({previous} {unit}), giá trị gần nhất "
                f"{latest_value} {unit} không thay đổi ({pct}%)."
            )
            required = ("không thay đổi", "không đổi", "không có biến động", "giữ nguyên", "ổn định")
            forbidden = ("tăng", "giảm")
        else:
            sentences.append(
                f"So với lần đo ngay trước ({previous} {unit}), giá trị gần nhất "
                f"{latest_value} {unit} đã {direction} {pct}%."
            )
            required = (direction,)
            forbidden = ("giảm",) if direction == "tăng" else ("tăng",)
        claims.append(
            TrendClaim(
                kind="mức biến động giữa hai lần đo gần nhất",
                required=required,
                forbidden=forbidden,
                anchors=(_percent_anchor(pct),),
            )
        )

    shape = series_shape(trend, facts)
    sentences.append(_shape_sentence(shape, trend, facts))
    # Luồng đơn chỉ số: cả đoạn nói về đúng một chỉ số, nên kiểm theo kiểu **chỉ cấm**
    # trên toàn đoạn — backend đã xác định chuỗi không đơn điệu thì "giảm dần" là sai,
    # không hoàn cảnh nào cứu được (đây là lỗi thứ ba trong ca WBC).
    # Luồng nhóm: một câu thường nhắc hai chỉ số ("LDL-C tăng dần trong khi HDL-C dao
    # động"), nên phải có lối thoát bằng từ bắt buộc, y như các claim vị trí.
    claims.append(
        TrendClaim(
            kind=f"hướng đi tổng thể của chuỗi ({shape})",
            required=_SHAPE_REQUIRED[shape] if shape_anchor else (),
            forbidden=_SHAPE_FORBIDDEN[shape],
            anchors=(_text_anchor(shape_anchor),) if shape_anchor else (),
        )
    )

    notable = [fact for fact in facts[:-1] if fact.relation not in {"within_reference", "unknown_reference"}]
    for fact in notable:
        sentences.append(
            f"Ngày {_format_date(fact.test_date)}: giá trị {fact.value} {unit} "
            f"{reference_relation_text(fact, unit)}."
        )

    claims.extend(_reference_claims(facts))
    return TrendClaimSet(sentences=tuple(sentences), claims=tuple(claims))


# --- kiểm output của model -----------------------------------------------------

# Chỉ tách câu ở dấu chấm KHÔNG nằm giữa hai chữ số, nếu không "8.0" bị cắt đôi và
# mọi neo số đều hỏng.
_SENTENCE_SPLIT_RE = re.compile(r"(?<!\d)\.(?!\d)|[;!?\n]+")


def split_sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]


def validate_claims(text: str, claims: list[TrendClaim] | tuple[TrendClaim, ...]) -> list[tuple[str, str]]:
    """Trả về ``(lý do, bằng chứng)`` cho mỗi claim bị model nói ngược.

    Danh sách claim rỗng → không kiểm gì; nhờ vậy các đường gọi cũ (và test cũ) giữ
    nguyên hành vi, việc kiểm ngữ nghĩa là opt-in do bên gọi truyền claim vào.
    """
    if not claims:
        return []

    lowered_text = text.casefold()
    sentences = [sentence.casefold() for sentence in split_sentences(text)]
    violations: list[tuple[str, str]] = []

    for claim in claims:
        if not claim.anchors:
            if any(term in lowered_text for term in claim.required):
                continue
            hit = next((term for term in claim.forbidden if term in lowered_text), None)
            if hit:
                violations.append((f"Mâu thuẫn dữ kiện backend: {claim.kind}", hit))
            continue

        anchor_re = re.compile("|".join(claim.anchors), re.IGNORECASE)
        for sentence in sentences:
            if not anchor_re.search(sentence):
                continue
            if any(term in sentence for term in claim.required):
                continue
            hit = next((term for term in claim.forbidden if term in sentence), None)
            if hit:
                violations.append((f"Mâu thuẫn dữ kiện backend: {claim.kind}", hit))
                break

    return violations


def merge_claims(claim_groups: list[tuple[TrendClaim, ...]]) -> list[TrendClaim]:
    """Gộp claim của nhiều chỉ số, bỏ những neo bị hai chỉ số tranh nhau.

    Ở chế độ nhóm, hai chỉ số có thể trùng giá trị (cùng 5.0) hoặc trùng % biến động
    mà nhãn lại khác nhau. Khi đó không thể quy một câu của model về đúng chỉ số nào,
    nên bỏ claim thay vì chặn oan. Neo theo tên chỉ số (nhãn hình dạng chuỗi) không
    bao giờ tranh nhau nên luôn giữ.
    """
    flat = [claim for group in claim_groups for claim in group]
    by_anchor: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for claim in flat:
        if claim.anchors:
            by_anchor[claim.anchors].add(claim.kind)

    merged: list[TrendClaim] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for claim in flat:
        if claim.anchors and len(by_anchor[claim.anchors]) > 1:
            continue
        key = (claim.kind, claim.anchors)
        if key in seen:
            continue
        seen.add(key)
        merged.append(claim)
    return merged


def format_claims_for_prompt(sentences: tuple[str, ...] | list[str]) -> str:
    return "\n".join(f"{index}. {sentence}" for index, sentence in enumerate(sentences, start=1))


def compose_deterministic_explanation(sentences: tuple[str, ...] | list[str]) -> str:
    """Đoạn giải thích ghép thẳng từ câu backend đã soạn.

    Dùng khi LLM lỗi hoặc bị guardrail chặn: vẫn đúng tuyệt đối vì không có chữ nào
    do model sinh ra, và giàu thông tin hơn hẳn câu "hiện không khả dụng" trước đây.
    """
    return " ".join(sentence.strip() for sentence in sentences if sentence.strip())
