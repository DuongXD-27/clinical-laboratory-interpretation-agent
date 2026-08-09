/**
 * Parse a reviewed laboratory value without treating an empty field as zero.
 *
 * @param {number | string} value
 * @returns {number | null}
 */
export function parseFiniteLabValue(value) {
  if (typeof value === "string" && value.trim() === "") {
    return null;
  }

  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Read OCR rows defensively. A successful response without rows must not make
 * the UI silently return to its idle state.
 *
 * @param {unknown} payload
 * @returns {Array<Record<string, unknown>>}
 */
export function getOcrIndicators(payload) {
  if (!payload || typeof payload !== "object") return [];
  const indicators = payload.indicators;
  return Array.isArray(indicators) ? indicators : [];
}
