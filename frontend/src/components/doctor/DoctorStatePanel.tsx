import type { ReactNode } from "react";
import { SystemState } from "@/components/common/SystemState";

type Props = {
  kind: "loading" | "empty" | "error" | "not-found";
  title: string;
  description?: ReactNode;
  action?: ReactNode;
};

export default function DoctorStatePanel({ kind, title, description, action }: Props) {
  return (
    <section className="doctor-state-panel">
      <SystemState kind={kind} title={title} description={description} action={action} />
    </section>
  );
}
