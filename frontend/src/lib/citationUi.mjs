import { sourceHostname } from "./patientUi.mjs";

const PUBLIC_SOURCE_NAMES = Object.freeze({
  "medlineplus.gov": "MedlinePlus",
  "tapchiyhocvietnam.vn": "Tạp chí Y học Việt Nam",
  "nhathuoclongchau.com.vn": "Nhà thuốc Long Châu",
  "vinmec.com": "Vinmec",
});

export function publicSourceLabel(source) {
  const sourceName = String(source?.source_name || source?.organization || "").trim();
  const title = String(source?.title || "").trim();
  const url = typeof source === "string" ? source : String(source?.url || "");
  if (sourceName) return sourceName;
  if (title) return title;
  const hostname = sourceHostname(url);
  return PUBLIC_SOURCE_NAMES[hostname] || hostname;
}

export function citationLabel(citation) {
  return publicSourceLabel(citation);
}

export function citationContext(citation) {
  return String(citation?.section_or_context || "").trim();
}
