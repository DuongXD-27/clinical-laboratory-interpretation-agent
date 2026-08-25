"use client";

import { AlertTriangle, ExternalLink, RotateCcw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import { Message, MessageContent, MessageHeader } from "@/components/ui/message";
import { sanitizeSuggestedAction } from "@/lib/assistantActions.mjs";
import { tokenizeInlineMarkdown } from "@/lib/inlineMarkdown.mjs";
import { formatDate } from "@/lib/patientUi.mjs";
import {
  authoritativeCriticalAlerts,
  progressLabel,
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
        if (token.type === "bold") return <strong key={index}>{token.value}</strong>;
        if (token.type === "code") return <code key={index}>{token.value}</code>;
        return <span key={index}>{token.value}</span>;
      })}
    </>
  );
}

function statusLabel(status: OrchestratorResponse["status"]) {
  if (status === "needs_input") return "Cần thêm thông tin";
  if (status === "blocked") return "Giới hạn an toàn";
  if (status === "error") return "Chưa hoàn tất";
  return null;
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
                {indicator.value} {indicator.unit}
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
              <div><dt>Kết quả gần nhất</dt><dd>{latest.value} {data.trend.canonical_unit}</dd></div>
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
              {question.text ?? question.question_text}
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
            <strong>{alert.indicator_name}: {alert.value} {alert.unit}</strong>
            <p>{alert.message}</p>
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

function Sources({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null;
  return (
    <details className="assistant-sources">
      <summary>Nguồn tham khảo ({sources.length})</summary>
      <ol>
        {sources.map((source) => {
          const hostname = new URL(source).hostname.replace(/^www\./, "");
          return (
            <li key={source}>
              <a href={source} target="_blank" rel="noopener noreferrer" aria-label={`Mở nguồn ${hostname} trong thẻ mới`}>
                <span>{hostname}</span>
                <ExternalLink aria-hidden="true" />
              </a>
            </li>
          );
        })}
      </ol>
    </details>
  );
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
  const progress = turn.progressStage ? progressLabel(turn.progressStage) : null;

  return (
    <Message align="start" className="assistant-turn">
      <MessageContent>
        <MessageHeader><span className="sr-only">Trợ lý LumiLab</span></MessageHeader>
        <Bubble variant="ghost" className="assistant-response">
          <BubbleContent>
            {turn.deliveryState === "CONNECTING" ? (
              <div className="assistant-progress" role="status">Đang kết nối an toàn…</div>
            ) : null}
            {turn.deliveryState === "RECEIVING_PROGRESS" && progress ? (
              <div className="assistant-progress" role="status" aria-live="polite" aria-atomic="true">
                <span aria-hidden="true" />{progress}
              </div>
            ) : null}
            {turn.deliveryState === "FAILED" || turn.deliveryState === "CANCELLED" ? (
              <TurnError turn={turn} requestActive={requestActive} onRetry={onRetry} />
            ) : null}
            {turn.deliveryState === "COMPLETED" && response ? (
              <div className="assistant-completed-response">
                <p className="assistant-prose"><InlineMarkdownText text={response.message} /></p>
                {statusLabel(response.status) ? (
                  <span className="assistant-response-status" data-status={response.status}>{statusLabel(response.status)}</span>
                ) : null}
                <StructuredMedicalPayload data={response.data} />
                <CriticalAlerts alerts={authoritativeCriticalAlerts(response.data) as CriticalAlert[]} />
                {response.safety_notice && response.safety_notice !== response.message ? (
                  <Alert variant="warning" className="assistant-safety-notice">
                    <AlertDescription>{response.safety_notice}</AlertDescription>
                  </Alert>
                ) : null}
                <Sources sources={responseSources(response)} />
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
