"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
  useState,
} from "react";
import { ArrowUp, CircleStop } from "lucide-react";

import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { canSubmitMessage, composerKeyAction } from "@/lib/orchestratorChat.mjs";

type Props = {
  composerRef: RefObject<HTMLTextAreaElement | null>;
  onboardingAccepted: boolean;
  requestActive: boolean;
  onSend: (message: string) => void;
  onStop: () => void;
};

export default function ChatComposer({
  composerRef,
  onboardingAccepted,
  requestActive,
  onSend,
  onStop,
}: Props) {
  const [draft, setDraft] = useState("");

  function submitDraft() {
    if (!canSubmitMessage(draft, onboardingAccepted, requestActive)) return;
    const message = draft.trim();
    setDraft("");
    onSend(message);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submitDraft();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
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
    <form
      className="assistant-composer"
      data-state={requestActive ? "generating" : "idle"}
      aria-busy={requestActive}
      onSubmit={handleSubmit}
    >
      <label className="sr-only" htmlFor="assistant-message-input">
        Nhập tin nhắn cho trợ lý
      </label>
      <InputGroup className="assistant-composer-field">
        <InputGroupTextarea
          className="assistant-composer-input"
          ref={composerRef}
          id="assistant-message-input"
          name="assistant-message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          aria-describedby="assistant-composer-hint"
          placeholder={
            onboardingAccepted
              ? "Hỏi về kết quả xét nghiệm của bạn…"
              : "Vui lòng xác nhận phạm vi sử dụng trước"
          }
          disabled={!onboardingAccepted}
          rows={1}
          autoComplete="off"
        />
        <InputGroupAddon align="inline-end" className="assistant-composer-actions">
          {requestActive ? (
            <InputGroupButton
              type="button"
              variant="outline"
              size="icon-sm"
              className="assistant-send-stop"
              aria-label="Dừng phản hồi"
              onClick={onStop}
            >
              <CircleStop data-icon="inline-start" aria-hidden="true" />
            </InputGroupButton>
          ) : (
            <InputGroupButton
              type="submit"
              variant="default"
              size="icon-sm"
              className="assistant-send-stop"
              aria-label="Gửi tin nhắn"
              disabled={!canSubmitMessage(draft, onboardingAccepted, false)}
            >
              <ArrowUp data-icon="inline-start" aria-hidden="true" />
            </InputGroupButton>
          )}
        </InputGroupAddon>
      </InputGroup>
      <p id="assistant-composer-hint" className="assistant-composer-hint">
        Enter để gửi · Shift+Enter để xuống dòng
      </p>
    </form>
  );
}
