"use client";

import { Clock3, MessageSquareText, RefreshCw } from "lucide-react";

import { SystemState } from "@/components/common/SystemState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConversationSummary } from "@/lib/api";
import { conversationLabel } from "@/lib/conversationTranscript.mjs";
import { formatMoment } from "@/lib/patientUi.mjs";

type Props = {
  conversations: ConversationSummary[];
  conversationId: number | null;
  loading: boolean;
  error: string | null;
  onOpenConversation: (conversationId: number) => void;
  onRefresh: () => void;
};

function dayKey(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? ""
    : parsed.toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });
}

function ThreadRows({
  id,
  label,
  items,
  conversationId,
  onOpenConversation,
}: {
  id: string;
  label: string;
  items: ConversationSummary[];
  conversationId: number | null;
  onOpenConversation: (conversationId: number) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section className="assistant-thread-group" aria-labelledby={id}>
      <h3 id={id}>{label}</h3>
      <ul>
        {items.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              className="assistant-thread-row"
              aria-current={conversation.id === conversationId ? "true" : undefined}
              onClick={() => onOpenConversation(conversation.id)}
            >
              <span className="assistant-thread-icon" aria-hidden="true">
                <MessageSquareText />
              </span>
              <span className="assistant-thread-copy">
                <strong>{conversationLabel(conversation)}</strong>
                <span>Tiếp tục hội thoại đã lưu</span>
              </span>
              <time dateTime={conversation.updated_at}>
                <Clock3 aria-hidden="true" />
                {formatMoment(conversation.updated_at)}
              </time>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ChatThreadList({
  conversations,
  conversationId,
  loading,
  error,
  onOpenConversation,
  onRefresh,
}: Props) {
  const today = dayKey(new Date().toISOString());
  const todayItems = conversations.filter((item) => dayKey(item.updated_at) === today);
  const earlierItems = conversations.filter((item) => dayKey(item.updated_at) !== today);

  return (
    <div
      id="assistant-conversation-list"
      className="assistant-history-view"
      role="region"
      aria-label="Lịch sử trò chuyện"
    >
      <div className="assistant-history-heading">
        <div>
          <p>Không gian riêng của bạn</p>
          <h2>Lịch sử trò chuyện</h2>
        </div>
        <span>{conversations.length} cuộc trò chuyện</span>
      </div>

      {loading ? (
        <div className="assistant-thread-skeletons" role="status" aria-label="Đang tải lịch sử trò chuyện">
          {[0, 1, 2].map((item) => <Skeleton key={item} className="assistant-thread-skeleton" />)}
        </div>
      ) : error ? (
        <SystemState
          kind="error"
          compact
          title="Chưa tải được lịch sử"
          description={error}
          action={(
            <Button type="button" variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw data-icon="inline-start" aria-hidden="true" />
              Thử lại
            </Button>
          )}
        />
      ) : conversations.length === 0 ? (
        <SystemState
          kind="empty"
          compact
          title="Chưa có cuộc trò chuyện nào"
          description="Các cuộc trò chuyện đã lưu sẽ xuất hiện tại đây sau khi bạn gửi câu hỏi đầu tiên."
        />
      ) : (
        <div className="assistant-thread-groups">
          <ThreadRows
            id="assistant-thread-today"
            label="Hôm nay"
            items={todayItems}
            conversationId={conversationId}
            onOpenConversation={onOpenConversation}
          />
          <ThreadRows
            id="assistant-thread-earlier"
            label="Trước đó"
            items={earlierItems}
            conversationId={conversationId}
            onOpenConversation={onOpenConversation}
          />
        </div>
      )}
    </div>
  );
}
