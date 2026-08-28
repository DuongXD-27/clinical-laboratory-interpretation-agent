from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    ConversationState,
    IntentEnum,
    OrchestratorRole,
    OrchestratorSessionContext,
    ResponseStyle,
    UIContext,
)
from src.services.auth import ROLE_GUEST

logger = logging.getLogger(__name__)


class SessionStore(Protocol):
    def get_or_create(self, current_user: object) -> OrchestratorSessionContext: ...

    def save(self, current_user: object, context: OrchestratorSessionContext) -> None: ...

    def acknowledge_onboarding(self, current_user: object) -> OrchestratorSessionContext: ...

    def activate_report(self, current_user: object, report_ref: str) -> OrchestratorSessionContext: ...


@dataclass
class _SessionRecord:
    context: OrchestratorSessionContext


class InMemorySessionStore:
    def __init__(self) -> None:
        self._records: dict[str, _SessionRecord] = {}
        self._patient_sessions: dict[int, str] = {}

    def _key_and_context_id(self, current_user: object) -> tuple[str, str, OrchestratorRole]:
        role = getattr(current_user, "role", "")
        if role == ROLE_GUEST:
            session_id = getattr(current_user, "session_id", None)
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("guest session_id is required")
            return f"guest:{session_id}", session_id, OrchestratorRole.GUEST

        if role == ROLE_PATIENT:
            account_key = getattr(current_user, "user_id", None)
            if account_key is None and isinstance(getattr(current_user, "id", None), int):
                account_key = current_user.id
            if not isinstance(account_key, int):
                raise ValueError("patient user_id is required")
            session_id = self._patient_sessions.setdefault(account_key, secrets.token_urlsafe(16))
            return f"patient:{account_key}", session_id, OrchestratorRole.PATIENT

        raise ValueError("role is not admitted")

    def get_or_create(self, current_user: object) -> OrchestratorSessionContext:
        key, session_id, role = self._key_and_context_id(current_user)
        record = self._records.get(key)
        if record is not None:
            return record.context

        user_style = getattr(current_user, "response_style", None) or ResponseStyle.SIMPLE
        context = OrchestratorSessionContext.from_server(
            session_id=session_id,
            user_role=role,
            response_style=user_style,
        )
        self._records[key] = _SessionRecord(context=context)
        return context

    def save(self, current_user: object, context: OrchestratorSessionContext) -> None:
        key, _, _ = self._key_and_context_id(current_user)
        self._records[key] = _SessionRecord(context=context)

    def acknowledge_onboarding(self, current_user: object) -> OrchestratorSessionContext:
        context = self.get_or_create(current_user)
        updated = OrchestratorSessionContext.from_server(
            session_id=context.session_id,
            user_role=context.user_role,
            onboarding_acknowledged=True,
            current_report_ref=context.current_report_ref,
            current_analyte=context.current_analyte,
            last_intent=context.last_intent,
            pending_ocr_review=context.pending_ocr_review,
            transient_ui_context=context.transient_ui_context,
            conversation_state=context.conversation_state,
            response_style=getattr(current_user, "response_style", None) or context.response_style,
        )
        self.save(current_user, updated)
        return updated

    def activate_report(self, current_user: object, report_ref: str) -> OrchestratorSessionContext:
        """Activate a server-persisted report and discard analyte context from the prior report."""
        context = self.get_or_create(current_user)
        updated = OrchestratorSessionContext.from_server(
            session_id=context.session_id,
            user_role=context.user_role,
            onboarding_acknowledged=context.onboarding_acknowledged,
            current_report_ref=report_ref,
            current_analyte=None,
            last_intent=context.last_intent,
            pending_ocr_review=context.pending_ocr_review,
            transient_ui_context=context.transient_ui_context,
            conversation_state=context.conversation_state,
            response_style=getattr(current_user, "response_style", None) or context.response_style,
        )
        self.save(current_user, updated)
        return updated

    def replace_pending_review(
        self,
        current_user: object,
        context: OrchestratorSessionContext,
        *,
        pending_ocr_review: bool,
    ) -> OrchestratorSessionContext:
        updated = OrchestratorSessionContext.from_server(
            session_id=context.session_id,
            user_role=context.user_role,
            onboarding_acknowledged=context.onboarding_acknowledged,
            current_report_ref=context.current_report_ref,
            current_analyte=context.current_analyte,
            last_intent=context.last_intent,
            pending_ocr_review=pending_ocr_review,
            transient_ui_context=context.transient_ui_context,
            conversation_state=context.conversation_state,
            response_style=getattr(current_user, "response_style", None) or context.response_style,
        )
        self.save(current_user, updated)
        return updated

    def update_after_turn(
        self,
        current_user: object,
        context: OrchestratorSessionContext,
        *,
        last_intent: IntentEnum | None,
        current_report_ref: str | None = None,
        current_analyte: str | None = None,
        transient_ui_context: UIContext | None = None,
        conversation_state: ConversationState | None = None,
        clear_analyte: bool = False,
    ) -> OrchestratorSessionContext:
        report_changed = current_report_ref is not None and current_report_ref != context.current_report_ref
        should_clear_analyte = clear_analyte or (report_changed and current_analyte is None)
        resolved_analyte = (
            None
            if should_clear_analyte
            else (current_analyte if current_analyte is not None else context.current_analyte)
        )
        # Onboarding chỉ tiến về phía trước qua acknowledge_onboarding, nên nó
        # được đọc từ bản ghi MỚI NHẤT trong store chứ không phải từ `context`
        # tham số: một caller giữ tham chiếu context cũ hơn (lấy ra trước khi
        # acknowledge) từng vô tình ghi đè flag đã lưu thành False, khiến lượt
        # kế tiếp bị chặn ONBOARDING_REQUIRED dù người dùng đã xác nhận.
        try:
            stored_key, _, _ = self._key_and_context_id(current_user)
            stored_record = self._records.get(stored_key)
        except ValueError:
            stored_record = None
        stored_context = stored_record.context if stored_record is not None else context
        updated = OrchestratorSessionContext.from_server(
            session_id=context.session_id,
            user_role=context.user_role,
            onboarding_acknowledged=stored_context.onboarding_acknowledged or context.onboarding_acknowledged,
            current_report_ref=current_report_ref or context.current_report_ref,
            current_analyte=resolved_analyte,
            last_intent=last_intent,
            pending_ocr_review=context.pending_ocr_review,
            transient_ui_context=transient_ui_context or context.transient_ui_context,
            conversation_state=conversation_state or context.conversation_state,
            response_style=getattr(current_user, "response_style", None) or context.response_style,
        )
        self.save(current_user, updated)
        return updated


