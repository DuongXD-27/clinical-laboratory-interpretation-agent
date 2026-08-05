"""
H-01 through H-15 documentation validation tests for P-056 V2 Tuan handoff.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HANDOFF_DIR = Path(__file__).parents[2] / "docs" / "version-handoff"
MANIFEST_PATH = HANDOFF_DIR / "v2_tuan_delivery_manifest.json"
HANDOFF_PATH = HANDOFF_DIR / "version-2-tuan-handoff.md"
PR_PATH = HANDOFF_DIR / "PULL_REQUEST_TUAN_V2.md"
RAGAS_JSON = Path(__file__).parents[2] / "eval" / "results" / "ragas_v2_baseline.json"

TOLERANCE = 1e-6

APPROVED_ANALYTES = {"WBC", "RBC", "Fasting plasma glucose", "Creatinine"}
PENDING_ANALYTES = {"HGB", "HbA1c", "LDL-C", "HDL-C", "Potassium"}
ALL_ANALYTES = APPROVED_ANALYTES | PENDING_ANALYTES

FORBIDDEN_PHRASES = [
    "production ready",
    "clinically validated",
    "all nine analytes supported",
    "all analytes approved",
    "all 9 analytes",
]

# H-01: Required artifacts exist
def test_H01_required_artifacts_exist():
    assert HANDOFF_PATH.exists(), f"Missing: {HANDOFF_PATH}"
    assert PR_PATH.exists(), f"Missing: {PR_PATH}"
    assert MANIFEST_PATH.exists(), f"Missing: {MANIFEST_PATH}"


# H-02: Delivery manifest schema — all required top-level keys
def test_H02_manifest_schema():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    required_keys = [
        "project", "release", "owner_scope", "branch",
        "baseline_commit", "final_commit_before_handoff", "generated_at",
        "delivery_status", "reference_data", "analytes",
        "reference_checker", "critical_detector", "ragas",
        "tests", "protected_files", "known_limitations", "deviations",
    ]
    for key in required_keys:
        assert key in manifest, f"Missing top-level key: {key}"


# H-03: Exactly nine analytes
def test_H03_exact_analyte_inventory():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    analytes = manifest["analytes"]
    assert len(analytes) == 9, f"Expected 9 analytes, got {len(analytes)}"
    names = {a["analyte"] for a in analytes}
    assert names == ALL_ANALYTES, f"Analyte mismatch: {names} != {ALL_ANALYTES}"


# H-04: Exactly four approved analytes
def test_H04_approved_list():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    approved = {
        a["analyte"]
        for a in manifest["analytes"]
        if a["normal_reference_status"] == "approved"
    }
    assert approved == APPROVED_ANALYTES, f"Approved mismatch: {approved}"


# H-05: Exactly five pending analytes
def test_H05_pending_list():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    pending = {
        a["analyte"]
        for a in manifest["analytes"]
        if a["normal_reference_status"] == "pending"
    }
    assert len(pending) == 5, f"Expected 5 pending, got {len(pending)}: {pending}"
    assert pending == PENDING_ANALYTES, f"Pending mismatch: {pending}"


# H-06: Data counts — 80 = 58 + 22
def test_H06_data_counts():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ref = manifest["reference_data"]
    total = ref["input_rows"]
    accepted = ref["runtime_accepted_rows"]
    quarantined = ref["quarantined_rows"]
    assert total == 80, f"input_rows={total}"
    assert accepted == 58, f"runtime_accepted_rows={accepted}"
    assert quarantined == 22, f"quarantined_rows={quarantined}"
    assert total == accepted + quarantined, f"{total} != {accepted} + {quarantined}"


# H-07: Manifest RAGAS values agree with eval/results/ragas_v2_baseline.json
def test_H07_ragas_values_match_result_json():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    result = json.loads(RAGAS_JSON.read_text(encoding="utf-8"))

    m_ragas = manifest["ragas"]
    r_summary = result["summary"]

    assert abs(m_ragas["faithfulness_mean"] - r_summary["faithfulness"]["mean"]) <= TOLERANCE
    assert abs(m_ragas["context_precision_mean"] - r_summary["context_precision"]["mean"]) <= TOLERANCE
    assert abs(m_ragas["custom_hallucination_proxy_mean"] - r_summary["custom_hallucination_proxy"]["mean"]) <= TOLERANCE

    assert m_ragas["total_cases"] == result["dataset"]["total_cases"]
    assert m_ragas["metric_eligible_cases"] == r_summary["faithfulness"]["count"]
    assert m_ragas["not_applicable_cases"] == r_summary["faithfulness"]["not_applicable_count"]

    assert m_ragas["dataset_sha256"] == result["dataset"]["sha256"]
    assert m_ragas["provider"] == result["evaluator"]["provider"]
    assert m_ragas["model"] == result["evaluator"]["model"]
    assert m_ragas["ragas_version"] == result["evaluator"]["ragas_version"]


# H-08: No unsupported production/clinical claims in docs
def test_H08_no_production_claim():
    texts = [
        HANDOFF_PATH.read_text(encoding="utf-8").lower(),
        PR_PATH.read_text(encoding="utf-8").lower(),
        MANIFEST_PATH.read_text(encoding="utf-8").lower(),
    ]
    for phrase in FORBIDDEN_PHRASES:
        for text in texts:
            # Allow only when followed by a negation or explicitly negated context
            # Simple check: phrase must not appear without negation within 60 chars prior
            occurrences = [m.start() for m in re.finditer(re.escape(phrase), text)]
            for pos in occurrences:
                context_before = text[max(0, pos - 60): pos]
                negation_words = ["not", "no ", "never", "without", "isn't", "is not", "not a", "not be", "not for"]
                negated = any(neg in context_before for neg in negation_words)
                assert negated, (
                    f"Unsupported phrase found without negation: '{phrase}' "
                    f"context: '...{text[max(0,pos-30):pos+len(phrase)+20]}...'"
                )


# H-09: Curated-context limitation stated in both handoff and PR
def test_H09_curated_context_limitation():
    handoff = HANDOFF_PATH.read_text(encoding="utf-8").lower()
    pr = PR_PATH.read_text(encoding="utf-8").lower()
    marker = "curated fixture"
    assert marker in handoff, "Handoff does not state curated fixture limitation"
    assert marker in pr, "PR body does not state curated fixture limitation"


# H-10: All five pending analytes visible in limitations or pending sections
def test_H10_pending_analytes_visible():
    handoff = HANDOFF_PATH.read_text(encoding="utf-8")
    for analyte in PENDING_ANALYTES:
        assert analyte in handoff, f"Pending analyte '{analyte}' not mentioned in handoff"


# H-11: Protected architecture declaration in handoff and PR
def test_H11_protected_architecture_declaration():
    handoff = HANDOFF_PATH.read_text(encoding="utf-8").lower()
    pr = PR_PATH.read_text(encoding="utf-8").lower()
    for doc, name in [(handoff, "handoff"), (pr, "PR")]:
        assert "graph.py" in doc, f"{name} does not mention graph.py"
        assert "state.py" in doc, f"{name} does not mention state.py"


# H-12: No secret-shaped value in new documentation or JSON
def test_H12_security_safety():
    patterns = [
        r"AIza[0-9A-Za-z_\-]{20,}",
        r"sk-[0-9A-Za-z_\-]{20,}",
        r"Bearer\s+[0-9A-Za-z._\-]{10,}",
    ]
    for path in [MANIFEST_PATH, HANDOFF_PATH, PR_PATH]:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            m = re.search(pattern, text)
            assert m is None, f"Secret-shaped value found in {path.name}: pattern={pattern}"


# H-13: Each completed TIP has a real commit hash resolvable by Git
def test_H13_commit_references():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    tip_map = manifest.get("tip_commit_map", {})
    completed_tips = ["TIP-000", "TIP-001", "TIP-002A", "TIP-002B", "TIP-003", "TIP-004A", "TIP-004B"]
    for tip in completed_tips:
        assert tip in tip_map, f"{tip} not in tip_commit_map"
        commit_hash = tip_map[tip]
        assert commit_hash and commit_hash != "pending_commit", f"{tip} has no commit hash"
        result = subprocess.run(
            ["git", "cat-file", "-t", commit_hash],
            capture_output=True, text=True,
            cwd=Path(__file__).parents[2]
        )
        assert result.returncode == 0 and result.stdout.strip() == "commit", (
            f"{tip} commit {commit_hash} is not resolvable in Git"
        )


# H-14: Reproduction commands in handoff (reference builder, checker tests, full tests, RAGAS validate-only, RAGAS live)
def test_H14_reproduction_commands():
    handoff = HANDOFF_PATH.read_text(encoding="utf-8")
    markers = [
        "build_reference",
        "test_services",
        "--ignore=tests/test_embed.py",
        "--validate-only",
        "--live",
    ]
    for marker in markers:
        assert marker in handoff, f"Reproduction command marker '{marker}' not found in handoff"
    # Live command must not embed a key value
    assert "AIza" not in handoff, "Live command must not embed an API key"
    assert "GOOGLE_API_KEY=" not in handoff, "Live command must not hardcode GOOGLE_API_KEY value"


# H-15: DEV-004B-01 appears in manifest and handoff
def test_H15_deviation_visibility():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    deviation_ids = {d["id"] for d in manifest.get("deviations", [])}
    assert "DEV-004B-01" in deviation_ids, "DEV-004B-01 not in manifest deviations"

    handoff = HANDOFF_PATH.read_text(encoding="utf-8")
    assert "DEV-004B-01" in handoff, "DEV-004B-01 not mentioned in handoff"
