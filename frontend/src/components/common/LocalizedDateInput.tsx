import type { ChangeEventHandler } from "react";
import { cn } from "@/lib/utils";

function formatVietnameseDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : "dd/mm/yyyy";
}

export default function LocalizedDateInput({
  id,
  value,
  onChange,
  ariaLabel,
  className,
}: {
  id: string;
  value: string;
  onChange: ChangeEventHandler<HTMLInputElement>;
  ariaLabel: string;
  className?: string;
}) {
  return (
    <span className="localized-date-control">
      <input
        id={id}
        aria-label={ariaLabel}
        type="date"
        lang="vi-VN"
        value={value}
        onChange={onChange}
        className={cn("localized-date-input", className)}
      />
      <span className="localized-date-display" aria-hidden="true">
        {formatVietnameseDate(value)}
      </span>
    </span>
  );
}
