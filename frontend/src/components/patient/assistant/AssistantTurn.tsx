"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";

import { BrandMark } from "@/components/common/BrandSignature";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import StatusIndicator, { type StatusState } from "@/components/common/StatusIndicator";
import { Message, MessageAvatar, MessageContent, MessageHeader } from "@/components/ui/message";
import { sanitizeSuggestedAction } from "@/lib/assistantActions.mjs";
import { formatClinicalText, formatClinicalValue } from "@/lib/clinicalUnit.mjs";
import { tokenizeInlineMarkdown } from "@/lib/inlineMarkdown.mjs";
import { formatDate } from "@/lib/patientUi.mjs";
import {
  authoritativeCriticalAlerts,
  safeHttpSources,
} from "@/lib/orchestratorChat.mjs";
import type { Role } from "@/lib/api";
import type { CriticalAlert } from "@/types/analysis";
import type {
  OrchestratorPayload,
  OrchestratorResponse,
  SuggestedAction,
} from "@/types/orchestrator";
import type { ChatTurn } from "./useOrchestratorChat";
import ChatSources from "./ChatSources";

type Props = {
  turn: ChatTurn;
  role: Role;
  requestActive: boolean;
  onRetry: (turnId: string) => void;
  onAction: (action: SuggestedAction) => void;
};

function actionLabel(action: SuggestedAction["action"]) {
  switch (action) {
    case "OPEN_REPORT": return "Mở phiếu";
    case "VIEW_ABNORMAL": return "Xem chỉ số bất thường";
    case "VIEW_HISTORY": return "Xem lịch sử";
    case "VIEW_TREND": return "Xem xu hướng";
    case "VIEW_DOCTOR_QUESTIONS": return "Câu hỏi cho bác sĩ";
    case "CONFIRM_OCR": return "Xác nhận OCR";
    case "RETRY": return "Thử lại";
  }
}

function InlineMarkdownText({ text }: { text: string }) {
  return (
    <>
      {tokenizeInlineMarkdown(text).map((token, index) => {
        if (token.type === "bold") return <strong key={index}>{formatClinicalText(token.value)}</strong>;
        if (token.type === "code") return <code key={index}>{token.value}</code>;
        return <span key={index}>{formatClinicalText(token.value)}</span>;
      })}
    </>
  );
}

function ResponseBody({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/).filter((paragraph) => paragraph.trim());
  return (
    <div className="assistant-response-body">
      {paragraphs.map((paragraph, index) => (
        <p className="assistant-prose" key={`${index}-${paragraph.slice(0, 24)}`}>
          <InlineMarkdownText text={paragraph} />
        </p>
      ))}
    </div>
  );
}

function statusLabel(status: OrchestratorResponse["status"]) {
  if (status === "needs_input") return "Cần thêm thông tin";
  if (status === "blocked") return "Giới hạn an toàn";
  if (status === "error") return "Chưa hoàn tất";
  return null;
}

function statusState(status: OrchestratorResponse["status"]): StatusState {
  if (status === "needs_input") return "input-review";
  if (status === "blocked") return "system-warning";
  return "system-error";
}

function StructuredMedicalPayload({ data }: { data: OrchestratorPayload }) {
  if (data.data_type === "analysis") {
    return (
      <section className="assistant-medical-block" aria-label="Các chỉ số trong kết quả">
        <h3>Chỉ số trong kết quả</h3>
        <ul className="assistant-indicator-list">
          {data.indicators.slice(0, 5).map((indicator) => (
            <li key={`${indicator.name}-${indicator.unit}`}>
              <span>{indicator.name}</span>
              <span className="assistant-medical-value">
                {formatClinicalValue(indicator.value, indicator.unit)}
                <small data-status={indicator.status.toLowerCase()}>{indicator.status}</small>
              </span>
            </li>
          ))}
        </ul>
      </section>
    );
  }

  if (data.data_type === "history_summary") {
    return (
      <section className="assistant-medical-block" aria-label="Thông tin phiếu xét nghiệm">
        <h3>Phiếu xét nghiệm</h3>
        <dl className="assistant-medical-facts">
          <div><dt>Ngày xét nghiệm</dt><dd>{formatDate(data.test_date)}</dd></div>
          <div><dt>Số chỉ số</dt><dd>{data.result_count}</dd></div>
          <div><dt>Trạng thái</dt><dd>{data.status}</dd></div>
        </dl>
      </section>
    );
  }

  if (data.data_type === "trend") {
    const latest = data.trend.points.at(-1);
    return (
      <section className="assistant-medical-block" aria-label={`Dữ liệu xu hướng ${data.trend.display_name}`}>
        <h3>{data.trend.display_name}</h3>
        <dl className="assistant-medical-facts">
          <div><dt>Số lần đo</dt><dd>{data.trend.result_count}</dd></div>
          {latest ? (
            <>
              <div><dt>Kết quả gần nhất</dt><dd>{formatClinicalValue(latest.value, data.trend.canonical_unit)}</dd></div>
              <div><dt>Ngày xét nghiệm</dt><dd>{formatDate(latest.test_date)}</dd></div>
              <div><dt>Đánh giá</dt><dd>{latest.assessment}</dd></div>
            </>
          ) : null}
        </dl>
      </section>
    );
  }

  if (data.data_type === "doctor_questions") {
    return (
      <section className="assistant-medical-block" aria-label="Câu hỏi gợi ý cho bác sĩ">
        <h3>Câu hỏi gợi ý</h3>
        <ol className="assistant-question-list">
          {data.questions.map((question, index) => (
            <li key={`${question.display_order ?? index}-${question.text ?? question.question_text}`}>
              {formatClinicalText(question.text ?? question.question_text)}
            </li>
          ))}
        </ol>
      </section>
    );
  }

  return null;
}

