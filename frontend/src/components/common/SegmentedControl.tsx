"use client";

import { cn } from "@/lib/utils";

type Option<T extends string> = {
  value: T;
  label: string;
  id?: string;
  controls?: string;
};

type Props<T extends string> = {
  value: T;
  options: readonly Option<T>[];
  onValueChange: (value: T) => void;
  ariaLabel: string;
  semantics?: "tabs" | "group";
  className?: string;
};

export default function SegmentedControl<T extends string>({
  value,
  options,
  onValueChange,
  ariaLabel,
  semantics = "group",
  className,
}: Props<T>) {
  const isTabs = semantics === "tabs";

  return (
    <div className={cn("segmented-control", className)} role={isTabs ? "tablist" : "group"} aria-label={ariaLabel}>
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            id={option.id}
            role={isTabs ? "tab" : undefined}
            aria-selected={isTabs ? active : undefined}
            aria-pressed={isTabs ? undefined : active}
            aria-controls={option.controls}
            tabIndex={isTabs ? (active ? 0 : -1) : undefined}
            className={cn("segmented-control__item", active && "is-active")}
            onClick={() => onValueChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
