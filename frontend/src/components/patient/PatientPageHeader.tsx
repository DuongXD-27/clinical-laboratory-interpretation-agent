import type { ReactNode } from "react";
import { PageHero } from "@/components/common/LayoutPrimitives";

type Props = {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
  titleId?: string;
  transitionName?: string;
};

export default function PatientPageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = "",
  titleId,
  transitionName,
}: Props) {
  return <PageHero eyebrow={eyebrow} title={title} description={description} actions={actions} titleId={titleId} className={className} transitionName={transitionName} />;
}
