import { sourceHostname } from "./patientUi.mjs";

export function citationLabel(citation) {
  const title = String(citation?.title || "").trim();
  const organization = String(citation?.organization || "").trim();
  if (organization && title) return `${organization} — ${title}`;
  return organization || title || sourceHostname(String(citation?.url || ""));
}

export function citationContext(citation) {
  return String(citation?.section_or_context || "").trim();
}
