import assert from "node:assert/strict";
import test from "node:test";

import { citationContext, citationLabel, publicSourceLabel } from "./citationUi.mjs";

test("citation label exposes organization and source title", () => {
  assert.equal(citationLabel({ organization: "WHO", title: "Laboratory guidance" }), "WHO");
});

test("citation presentation falls back safely and keeps context separate", () => {
  const citation = { url: "https://example.org/guidance", section_or_context: "Table 2" };
  assert.equal(citationLabel(citation), "example.org");
  assert.equal(citationContext(citation), "Table 2");
});

test("agent citations use public source labels and never an icon tag name", () => {
  assert.equal(publicSourceLabel({ source_name: "MedlinePlus", title: "WBC", url: "https://medlineplus.gov/lab-tests/white-blood-count-wbc/" }), "MedlinePlus");
  assert.equal(publicSourceLabel({ title: "Tạp chí Y học Việt Nam", url: "https://example.org/paper" }), "Tạp chí Y học Việt Nam");
  assert.equal(publicSourceLabel("https://nhathuoclongchau.com.vn/bai-viet/wbc.html"), "Nhà thuốc Long Châu");
  assert.notEqual(publicSourceLabel("https://medlineplus.gov/lab-tests/white-blood-count-wbc/"), "svg");
});
