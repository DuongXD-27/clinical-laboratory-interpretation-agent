"use client";

import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { MessageCircle } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import ChatPanel from "@/components/patient/assistant/ChatPanel";
import { useOrchestratorChat } from "@/components/patient/assistant/useOrchestratorChat";
import {
  acknowledgeOrchestratorOnboarding,
  clearSession,
  UnauthorizedError,
  type Role,
} from "@/lib/api";
import { actionDestination, sanitizeSuggestedAction } from "@/lib/assistantActions.mjs";
import type { OrchestratorUiContext, SuggestedAction } from "@/types/orchestrator";

type Props = {
  role: Role;
};

function uiContextForPath(pathname: string, searchParams: URLSearchParams): OrchestratorUiContext {
  const reportMatch = pathname.match(/^\/patient\/(?:reports|history)\/([A-Za-z0-9_.%+-]+)$/);
  const isTrend = pathname.startsWith("/patient/trends");
  const analyteParam = searchParams.get("analyte");
  return {
    screen: "patient",
    view: pathname.startsWith("/patient/analysis")
      ? "analysis"
      : pathname.startsWith("/patient/history") || pathname.startsWith("/patient/reports")
        ? "history"
        : isTrend
          ? "trend"
          : "dashboard",
    ...(reportMatch ? { candidate_report_ref: reportMatch[1] } : {}),
    ...(isTrend && analyteParam ? { candidate_analyte: analyteParam } : {}),
  };
}

export default function AssistantWidget({ role }: Props) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const launcherRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [onboardingAccepted, setOnboardingAccepted] = useState(false);
  const [onboardingLoading, setOnboardingLoading] = useState(false);
  const [onboardingError, setOnboardingError] = useState<string | null>(null);
  const uiContext = useMemo(
    () => uiContextForPath(pathname, searchParams),
    [pathname, searchParams],
  );

  const onUnauthorized = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [router]);
  const onOnboardingRequired = useCallback(() => setOnboardingAccepted(false), []);

  // Chỉ bệnh nhân có hội thoại được lưu. Khách vẫn chat bình thường — hợp đồng
  // của chế độ khách là không lưu gì, và ở đây nó được tôn trọng bằng cách
  // không gọi API hội thoại, chứ không phải gọi rồi nuốt 403.
  const persistence = role === "patient";

  const {
    turns,
    requestActive,
    conversations,
    conversationId,
    loadingTranscript,
    openConversation,
    startNewChat,
    send,
    stop,
    retry,
  } = useOrchestratorChat({
    uiContext,
    persistence,
    onUnauthorized,
    onOnboardingRequired,
  });

  const closePanel = useCallback(() => {
    setOpen(false);
    requestAnimationFrame(() => launcherRef.current?.focus());
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      if (onboardingAccepted) composerRef.current?.focus();
      else panelRef.current?.querySelector<HTMLButtonElement>(".assistant-onboarding button")?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [onboardingAccepted, open]);

  useEffect(() => {
    if (!open || !mobile || !panelRef.current) return;
    document.body.classList.add("assistant-mobile-open");
    const panel = panelRef.current;
    const siblings = panel.parentElement
      ? [...panel.parentElement.children].filter(
          (element): element is HTMLElement => element !== panel && element instanceof HTMLElement,
        )
      : [];
    const previouslyInert = siblings.map((element) => [element, element.hasAttribute("inert")] as const);
    for (const [element] of previouslyInert) element.setAttribute("inert", "");
    return () => {
      document.body.classList.remove("assistant-mobile-open");
      for (const [element, inert] of previouslyInert) {
        if (!inert) element.removeAttribute("inert");
      }
    };
  }, [mobile, open]);

  async function acknowledge() {
    if (onboardingLoading) return;
    setOnboardingLoading(true);
    setOnboardingError(null);
    try {
      await acknowledgeOrchestratorOnboarding();
      setOnboardingAccepted(true);
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      setOnboardingError("Chưa thể ghi nhận xác nhận. Vui lòng thử lại.");
    } finally {
      setOnboardingLoading(false);
    }
  }

  function handlePanelKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closePanel();
      return;
    }
    if (!mobile || event.key !== "Tab" || !panelRef.current) return;
    const focusable = [...panelRef.current.querySelectorAll<HTMLElement>(
      'button:not([disabled]), textarea:not([disabled]), a[href], summary, [tabindex]:not([tabindex="-1"])',
    )].filter((element) => !element.hidden);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function runAction(action: SuggestedAction) {
    const safeAction = sanitizeSuggestedAction(action, role) as SuggestedAction | null;
    if (!safeAction) return;
    if (safeAction.action === "RETRY") {
      const latest = turns.at(-1);
      if (latest) void send(latest.userMessage);
      return;
    }
    const destination = actionDestination(safeAction, role);
    if (destination) {
      router.push(destination);
      closePanel();
    }
  }

  return (
    <>
      {!open ? (
        <button
          ref={launcherRef}
          type="button"
          className="assistant-launcher"
          aria-label={open ? "Đóng trợ lý AI" : "Mở trợ lý AI"}
          aria-expanded={open}
          aria-controls="patient-ai-assistant"
          onClick={() => setOpen(true)}
        >
          <MessageCircle aria-hidden="true" />
          <span className="assistant-launcher-label">Hỏi trợ lý</span>
        </button>
      ) : null}

      <ChatPanel
        open={open}
        mobile={mobile}
        role={role}
        panelRef={panelRef}
        composerRef={composerRef}
        onboardingAccepted={onboardingAccepted}
        onboardingLoading={onboardingLoading}
        onboardingError={onboardingError}
        turns={turns}
        requestActive={requestActive}
        conversations={conversations}
        conversationId={conversationId}
        loadingTranscript={loadingTranscript}
        persistence={persistence}
        onNewChat={() => void startNewChat()}
        onOpenConversation={(id) => void openConversation(id)}
        onClose={closePanel}
        onAcknowledge={() => void acknowledge()}
        onSend={(message) => void send(message)}
        onStop={stop}
        onRetry={(turnId) => void retry(turnId)}
        onAction={runAction}
        onPanelKeyDown={handlePanelKeyDown}
      />
    </>
  );
}