# ---------------------------------------------------------------------------
# Store gan theo tung hoi thoai, co luu xuong DB
# ---------------------------------------------------------------------------
#
# Vi sao KE THUA `InMemorySessionStore` thay vi viet store moi: toan bo logic
# chuyen trang thai (`update_after_turn`, `activate_report`,
# `replace_pending_review`) rat tinh vi -- no quyet dinh khi nao xoa
# `current_analyte`, khi nao giu -- va dang duoc ca bo test orchestrator bao ve.
# Viet lai la viet lai ca nhung quyet dinh do. O day chi thay hai thu: KHOA tra
# context, va viec luu xuong DB. Moi method dan xuat goi `self.get_or_create()`
# va `self.save()` nen tu dong thanh gan-theo-hoi-thoai ma khong sua dong nao.

_BINDING: ContextVar[tuple[object, object] | None] = ContextVar(
    "conversation_binding",
    default=None,
)


@contextmanager
def bind_conversation(db: object, conversation: object) -> Iterator[None]:
    """Gan (session DB, hoi thoai) cho suot mot luot xu ly.

    Dung contextvar chu khong them tham so vao muoi method cua store: lam vay
    phai sua moi cho goi trong `service.py`, ma do la vung code cua nguoi khac.
    Repo nay da co tien le dung khuon -- `request_timing` cung gan theo request
    bang contextvar.

    Khach khong bao gio duoc gan, nen voi khach store roi ve dung hanh vi
    in-memory cu. Hop dong "khach khong luu gi" giu nguyen ma khong can nhanh re.
    """

    token = _BINDING.set((db, conversation))
    try:
        yield
    finally:
        _BINDING.reset(token)


def current_binding() -> tuple[object, object] | None:
    return _BINDING.get()


