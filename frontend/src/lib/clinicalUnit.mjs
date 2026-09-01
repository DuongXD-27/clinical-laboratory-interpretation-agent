const SUPERSCRIPT = Object.freeze({
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
  "+": "⁺",
  "-": "⁻",
});

const ORDINARY = Object.freeze(
  Object.fromEntries(Object.entries(SUPERSCRIPT).map(([plain, raised]) => [raised, plain])),
);

const SUPERSCRIPT_SEQUENCE = /[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+/gu;
const PROTECTED_TEXT = /(```[\s\S]*?```|`[^`\n]*`|(?:https?:\/\/|www\.)[^\s<]+)/giu;

function exponentToSuperscript(exponent) {
  return Array.from(
    String(exponent).replace(/\s+/gu, "").replace("−", "-"),
    (character) => SUPERSCRIPT[character] ?? character,
  ).join("");
}

function superscriptToExponent(exponent) {
  return Array.from(String(exponent), (character) => ORDINARY[character] ?? character).join("");
}

function formatUnprotectedClinicalText(text) {
  return text
    .replace(
      /\b(\d+(?:[.,]\d+)?)(?:\s*[xX*×·]\s*|\s+)10\s*\^\s*([+\-−]?\s*\d+)\s*\/\s*[Ll]\b/gu,
      (_, value, exponent) => `${value} × 10${exponentToSuperscript(exponent)}/L`,
    )
    .replace(
      /(?<![A-Za-z0-9_])[xX*×·]\s*10\s*\^\s*([+\-−]?\s*\d+)\s*\/\s*[Ll]\b/gu,
      (_, exponent) => `× 10${exponentToSuperscript(exponent)}/L`,
    )
    .replace(
      /(?<![A-Za-z0-9_])10\s*\^\s*([+\-−]?\s*\d+)\s*\/\s*[Ll]\b/gu,
      (_, exponent) => `10${exponentToSuperscript(exponent)}/L`,
    );
}

/**
 * Presentation-only normalization for clinical prose and labels.
 *
 * Only the clinical power-of-ten-per-litre pattern is targeted. URLs and code
 * spans/fences are left byte-for-byte unchanged so ordinary math, identifiers,
 * Markdown and source links keep their original meaning.
 */
export function formatClinicalText(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .split(PROTECTED_TEXT)
    .map((segment, index) => index % 2 === 1 ? segment : formatUnprotectedClinicalText(segment))
    .join("");
}

/** Formats a standalone canonical unit without changing the stored/API value. */
export function formatClinicalUnit(unit) {
  if (unit === null || unit === undefined) return "";
  return formatClinicalText(String(unit).trim());
}

/**
 * Formats a unit placed directly after a numeric value. Scientific count units
 * receive the multiplication sign while ordinary units remain unchanged.
 */
export function formatClinicalUnitSuffix(unit) {
  const formatted = formatClinicalUnit(unit);
  if (!formatted) return "";
  if (/^×\s+10[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+\/L\b/u.test(formatted)) return formatted;
  if (/^10[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+\/L\b/u.test(formatted)) return `× ${formatted}`;
  return formatted;
}

/** Formats a complete value + unit pair for labels, tooltips and prose. */
export function formatClinicalValue(value, unit) {
  const displayValue = value === null || value === undefined ? "" : String(value);
  const displayUnit = formatClinicalUnitSuffix(unit);
  return [displayValue, displayUnit].filter(Boolean).join(" ");
}

/**
 * Maps the Unicode presentation used by editable unit fields back to the
 * canonical caret form expected by existing API/OCR contracts.
 */
export function canonicalizeClinicalUnitInput(value) {
  if (value === null || value === undefined) return "";
  const restoredExponent = String(value).replace(
    new RegExp(`10(${SUPERSCRIPT_SEQUENCE.source})`, "gu"),
    (_, exponent) => `10^${superscriptToExponent(exponent)}`,
  );
  return restoredExponent
    .replace(/^\s*[xX*×·]\s*(?=10\s*\^)/u, "")
    .replace(/10\s*\^\s*([+\-−]?\s*\d+)\s*\/\s*[Ll]\b/gu, (_, exponent) => (
      `10^${String(exponent).replace(/\s+/gu, "").replace("−", "-")}/L`
    ));
}
