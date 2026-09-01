"use client";

import { Fragment, type KeyboardEvent, type RefObject, useState } from "react";

import { SystemState } from "@/components/common/SystemState";
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
import { Skeleton } from "@/components/ui/skeleton";
import type { ConversationSummary, Role } from "@/lib/api";
import type { SuggestedAction } from "@/types/orchestrator";
import AssistantTurn from "./AssistantTurn";
import ChatComposer from "./ChatComposer";
import ChatEmptyState from "./ChatEmptyState";
import ChatHeader from "./ChatHeader";
import ChatThreadList from "./ChatThreadList";
import type { AssistantVisibility } from "@/lib/motion";
import type { ChatTurn } from "./useOrchestratorChat";

type Props = {
  mobile: boolean;
  role: Role;
  panelRef: RefObject<HTMLElement | null>;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  contextLabel: string;
  onboardingAccepted: boolean;
  onboardingLoading: boolean;
  onboardingError: string | null;
  turns: ChatTurn[];
  requestActive: boolean;
  conversations: ConversationSummary[];
  conversationId: number | null;
  loadingTranscript: boolean;
  loadingConversations: boolean;
  conversationListError: string | null;
  transcriptError: string | null;
  persistence: boolean;
  state?: AssistantVisibility;
  onNewChat: () => void;
  onOpenConversation: (conversationId: number) => void;
  onRefreshConversations: () => void;
  onClose: () => void;
  onAcknowledge: () => void;
  onSend: (message: string) => void;
  onStop: () => void;
  onRetry: (turnId: string) => void;
  onAction: (action: SuggestedAction) => void;
  onPanelKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
  onAnimationEnd?: (event: React.AnimationEvent<HTMLElement>) => void;
};

export default function ChatPanel({
  mobile,
  role,
  panelRef,
  composerRef,
  contextLabel,
  onboardingAccepted,
  onboardingLoading,
  onboardingError,
  turns,
  requestActive,
  conversations,
  conversationId,
  loadingTranscript,
  loadingConversations,
  conversationListError,
  transcriptError,
  persistence,
  onNewChat,
  onOpenConversation,
  onRefreshConversations,
  onClose,
  onAcknowledge,
  onSend,
  onStop,
  onRetry,
  onAction,
  onPanelKeyDown,
  state = "open",
  onAnimationEnd,
}: Props) {
  const [view, setView] = useState<"conversation" | "history">("conversation");

  function startNewChat() {
    if (requestActive) onStop();
    onNewChat();
    setView("conversation");
    requestAnimationFrame(() => composerRef.current?.focus());
  }

  function toggleHistory() {
    if (view === "history") {
      setView("conversation");
      return;
    }
    if (requestActive) onStop();
    onRefreshConversations();
    setView("history");
  }

  function openConversation(target: number) {
    setView("conversation");
    onOpenConversation(target);
  }

  function submitPrompt(prompt: string) {
    if (!onboardingAccepted || requestActive) return;
    onSend(prompt);
  }

  return (
    <section
      id="patient-ai-assistant"
      ref={panelRef}
      className="assistant-panel"
      data-state={state}
      hidden={state === "closed"}
      role="dialog"
      aria-modal={mobile ? true : undefined}
      aria-labelledby="assistant-dialog-title"
      aria-describedby="assistant-dialog-subtitle"
      tabIndex={-1}
      onKeyDown={onPanelKeyDown}
      onAnimationEnd={onAnimationEnd}
    >
      <ChatHeader
        persistence={persistence}
        requestActive={requestActive}
        contextLabel={view === "history" ? "Các cuộc trò chuyện đã lưu" : contextLabel}
        view={view}
        onNewChat={startNewChat}
        onHistory={toggleHistory}
        onClose={onClose}
      />

      {view === "history" ? (
        <ChatThreadList
          conversations={conversations}
          conversationId={conversationId}
          loading={loadingConversations}
          error={conversationListError}
          onOpenConversation={openConversation}
          onRefresh={onRefreshConversations}
        />
      ) : (
        <div className="assistant-conversation-view">
          {!onboardingAccepted ? (
            <section className="assistant-onboarding" aria-labelledby="assistant-onboarding-title">
              <div>
                <p className="assistant-onboarding-kicker">Hướng dẫn an toàn</p>
                <h2 id="assistant-onboarding-title">Trước khi bắt đầu</h2>
                <p>
                  Trợ lý giúp giải thích và điều hướng kết quả hiện có, không
                  chẩn đoán hoặc thay thế chuyên gia y tế.
                </p>
              </div>
              {onboardingError ? (
                <p className="assistant-onboarding-error" role="alert">{onboardingError}</p>
              ) : null}
              <Button type="button" disabled={onboardingLoading} onClick={onAcknowledge}>
                {onboardingLoading ? "Đang ghi nhận…" : "Tôi đã hiểu"}
              </Button>
            </section>
          ) : null}

          <MessageScrollerProvider autoScroll>
            <MessageScroller
              className="assistant-transcript-shell"
              role="log"
              aria-live="polite"
              aria-relevant="additions text"
              aria-label="Cuộc trò chuyện với trợ lý"
            >
              <MessageScrollerViewport className="assistant-transcript">
                <MessageScrollerContent className="assistant-transcript-content">
                  {onboardingAccepted && loadingTranscript ? (
                    <MessageScrollerItem messageId="loading-transcript">
                      <div className="assistant-loading-transcript" role="status">
                        <Skeleton className="assistant-loading-avatar" />
                        <span className="assistant-loading-lines">
                          <Skeleton />
                          <Skeleton />
                          <Skeleton />
                        </span>
                        <span className="sr-only">Đang mở cuộc trò chuyện</span>
                      </div>
                    </MessageScrollerItem>
                  ) : null}

                  {onboardingAccepted && !loadingTranscript && transcriptError ? (
                    <MessageScrollerItem messageId="transcript-error">
                      <SystemState
                        kind="error"
                        compact
                        title="Chưa mở được cuộc trò chuyện"
                        description={transcriptError}
                      />
                    </MessageScrollerItem>
                  ) : null}

                  {onboardingAccepted && !loadingTranscript && !transcriptError && turns.length === 0 ? (
                    <MessageScrollerItem messageId="empty-conversation">
                      <ChatEmptyState contextLabel={contextLabel} onPrompt={submitPrompt} />
                    </MessageScrollerItem>
                  ) : null}

                  {turns.map((turn) => (
                    <Fragment key={turn.id}>
                      {turn.userMessage ? (
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
                      ) : null}
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

          <ChatComposer
            composerRef={composerRef}
            onboardingAccepted={onboardingAccepted}
            requestActive={requestActive}
            onSend={onSend}
            onStop={onStop}
          />
        </div>
      )}
    </section>
  );
}
