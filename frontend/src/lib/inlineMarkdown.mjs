// Minimal, dependency-free inline markdown tokenizer for chat messages.
// Handles only **bold** and `code` — the two inline styles the App Help
// corpus (and other orchestrator responses) actually use. Not a general
// markdown parser: headings, links, lists etc. are left as plain text
// (line breaks already render via the `white-space: pre-wrap` CSS on the
// message bubble, so lists/numbered steps still look fine unstyled).

const INLINE_TOKEN_RE = /\*\*(.+?)\*\*|`([^`]+?)`/g;

export function tokenizeInlineMarkdown(text) {
  if (!text) return [];
  const tokens = [];
  let lastIndex = 0;
  let match;
  INLINE_TOKEN_RE.lastIndex = 0;
  while ((match = INLINE_TOKEN_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    if (match[1] !== undefined) {
      tokens.push({ type: "bold", value: match[1] });
    } else {
      tokens.push({ type: "code", value: match[2] });
    }
    lastIndex = INLINE_TOKEN_RE.lastIndex;
  }
  if (lastIndex < text.length) {
    tokens.push({ type: "text", value: text.slice(lastIndex) });
  }
  return tokens;
}
