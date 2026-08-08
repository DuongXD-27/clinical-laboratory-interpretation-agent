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