class ConversationScopedSessionStore(InMemorySessionStore):
    """Context song theo tung hoi thoai, va song qua lan tai lai trang.

    Khac biet duy nhat so voi lop cha:

    - Khoa la `conv:{conversation_id}` thay vi `patient:{user_id}`. Day chinh la
      thu lam CP-05 dat: hai hoi thoai la hai khoa, nen `current_analyte` cua
      hoi thoai 1 khong the chay sang hoi thoai 2.
    - Lan cham dau tien nap context tu hang DB, nen tai lai trang khong mat
      ngu canh (CP-04).
    - Moi `save()` ghi thang xuong dung hang do.
    """

    def _key_and_context_id(self, current_user: object) -> tuple[str, str, OrchestratorRole]:
        binding = current_binding()
        if binding is not None and getattr(current_user, "role", "") == ROLE_PATIENT:
            _, conversation = binding
            conversation_id = getattr(conversation, "id", None)
            if isinstance(conversation_id, int):
                return f"conv:{conversation_id}", str(conversation_id), OrchestratorRole.PATIENT

        # Kiem lai `role` o day chu khong tin vao `resolve_conversation` da chan
        # dung: role tra ve tu day quyet dinh `user_role` trong context, va gan
        # PATIENT cho mot phien khach la noi doi voi moi lop phia sau. Mot bien
        # co dung o hai noi thi phai dung o ca hai, khong phai o mot.
        return super()._key_and_context_id(current_user)

    def get_or_create(self, current_user: object) -> OrchestratorSessionContext:
        binding = current_binding()
        if binding is None:
            return super().get_or_create(current_user)

        key, session_id, role = self._key_and_context_id(current_user)
        _, conversation = binding

        # Doc lai tu hang DB o MOI luot, khong phai chi khi cache truot.
        #
        # De cache RAM lam nguon su that thi "tai lai trang" chang chung minh
        # duoc gi: context van con vi no nam trong tien trinh, chu khong vi no
        # da duoc luu. Va o production co nhieu worker thi luot sau roi vao
        # worker khac la mat ngu canh -- dung loai loi ma checkpointer
        # in-memory cua graph dang mac. Hang DB lam chu thi ca hai het.
        record = self._records.get(key)
        context = self._hydrate(
            conversation,
            session_id=session_id,
            role=role,
            carry=record.context if record is not None else None,
        )
        self._records[key] = _SessionRecord(context=context)
        return context

    @staticmethod
    def _hydrate(
        conversation: object,
        *,
        session_id: str,
        role: OrchestratorRole,
        carry: OrchestratorSessionContext | None = None,
    ) -> OrchestratorSessionContext:
        """Dung lai context tu hang DB, giu lai phan chi ton tai trong tien trinh.

        `pending_ocr_review` va `transient_ui_context` KHONG co cot trong DB, va
        khong nen co: mot ban nhap OCR dang cho duyet song trong checkpointer
        in-memory cua graph, nen luu con tro tro den no xuong DB la tao ra mot
        con tro treo sau khi restart. Chung di theo `carry` -- van la trong
        tien trinh, dung nhu truoc day.
        """

        state = ConversationState(
            pending_question=getattr(conversation, "pending_question", None),
            pending_question_timestamp=getattr(conversation, "pending_question_at", None),
            expected_entity=getattr(conversation, "expected_entity", None),
        )

        raw_intent = getattr(conversation, "last_intent", None)
        try:
            last_intent = IntentEnum(raw_intent) if raw_intent else None
        except ValueError:
            # Intent luu tu ban cu ma enum da bo gia tri do: bo qua thay vi no.
            # Mat mot chut ngu canh con hon hoi thoai khong mo duoc nua.
            last_intent = None

        return OrchestratorSessionContext.from_server(
            session_id=session_id,
            user_role=role,
            onboarding_acknowledged=bool(getattr(conversation, "onboarding_acknowledged", False)),
            current_report_ref=getattr(conversation, "current_report_ref", None),
            current_analyte=getattr(conversation, "current_analyte", None),
            last_intent=last_intent,
            pending_ocr_review=bool(carry.pending_ocr_review) if carry is not None else False,
            transient_ui_context=carry.transient_ui_context if carry is not None else None,
            conversation_state=state,
        )

    def reset(self) -> None:
        """Xoa cache trong tien trinh. Danh cho test, khong cho duong chay that.

        Cac test dung DB tam moi cho tung test, nen id hoi thoai lai bat dau tu
        1. Khong xoa thi khoa `conv:1` cua test truoc con nguyen va test sau
        thua huong `transient_ui_context` cua no -- do la loai lien luy giua cac
        test rat kho truy.
        """

        self._records.clear()
        self._patient_sessions.clear()

    def save(self, current_user: object, context: OrchestratorSessionContext) -> None:
        super().save(current_user, context)

        binding = current_binding()
        if binding is None:
            return

        db, conversation = binding
        try:
            from src.services import conversation_repository

            conversation_repository.save_context(db, conversation=conversation, context=context)
        except Exception:
            # Nuot co chu y, va nuot o BIEN chu khong chi trong repository: ghi
            # context that bai thi nguoi dung mat ngu canh o luot sau, con de
            # exception bay len la mat ca cau tra loi dang co. Context trong RAM
            # da duoc luu o dong dau nen luot nay van dung.
            logger.warning("conversation_context_save_failed", exc_info=True)


default_session_store = ConversationScopedSessionStore()
