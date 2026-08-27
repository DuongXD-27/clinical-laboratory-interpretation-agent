import assert from "node:assert/strict";
import test from "node:test";

import { citationContext, citationLabel } from "./citationUi.mjs";

test("citation label exposes organization and source title", () => {
  assert.equal(citationLabel({ organization: "WHO", title: "Laboratory guidance" }), "WHO — Laboratory guidance");
});

test("citation presentation falls back safely and keeps context separate", () => {
  const citation = { url: "https://example.org/guidance", section_or_context: "Table 2" };
  assert.equal(citationLabel(citation), "example.org");
  assert.equal(citationContext(citation), "Table 2");
});
