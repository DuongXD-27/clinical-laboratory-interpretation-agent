"use client";

import { useCallback, useRef, useState } from "react";

import { streamOrchestratorMessage, UnauthorizedError } from "@/lib/api";
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
};

type ActiveRequest = {
  requestId: string;
  turnId: string;
  controller: AbortController;
};

type Options = {
  uiContext: OrchestratorUiContext;
  onUnauthorized: () => void;
  onOnboardingRequired: () => void;
};

function localId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useOrchestratorChat({
  uiContext,
  onUnauthorized,
  onOnboardingRequired,
}: Options) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const activeRequestRef = useRef<ActiveRequest | null>(null);

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
    return true;
  }, [onOnboardingRequired, onUnauthorized, uiContext, updateTurn]);

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
    send,
    stop,
    retry,
  };
}

