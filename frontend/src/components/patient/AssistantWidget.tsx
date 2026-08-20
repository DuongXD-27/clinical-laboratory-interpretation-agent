"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  acknowledgeOrchestratorOnboarding,
  clearSession,
  sendOrchestratorMessage,
  UnauthorizedError,
  type Role,
} from "@/lib/api";
import {
  actionDestination,
  sanitizeSuggestedAction,
  shouldOfferOcrConfirm,
} from "@/lib/assistantActions.mjs";
import { formatDate } from "@/lib/patientUi.mjs";
import type { OrchestratorPayload, OrchestratorResponse, SuggestedAction } from "@/types/orchestrator";

type ChatMessage = {
  id: string;
  sender: "assistant" | "user";
  text: string;
  response?: OrchestratorResponse;
};

type Props = {
  role: Role;
};

const starterPrompts = [
  "Tôi có thể làm gì với kết quả xét nghiệm hiện có?",
  "Giải thích kết quả hiện tại",
  "Chuẩn bị câu hỏi cho bác sĩ",
];

function messageId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function uiContextForPath(pathname: string) {
  const reportMatch = pathname.match(/^\/patient\/(?:reports|history)\/([A-Za-z0-9_.%+-]+)$/);
  return {
    screen: "patient",
    view: pathname.startsWith("/patient/analysis")
      ? "analysis"
      : pathname.startsWith("/patient/history") || pathname.startsWith("/patient/reports")
        ? "history"
        : pathname.startsWith("/patient/trends")
          ? "trend"
          : "dashboard",
    ...(reportMatch ? { candidate_report_ref: reportMatch[1] } : {}),
  };
}

function statusLabel(status: OrchestratorResponse["status"]) {
  if (status === "success") return "Hoàn tất";
  if (status === "needs_input") return "Cần thêm thông tin";
  if (status === "blocked") return "Bị chặn an toàn";
  return "Có lỗi";
}

function actionLabel(action: string) {
  switch (action) {
    case "OPEN_REPORT":
      return "Mở phiếu";
    case "VIEW_ABNORMAL":
      return "Xem chỉ số bất thường";
    case "VIEW_HISTORY":
      return "Xem lịch sử";
    case "VIEW_TREND":
      return "Xem xu hướng";
    case "VIEW_DOCTOR_QUESTIONS":
      return "Câu hỏi cho bác sĩ";
    case "CONFIRM_OCR":
      return "Xác nhận OCR";
    case "RETRY":
      return "Thử lại";
    default:
      return "Hành động";
  }
}

function safeSources(sources: string[] | undefined) {
  return (sources ?? []).filter((source) => {
    try {
      const url = new URL(source);
      return url.protocol === "http:" || url.protocol === "https:";
    } catch {
      return false;
    }
  });
}

