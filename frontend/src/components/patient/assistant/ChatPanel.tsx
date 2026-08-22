"use client";

import {
  Fragment,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
  useState,
} from "react";
import { Send, Sparkles, Square, X } from "lucide-react";

import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import { Message, MessageContent, MessageHeader } from "@/components/ui/message";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { Textarea } from "@/components/ui/textarea";
import { canSubmitMessage, composerKeyAction } from "@/lib/orchestratorChat.mjs";
import type { Role } from "@/lib/api";
import type { SuggestedAction } from "@/types/orchestrator";
import AssistantTurn from "./AssistantTurn";
import type { ChatTurn } from "./useOrchestratorChat";

const starterPrompts = [
  "Giải thích WBC của em",
  "Xem xu hướng HbA1c gần đây",
  "Chuẩn bị câu hỏi cho bác sĩ",
];

type Props = {
  open: boolean;
  mobile: boolean;
  role: Role;
  panelRef: RefObject<HTMLElement | null>;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  onboardingAccepted: boolean;
  onboardingLoading: boolean;
  onboardingError: string | null;
  turns: ChatTurn[];
  requestActive: boolean;
  onClose: () => void;
  onAcknowledge: () => void;
  onSend: (message: string) => void;
  onStop: () => void;
  onRetry: (turnId: string) => void;
  onAction: (action: SuggestedAction) => void;
  onPanelKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
};

function EmptyConversation({ onPrompt }: { onPrompt: (prompt: string) => void }) {
  return (
    <div className="assistant-empty-state">
      <div className="assistant-empty-mark" aria-hidden="true"><Sparkles /></div>
      <h2>Tôi có thể giúp bạn hiểu kết quả xét nghiệm hiện có.</h2>
      <p>Tôi hỗ trợ giải thích, xem lịch sử và chuẩn bị câu hỏi; không thay thế chẩn đoán của bác sĩ.</p>
      <div className="assistant-starters" aria-label="Gợi ý bắt đầu">
        {starterPrompts.map((prompt) => (
          <button type="button" key={prompt} onClick={() => onPrompt(prompt)}>{prompt}</button>
        ))}
      </div>
    </div>
  );
}

