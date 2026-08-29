import {
  AlertOctagon,
  AlertTriangle,
  Check,
  CheckCircle2,
  Circle,
  CircleHelp,
  Clock3,
  FileWarning,
  Info,
  MessageCircleQuestion,
  ScanSearch,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusFamily = "clinical" | "trust" | "workflow" | "interaction" | "system";
export type StatusLevel = "inline" | "soft" | "strong";
export type StatusState =
  | "normal" | "abnormal" | "critical" | "unknown"
  | "unverified" | "pending-verification" | "verified"
  | "pending" | "reviewing" | "processed" | "completed" | "cancelled" | "rejected" | "corrected" | "skipped"
  | "question" | "answered"
  | "ocr-review" | "input-review" | "unsupported" | "info" | "system-ok" | "system-warning" | "system-error";

type StatusConfig = {
  family: StatusFamily;
  label: string;
  tone: "critical" | "attention" | "positive" | "neutral" | "review" | "question";
  level: StatusLevel;
  icon: LucideIcon;
};

export const STATUS_CONFIG: Record<StatusState, StatusConfig> = {
  normal: { family: "clinical", label: "Bình thường", tone: "positive", level: "inline", icon: CheckCircle2 },
  abnormal: { family: "clinical", label: "Bất thường", tone: "attention", level: "soft", icon: AlertTriangle },
  critical: { family: "clinical", label: "Giá trị khẩn cấp", tone: "critical", level: "strong", icon: AlertOctagon },
  unknown: { family: "clinical", label: "Chưa phân loại", tone: "neutral", level: "inline", icon: CircleHelp },
  unverified: { family: "trust", label: "Chưa kiểm chứng", tone: "neutral", level: "inline", icon: Circle },
  "pending-verification": { family: "trust", label: "Đang chờ bác sĩ xem", tone: "review", level: "soft", icon: Clock3 },
  verified: { family: "trust", label: "Đã xác minh", tone: "positive", level: "inline", icon: CheckCircle2 },
  pending: { family: "workflow", label: "Chờ đánh giá", tone: "neutral", level: "inline", icon: Clock3 },
  reviewing: { family: "workflow", label: "Đang xử lý", tone: "review", level: "inline", icon: Clock3 },
  processed: { family: "workflow", label: "Đã xử lý", tone: "positive", level: "inline", icon: Check },
  completed: { family: "workflow", label: "Đã hoàn tất", tone: "positive", level: "inline", icon: CheckCircle2 },
  cancelled: { family: "workflow", label: "Đã hủy", tone: "neutral", level: "inline", icon: XCircle },
  rejected: { family: "workflow", label: "Từ chối", tone: "attention", level: "soft", icon: XCircle },
  corrected: { family: "workflow", label: "Đã đính chính", tone: "review", level: "inline", icon: Check },
  skipped: { family: "workflow", label: "Đã bỏ qua", tone: "neutral", level: "inline", icon: Circle },
  question: { family: "interaction", label: "Có câu hỏi", tone: "question", level: "soft", icon: MessageCircleQuestion },
  answered: { family: "interaction", label: "Đã trả lời", tone: "positive", level: "inline", icon: CheckCircle2 },
  "ocr-review": { family: "system", label: "OCR cần kiểm tra", tone: "review", level: "soft", icon: ScanSearch },
  "input-review": { family: "system", label: "Cần kiểm tra dữ liệu đầu vào", tone: "review", level: "soft", icon: FileWarning },
  unsupported: { family: "system", label: "Chưa được hỗ trợ", tone: "neutral", level: "inline", icon: Info },
  info: { family: "system", label: "Thông tin", tone: "neutral", level: "inline", icon: Info },
  "system-ok": { family: "system", label: "Thành công", tone: "positive", level: "inline", icon: CheckCircle2 },
  "system-warning": { family: "system", label: "Cảnh báo", tone: "attention", level: "soft", icon: AlertTriangle },
  "system-error": { family: "system", label: "Lỗi", tone: "critical", level: "soft", icon: AlertOctagon },
};

type Props = {
  state: StatusState;
  label?: React.ReactNode;
  level?: StatusLevel;
  icon?: LucideIcon;
  size?: "sm" | "md";
  className?: string;
};

export default function StatusIndicator({ state, label, level, icon, size = "sm", className }: Props) {
  const config = STATUS_CONFIG[state];
  const Icon = icon ?? config.icon;
  const resolvedLevel = level ?? config.level;

  return (
    <span
      className={cn(
        "status-indicator",
        `status-indicator--${config.family}`,
        `status-indicator--${config.tone}`,
        `status-indicator--${resolvedLevel}`,
        `status-indicator--${size}`,
        className,
      )}
      data-family={config.family}
      data-state={state}
    >
      <span className="status-indicator__glyph" aria-hidden="true">
        <Icon />
      </span>
      <span className="status-indicator__label">{label ?? config.label}</span>
    </span>
  );
}
