import { ArrowDownWideNarrow } from "lucide-react";
import type { ReactNode } from "react";

type Props = {
  filters: ReactNode;
  total: number;
  itemLabel: string;
  contextLabel: string;
};

export default function DoctorQueueToolbar({ filters, total, itemLabel, contextLabel }: Props) {
  return (
    <div className="doctor-queue-toolbar">
      <div className="doctor-queue-toolbar__filters">{filters}</div>
      <div className="doctor-queue-toolbar__context" aria-live="polite">
        <span className="doctor-queue-toolbar__total">
          <strong>{total}</strong> {itemLabel}
        </span>
        <span className="doctor-queue-toolbar__sort">
          <ArrowDownWideNarrow aria-hidden="true" />
          {contextLabel}
        </span>
      </div>
    </div>
  );
}