export default function ChatPanel({
  open,
  mobile,
  role,
  panelRef,
  composerRef,
  onboardingAccepted,
  onboardingLoading,
  onboardingError,
  turns,
  requestActive,
  onClose,
  onAcknowledge,
  onSend,
  onStop,
  onRetry,
  onAction,
  onPanelKeyDown,
}: Props) {
  const [draft, setDraft] = useState("");

  function submitDraft() {
    if (!canSubmitMessage(draft, onboardingAccepted, requestActive)) return;
    const message = draft.trim();
    setDraft("");
    onSend(message);
  }

  function submitPrompt(prompt: string) {
    if (!canSubmitMessage(prompt, onboardingAccepted, requestActive)) return;
    onSend(prompt);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitDraft();
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    const action = composerKeyAction({
      key: event.key,
      shiftKey: event.shiftKey,
      ctrlKey: event.ctrlKey,
      metaKey: event.metaKey,
      isComposing: event.nativeEvent.isComposing,
    });
    if (action === "send") {
      event.preventDefault();
      submitDraft();
    }
  }

  return (
    <section
      id="patient-ai-assistant"
      ref={panelRef}
      className="assistant-panel"
      role="dialog"
      aria-modal={mobile ? true : undefined}
      aria-labelledby="assistant-dialog-title"
      aria-describedby="assistant-dialog-subtitle"
      hidden={!open}
      tabIndex={-1}
      onKeyDown={onPanelKeyDown}
    >
      <header className="assistant-header">
        <div className="assistant-brand-mark" aria-hidden="true"><Sparkles /></div>
        <div className="assistant-header-copy">
          <h2 id="assistant-dialog-title">Trợ lý kết quả xét nghiệm</h2>
          <p id="assistant-dialog-subtitle">Hỗ trợ giải thích, không chẩn đoán</p>
        </div>
        {requestActive ? <span className="assistant-active-indicator"><i aria-hidden="true" />Đang hỗ trợ</span> : null}
        <Button type="button" variant="ghost" size="icon" className="assistant-close" aria-label="Đóng trợ lý" onClick={onClose}>
          <X aria-hidden="true" />
        </Button>
      </header>

      <div className="assistant-onboarding-slot">
        {!onboardingAccepted ? (
          <section className="assistant-onboarding" aria-labelledby="assistant-onboarding-title">
            <div>
              <h2 id="assistant-onboarding-title">Trước khi bắt đầu</h2>
              <p>Trợ lý giúp giải thích và điều hướng kết quả hiện có, không chẩn đoán hoặc thay thế chuyên gia y tế.</p>
            </div>
            {onboardingError ? <p className="assistant-onboarding-error" role="alert">{onboardingError}</p> : null}
            <Button type="button" disabled={onboardingLoading} onClick={onAcknowledge}>
              {onboardingLoading ? "Đang ghi nhận…" : "Tôi đã hiểu"}
            </Button>
          </section>
        ) : null}
      </div>

      <MessageScrollerProvider autoScroll>
        <MessageScroller
          className="assistant-transcript-shell"
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label="Cuộc trò chuyện với trợ lý"
        >
          <MessageScrollerViewport
            className="assistant-transcript"
          >
            <MessageScrollerContent className="assistant-transcript-content">
              {onboardingAccepted && turns.length === 0 ? (
                <MessageScrollerItem messageId="empty-conversation">
                  <EmptyConversation onPrompt={submitPrompt} />
                </MessageScrollerItem>
              ) : null}
              {turns.map((turn) => (
                <Fragment key={turn.id}>
                  <MessageScrollerItem messageId={`${turn.id}-user`} scrollAnchor>
                    <Message align="end" className="assistant-user-message">
                      <MessageContent>
                        <MessageHeader><span className="sr-only">Bạn</span></MessageHeader>
                        <Bubble variant="tinted" align="end" className="assistant-user-bubble">
                          <BubbleContent>{turn.userMessage}</BubbleContent>
                        </Bubble>
                        <time className="sr-only" dateTime={turn.createdAt}>Tin nhắn đã gửi</time>
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                  <MessageScrollerItem messageId={`${turn.id}-assistant`}>
                    <AssistantTurn
                      turn={turn}
                      role={role}
                      requestActive={requestActive}
                      onRetry={onRetry}
                      onAction={onAction}
                    />
                  </MessageScrollerItem>
                </Fragment>
              ))}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton direction="end" size="sm" className="assistant-scroll-latest">
            Tin nhắn mới ↓
          </MessageScrollerButton>
        </MessageScroller>
      </MessageScrollerProvider>

      <form className="assistant-composer" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="assistant-message-input">Nhập tin nhắn cho trợ lý</label>
        <div className="assistant-composer-field">
          <Textarea
            ref={composerRef}
            id="assistant-message-input"
            name="assistant-message"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder={onboardingAccepted ? "Hỏi về kết quả xét nghiệm của bạn…" : "Vui lòng xác nhận phạm vi sử dụng trước"}
            disabled={!onboardingAccepted}
            rows={1}
            autoComplete="off"
          />
          {requestActive ? (
            <Button type="button" variant="outline" size="icon" className="assistant-send-stop" aria-label="Dừng phản hồi" onClick={onStop}>
              <Square aria-hidden="true" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon"
              className="assistant-send-stop"
              aria-label="Gửi tin nhắn"
              disabled={!canSubmitMessage(draft, onboardingAccepted, false)}
            >
              <Send aria-hidden="true" />
            </Button>
          )}
        </div>
        <p className="assistant-composer-hint">
          {requestActive ? "Bạn vẫn có thể soạn câu hỏi tiếp theo." : "Enter để gửi · Shift+Enter để xuống dòng"}
        </p>
      </form>
    </section>
  );
}
