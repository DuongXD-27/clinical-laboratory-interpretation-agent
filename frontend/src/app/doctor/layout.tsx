import type { ReactNode } from "react";
import DoctorShell from "@/components/doctor/DoctorShell";

export default function DoctorLayout({ children }: { children: ReactNode }) {
  return <DoctorShell>{children}</DoctorShell>;
}
