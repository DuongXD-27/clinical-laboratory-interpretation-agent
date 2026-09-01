"use client";

import { Activity, FileText, MessageSquareText, Stethoscope } from "lucide-react";

import { BrandMark } from "@/components/common/BrandSignature";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

const starterPrompts = [
  { label: "Giải thích chỉ số bất thường", icon: Activity },
  { label: "Tóm tắt phiếu xét nghiệm này", icon: FileText },
  { label: "Gợi ý câu hỏi để hỏi bác sĩ", icon: Stethoscope },
  { label: "Xem xu hướng gần đây", icon: MessageSquareText },
] as const;

export default function ChatEmptyState({
  contextLabel,
  onPrompt,
}: {
  contextLabel: string;
  onPrompt: (prompt: string) => void;
}) {
  return (
    <Empty className="assistant-empty-state">
      <EmptyHeader>
        <EmptyMedia className="assistant-empty-mark">
          <BrandMark />
        </EmptyMedia>
        <p className="assistant-empty-kicker">Trợ lý lâm sàng cá nhân</p>
        <EmptyTitle>Chào bạn, mình có thể hỗ trợ điều gì?</EmptyTitle>
        <EmptyDescription>
          Mình giúp diễn giải kết quả hiện có bằng ngôn ngữ dễ hiểu và chuẩn bị
          câu hỏi cho bác sĩ; không thay thế chẩn đoán y khoa.
        </EmptyDescription>
      </EmptyHeader>
      <p className="assistant-context-note">{contextLabel}</p>
      <EmptyContent className="assistant-starters" aria-label="Gợi ý bắt đầu">
        {starterPrompts.map(({ label, icon: Icon }) => (
          <Button key={label} type="button" variant="outline" size="sm" onClick={() => onPrompt(label)}>
            <Icon data-icon="inline-start" aria-hidden="true" />
            <span>{label}</span>
          </Button>
        ))}
      </EmptyContent>
    </Empty>
  );
}
