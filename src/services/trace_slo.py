"""SLO và error budget — hàm thuần, không chạm DB.

## Vì sao cần SLO, khi đã có P95

P95 trả lời "chậm bao nhiêu". SLO trả lời **"thế nào mới được coi là ổn"** — và
đó là câu mà số liệu thô không tự trả lời được. Không có ngưỡng thì P95 = 6.6s
là một con số trung tính: người lạc quan đọc thành "LLM vốn chậm", người bi quan
đọc thành "hỏng rồi", và không ai sai.

## Error budget mới là phần đổi cách làm việc

SLO 99.5% nghĩa là **được phép** 0.5% request lỗi. Error budget biến con số đó
thành một lượng cụ thể: trong 1000 request thì được lỗi 5 lần. Dùng 2 lần là
còn 60% ngân sách — vẫn ổn. Dùng 5 lần là hết, và lúc đó việc cần làm không phải
là bàn xem 0.5% có hợp lý hay không, mà là dừng thả tính năng mới.

## Ngưỡng ở đây là ĐỀ XUẤT, không phải sự thật

CLAUDE.md ghi rõ: ngưỡng phải chọn từ số đo thật chứ không phải đoán, và đặt bừa
một con số rồi tô đỏ theo nó chỉ dạy người xem bỏ qua màu đỏ. Ba ngưỡng dưới đây
chọn từ số đo thật của production ngày 27/08 — P95 đường AI là 6.6s, error rate
0.25% — nên `LATENCY_SLO_MS = 8000` là "hơi rộng hơn hiện trạng", tức đạt được
nhưng vẫn bắt được một đợt xấu đi thật.

Nhóm phải chốt lại ba con số này. Chúng ở đây để bàn, không phải để tin.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.services.trace_metrics import GROUP_AI, classify_path

# --- ba SLO, chon tu so do that ngay 27/08 ---------------------------------

# 99.5% request AI khong gap loi server. Do duoc: 0.25% loi hien tai.
AVAILABILITY_TARGET_PCT = 99.5

# 95% request AI hoan thanh duoi 8 giay. Do duoc: P95 = 6.6s.
LATENCY_TARGET_PCT = 95.0
LATENCY_SLO_MS = 8000.0

# 98% luot tra loi KHONG phai thay bang van ban dung san.
#
# Day la SLO chat luong duy nhat do duoc o thoi diem nay. Khong phai
# groundedness — thu do can mot bo danh gia truc tuyen cham diem tung cau tra
# loi, ma he thong chua co. Guardrail phai thay van ban nghia la benh nhan nhan
# noi dung xuong cap trong khi response van 200, nen no la tin hieu chat luong
# that, chi hep hon.
QUALITY_TARGET_PCT = 98.0

STATUS_HEALTHY = "HEALTHY"
STATUS_AT_RISK = "AT_RISK"
STATUS_BREACHED = "BREACHED"
STATUS_NO_DATA = "NO_DATA"

# Dung tren 75% ngan sach thi chuyen AT_RISK. Chon 75% chu khong 90%: canh bao o
# 90% thi khi thay canh bao da gan het ngan sach, khong con cho de xu ly.
AT_RISK_BUDGET_PCT = 75.0


@dataclass
class SloResult:
    name: str
    target_pct: float
    actual_pct: float | None
    status: str
    sample_count: int
    # Bao nhieu phan tram ngan sach loi da dung. `None` khi chua co mau.
    budget_used_pct: float | None
    # So luot con duoc phep loi truoc khi vi pham SLO.
    budget_remaining: float | None
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "target_pct": self.target_pct,
            "actual_pct": self.actual_pct,
            "status": self.status,
            "sample_count": self.sample_count,
            "budget_used_pct": self.budget_used_pct,
            "budget_remaining": self.budget_remaining,
            "detail": self.detail,
        }


def _evaluate(
    *,
    name: str,
    good: int,
    total: int,
    target_pct: float,
    detail: str,
) -> SloResult:
    """Mot SLO tu so luot 'tot' tren tong so luot.

    `NO_DATA` khi chua co mau — KHONG phai `HEALTHY`. Mot he thong khong nhan
    request nao thi khong the goi la khoe manh; no co the da chet, va to xanh
    len do la cach chac nhat de khong ai phat hien.
    """

    if total <= 0:
        return SloResult(
            name=name,
            target_pct=target_pct,
            actual_pct=None,
            status=STATUS_NO_DATA,
            sample_count=0,
            budget_used_pct=None,
            budget_remaining=None,
            detail=detail,
        )

    actual_pct = good / total * 100
    # Ngan sach loi: so luot duoc phep khong-tot.
    budget_total = total * (100 - target_pct) / 100
    budget_spent = total - good

    if budget_total <= 0:
        # SLO 100%: mot luot khong tot la vi pham ngay.
        budget_used_pct = 100.0 if budget_spent else 0.0
        budget_remaining = max(0.0, -budget_spent)
    else:
        budget_used_pct = round(budget_spent / budget_total * 100, 1)
        budget_remaining = round(budget_total - budget_spent, 1)

    if actual_pct < target_pct:
        status = STATUS_BREACHED
    elif budget_used_pct >= AT_RISK_BUDGET_PCT:
        status = STATUS_AT_RISK
    else:
        status = STATUS_HEALTHY

    return SloResult(
        name=name,
        target_pct=target_pct,
        actual_pct=round(actual_pct, 2),
        status=status,
        sample_count=total,
        budget_used_pct=budget_used_pct,
        budget_remaining=budget_remaining,
        detail=detail,
    )


def evaluate_slos(rows: Iterable[object], *, group: str = GROUP_AI) -> dict[str, object]:
    """Ba SLO cho mot nhom endpoint, kem trang thai tong.

    Chi tinh tren nhom AI: SLO do tre 8 giay khong co nghia gi voi `/auth/login`,
    va tron hai nhom lai thi hon mot nghin request API thuong se lam moi SLO
    trong nhu dat de dang.
    """

    total = 0
    non_error = 0
    fast = 0
    llm_calls = 0
    guardrail_fallbacks = 0

    for row in rows:
        if (
            classify_path(
                str(getattr(row, "path", "") or ""),
                str(getattr(row, "method", "GET") or "GET"),
            )
            != group
        ):
            continue

        total += 1
        if int(getattr(row, "status_code", 0) or 0) < 500:
            non_error += 1
        if float(getattr(row, "duration_ms", 0.0) or 0.0) < LATENCY_SLO_MS:
            fast += 1
        llm_calls += int(getattr(row, "llm_call_count", 0) or 0)
        guardrail_fallbacks += int(getattr(row, "guardrail_fallback_count", 0) or 0)

    availability = _evaluate(
        name="availability",
        good=non_error,
        total=total,
        target_pct=AVAILABILITY_TARGET_PCT,
        detail="Request AI không gặp lỗi server",
    )
    latency = _evaluate(
        name="latency",
        good=fast,
        total=total,
        target_pct=LATENCY_TARGET_PCT,
        detail=f"Request AI hoàn thành dưới {int(LATENCY_SLO_MS / 1000)} giây",
    )
    # Mau cua SLO chat luong la SO LUOT GOI LLM, khong phai so request: mot
    # request `/analyze` nhieu chi so goi LLM nhieu lan, va guardrail xet tung
    # luot mot.
    quality_total = llm_calls + guardrail_fallbacks
    quality = _evaluate(
        name="quality",
        good=max(0, quality_total - guardrail_fallbacks),
        total=quality_total,
        target_pct=QUALITY_TARGET_PCT,
        detail="Lượt trả lời không phải thay bằng văn bản dựng sẵn",
    )

    results = [availability, latency, quality]

    # Trang thai tong lay theo cai TOI NHAT. Lay trung binh se lam mot SLO vi
    # pham bi hai SLO khoe che di — dung loai che lap ma con so trung binh 85ms
    # da gay ra.
    order = {
        STATUS_BREACHED: 0,
        STATUS_AT_RISK: 1,
        STATUS_NO_DATA: 2,
        STATUS_HEALTHY: 3,
    }
    overall = min((r.status for r in results), key=lambda s: order[s])

    return {
        "overall_status": overall,
        "slos": [r.as_dict() for r in results],
        # Ngung nay la DE XUAT, chon tu so do that ngay 27/08. Nhom phai chot lai.
        "thresholds_provisional": True,
    }


__all__ = [
    "AVAILABILITY_TARGET_PCT",
    "LATENCY_SLO_MS",
    "LATENCY_TARGET_PCT",
    "QUALITY_TARGET_PCT",
    "STATUS_AT_RISK",
    "STATUS_BREACHED",
    "STATUS_HEALTHY",
    "STATUS_NO_DATA",
    "SloResult",
    "evaluate_slos",
]
