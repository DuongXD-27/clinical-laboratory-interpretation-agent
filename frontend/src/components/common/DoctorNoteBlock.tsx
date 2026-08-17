import { formatMoment } from "@/lib/patientUi.mjs";

type Props = {
  note: string;
  doctorName?: string | null;
  reviewedAt?: string | null;
};

export default function DoctorNoteBlock({ note, doctorName, reviewedAt }: Props) {
  return (
    <div className="doctor-note-block">
      <p className="doctor-note-block__label">Bác sĩ đính chính</p>
      <p className="doctor-note-block__content">{note}</p>
      {(doctorName || reviewedAt) && (
        <p className="doctor-note-block__meta">
          {doctorName || "Bác sĩ"}
          {reviewedAt ? ` · ${formatMoment(reviewedAt)}` : ""}
        </p>
      )}
    </div>
  );
}
