"use client";

import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { BrandMark } from "@/components/common/BrandSignature";
import ChatPanel from "@/components/patient/assistant/ChatPanel";
import { useOrchestratorChat } from "@/components/patient/assistant/useOrchestratorChat";
import {
  acknowledgeOrchestratorOnboarding,
  clearSession,
  UnauthorizedError,
  type Role,
} from "@/lib/api";
import { actionDestination, sanitizeSuggestedAction } from "@/lib/assistantActions.mjs";
import { MOTION_DURATIONS, type AssistantVisibility } from "@/lib/motion";
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

function contextLabelForUiContext(context: OrchestratorUiContext) {
  if (context.candidate_report_ref) return "Đang hỗ trợ dựa trên phiếu hiện tại";
  if (context.view === "trend" && context.candidate_analyte) {
    return `Đang hỗ trợ dựa trên xu hướng ${context.candidate_analyte}`;
  }
  if (context.view === "trend") return "Đang hỗ trợ dựa trên xu hướng gần đây";
  if (context.view === "analysis") return "Đang hỗ trợ tại màn hình phân tích";
  if (context.view === "history") return "Đang hỗ trợ tại lịch sử xét nghiệm";
  return "Hỗ trợ hiểu kết quả xét nghiệm của bạn";
}

export default function AssistantWidget({ role }: Props) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const launcherRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const [visibility, setVisibility] = useState<AssistantVisibility>("closed");
  const [mobile, setMobile] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [onboardingAccepted, setOnboardingAccepted] = useState(false);
  const [onboardingLoading, setOnboardingLoading] = useState(false);
  const [onboardingError, setOnboardingError] = useState<string | null>(null);
  const uiContext = useMemo(
    () => uiContextForPath(pathname, searchParams),
    [pathname, searchParams],
  );
  const contextLabel = useMemo(() => contextLabelForUiContext(uiContext), [uiContext]);

  const onUnauthorized = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [router]);
  const onOnboardingRequired = useCallback(() => setOnboardingAccepted(false), []);
  const onOnboardingAccepted = useCallback(() => setOnboardingAccepted(true), []);

  const persistence = role === "patient";

  const {
    turns,
    requestActive,
    conversations,
    conversationId,
    loadingTranscript,
    loadingConversations,
    conversationListError,
    transcriptError,
    openConversation,
    refreshConversations,
    startNewChat,
    send,
    stop,
    retry,
  } = useOrchestratorChat({
    uiContext,
    persistence,
    onUnauthorized,
    onOnboardingRequired,
    onOnboardingAccepted,
  });

  const openPanel = useCallback(() => {
    setVisibility(reducedMotion ? "open" : "opening");
  }, [reducedMotion]);

  const closePanel = useCallback(() => {
    if (reducedMotion) {
      setVisibility("closed");
      requestAnimationFrame(() => launcherRef.current?.focus());
      return;
    }
    setVisibility("closing");
  }, [reducedMotion]);

  const handleAnimationEnd = useCallback((event: React.AnimationEvent<HTMLElement>) => {
    if (event.target !== panelRef.current) return;
    if (visibility === "opening") {
      setVisibility("open");
    } else if (visibility === "closing") {
      setVisibility("closed");
      requestAnimationFrame(() => launcherRef.current?.focus());
    }
  }, [visibility]);

  // Safety fallback timer if onAnimationEnd is skipped or suppressed
  useEffect(() => {
    if (visibility === "opening") {
      const timer = setTimeout(() => {
        setVisibility((current) => (current === "opening" ? "open" : current));
      }, MOTION_DURATIONS.chatOpen + 120);
      return () => clearTimeout(timer);
    }
    if (visibility === "closing") {
      const timer = setTimeout(() => {
        setVisibility((current) => {
          if (current === "closing") {
            requestAnimationFrame(() => launcherRef.current?.focus());
            return "closed";
          }
          return current;
        });
      }, MOTION_DURATIONS.chatClose + 120);
      return () => clearTimeout(timer);
    }
  }, [visibility]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      setReducedMotion(media.matches);
      if (!media.matches) return;
      setVisibility((current) => {
        if (current === "opening") return "open";
        if (current === "closing") {
          requestAnimationFrame(() => launcherRef.current?.focus());
          return "closed";
        }
        return current;
      });
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (visibility !== "open") return;
    const frame = requestAnimationFrame(() => {
      if (onboardingAccepted) composerRef.current?.focus();
      else panelRef.current?.querySelector<HTMLButtonElement>(".assistant-onboarding button")?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [onboardingAccepted, visibility]);

  const isPanelActive = visibility === "open" || visibility === "opening";

  useEffect(() => {
    if (!isPanelActive || !mobile || !panelRef.current) return;
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
  }, [isPanelActive, mobile]);

  async function acknowledge() {
    if (onboardingLoading) return;
    setOnboardingLoading(true);
    setOnboardingError(null);
    try {
      if (persistence && conversationId === null) {
        const createdId = await startNewChat();
        if (createdId === null) {
          setOnboardingError("Chưa thể bắt đầu cuộc trò chuyện. Vui lòng thử lại.");
          return;
        }
      }
      await acknowledgeOrchestratorOnboarding();
      setOnboardingAccepted(true);
    } catch (caught: unknown) {
      if (caught instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      const message =
        caught instanceof Error && caught.message
          ? caught.message
          : "Chưa thể ghi nhận xác nhận. Vui lòng thử lại.";
      setOnboardingError(message);
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
      router.push(destination, { transitionTypes: ["nav-route"] });
      closePanel();
    }
  }

  const open = visibility === "open" || visibility === "opening";
  const isLauncherVisible = visibility === "closed";

  return (
    <>
      {isLauncherVisible ? (
        <button
          ref={launcherRef}
          type="button"
          className="assistant-launcher"
          aria-label={open ? "Đóng trợ lý AI" : "Mở trợ lý AI"}
          aria-expanded={open}
          aria-controls="patient-ai-assistant"
          onClick={openPanel}
        >
          <BrandMark className="assistant-launcher-mark" />
          <span className="assistant-launcher-copy">
            <strong>Trợ lý Lumi</strong>
            <small><i aria-hidden="true" /> Sẵn sàng hỗ trợ</small>
          </span>
        </button>
      ) : null}

      <ChatPanel
          mobile={mobile}
          role={role}
          state={visibility}
          panelRef={panelRef}
          composerRef={composerRef}
          contextLabel={contextLabel}
          onboardingAccepted={onboardingAccepted}
          onboardingLoading={onboardingLoading}
          onboardingError={onboardingError}
          turns={turns}
          requestActive={requestActive}
          conversations={conversations}
          conversationId={conversationId}
          loadingTranscript={loadingTranscript}
          loadingConversations={loadingConversations}
          conversationListError={conversationListError}
          transcriptError={transcriptError}
          persistence={persistence}
          onNewChat={() => void startNewChat()}
          onOpenConversation={(id) => void openConversation(id)}
          onRefreshConversations={() => void refreshConversations()}
          onClose={closePanel}
          onAcknowledge={() => void acknowledge()}
          onSend={(message) => void send(message)}
          onStop={stop}
          onRetry={(turnId) => void retry(turnId)}
          onAction={runAction}
          onPanelKeyDown={handlePanelKeyDown}
          onAnimationEnd={handleAnimationEnd}
      />
    </>
  );
}
