"""Hop dong API cua phan hoi thoai.

Tach khoi `orchestrator_schemas.py` co chu y: `OrchestratorRequest` /
`OrchestratorResponse` la hop dong cua mot LUOT noi chuyen va dang bi cac golden
chat luong phan hoi khoa cung. Cac schema o day noi ve VIEC QUAN LY hoi thoai --
mo moi, liet ke, doc lai transcript -- va se con doi nhieu. Tron hai thu vao mot
file la moi lan them mot truong quan ly lai phai chung minh khong lam lech golden.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationSummarySchema(BaseModel):
    """Mot dong trong danh sach hoi thoai.

    Khong tra bat ky truong context nao (`current_analyte`, `pending_question`).
    Danh sach ben le man hinh chi can biet "hoi thoai nao, ve gi, luc nao"; do
    context ra day la cong bo trang thai noi bo cua orchestrator cho client, roi
    som muon co nguoi viet giao dien dua vao no.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    title: str | None = None
    onboarding_acknowledged: bool = False
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ConversationSummarySchema] = Field(default_factory=list)
    total: int


class ConversationMessageSchema(BaseModel):
    """Mot luot da xay ra.

    `content` la van ban DA qua guardrail. Doc lai lich su phai thay dung thu da
    hien tren man hinh, khong thay ban tien kiem duyet.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    role: str
    content: str
    created_at: datetime
    intent: str | None = None
    reason_code: str | None = None
    data_type: str | None = None


class ConversationDetailResponse(BaseModel):
    """Hoi thoai kem toan bo transcript.

    Tra ca hai trong MOT lan goi thay vi hai endpoint: man hinh tai lai luon can
    dong thoi ca tieu de va cac luot, va hai request tao ra mot khoang thoi gian
    ma giao dien co tieu de nhung chua co noi dung.
    """

    model_config = ConfigDict(extra="forbid")

    conversation: ConversationSummarySchema
    messages: list[ConversationMessageSchema] = Field(default_factory=list)


class ConversationCreateRequest(BaseModel):
    """New Chat.

    Khong co truong nao ngoai tieu de goi y, va khong co truong nao cho phep sao
    chep context tu hoi thoai cu. Hoi thoai moi RONG la ca dac diem chinh cua no.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)


__all__ = [
    "ConversationCreateRequest",
    "ConversationDetailResponse",
    "ConversationListResponse",
    "ConversationMessageSchema",
    "ConversationSummarySchema",
]
