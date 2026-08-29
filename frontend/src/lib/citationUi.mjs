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
  return [citation?.publication_date, citation?.section_or_context]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join(" · ");
}

export function uniqueCitations(citations = []) {
  const seen = new Set();
  return citations.filter((citation) => {
    const sourceId = String(citation?.source_id || "").trim();
    const fallback = [citation?.url, citation?.organization, citation?.title]
      .map((value) => String(value || "").trim().toLowerCase())
      .join("|");
    const key = sourceId || fallback;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function uniqueSourceUrls(sources = []) {
  const seen = new Set();
  return sources.filter((source) => {
    const key = String(source || "").trim().toLowerCase().replace(/\/$/, "");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
