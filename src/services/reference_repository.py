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


class ReferenceRepositoryError(Exception):
    """Raised when reference checker configuration or runtime rules are unusable."""


@dataclass(frozen=True)
class ReferenceLookupResult:
    matched: bool
    rule: dict[str, Any] | None
    canonical_analyte: str | None
    reason: str | None


@dataclass(frozen=True)
class AgeRange:
    min_age: Decimal
    max_age: Decimal


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
        self.analyte_aliases = MappingProxyType(
            {
                self._alias_key(alias): str(canonical).strip()
                for alias, canonical in config_copy["analyte_aliases"].items()
            }
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
        self.unit_map_aliases = MappingProxyType(
            {
                str(analyte).strip(): str(unit_name).strip()
                for analyte, unit_name in config_copy.get("unit_map_aliases", {}).items()
            }
        )
        self._rules = tuple(rules_copy)
        self._rules_by_analyte = self._index_rules(self._rules)

        requested_approved = {str(item).strip() for item in config_copy["approved_analytes"]}
        explicit_pending = {str(item).strip() for item in config_copy["pending_analytes"]}
        unit_conflicts = self._find_unit_conflicts(requested_approved, unit_rows_copy)

        self.unit_conflict_analytes = frozenset(unit_conflicts)
        self.approved_analytes = frozenset(requested_approved - unit_conflicts)
        self.pending_analytes = frozenset(explicit_pending | unit_conflicts)

        if not self.approved_analytes:
            raise ReferenceRepositoryError("no approved analytes remain after unit validation")

    @classmethod
    def from_default_files(cls) -> "ReferenceRepository":
        root = cls.default_repo_root()
        return cls.from_files(
            config_path=root / "data/reference/reference_checker_v2_config.json",
            ranges_path=root / "data/reference/reference_ranges_v2.json",
            units_path=root / "data/reference/units_metric.csv",
        )

    @classmethod
    def from_files(
        cls,
        *,
        config_path: str | Path,
        ranges_path: str | Path,
        units_path: str | Path | None = None,
    ) -> "ReferenceRepository":
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
        return cls(config=config, rules=rules, unit_rows=unit_rows)

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
            unit_key = self.unit_map_aliases.get(analyte, analyte)
            expected_unit = unit_map.get(unit_key)
            ri_units = {
                self._rule_unit(rule)
                for rule in self._rules_by_analyte.get(analyte, ())
                if self._norm_text(rule.get("reference_type")) in self.allowed_reference_types
            }
            ri_units.discard(None)
            if not expected_unit or not ri_units or ri_units != {expected_unit}:
                conflicts.add(analyte)
        return conflicts

    def select_rule(
        self,
        *,
        analyte: str,
        unit: str,
        patient_gender: str,
        patient_age: int | float | None,
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
        candidates = [rule for rule in candidates if self._rule_unit(rule) == input_unit]
        if not candidates:
            return self._miss(canonical, "unit_not_supported")

        patient_age_decimal = self._parse_patient_age(patient_age)
        age_candidates = []
        if patient_age_decimal is not None:
            for rule in candidates:
                age_range = self.parse_age_scope(rule.get("age_scope"))
                if age_range and age_range.min_age <= patient_age_decimal <= age_range.max_age:
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
            return self._miss(canonical, "ambiguous_reference_rule")

        return ReferenceLookupResult(
            matched=True,
            rule=deepcopy(sex_candidates[0]),
            canonical_analyte=canonical,
            reason=None,
        )

    def resolve_analyte(self, analyte: str) -> str | None:
        return self.analyte_aliases.get(self._alias_key(analyte))

    def parse_age_scope(self, value: Any) -> AgeRange | None:
        text = str(value or "").strip()
        if not text:
            return None
        alias = self.age_scope_aliases.get(self._alias_key(text))
        if alias:
            return alias

        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*", text)
        if not match:
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
            "G/L": "10^9/L",
            "T/L": "10^12/L",
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
        return str(value or "").strip().lower()

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
