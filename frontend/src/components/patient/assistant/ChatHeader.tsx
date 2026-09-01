"use client";

import { History, Plus, X } from "lucide-react";

import { BrandMark } from "@/components/common/BrandSignature";
import { Button } from "@/components/ui/button";

type Props = {
  persistence: boolean;
  requestActive: boolean;
  contextLabel: string;
  view: "conversation" | "history";
  onNewChat: () => void;
  onHistory: () => void;
  onClose: () => void;
};

export default function ChatHeader({
  persistence,
  requestActive,
  contextLabel,
  view,
  onNewChat,
  onHistory,
  onClose,
}: Props) {
  return (
    <header className="assistant-header">
      <BrandMark className="assistant-header-mark" />
      <div className="assistant-header-copy">
        <div className="assistant-header-title-row">
          <h2 id="assistant-dialog-title">LumiLab Assistant</h2>
        </div>
        <div className="assistant-header-meta">
          <span className="assistant-status" data-active={requestActive ? "true" : "false"}>
            <i aria-hidden="true" />
            {requestActive ? "Đang hỗ trợ" : "Sẵn sàng"}
          </span>
          <span aria-hidden="true">·</span>
          <p id="assistant-dialog-subtitle">{contextLabel}</p>
        </div>
      </div>

      <div className="assistant-header-actions" aria-label="Điều khiển trò chuyện">
        <Button type="button" variant="ghost" size="sm" onClick={onNewChat}>
          <Plus data-icon="inline-start" aria-hidden="true" />
          <span>Chat mới</span>
        </Button>
        {persistence ? (
          <Button
            type="button"
            variant={view === "history" ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={view === "history"}
            onClick={onHistory}
          >
            <History data-icon="inline-start" aria-hidden="true" />
            <span>Lịch sử</span>
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="assistant-close"
          aria-label="Đóng trợ lý"
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </Button>
      </div>
    </header>
  );
}
