"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ConversationNotFoundError,
  createConversation,
  getConversation,
  listConversations,
  streamOrchestratorMessage,
  UnauthorizedError,
  type ConversationSummary,
} from "@/lib/api";
import {
  messagesToTurns,
  pickInitialConversation,
} from "@/lib/conversationTranscript.mjs";
import { isCurrentRequest } from "@/lib/orchestratorChat.mjs";
import type {
  OrchestratorProgressStage,
  OrchestratorResponse,
  OrchestratorUiContext,
} from "@/types/orchestrator";

export type ChatDeliveryState =
  | "IDLE"
  | "CONNECTING"
  | "RECEIVING_PROGRESS"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type ChatTurn = {
  id: string;
  requestId: string;
  userMessage: string;
  response?: OrchestratorResponse;
  progressStage?: OrchestratorProgressStage;
  deliveryState: ChatDeliveryState;
  createdAt: string;
  error?: string;
  retryable: boolean;
  /** Lượt được dựng lại từ transcript đã lưu, không phải lượt vừa chạy.
   *
   * Lượt dựng lại chỉ có văn bản: server lưu nội dung đã qua guardrail chứ
   * không lưu nguyên payload có cấu trúc. Xem `conversationTranscript.mjs` để
   * biết vì sao đó là lựa chọn có chủ ý.
   */
  restored?: boolean;
  restoredMessage?: string | null;
  restoredIntent?: string | null;
};

type ActiveRequest = {
  requestId: string;
  turnId: string;
  controller: AbortController;
};

type Options = {
  uiContext: OrchestratorUiContext;
  /** Chỉ bệnh nhân mới có hội thoại được lưu.
   *
   * Khách vẫn chat bình thường, chỉ là không nạp và không lưu gì — đúng hợp
   * đồng hiện hành của chế độ khách. Kiểm ở đây thay vì gọi API rồi nuốt 403:
   * gọi một endpoint mà ta biết chắc sẽ bị từ chối là làm nhiễu log của chính
   * mình.
   */
  persistence: boolean;
  onUnauthorized: () => void;
  onOnboardingRequired: () => void;
  onOnboardingAccepted?: () => void;
};

const STORAGE_KEY = "vmec05_conversation_id";

function readStoredConversationId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Cửa sổ ẩn danh, hoặc trình duyệt chặn site data. Mất chỗ đánh dấu là
    // chuyện nhỏ; để nó ném ra và làm hỏng cả khung chat mới là chuyện lớn.
    return null;
  }
}

function storeConversationId(conversationId: number | null): void {
  try {
    if (conversationId === null) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, String(conversationId));
  } catch {
    /* xem readStoredConversationId */
  }
}