function StructuredPayload({ data }: { data: OrchestratorPayload }) {
  if (data.data_type === "analysis") {
    return (
      <div className="assistant-structured">
        <strong>Chỉ số trong kết quả</strong>
        <ul>
          {data.indicators.slice(0, 5).map((indicator) => (
            <li key={`${indicator.name}-${indicator.unit}`}>
              <span>{indicator.name}</span>
              <span>{indicator.value} {indicator.unit} · {indicator.status}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (data.data_type === "history_summary") {
    return (
      <div className="assistant-structured">
        <strong>Phiếu gần nhất</strong>
        <dl>
          <div><dt>Ngày xét nghiệm</dt><dd>{formatDate(data.test_date)}</dd></div>
          <div><dt>Số chỉ số</dt><dd>{data.result_count}</dd></div>
          <div><dt>Trạng thái</dt><dd>{data.status}</dd></div>
        </dl>
        {data.summary && <p>{data.summary}</p>}
      </div>
    );
  }

  if (data.data_type === "trend") {
    return (
      <div className="assistant-structured">
        <strong>{data.trend.display_name}</strong>
        <dl>
          <div><dt>Đơn vị</dt><dd>{data.trend.canonical_unit}</dd></div>
          <div><dt>Số điểm</dt><dd>{data.trend.result_count}</dd></div>
        </dl>
      </div>
    );
  }

  if (data.data_type === "doctor_questions") {
    return (
      <div className="assistant-structured">
        <strong>Câu hỏi gợi ý</strong>
        <ol>
          {data.questions.map((question, index) => (
            <li key={`${question.display_order ?? index}-${question.text ?? question.question_text}`}>
              {question.text ?? question.question_text}
            </li>
          ))}
        </ol>
      </div>
    );
  }

  if (data.data_type === "explanation") {
    return <div className="assistant-structured"><p>{data.explanation}</p></div>;
  }

  if (data.data_type === "needs_input") {
    return (
      <div className="assistant-structured">
        <p>{data.prompt}</p>
        {data.missing_fields && data.missing_fields.length > 0 && (
          <p>Cần bổ sung: {data.missing_fields.join(", ")}</p>
        )}
      </div>
    );
  }

  if (data.data_type === "blocked") {
    return <div className="assistant-structured"><p>{data.safety_notice}</p></div>;
  }

  return null;
}

export default function AssistantWidget({ role }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const panelRef = useRef<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [onboardingAccepted, setOnboardingAccepted] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "assistant-welcome",
      sender: "assistant",
      text: "Tôi có thể giúp bạn hiểu và điều hướng kết quả xét nghiệm hiện có.",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastUserMessage = useMemo(
    () => [...messages].reverse().find((message) => message.sender === "user")?.text ?? "",
    [messages],
  );

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  async function acknowledge() {
    setLoading(true);
    setError(null);
    try {
      const response = await acknowledgeOrchestratorOnboarding();
      setOnboardingAccepted(true);
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          sender: "assistant",
          text: response.message,
          response,
        },
      ]);
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) {
        clearSession();
        router.replace("/login");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Chưa thể ghi nhận xác nhận.");
    } finally {
      setLoading(false);
    }
  }

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    setDraft("");
    setMessages((current) => [...current, { id: messageId(), sender: "user", text: trimmed }]);
    try {
      const response = await sendOrchestratorMessage(trimmed, uiContextForPath(pathname));
      if (response.reason_code === "ONBOARDING_REQUIRED") {
        setOnboardingAccepted(false);
      }
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          sender: "assistant",
          text: response.message,
          response,
        },
      ]);
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) {
        clearSession();
        router.replace("/login");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Trợ lý chưa thể phản hồi lúc này.");
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!onboardingAccepted) return;
    void sendMessage(draft);
  }

  function runAction(action: SuggestedAction) {
    const safeAction = sanitizeSuggestedAction(action, role);
    if (!safeAction) return;
    if (safeAction.action === "RETRY") {
      void sendMessage(lastUserMessage);
      return;
    }
    const destination = actionDestination(safeAction, role);
    if (destination) {
      router.push(destination);
      setOpen(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="assistant-launcher"
        aria-label={open ? "Đóng trợ lý AI" : "Mở trợ lý AI"}
        aria-expanded={open}
        aria-controls="patient-ai-assistant"
        onClick={() => setOpen((current) => !current)}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false">
          <path d="M5 6.75A3.75 3.75 0 0 1 8.75 3h6.5A3.75 3.75 0 0 1 19 6.75v4.5A3.75 3.75 0 0 1 15.25 15H11l-4.6 3.45A.88.88 0 0 1 5 17.75V15.2a3.75 3.75 0 0 1-2.75-3.6V6.75Z" />
          <path d="M9.1 8.1h5.8M9.1 11h3.8" />
        </svg>
      </button>

      {open && (
        <section
          id="patient-ai-assistant"
          ref={panelRef}
          className="assistant-panel"
          aria-label="Trợ lý AI VMEC"
          tabIndex={-1}
        >
          <header className="assistant-header">
            <div>
              <span>Trợ lý AI</span>
              <strong>Điều hướng kết quả xét nghiệm</strong>
            </div>
            <button type="button" aria-label="Thu gọn trợ lý AI" onClick={() => setOpen(false)}>×</button>
          </header>

          {!onboardingAccepted && (
            <div className="assistant-onboarding" role="region" aria-labelledby="assistant-onboarding-title">
              <h2 id="assistant-onboarding-title">Trước khi sử dụng trợ lý</h2>
              <p>Trợ lý giúp giải thích và điều hướng các khả năng hiện có của VMEC.</p>
              <p>Trợ lý không chẩn đoán, không thay thế chuyên gia y tế, và trạng thái y khoa vẫn dựa trên quy trình hệ thống đã phê duyệt.</p>
              <button type="button" className="primary-button" disabled={loading} onClick={() => void acknowledge()}>
                {loading ? "Đang ghi nhận..." : "Tôi đã hiểu"}
              </button>
            </div>
          )}

          <div className="assistant-messages" aria-live="polite">
            {messages.map((message) => (
              <article key={message.id} className={`assistant-message ${message.sender}`}>
                <p>{message.text}</p>
                {message.response && (
                  <>
                    <span className={`assistant-status assistant-status-${message.response.status}`}>
                      {statusLabel(message.response.status)}
                    </span>
                    <StructuredPayload data={message.response.data} />
                    {message.response.safety_notice && (
                      <p className="assistant-safety">{message.response.safety_notice}</p>
                    )}
                    {shouldOfferOcrConfirm(message.response, role) && (
                      <p className="assistant-ocr-notice">Cần xác nhận OCR trong giao diện hiện có trước khi phân tích.</p>
                    )}
                    {safeSources(message.response.sources).length > 0 && (
                      <div className="assistant-sources">
                        <strong>Nguồn</strong>
                        {safeSources(message.response.sources).map((source) => (
                          <a key={source} href={source} target="_blank" rel="noreferrer">
                            {new URL(source).hostname.replace(/^www\./, "")}
                          </a>
                        ))}
                      </div>
                    )}
                    {message.response.suggested_actions && message.response.suggested_actions.length > 0 && (
                      <div className="assistant-actions" aria-label="Hành động gợi ý">
                        {message.response.suggested_actions.map((action, index) => {
                          const safeAction = sanitizeSuggestedAction(action, role);
                          if (!safeAction) return null;
                          return (
                            <button
                              key={`${safeAction.action}-${index}`}
                              type="button"
                              className="secondary-button"
                              onClick={() => runAction(action)}
                              disabled={loading || (safeAction.action === "RETRY" && !lastUserMessage)}
                            >
                              {actionLabel(safeAction.action)}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </>
                )}
              </article>
            ))}
            {loading && <div className="loading-message assistant-loading" role="status"><span className="loading-dot" aria-hidden="true" />Đang chờ phản hồi...</div>}
            {error && <div className="error-message assistant-error" role="alert">{error}</div>}
          </div>

          {onboardingAccepted && (
            <div className="assistant-starters" aria-label="Gợi ý bắt đầu">
              {messages.length <= 2 && starterPrompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => void sendMessage(prompt)} disabled={loading}>
                  {prompt}
                </button>
              ))}
            </div>
          )}

          <form className="assistant-composer" onSubmit={handleSubmit}>
            <label htmlFor="assistant-message-input">Nhập tin nhắn cho trợ lý</label>
            <textarea
              id="assistant-message-input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={onboardingAccepted ? "Hỏi về kết quả hoặc thao tác tiếp theo..." : "Vui lòng xác nhận phạm vi sử dụng trước"}
              disabled={!onboardingAccepted || loading}
              rows={2}
            />
            <button type="submit" className="primary-button" disabled={!onboardingAccepted || loading || !draft.trim()}>
              Gửi
            </button>
          </form>
        </section>
      )}
    </>
  );
}
