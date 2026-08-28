from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any

from src.services.analyte_catalog import AnalyteCatalogContract, get_analyte_catalog_contract
from src.services.analyte_name_resolution import (
    SAFE_RUNTIME_ALIASES,
    AnalyteNameResolution,
    normalize_analyte_lookup_key,
    resolve_analyte_name,
)
from src.services.analyte_resolver import FROZEN_CLINICAL_RULE_BANDS, canonical_analyte_id
from src.services.measurement_conversion import (
    cholesterol_mg_dl_to_mmol_l,
    triglyceride_mg_dl_to_mmol_l,
)


class ReferenceRepositoryError(Exception):
    """Raised when reference checker configuration or runtime rules are unusable."""


@dataclass(frozen=True)
class ReferenceLookupResult:
    matched: bool
    rule: dict[str, Any] | None
    canonical_analyte: str | None
    reason: str | None
    comparison_value: Decimal | None = None
    comparison_unit: str | None = None


@dataclass(frozen=True)
class AgeRange:
    min_age: Decimal
    max_age: Decimal | None

    def contains(self, age: Decimal) -> bool:
        if age < self.min_age:
            return False
        return self.max_age is None or age <= self.max_age


class ReferenceRepository:
    REQUIRED_CONFIG_KEYS = {
        "config_version",
        "allowed_reference_types",
        "approved_analytes",
        "pending_analytes",
        "analyte_aliases",
    }
    REQUIRED_RULE_KEYS = {
        "analyte_canonical",
        "sex",
        "age_scope",
        "reference_type",
        "range_lower",
        "range_upper",
    }

    def __init__(
        self,
        *,
        config: dict[str, Any],
        rules: list[dict[str, Any]],
        unit_rows: list[dict[str, str]] | None = None,
        catalog_contract: AnalyteCatalogContract | None = None,
    ):
        self._validate_config(config)
        self._validate_rules(rules)

        config_copy = deepcopy(config)
        rules_copy = deepcopy(rules)
        unit_rows_copy = deepcopy(unit_rows or [])

        self.config_version = str(config_copy["config_version"])
        self.allowed_reference_types = frozenset(
            self._norm_text(value) for value in config_copy["allowed_reference_types"]
        )
        if catalog_contract is not None:
            self._validate_catalog_sync(config_copy, catalog_contract)
            requested_approved = set(catalog_contract.approved_names)
            alias_source = catalog_contract.runtime_alias_map()
            explicit_pending: set[str] = set()
        else:
            requested_approved = {str(item).strip() for item in config_copy["approved_analytes"]}
            alias_source = {
                str(alias).strip(): str(canonical).strip()
                for alias, canonical in config_copy["analyte_aliases"].items()
            }
            explicit_pending = {str(item).strip() for item in config_copy["pending_analytes"]}
        self._catalog_contract = catalog_contract
        effective_alias_source = dict(alias_source)
        for alias, canonical in SAFE_RUNTIME_ALIASES.items():
            if canonical not in requested_approved:
                continue
            effective_alias_source[alias] = canonical

        normalized_aliases: dict[str, str] = {}
        for alias, canonical in effective_alias_source.items():
            key = self._alias_key(alias)
            existing = normalized_aliases.get(key)
            if existing is not None and existing != canonical:
                raise ReferenceRepositoryError(
                    f"deterministic alias collision for {alias!r}: {existing!r} vs {canonical!r}"
                )
            normalized_aliases[key] = str(canonical).strip()
        self.analyte_aliases = MappingProxyType(normalized_aliases)
        aliases_by_canonical: dict[str, list[str]] = {}
        for alias, canonical in effective_alias_source.items():
            aliases_by_canonical.setdefault(str(canonical).strip(), []).append(str(alias).strip())
        self._aliases_by_canonical = MappingProxyType(
            {name: tuple(sorted(set(aliases), key=str.casefold)) for name, aliases in aliases_by_canonical.items()}
        )
        self.trend_max_gap_days = self._load_trend_gap_policy(
            config_copy.get("trend_max_gap_days"),
            requested_approved=requested_approved,
        )
        self.age_scope_aliases = MappingProxyType(
            {
                self._alias_key(alias): AgeRange(
                    min_age=Decimal(str(bounds["min_age"])),
                    max_age=Decimal(str(bounds["max_age"])),
                )
                for alias, bounds in config_copy.get("age_scope_aliases", {}).items()
            }
        )
        self._rules = tuple(rules_copy)
        self._rules_by_analyte = self._index_rules(self._rules)

        unit_conflicts = self._find_unit_conflicts(requested_approved, unit_rows_copy)

        self.unit_conflict_analytes = frozenset(unit_conflicts)
        self.approved_analytes = frozenset(requested_approved - unit_conflicts)
        self.pending_analytes = frozenset(explicit_pending | unit_conflicts)

        if not self.approved_analytes:
            raise ReferenceRepositoryError("no approved analytes remain after unit validation")

    @staticmethod
    def _validate_catalog_sync(
        config: dict[str, Any],
        catalog_contract: AnalyteCatalogContract,
    ) -> None:
        config_approved = {str(item).strip() for item in config["approved_analytes"]}
        catalog_approved = set(catalog_contract.approved_names)
        if config_approved != catalog_approved:
            raise ReferenceRepositoryError("reference_checker_config approved_analytes drift from analyte_catalog")

        config_aliases = {
            str(alias).strip(): str(canonical).strip() for alias, canonical in config["analyte_aliases"].items()
        }
        catalog_aliases = catalog_contract.runtime_alias_map()
        if config_aliases != catalog_aliases:
            raise ReferenceRepositoryError("reference_checker_config analyte_aliases drift from analyte_catalog")

        config_holds = {
            str(name).strip()
            for name, metadata in config.get("hold_analytes", {}).items()
            if isinstance(metadata, dict) and str(metadata.get("status", "")).strip().upper() == "HOLD"
        }
        catalog_holds = {entry.canonical_name for entry in catalog_contract.entries if entry.runtime_status == "HOLD"}
        if config_holds != catalog_holds:
            raise ReferenceRepositoryError("reference_checker_config hold_analytes drift from analyte_catalog")

    @staticmethod
    def _load_trend_gap_policy(
        raw_policy: Any,
        *,
        requested_approved: set[str],
    ) -> MappingProxyType:
        """Read the optional config-only maximum interval between trend points.

        Omitting the key is backwards-compatible and means no limit for every
        approved analyte.  When supplied it must explicitly cover the complete
        approved catalog, preventing a silent default for a newly added analyte.
        """
        if raw_policy is None:
            return MappingProxyType({name: None for name in requested_approved})
        if not isinstance(raw_policy, dict) or set(raw_policy) != requested_approved:
            raise ReferenceRepositoryError("trend_max_gap_days must declare exactly the approved analytes")
        normalized: dict[str, int | None] = {}
        for analyte, value in raw_policy.items():
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
                raise ReferenceRepositoryError(f"trend_max_gap_days for {analyte} must be a positive integer or null")
            normalized[analyte] = value
        return MappingProxyType(normalized)

    @classmethod
    def from_default_files(cls) -> ReferenceRepository:
        root = cls.default_repo_root()
        return cls.from_files(
            config_path=root / "data/reference/reference_checker_config.json",
            ranges_path=root / "data/reference/reference_ranges.json",
            units_path=root / "data/reference/units_metric.csv",
            catalog_contract=get_analyte_catalog_contract(),
        )

    @classmethod
    def from_files(
        cls,
        *,
        config_path: str | Path,
        ranges_path: str | Path,
        units_path: str | Path | None = None,
        catalog_contract: AnalyteCatalogContract | None = None,
    ) -> ReferenceRepository:
        config_file = Path(config_path)
        ranges_file = Path(ranges_path)
        units_file = Path(units_path) if units_path is not None else None

        config = cls._load_json_file(config_file, "config")
        rules = cls._load_json_file(ranges_file, "runtime ranges")
        if not isinstance(config, dict):
            raise ReferenceRepositoryError("config JSON must be an object")
        if not isinstance(rules, list):
            raise ReferenceRepositoryError("runtime ranges JSON must be a list")

        unit_rows = cls._load_units_file(units_file) if units_file else []
        return cls(
            config=config,
            rules=rules,
            unit_rows=unit_rows,
            catalog_contract=catalog_contract,
        )

    @staticmethod
    def default_repo_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _load_json_file(cls, path: Path, label: str) -> Any:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError as exc:
            raise ReferenceRepositoryError(f"missing {label} file: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ReferenceRepositoryError(f"invalid {label} JSON: {path}") from exc

    @classmethod
    def _load_units_file(cls, path: Path | None) -> list[dict[str, str]]:
        if path is None:
            return []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                return list(csv.DictReader(file))
        except FileNotFoundError as exc:
            raise ReferenceRepositoryError(f"missing units file: {path}") from exc

    @classmethod
    def _validate_config(cls, config: dict[str, Any]) -> None:
        missing = cls.REQUIRED_CONFIG_KEYS - set(config)
        if missing:
            raise ReferenceRepositoryError(f"config missing required keys: {', '.join(sorted(missing))}")
        if not isinstance(config["allowed_reference_types"], list):
            raise ReferenceRepositoryError("allowed_reference_types must be a list")
        if not isinstance(config["approved_analytes"], list):
            raise ReferenceRepositoryError("approved_analytes must be a list")
        if not isinstance(config["pending_analytes"], list):
            raise ReferenceRepositoryError("pending_analytes must be a list")
        if not isinstance(config["analyte_aliases"], dict):
            raise ReferenceRepositoryError("analyte_aliases must be an object")

    @classmethod
    def _validate_rules(cls, rules: list[dict[str, Any]]) -> None:
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ReferenceRepositoryError(f"runtime rule at index {index} must be an object")
            missing = cls.REQUIRED_RULE_KEYS - set(rule)
            if missing:
                raise ReferenceRepositoryError(
                    f"runtime rule at index {index} missing required keys: {', '.join(sorted(missing))}"
                )
            if cls._parse_bound(rule.get("range_lower")) is None and cls._parse_bound(rule.get("range_upper")) is None:
                raise ReferenceRepositoryError(f"runtime rule at index {index} has no usable bounds")

    @staticmethod
    def _index_rules(rules: tuple[dict[str, Any], ...]) -> dict[str, tuple[dict[str, Any], ...]]:
        indexed: dict[str, list[dict[str, Any]]] = {}
        for rule in rules:
            indexed.setdefault(str(rule.get("analyte_canonical", "")).strip(), []).append(rule)
        return {key: tuple(value) for key, value in indexed.items()}

    def _find_unit_conflicts(
        self,
        requested_approved: set[str],
        unit_rows: list[dict[str, str]],
    ) -> set[str]:
        if not unit_rows:
            return set()

        unit_map = {
            str(row.get("test_name", "")).strip(): self.normalize_unit(row.get("standardized_unit", ""))
            for row in unit_rows
        }
        conflicts: set[str] = set()
        for analyte in requested_approved:
            expected_unit = unit_map.get(analyte)
            analyte_rules = self._rules_by_analyte.get(analyte, ())
            analyte_units = {self._rule_unit(rule) for rule in analyte_rules}
            analyte_units.discard(None)
            if not expected_unit or not analyte_units or analyte_units != {expected_unit}:
                conflicts.add(analyte)
        return conflicts

    def aliases_for(self, canonical_analyte: str) -> tuple[str, ...]:
        """Declared input aliases for one canonical analyte."""
        return self._aliases_by_canonical.get(canonical_analyte, ())

    def canonical_unit_for(self, canonical_analyte: str) -> str | None:
        """Return the sole approved RI unit, or ``None`` if it is not unique."""
        units = {
            self._rule_unit(rule)
            for rule in self._rules_by_analyte.get(canonical_analyte, ())
            if self._norm_text(rule.get("reference_type")) in self.allowed_reference_types
        }
        units.discard(None)
        return next(iter(units)) if len(units) == 1 else None

    def select_rule(
        self,
        *,
        analyte: str,
        unit: str,
        patient_gender: str,
        patient_age: int | float | None,
        value: Any = None,
    ) -> ReferenceLookupResult:
        canonical = self.resolve_analyte(analyte)
        if canonical is None:
            return self._miss(None, "analyte_not_supported")
        if canonical in self.unit_conflict_analytes:
            return self._miss(canonical, "unit_data_conflict")
        if canonical in self.pending_analytes or canonical not in self.approved_analytes:
            return self._miss(canonical, "analyte_not_approved")

        candidates = list(self._rules_by_analyte.get(canonical, ()))
        if not candidates:
            return self._miss(canonical, "analyte_not_approved")

        candidates = [
            rule for rule in candidates if self._norm_text(rule.get("reference_type")) in self.allowed_reference_types
        ]
        if not candidates:
            return self._miss(canonical, "reference_type_not_supported")

        input_unit = self.normalize_unit(unit)
        exact_unit_candidates = [rule for rule in candidates if self._rule_unit(rule) == input_unit]
        comparison_value = None
        comparison_unit = None
        if exact_unit_candidates:
            candidates = exact_unit_candidates
        else:
            converted_value = None
            converted_unit = None
            converted_candidates = []
            for rule in candidates:
                rule_unit = self._rule_unit(rule)
                candidate_value = self._convert_input_for_rule(
                    canonical,
                    value,
                    input_unit,
                    rule_unit,
                )
                if candidate_value is not None:
                    converted_value = candidate_value
                    converted_unit = rule_unit
                    converted_candidates.append(rule)
            candidates = converted_candidates
            comparison_value = converted_value
            comparison_unit = converted_unit
        if not candidates:
            return self._miss(canonical, "unit_not_supported")

        patient_age_decimal = self._parse_patient_age(patient_age)
        age_candidates = []
        if patient_age_decimal is not None:
            for rule in candidates:
                age_range = self.parse_age_scope(rule.get("age_scope"))
                if age_range and age_range.contains(patient_age_decimal):
                    age_candidates.append(rule)
        if not age_candidates:
            return self._miss(canonical, "age_scope_not_supported")

        patient_sex = self.normalize_patient_gender(patient_gender)
        if patient_sex is None:
            return self._miss(canonical, "invalid_patient_gender")

        sex_candidates = self._select_sex_candidates(age_candidates, patient_sex)
        if not sex_candidates:
            return self._miss(canonical, "sex_scope_not_supported")
        if len(sex_candidates) > 1:
            ri_candidates = [r for r in sex_candidates if self._norm_text(r.get("reference_type")) == "RI"]
            if len(ri_candidates) == 1:
                sex_candidates = ri_candidates
            elif len(ri_candidates) > 1:
                return self._miss(canonical, "ambiguous_reference_rule")
            else:
                cdl_candidates = [
                    r for r in sex_candidates if self._norm_text(r.get("reference_type")) in {"CDL", "BAND"}
                ]
                if len(cdl_candidates) == 1:
                    sex_candidates = cdl_candidates
                else:
                    if canonical == "HDL-C":
                        baseline_cdl = [
                            r
                            for r in cdl_candidates
                            if r.get("range_lower") is not None and r.get("range_upper") is not None
                        ]
                    else:
                        baseline_cdl = [
                            r for r in cdl_candidates if r.get("range_lower") is None or r.get("range_lower") == 0
                        ]
                    if len(baseline_cdl) == 1:
                        sex_candidates = baseline_cdl
                    else:
                        return self._miss(canonical, "ambiguous_reference_rule")

        return ReferenceLookupResult(
            matched=True,
            rule=deepcopy(sex_candidates[0]),
            canonical_analyte=canonical,
            reason=None,
            comparison_value=comparison_value,
            comparison_unit=comparison_unit,
        )

    def resolve_band(
        self,
        *,
        analyte: str,
        value: float,
        unit: str,
        patient_gender: str | None = None,
        patient_age: int | float | None = None,
    ) -> str | None:
        """Resolve the deterministic band id consistent with the Reference Checker.

        GRQ-004 boundary-consistency contract: this method NEVER applies its own
        boundary algorithm. It reuses, verbatim:
        - ``select_rule`` — the exact row-selection helper the reference checker
          calls, so the matched baseline row (and its bounds/operators) is
          IDENTICAL to the one behind the checker's deterministic status;
        - the checker's own ``_classify`` and ``_parse_rule_bound``
          (lazy-imported, read-only) so comparison operators cannot drift.

        The frozen band vocabulary (``FROZEN_CLINICAL_RULE_BANDS``) supplies
        labels only. Selection rules:
        - checker semantic NORMAL -> the baseline row's own band;
        - checker semantic HIGH   -> the DEEPEST band segment above the baseline
          whose closed interval contains the value;
        - checker semantic LOW    -> the LOWEST band segment below the baseline
          whose closed interval contains the value;
        - a value inside a literal uncovered gap, any ambiguity (duplicate
          baseline rows, segment/band count mismatch), or any failure -> None
          (fail closed; caller keeps current behaviour, no band_note retrieval).
        """
        canonical = self.resolve_analyte(analyte)
        if canonical is None:
            return None
        bands = FROZEN_CLINICAL_RULE_BANDS.get(canonical_analyte_id(canonical))
        if not bands:
            return None

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None

        # Option A: exact same row selection as the authoritative checker.
        result = self.select_rule(
            analyte=analyte,
            unit=unit,
            patient_gender=patient_gender or "",
            patient_age=patient_age,
        )
        if not result.matched or not result.rule:
            return None

        # Option B: the checker's own classifier and bound parser.
        from src.agents.nodes.reference_range_checker_node import (
            _classify,
            _parse_rule_bound,
        )

        lower = _parse_rule_bound(result.rule.get("range_lower"))
        upper = _parse_rule_bound(result.rule.get("range_upper"))
        semantic = _classify(
            Decimal(str(numeric)),
            lower,
            upper,
            rule_type=result.rule.get("reference_type"),
            upper_operator=result.rule.get("upper_operator"),
        )
        if semantic not in {"low", "normal", "high"}:
            return None

        segments: list[tuple[float, float]] = []
        for segment_rule in self._rules_by_analyte.get(canonical, ()):
            if self._norm_text(segment_rule.get("reference_type")) not in {"CDL", "BAND"}:
                continue
            segment_lower = _parse_rule_bound(segment_rule.get("range_lower"))
            segment_upper = _parse_rule_bound(segment_rule.get("range_upper"))
            segments.append(
                (
                    float("-inf") if segment_lower is None else float(segment_lower),
                    float("inf") if segment_upper is None else float(segment_upper),
                )
            )
        segments.sort()
        if len(segments) != len(bands):
            return None

        baseline_lower = float("-inf") if lower is None else float(lower)
        baseline_upper = float("inf") if upper is None else float(upper)
        baseline_matches = [
            index
            for index, (segment_lower, segment_upper) in enumerate(segments)
            if segment_lower == baseline_lower and segment_upper == baseline_upper
        ]
        if len(baseline_matches) != 1:
            return None  # ambiguous baseline row identity: fail closed
        baseline_index = baseline_matches[0]

        def contains(index: int) -> bool:
            segment_lower, segment_upper = segments[index]
            return segment_lower <= numeric <= segment_upper

        if semantic == "normal":
            chosen_index = baseline_index
        elif semantic == "high":
            candidates = [index for index in range(baseline_index + 1, len(segments)) if contains(index)]
            if not candidates:
                return None
            chosen_index = max(candidates)
        else:  # low
            candidates = [index for index in range(0, baseline_index) if contains(index)]
            if not candidates:
                return None
            chosen_index = min(candidates)
        return bands[chosen_index]

    def resolve_analyte(self, analyte: str) -> str | None:
        return self.resolve_analyte_result(analyte).canonical_name

    def resolve_analyte_result(self, analyte: str) -> AnalyteNameResolution:
        """Return a structured exact, ambiguous, or unsupported outcome."""
        return resolve_analyte_name(analyte, self.analyte_aliases)

    def runtime_status_for(self, analyte: str) -> str | None:
        canonical = self.resolve_analyte(analyte)
        if self._catalog_contract is None:
            if canonical is None:
                return None
            if canonical in self.approved_analytes:
                return "APPROVED"
            if canonical in self.pending_analytes:
                return "HOLD"
            return None
        if canonical is not None:
            return self._catalog_contract.runtime_status_for(canonical)
        return self._catalog_contract.runtime_status_for(analyte)

    def parse_age_scope(self, value: Any) -> AgeRange | None:
        text = str(value or "").strip()
        if not text:
            return None
        alias = self.age_scope_aliases.get(self._alias_key(text))
        if alias:
            return alias

        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*", text)
        if not match:
            match = re.fullmatch(r"\s*(?:>=|≥)\s*(\d+(?:\.\d+)?)\s*", text)
            if match:
                return AgeRange(min_age=Decimal(match.group(1)), max_age=None)
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*\+\s*", text)
            if match:
                return AgeRange(min_age=Decimal(match.group(1)), max_age=None)
            return None
        min_age = Decimal(match.group(1))
        max_age = Decimal(match.group(2))
        if min_age > max_age:
            return None
        return AgeRange(min_age=min_age, max_age=max_age)

    @classmethod
    def normalize_unit(cls, value: Any) -> str:
        text = str(value or "").strip()
        unit_aliases = {
            "×10^9/L": "10^9/L",
            "10^9/L": "10^9/L",
            "10^3/uL": "10^9/L",
            "10^3/µL": "10^9/L",
            "10^3/μL": "10^9/L",
            "×10^12/L": "10^12/L",
            "10^12/L": "10^12/L",
            "µmol/L": "umol/L",
            "μmol/L": "umol/L",
            "umol/L": "umol/L",
            "µmol/l": "umol/L",
            "μmol/l": "umol/L",
            "umol/l": "umol/L",
            "mmol/l": "mmol/L",
            "mmol/L": "mmol/L",
            "G/L": "10^9/L",
            "T/L": "10^12/L",
            "U/l": "U/L",
            "u/l": "U/L",
            "U/L": "U/L",
            "%CV": "%",
            "%cv": "%",
        }
        return unit_aliases.get(text, text)

    @classmethod
    def normalize_patient_gender(cls, value: Any) -> str | None:
        text = cls._alias_key(value)
        if text in {"male", "nam", "m"}:
            return "M"
        if text in {"female", "nữ", "nu", "f"}:
            return "F"
        if text in {"other", "a", "all", "any"}:
            return "A"
        return None

    @staticmethod
    def _alias_key(value: Any) -> str:
        return normalize_analyte_lookup_key(value)

    @staticmethod
    def _norm_text(value: Any) -> str:
        return str(value or "").strip().upper()

    @classmethod
    def _parse_bound(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    @classmethod
    def _parse_patient_age(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    def _rule_unit(self, rule: dict[str, Any]) -> str | None:
        raw_unit = rule.get("unit_canonical") or rule.get("unit_display_vn") or rule.get("unit_machine")
        unit = self.normalize_unit(raw_unit)
        return unit or None

    @classmethod
    def _convert_input_for_rule(
        cls,
        canonical_analyte: str,
        value: Any,
        input_unit: str,
        rule_unit: str | None,
    ) -> Decimal | None:
        if value is None or rule_unit is None:
            return None
        if input_unit != "mg/dL" or rule_unit != "mmol/L":
            return None
        try:
            if canonical_analyte in {"Total cholesterol", "HDL-C", "LDL-C"}:
                return cholesterol_mg_dl_to_mmol_l(value)
            if canonical_analyte == "Triglyceride":
                return triglyceride_mg_dl_to_mmol_l(value)
        except (TypeError, ValueError):
            return None
        return None

    @classmethod
    def _rule_sex(cls, rule: dict[str, Any]) -> str | None:
        text = cls._norm_text(rule.get("sex"))
        if text in {"M", "F", "A"}:
            return text
        return None

    def _select_sex_candidates(self, candidates: list[dict[str, Any]], patient_sex: str) -> list[dict[str, Any]]:
        if patient_sex in {"M", "F"}:
            exact = [rule for rule in candidates if self._rule_sex(rule) == patient_sex]
            if exact:
                return exact
            return [rule for rule in candidates if self._rule_sex(rule) == "A"]
        return [rule for rule in candidates if self._rule_sex(rule) == "A"]

    @staticmethod
    def _miss(canonical_analyte: str | None, reason: str) -> ReferenceLookupResult:
        return ReferenceLookupResult(
            matched=False,
            rule=None,
            canonical_analyte=canonical_analyte,
            reason=reason,
        )