function CriticalAlerts({ alerts }: { alerts: CriticalAlert[] }) {
  if (alerts.length === 0) return null;
  return (
    <div className="assistant-critical-list">
      {alerts.map((alert, index) => (
        <Alert
          key={`${alert.indicator_name}-${alert.value}-${index}`}
          variant="destructive"
          className="assistant-critical-alert"
          role="alert"
        >
          <AlertTriangle aria-hidden="true" />
          <AlertTitle>Cần chú ý khẩn</AlertTitle>
          <AlertDescription>
            <strong>{alert.indicator_name}: {formatClinicalValue(alert.value, alert.unit)}</strong>
            <p>{formatClinicalText(alert.message)}</p>
          </AlertDescription>
        </Alert>
      ))}
    </div>
  );
}

function responseSources(response: OrchestratorResponse) {
  const nested = response.data.data_type === "explanation" ? response.data.sources ?? [] : [];
  return safeHttpSources([...(response.sources ?? []), ...nested]);
}

function TurnError({ turn, requestActive, onRetry }: Pick<Props, "turn" | "requestActive" | "onRetry">) {
  return (
    <Alert variant={turn.deliveryState === "CANCELLED" ? "default" : "warning"} role="alert" className="assistant-turn-error">
      <AlertTitle>{turn.error ?? "Chưa thể hoàn tất"}</AlertTitle>
      <AlertDescription>Bạn có thể thử lại khi sẵn sàng.</AlertDescription>
      <Button type="button" variant="outline" size="sm" disabled={requestActive} onClick={() => onRetry(turn.id)}>
        <RotateCcw data-icon="inline-start" aria-hidden="true" />
        Thử lại
      </Button>
    </Alert>
  );
}

export default function AssistantTurn({ turn, role, requestActive, onRetry, onAction }: Props) {
  const response = turn.response;

  if (turn.deliveryState === "CONNECTING" || turn.deliveryState === "RECEIVING_PROGRESS") {
    return (
      <Message align="start" className="assistant-thinking">
        <MessageAvatar className="assistant-thinking-avatar"><BrandMark /></MessageAvatar>
        <MessageContent className="assistant-thinking-content">
          <div className="assistant-thinking-status" role="status" aria-live="polite" aria-atomic="true">
            <span className="assistant-thinking-label shimmer">LumiLab đang trả lời</span>
            <span className="assistant-thinking-dots" aria-hidden="true">•••</span>
          </div>
        </MessageContent>
      </Message>
    );
  }

  return (
    <Message align="start" className="assistant-turn">
      <MessageAvatar className="assistant-avatar"><BrandMark /></MessageAvatar>
      <MessageContent>
        <MessageHeader><span>Trợ lý LumiLab</span></MessageHeader>
        <Bubble variant="ghost" className="assistant-response">
          <BubbleContent>
            {turn.deliveryState === "FAILED" || turn.deliveryState === "CANCELLED" ? (
              <TurnError turn={turn} requestActive={requestActive} onRetry={onRetry} />
            ) : null}
            {turn.restored && !response ? (
              <div className="assistant-completed-response">
                {/* Lượt dựng lại từ transcript đã lưu: chỉ có văn bản đã qua
                    guardrail, không có nút hành động và không có khối chỉ số.
                    Server không lưu payload có cấu trúc — xem
                    `conversationTranscript.mjs` để biết vì sao. */}
                {turn.restoredMessage ? (
                  <ResponseBody text={turn.restoredMessage} />
                ) : (
                  <p className="assistant-prose assistant-restored-gap">
                    Lượt này chưa có câu trả lời được lưu.
                  </p>
                )}
              </div>
            ) : null}
            {turn.deliveryState === "COMPLETED" && response ? (
              <div className="assistant-completed-response">
                <ResponseBody text={response.message} />
                {statusLabel(response.status) ? (
                  <StatusIndicator state={statusState(response.status)} label={statusLabel(response.status)} />
                ) : null}
                <StructuredMedicalPayload data={response.data} />
                <CriticalAlerts alerts={authoritativeCriticalAlerts(response.data) as CriticalAlert[]} />
                {response.safety_notice && response.safety_notice !== response.message ? (
                  <Alert variant="warning" className="assistant-safety-notice">
                    <AlertDescription>{formatClinicalText(response.safety_notice)}</AlertDescription>
                  </Alert>
                ) : null}
                <ChatSources sources={responseSources(response)} />
                {response.suggested_actions && response.suggested_actions.length > 0 ? (
                  <div className="assistant-actions" aria-label="Hành động gợi ý">
                    {response.suggested_actions.map((action, index) => (
                      (() => {
                        const safeAction = sanitizeSuggestedAction(action, role) as SuggestedAction | null;
                        if (!safeAction) return null;
                        return (
                          <Button
                            key={`${safeAction.action}-${index}`}
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={requestActive || (safeAction.action === "RETRY" && !turn.userMessage)}
                            onClick={() => onAction(safeAction)}
                          >
                            {actionLabel(safeAction.action)}
                          </Button>
                        );
                      })()
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  );
}