function localId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useOrchestratorChat({
  uiContext,
  persistence,
  onUnauthorized,
  onOnboardingRequired,
  onOnboardingAccepted,
}: Options) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const activeRequestRef = useRef<ActiveRequest | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [loadingTranscript, setLoadingTranscript] = useState(false);

  // Ref chứ không phải deps của `send`: `send` được truyền xuống ChatPanel, và
  // dựng lại nó sau mỗi lần đổi hội thoại làm composer mất focus giữa lúc đang
  // gõ. Mọi chỗ đổi hội thoại đều đi qua `selectConversation`, nên ref không
  // bao giờ lệch với state — đồng bộ ngay trong render sẽ vi phạm quy tắc của
  // React và cũng không cần thiết.
  const conversationIdRef = useRef<number | null>(null);

  const selectConversation = useCallback((target: number | null) => {
    conversationIdRef.current = target;
    setConversationId(target);
    storeConversationId(target);
  }, []);

  const openConversation = useCallback(async (target: number | null) => {
    selectConversation(target);
    if (target === null) {
      setTurns([]);
      return;
    }
    setLoadingTranscript(true);
    try {
      const detail = await getConversation(target);
      if (detail.conversation.onboarding_acknowledged) {
        onOnboardingAccepted?.();
      }
      setTurns(messagesToTurns(detail.messages) as ChatTurn[]);
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      if (caught instanceof ConversationNotFoundError) {
        // Id đã cũ — hội thoại bị xoá, hoặc còn sót từ tài khoản khác từng
        // đăng nhập trên máy này. Mở hội thoại trống, không báo lỗi đỏ cho một
        // chuyện tự sửa được.
        selectConversation(null);
        setTurns([]);
        return;
      }
      setTurns([]);
    } finally {
      setLoadingTranscript(false);
    }
  }, [onOnboardingAccepted, onUnauthorized, selectConversation]);

  const refreshConversations = useCallback(async () => {
    if (!persistence) return [];
    try {
      const items = await listConversations();
      setConversations(items);
      if (items.some((item) => item.onboarding_acknowledged)) {
        onOnboardingAccepted?.();
      }
      return items;
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) onUnauthorized();
      return [];
    }
  }, [onOnboardingAccepted, onUnauthorized, persistence]);

  // Nạp lại lịch sử khi vào trang. Đây là thứ làm cho F5 không mất gì.
  useEffect(() => {
    if (!persistence) return;
    let cancelled = false;
    void (async () => {
      const items = await refreshConversations();
      if (cancelled) return;
      const initial = pickInitialConversation(items, readStoredConversationId());
      if (initial !== null) await openConversation(initial);
    })();
    return () => {
      cancelled = true;
    };
  }, [openConversation, persistence, refreshConversations]);

  const startNewChat = useCallback(async () => {
    if (!persistence) {
      setTurns([]);
      return;
    }
    try {
      const created = await createConversation();
      if (created.onboarding_acknowledged) {
        onOnboardingAccepted?.();
      }
      setConversations((current) => [created, ...current]);
      selectConversation(created.id);
      // Transcript trống vì hàng vừa tạo chưa có tin nhắn nào — và context
      // cũng trống theo cấu trúc, vì context nằm trên chính hàng đó. New Chat
      // ở đây không phải là "xoá màn hình".
      setTurns([]);
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) onUnauthorized();
    }
  }, [onOnboardingAccepted, onUnauthorized, persistence, selectConversation]);

  const updateTurn = useCallback((turnId: string, patch: Partial<ChatTurn>) => {
    setTurns((current) => current.map((turn) => (turn.id === turnId ? { ...turn, ...patch } : turn)));
  }, []);

  const send = useCallback(async (message: string) => {
    const userMessage = message.trim();
    if (!userMessage || activeRequestRef.current) return false;

    const turnId = localId();
    const requestId = localId();
    const controller = new AbortController();
    activeRequestRef.current = { requestId, turnId, controller };
    setActiveTurnId(turnId);
    setTurns((current) => [
      ...current,
      {
        id: turnId,
        requestId,
        userMessage,
        deliveryState: "CONNECTING",
        createdAt: new Date().toISOString(),
        retryable: false,
      },
    ]);

    try {
      const terminal = await streamOrchestratorMessage(userMessage, {
        uiContext,
        clientRequestId: requestId,
        signal: controller.signal,
        conversationId: conversationIdRef.current,
        onEvent(event) {
          if (!isCurrentRequest(activeRequestRef.current?.requestId ?? null, requestId, controller.signal.aborted)) {
            return;
          }
          if (event.event_type === "progress") {
            updateTurn(turnId, {
              progressStage: event.payload.stage,
              deliveryState: "RECEIVING_PROGRESS",
            });
          }
        },
      });

      if (!isCurrentRequest(activeRequestRef.current?.requestId ?? null, requestId, controller.signal.aborted)) {
        return true;
      }
      if (terminal.event_type === "message.completed") {
        updateTurn(turnId, {
          response: terminal.payload.response,
          deliveryState: "COMPLETED",
          retryable: false,
        });
        if (terminal.payload.response.reason_code === "ONBOARDING_REQUIRED") {
          onOnboardingRequired();
        }
      } else {
        updateTurn(turnId, {
          deliveryState: "FAILED",
          error: "Trợ lý chưa thể phản hồi lúc này. Vui lòng thử lại.",
          retryable: true,
        });
      }
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) {
        onUnauthorized();
        return true;
      }
      if (controller.signal.aborted) return true;
      updateTurn(turnId, {
        deliveryState: "FAILED",
        error: "Kết nối bị gián đoạn. Vui lòng thử lại.",
        retryable: true,
      });
    } finally {
      if (activeRequestRef.current?.requestId === requestId) {
        activeRequestRef.current = null;
        setActiveTurnId(null);
      }
    }

    // Làm mới danh sách sau mỗi lượt: câu hỏi đầu tiên đặt tên cho hội thoại,
    // và thứ tự trong danh sách sắp theo lần cập nhật gần nhất. Không làm mới
    // thì nhãn ở thanh bên đứng yên ở "Cuộc trò chuyện mới" mãi.
    if (persistence) {
      const items = await refreshConversations();
      // Lượt đầu chưa có id: server đã tự mở hội thoại, giờ nhận lại id đó để
      // các lượt sau đi đúng chỗ.
      if (conversationIdRef.current === null && items.length > 0) {
        selectConversation(items[0].id);
      }
    }
    return true;
  }, [
    onOnboardingRequired,
    onUnauthorized,
    persistence,
    refreshConversations,
    selectConversation,
    uiContext,
    updateTurn,
  ]);

  const stop = useCallback(() => {
    const active = activeRequestRef.current;
    if (!active) return;
    active.controller.abort();
    activeRequestRef.current = null;
    setActiveTurnId(null);
    updateTurn(active.turnId, {
      deliveryState: "CANCELLED",
      error: "Đã dừng",
      retryable: true,
    });
  }, [updateTurn]);

  const retry = useCallback((turnId: string) => {
    const turn = turns.find((candidate) => candidate.id === turnId);
    if (!turn || activeRequestRef.current || !turn.retryable) return Promise.resolve(false);
    return send(turn.userMessage);
  }, [send, turns]);

  return {
    turns,
    activeTurnId,
    requestActive: activeTurnId !== null,
    conversations,
    conversationId,
    loadingTranscript,
    openConversation,
    startNewChat,
    send,
    stop,
    retry,
  };
}

