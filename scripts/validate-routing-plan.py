#!/usr/bin/env python3
"""Validate an Adaptive Agent Routing V2 JSON routing ledger.

This validator is intentionally read-only and uses only the Python standard
library. It checks declared structure and routing invariants; it cannot prove
model capability, sandbox enforcement, or task correctness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import re
import sys
import unicodedata
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "aar.routing-ledger.v2"
LEDGER_PHASES = {"planning", "active", "finalized"}
NODE_LIFECYCLE_STATES = {"planned", "dispatched", "completed", "dispatch_blocked"}
PROFILES = {"balanced", "latency", "economy", "quality"}
CHILD_POLICIES = {"adaptive", "luna_max_only"}
ECONOMY_EVALUATION_MODES = {"qualitative", "quantitative"}
ECONOMY_DELEGATION_DECISIONS = {"delegate", "keep_parent"}
ECONOMY_TIE_BREAKS = {"declared_order", "pair_key_lexicographic"}
ECONOMY_FORMULA_VERSION = "expected-total-cost-v1"
ECONOMY_DECIMAL_PLACES = 6
ECONOMY_QUANTUM = Decimal("0.000001")
ECONOMY_MAX_COST = 1_000_000_000_000_000.0
RETRY_KINDS = {"none", "transient", "substantive"}
METRIC_SOURCES = {"runtime", "local_telemetry", "community_prior", "none"}
ORCHESTRATION_STATES = {"manual_allowed", "ultra_owned", "unknown"}
FAMILIES = {"sol", "terra", "luna", "other", "unknown"}
PAIR_FAMILIES = FAMILIES - {"unknown"}
EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra", "unknown"}
PAIR_EFFORTS = EFFORTS - {"unknown"}
CHILD_EFFORTS = PAIR_EFFORTS - {"ultra"}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
POLICY_DENIED_EFFORTS = {
    "luna": frozenset({"low", "medium", "high"}),
    "terra": frozenset({"low", "medium"}),
}
WORK_CLASSES = {"structured", "general", "open", "critical"}
CLASS_RANK = {"structured": 0, "general": 1, "open": 2, "critical": 3}
RISKS = {"low", "medium", "high", "irreversible"}
CONTEXT_SCOPES = {"bounded", "repository", "cross_system", "unknown"}
ORACLES = {"deterministic", "strong", "weak", "none"}
ACCESS_MODES = {"read_only", "workspace_write", "external_write"}
ROLES = {
    "architect",
    "diagnostician",
    "explorer",
    "structured_operator",
    "implementer",
    "validator",
    "reviewer",
}
SELECTION_ORIGINS = {"automatic", "fallback", "inherited", "explicit_user"}
DISPATCH_MODES = {"explicit", "inherit_parent"}
RECEIPT_STATUSES = {"accepted", "rejected"}
CONFIRMATION_STATUSES = {
    "confirmed-explicit",
    "confirmed-inherited",
    "default-unresolved",
    "inherited-unresolved",
    "runtime-rejected",
    "fallback-confirmed",
}
RESULT_STATUSES = {"success", "partial", "blocked", "failed", "escalate"}
FAILURE_CLASSIFICATIONS = {
    "none",
    "transient",
    "missing_context",
    "bad_decomposition",
    "weak_oracle",
    "reasoning_failure",
    "scope_became_open",
    "permission_or_decision",
    "interrupted_partial_write",
    "runtime_unavailable",
    "runtime_receipt_mismatch",
    "model_effort_unresolved",
    "validation_failure",
}
FALLBACK_REASONS = {
    "unavailable",
    "policy_rejection",
    "validation_failure",
    "scope_change",
}
VALIDATION_KINDS = {
    "test",
    "compile",
    "schema",
    "diff",
    "command",
    "evidence_review",
    "render",
    "pre_state",
    "post_state",
    "external_state",
}
VALIDATION_PHASES = {"pre", "post"}
READ_ONLY_ENFORCEMENT = {"sandbox", "instruction_pre_post_check"}
NODE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
EXECUTOR_ID_RE = NODE_ID_RE
TASK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
FORK_TURNS_RE = re.compile(r"^(?:none|all|[1-9][0-9]*)$")
RECEIPT_REF_RE = re.compile(r"^spawn_agent:\S(?:.*\S)?$")
WRITE_POST_VALIDATION_KINDS = {
    "test",
    "compile",
    "schema",
    "diff",
    "command",
    "render",
    "post_state",
    "external_state",
}
CANONICAL_MODEL_ALIASES = {"gpt-5.6": "sol"}
LUNA_MAX_PAIR_KEY = ("gpt-5.6-luna", "luna", "max")


class DuplicateJSONKeyError(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(f"Duplicate JSON object key '{key}'.")
        result[key] = value
    return result


@dataclass
class Issue:
    code: str
    path: str
    message: str
    node_id: str | None = None
    related_node_ids: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.node_id is not None:
            data["node_id"] = self.node_id
        if self.related_node_ids:
            data["related_node_ids"] = list(self.related_node_ids)
        return data


def _sort_issues(issues: Iterable[Issue]) -> list[Issue]:
    return sorted(
        issues,
        key=lambda issue: (
            issue.code,
            issue.path,
            issue.node_id or "",
            issue.related_node_ids,
            issue.message,
        ),
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        # Python integers are always finite. Passing an arbitrarily large int
        # through math.isfinite first coerces it to float and may overflow.
        return True
    return isinstance(value, float) and math.isfinite(value)


def _decimal_places(value: int | float) -> int:
    exponent = Decimal(str(value)).as_tuple().exponent
    return max(0, -exponent)


def _economy_expected_total(value: dict[str, Any]) -> Decimal:
    decimal_value = lambda field: Decimal(str(value[field]))
    total = (
        decimal_value("initial_cost")
        + decimal_value("retry_probability") * decimal_value("retry_cost_if_triggered")
        + decimal_value("rework_probability") * decimal_value("rework_cost_if_triggered")
        + decimal_value("review_cost")
        + decimal_value("escalation_probability")
        * decimal_value("escalation_cost_if_triggered")
        + decimal_value("coordination_cost")
    )
    return total.quantize(ECONOMY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _pair_key(pair: Any) -> tuple[str, str, str] | None:
    if not isinstance(pair, dict):
        return None
    model = pair.get("model")
    family = pair.get("family")
    effort = pair.get("effort")
    if not all(isinstance(value, str) for value in (model, family, effort)):
        return None
    return model, family, effort


def _pair_text(pair: Any) -> str:
    key = _pair_key(pair)
    if key is None:
        return "unresolved"
    model, _, effort = key
    return f"{model} / {effort}"


def _model_task_slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")


def _expected_task_name(node_id: str, attempt_index: int, pair: dict[str, Any]) -> str:
    return f"{_model_task_slug(pair['model'])}_{pair['effort']}_{node_id}_a{attempt_index}"


def _expected_agent_label(role: str, pair: dict[str, Any]) -> str:
    return f"{role} ({pair['model']}, {pair['effort']})"


def _policy_denied(pair: Any) -> bool:
    key = _pair_key(pair)
    if key is None:
        return False
    _, family, effort = key
    return effort == "ultra" or effort in POLICY_DENIED_EFFORTS.get(family, ())


def _model_family_diagnostic(model: str, declared_family: str) -> str | None:
    """Return a diagnostic when a known-family slug is ambiguous or mislabeled."""
    lowered = model.strip().lower()
    alias_family = CANONICAL_MODEL_ALIASES.get(lowered)
    markers = {
        family
        for family in ("sol", "terra", "luna")
        if re.search(rf"(^|[^a-z]){family}([^a-z]|$)", lowered)
    }

    if alias_family is not None:
        if declared_family != alias_family:
            return f"Canonical model alias implies family '{alias_family}', not '{declared_family}'."
        return None
    if len(markers) > 1:
        return f"Model slug contains multiple family markers: {sorted(markers)}."
    if len(markers) == 1:
        marker = next(iter(markers))
        canonical_suffix = re.search(rf"(?:^|[-_.]){marker}$", lowered) is not None
        if not canonical_suffix:
            return f"Model slug contains non-canonical family marker '{marker}'."
        if declared_family != marker:
            return f"Model slug implies family '{marker}', not '{declared_family}'."
        return None
    if declared_family in {"sol", "terra", "luna"}:
        return f"Known family '{declared_family}' requires a canonical family suffix or registered alias."
    return None


def _surface_kind_and_value(surface: str) -> tuple[str, str]:
    raw = surface.strip().replace("\\", "/")
    is_drive_path = re.match(r"^[A-Za-z]:/", raw) is not None
    colon_index = raw.find(":")
    slash_index = raw.find("/")
    is_opaque = (
        not is_drive_path
        and colon_index >= 0
        and (slash_index < 0 or colon_index < slash_index)
        and not raw.startswith("./")
    )
    if is_opaque:
        return "opaque", raw.casefold()
    normalized = posixpath.normpath(raw)
    if normalized == ".":
        normalized = ""
    return "path", normalized.casefold().rstrip("/")


def _surfaces_overlap(left: str, right: str) -> bool:
    left_kind, left_value = _surface_kind_and_value(left)
    right_kind, right_value = _surface_kind_and_value(right)
    if left_kind != right_kind:
        return False
    if left_value == right_value:
        return True
    if left_kind == "opaque":
        return False
    if not left_value or not right_value:
        return True
    return left_value.startswith(f"{right_value}/") or right_value.startswith(f"{left_value}/")


def _derived_contract_floors(node: dict[str, Any]) -> tuple[str, str, str]:
    work_class = node["work_class"]
    risk = node["risk"]
    if risk in {"high", "irreversible"} or work_class == "critical":
        return "critical", "xhigh", "xhigh"
    if work_class == "open":
        return "open", "high", "xhigh"
    return "general", "high", "high"


def _contains_invisible_or_control(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def _has_visible_base(value: str) -> bool:
    return any(
        unicodedata.category(character)[0] not in {"C", "M", "Z"}
        for character in value
    )


def _runtime_catalog_sha256(available_pairs: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "model": pair["model"],
            "family": pair["family"],
            "effort": pair["effort"],
            "eligible_work_classes": sorted(pair["eligible_work_classes"]),
        }
        for pair in available_pairs
    ]
    normalized.sort(
        key=lambda pair: (
            pair["model"],
            pair["family"],
            pair["effort"],
            pair["eligible_work_classes"],
        )
    )
    canonical = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_metric_as_of(value: str) -> bool:
    if value != value.strip() or _contains_invisible_or_control(value):
        return False
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            return True
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None
    except ValueError:
        return False


class StructureValidator:
    def __init__(self) -> None:
        self.errors: list[Issue] = []

    def error(self, code: str, path: str, message: str, node_id: str | None = None) -> None:
        self.errors.append(Issue(code, path, message, node_id))

    def object(
        self,
        value: Any,
        path: str,
        required: Iterable[str],
        optional: Iterable[str] = (),
    ) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.error("SCHEMA_TYPE", path, "Expected an object.")
            return None
        required_set = set(required)
        allowed = required_set | set(optional)
        for key in sorted(required_set - value.keys()):
            self.error("SCHEMA_REQUIRED", f"{path}/{key}", f"Missing required field '{key}'.")
        for key in sorted(value.keys() - allowed):
            self.error("SCHEMA_UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'.")
        return value

    def string(self, value: Any, path: str, nonempty: bool = True) -> None:
        if not isinstance(value, str):
            self.error("SCHEMA_TYPE", path, "Expected a string.")
        elif nonempty and not value.strip():
            self.error("SCHEMA_VALUE", path, "String must not be empty.")

    def model_identifier(self, value: Any, path: str) -> None:
        self.string(value, path)
        if isinstance(value, str) and (
            value != value.strip() or _contains_invisible_or_control(value)
        ):
            self.error(
                "SCHEMA_PATTERN",
                path,
                "Model identifiers may not contain leading/trailing whitespace or invisible/control characters.",
            )

    def enum(self, value: Any, allowed: set[str], path: str) -> None:
        if not isinstance(value, str):
            self.error("SCHEMA_TYPE", path, "Expected a string enum value.")
        elif value not in allowed:
            self.error("SCHEMA_ENUM", path, f"Expected one of {sorted(allowed)}, got '{value}'.")

    def integer(self, value: Any, path: str, minimum: int = 0, maximum: int | None = None) -> None:
        if not _is_int(value):
            self.error("SCHEMA_TYPE", path, "Expected an integer.")
        elif value < minimum or (maximum is not None and value > maximum):
            suffix = f" and at most {maximum}" if maximum is not None else ""
            self.error("SCHEMA_VALUE", path, f"Expected at least {minimum}{suffix}.")

    def number(
        self,
        value: Any,
        path: str,
        minimum: float = 0.0,
        maximum: float | None = None,
        max_decimal_places: int | None = None,
    ) -> None:
        if not _is_finite_number(value):
            self.error("SCHEMA_TYPE", path, "Expected a finite number.")
        elif value < minimum or (maximum is not None and value > maximum):
            suffix = f" and at most {maximum}" if maximum is not None else ""
            self.error("SCHEMA_VALUE", path, f"Expected at least {minimum}{suffix}.")
        elif max_decimal_places is not None and _decimal_places(value) > max_decimal_places:
            self.error(
                "SCHEMA_VALUE",
                path,
                f"Expected at most {max_decimal_places} decimal places.",
            )

    def string_list(self, value: Any, path: str, min_items: int = 0) -> None:
        if not isinstance(value, list):
            self.error("SCHEMA_TYPE", path, "Expected an array.")
            return
        if len(value) < min_items:
            self.error("SCHEMA_MIN_ITEMS", path, f"Expected at least {min_items} item(s).")
        seen: set[str] = set()
        for index, item in enumerate(value):
            item_path = f"{path}/{index}"
            self.string(item, item_path)
            if isinstance(item, str):
                if item in seen:
                    self.error("SCHEMA_DUPLICATE_ITEM", item_path, f"Duplicate item '{item}'.")
                seen.add(item)

    def pair(self, value: Any, path: str) -> None:
        pair = self.object(value, path, {"model", "family", "effort"})
        if pair is None:
            return
        if "model" in pair:
            self.model_identifier(pair["model"], f"{path}/model")
        if "family" in pair:
            self.enum(pair["family"], PAIR_FAMILIES, f"{path}/family")
        if "effort" in pair:
            self.enum(pair["effort"], PAIR_EFFORTS, f"{path}/effort")

    def runtime_pair(self, value: Any, path: str) -> None:
        pair = self.object(value, path, {"model", "family", "effort", "eligible_work_classes"})
        if pair is None:
            return
        self.model_identifier(pair.get("model"), f"{path}/model")
        self.enum(pair.get("family"), PAIR_FAMILIES, f"{path}/family")
        self.enum(pair.get("effort"), PAIR_EFFORTS, f"{path}/effort")
        classes = pair.get("eligible_work_classes")
        self.string_list(classes, f"{path}/eligible_work_classes", min_items=1)
        if isinstance(classes, list):
            for index, value_item in enumerate(classes):
                if isinstance(value_item, str) and value_item not in WORK_CLASSES:
                    self.error(
                        "SCHEMA_ENUM",
                        f"{path}/eligible_work_classes/{index}",
                        f"Unknown work class '{value_item}'.",
                    )

    def economy_candidate_estimate(self, value: Any, path: str) -> None:
        estimate = self.object(
            value,
            path,
            {
                "pair",
                "sample_size",
                "evidence_ref",
                "initial_cost",
                "retry_probability",
                "retry_cost_if_triggered",
                "rework_probability",
                "rework_cost_if_triggered",
                "review_cost",
                "escalation_probability",
                "escalation_cost_if_triggered",
                "coordination_cost",
                "expected_total_cost",
            },
        )
        if estimate is None:
            return
        self.pair(estimate.get("pair"), f"{path}/pair")
        self.integer(estimate.get("sample_size"), f"{path}/sample_size", 1)
        self.string(estimate.get("evidence_ref"), f"{path}/evidence_ref")
        for field_name in (
            "initial_cost",
            "retry_cost_if_triggered",
            "rework_cost_if_triggered",
            "review_cost",
            "escalation_cost_if_triggered",
            "coordination_cost",
            "expected_total_cost",
        ):
            self.number(
                estimate.get(field_name),
                f"{path}/{field_name}",
                maximum=ECONOMY_MAX_COST,
                max_decimal_places=ECONOMY_DECIMAL_PLACES,
            )
        for field_name in (
            "retry_probability",
            "rework_probability",
            "escalation_probability",
        ):
            self.number(
                estimate.get(field_name),
                f"{path}/{field_name}",
                0.0,
                1.0,
                ECONOMY_DECIMAL_PLACES,
            )

    def economy_parent_estimate(self, value: Any, path: str) -> None:
        estimate = self.object(
            value,
            path,
            {
                "pair",
                "sample_size",
                "evidence_ref",
                "initial_cost",
                "retry_probability",
                "retry_cost_if_triggered",
                "rework_probability",
                "rework_cost_if_triggered",
                "review_cost",
                "escalation_probability",
                "escalation_cost_if_triggered",
                "coordination_cost",
                "expected_total_cost",
            },
        )
        if estimate is None:
            return
        self.pair(estimate.get("pair"), f"{path}/pair")
        self.integer(estimate.get("sample_size"), f"{path}/sample_size", 1)
        self.string(estimate.get("evidence_ref"), f"{path}/evidence_ref")
        for field_name in (
            "initial_cost",
            "retry_cost_if_triggered",
            "rework_cost_if_triggered",
            "review_cost",
            "escalation_cost_if_triggered",
            "coordination_cost",
            "expected_total_cost",
        ):
            self.number(
                estimate.get(field_name),
                f"{path}/{field_name}",
                maximum=ECONOMY_MAX_COST,
                max_decimal_places=ECONOMY_DECIMAL_PLACES,
            )
        for field_name in (
            "retry_probability",
            "rework_probability",
            "escalation_probability",
        ):
            self.number(
                estimate.get(field_name),
                f"{path}/{field_name}",
                0.0,
                1.0,
                ECONOMY_DECIMAL_PLACES,
            )

    def economy_evaluation(self, value: Any, path: str) -> None:
        evaluation = self.object(
            value,
            path,
            {
                "mode",
                "formula_version",
                "cost_unit",
                "cohort_id",
                "parent_estimate",
                "candidate_estimates",
                "qualitative_order",
                "tie_break",
                "delegation_decision",
                "rationale",
            },
        )
        if evaluation is None:
            return
        self.enum(evaluation.get("mode"), ECONOMY_EVALUATION_MODES, f"{path}/mode")
        self.enum(evaluation.get("tie_break"), ECONOMY_TIE_BREAKS, f"{path}/tie_break")
        self.enum(
            evaluation.get("delegation_decision"),
            ECONOMY_DELEGATION_DECISIONS,
            f"{path}/delegation_decision",
        )
        self.string(evaluation.get("rationale"), f"{path}/rationale")
        for field_name in ("formula_version", "cost_unit", "cohort_id"):
            if evaluation.get(field_name) is not None:
                self.string(evaluation.get(field_name), f"{path}/{field_name}")
        if evaluation.get("parent_estimate") is not None:
            self.economy_parent_estimate(
                evaluation.get("parent_estimate"),
                f"{path}/parent_estimate",
            )

        estimates = evaluation.get("candidate_estimates")
        if not isinstance(estimates, list):
            self.error("SCHEMA_TYPE", f"{path}/candidate_estimates", "Expected an array.")
        else:
            seen_estimates: set[tuple[str, str, str]] = set()
            for index, estimate in enumerate(estimates):
                estimate_path = f"{path}/candidate_estimates/{index}"
                self.economy_candidate_estimate(estimate, estimate_path)
                if isinstance(estimate, dict):
                    key = _pair_key(estimate.get("pair"))
                    if key is not None:
                        if key in seen_estimates:
                            self.error(
                                "SCHEMA_DUPLICATE_ITEM",
                                f"{estimate_path}/pair",
                                f"Duplicate economy candidate {key}.",
                            )
                        seen_estimates.add(key)

        order = evaluation.get("qualitative_order")
        if not isinstance(order, list):
            self.error("SCHEMA_TYPE", f"{path}/qualitative_order", "Expected an array.")
        else:
            seen_order: set[tuple[str, str, str]] = set()
            for index, candidate in enumerate(order):
                candidate_path = f"{path}/qualitative_order/{index}"
                self.pair(candidate, candidate_path)
                key = _pair_key(candidate)
                if key is not None:
                    if key in seen_order:
                        self.error(
                            "SCHEMA_DUPLICATE_ITEM",
                            candidate_path,
                            f"Duplicate qualitative economy candidate {key}.",
                        )
                    seen_order.add(key)

    def validation_step(self, value: Any, path: str) -> None:
        step = self.object(value, path, {"id", "kind", "phase", "required"}, {"target"})
        if step is None:
            return
        self.string(step.get("id"), f"{path}/id")
        self.enum(step.get("kind"), VALIDATION_KINDS, f"{path}/kind")
        self.enum(step.get("phase"), VALIDATION_PHASES, f"{path}/phase")
        if not isinstance(step.get("required"), bool):
            self.error("SCHEMA_TYPE", f"{path}/required", "Expected a boolean.")
        if "target" in step:
            self.string(step["target"], f"{path}/target")

    def dispatch_attempt(self, value: Any, path: str) -> None:
        attempt = self.object(
            value,
            path,
            {
                "attempt_index",
                "mode",
                "task_name",
                "agent_label",
                "fork_turns",
                "requested_pair",
                "model",
                "reasoning_effort",
                "receipt_status",
                "receipt_ref",
                "effective_pair",
                "confirmation_status",
            },
            {"event_seq"},
        )
        if attempt is None:
            return
        self.integer(attempt.get("attempt_index"), f"{path}/attempt_index", 1)
        if "event_seq" in attempt:
            self.integer(attempt.get("event_seq"), f"{path}/event_seq", 1)
        self.enum(attempt.get("mode"), DISPATCH_MODES, f"{path}/mode")
        self.string(attempt.get("task_name"), f"{path}/task_name")
        task_name = attempt.get("task_name")
        if isinstance(task_name, str) and not TASK_NAME_RE.fullmatch(task_name):
            self.error(
                "SCHEMA_PATTERN",
                f"{path}/task_name",
                "task_name must contain only lowercase letters, digits, and underscores and start with a letter.",
            )
        self.string(attempt.get("agent_label"), f"{path}/agent_label")
        self.string(attempt.get("fork_turns"), f"{path}/fork_turns")
        fork_turns = attempt.get("fork_turns")
        if isinstance(fork_turns, str) and not FORK_TURNS_RE.fullmatch(fork_turns):
            self.error(
                "SCHEMA_PATTERN",
                f"{path}/fork_turns",
                "fork_turns must be 'none', 'all', or a positive integer encoded as a string.",
            )
        self.pair(attempt.get("requested_pair"), f"{path}/requested_pair")
        model = attempt.get("model")
        if model is not None:
            self.model_identifier(model, f"{path}/model")
        reasoning_effort = attempt.get("reasoning_effort")
        if reasoning_effort is not None:
            self.enum(reasoning_effort, CHILD_EFFORTS, f"{path}/reasoning_effort")
        self.enum(attempt.get("receipt_status"), RECEIPT_STATUSES, f"{path}/receipt_status")
        receipt_ref = attempt.get("receipt_ref")
        if receipt_ref is not None:
            self.string(receipt_ref, f"{path}/receipt_ref")
        effective_pair = attempt.get("effective_pair")
        if effective_pair is not None:
            self.pair(effective_pair, f"{path}/effective_pair")
        self.enum(
            attempt.get("confirmation_status"),
            CONFIRMATION_STATUSES,
            f"{path}/confirmation_status",
        )

    def dispatch(self, value: Any, path: str) -> None:
        dispatch = self.object(value, path, {"attempts", "effective_attempt"})
        if dispatch is None:
            return
        attempts = dispatch.get("attempts")
        if not isinstance(attempts, list):
            self.error("SCHEMA_TYPE", f"{path}/attempts", "Expected an array.")
        else:
            if not attempts:
                self.error("SCHEMA_MIN_ITEMS", f"{path}/attempts", "Expected at least one dispatch attempt.")
            for index, attempt in enumerate(attempts):
                self.dispatch_attempt(attempt, f"{path}/attempts/{index}")
        effective_attempt = dispatch.get("effective_attempt")
        if effective_attempt is not None:
            self.integer(effective_attempt, f"{path}/effective_attempt", 1)

    def result_attestation(self, value: Any, path: str) -> None:
        result = self.object(
            value,
            path,
            {
                "status",
                "dispatch_attempt",
                "agent_label",
                "assigned_pair_echo",
                "confirmation_status_echo",
            },
            {"event_seq", "failure_classification", "failure_evidence"},
        )
        if result is None:
            return
        self.enum(result.get("status"), RESULT_STATUSES, f"{path}/status")
        self.integer(result.get("dispatch_attempt"), f"{path}/dispatch_attempt", 1)
        if "event_seq" in result:
            self.integer(result.get("event_seq"), f"{path}/event_seq", 1)
        if "failure_classification" in result:
            self.enum(
                result.get("failure_classification"),
                FAILURE_CLASSIFICATIONS,
                f"{path}/failure_classification",
            )
        if "failure_evidence" in result:
            failure_evidence = result.get("failure_evidence")
            self.string_list(failure_evidence, f"{path}/failure_evidence")
            if isinstance(failure_evidence, list):
                for index, evidence_item in enumerate(failure_evidence):
                    if isinstance(evidence_item, str) and (
                        evidence_item != evidence_item.strip()
                        or _contains_invisible_or_control(evidence_item)
                        or not any(character.isalnum() for character in evidence_item)
                    ):
                        self.error(
                            "SCHEMA_PATTERN",
                            f"{path}/failure_evidence/{index}",
                            (
                                "Failure evidence must contain a visible letter or number and no "
                                "surrounding whitespace or invisible/control characters."
                            ),
                        )
        self.string(result.get("agent_label"), f"{path}/agent_label")
        self.pair(result.get("assigned_pair_echo"), f"{path}/assigned_pair_echo")
        self.enum(
            result.get("confirmation_status_echo"),
            CONFIRMATION_STATUSES,
            f"{path}/confirmation_status_echo",
        )

    def node(self, value: Any, path: str) -> None:
        required = {
            "id",
            "executor_id",
            "wave",
            "role",
            "objective",
            "why_delegate",
            "work_class",
            "risk",
            "context_scope",
            "oracle",
            "access_mode",
            "depends_on",
            "known_facts",
            "hypotheses",
            "owned_mutable_surfaces",
            "read_only_surfaces",
            "write_conflict_groups",
            "forbidden_actions",
            "deliverables",
            "acceptance_criteria",
            "validation_steps",
            "expected_evidence",
            "attempt_budget",
            "recovery_steps",
            "stop_conditions",
            "escalate_when",
            "requirements",
            "selection",
            "lifecycle_state",
            "dispatch",
            "result",
        }
        optional = {
            "economy_evaluation",
            "read_only_control",
            "review_of",
            "work_unit_id",
            "retry_of",
            "retry_kind",
        }
        node = self.object(value, path, required, optional)
        if node is None:
            return
        node_id = node.get("id") if isinstance(node.get("id"), str) else None
        self.string(node.get("id"), f"{path}/id")
        if node_id is not None and not NODE_ID_RE.fullmatch(node_id):
            self.error("SCHEMA_PATTERN", f"{path}/id", "ID must match ^[a-z][a-z0-9_]{0,63}$.", node_id)
        self.string(node.get("executor_id"), f"{path}/executor_id")
        executor_id = node.get("executor_id")
        if isinstance(executor_id, str) and not EXECUTOR_ID_RE.fullmatch(executor_id):
            self.error(
                "SCHEMA_PATTERN",
                f"{path}/executor_id",
                "Executor ID must match ^[a-z][a-z0-9_]{0,63}$.",
                node_id,
            )
        if "work_unit_id" in node:
            self.string(node.get("work_unit_id"), f"{path}/work_unit_id")
            work_unit_id = node.get("work_unit_id")
            if isinstance(work_unit_id, str) and not NODE_ID_RE.fullmatch(work_unit_id):
                self.error(
                    "SCHEMA_PATTERN",
                    f"{path}/work_unit_id",
                    "Work-unit ID must match ^[a-z][a-z0-9_]{0,63}$.",
                    node_id,
                )
        if "retry_of" in node and node.get("retry_of") is not None:
            self.string(node.get("retry_of"), f"{path}/retry_of")
            retry_of = node.get("retry_of")
            if isinstance(retry_of, str) and not NODE_ID_RE.fullmatch(retry_of):
                self.error(
                    "SCHEMA_PATTERN",
                    f"{path}/retry_of",
                    "retry_of must be null or a canonical node ID.",
                    node_id,
                )
        if "retry_kind" in node:
            self.enum(node.get("retry_kind"), RETRY_KINDS, f"{path}/retry_kind")
        self.integer(node.get("wave"), f"{path}/wave")
        self.enum(node.get("role"), ROLES, f"{path}/role")
        self.string(node.get("objective"), f"{path}/objective")
        self.string(node.get("why_delegate"), f"{path}/why_delegate")
        self.enum(node.get("work_class"), WORK_CLASSES, f"{path}/work_class")
        self.enum(node.get("risk"), RISKS, f"{path}/risk")
        self.enum(node.get("context_scope"), CONTEXT_SCOPES, f"{path}/context_scope")
        self.enum(node.get("oracle"), ORACLES, f"{path}/oracle")
        self.enum(node.get("access_mode"), ACCESS_MODES, f"{path}/access_mode")
        self.enum(
            node.get("lifecycle_state"),
            NODE_LIFECYCLE_STATES,
            f"{path}/lifecycle_state",
        )
        for field_name, minimum in (
            ("depends_on", 0),
            ("known_facts", 0),
            ("hypotheses", 0),
            ("owned_mutable_surfaces", 0),
            ("read_only_surfaces", 0),
            ("write_conflict_groups", 0),
            ("forbidden_actions", 1),
            ("deliverables", 1),
            ("acceptance_criteria", 1),
            ("expected_evidence", 1),
            ("review_of", 0),
            ("recovery_steps", 1),
            ("stop_conditions", 1),
            ("escalate_when", 1),
        ):
            if field_name in node:
                self.string_list(node[field_name], f"{path}/{field_name}", min_items=minimum)

        steps = node.get("validation_steps")
        if not isinstance(steps, list):
            self.error("SCHEMA_TYPE", f"{path}/validation_steps", "Expected an array.")
        else:
            for index, step in enumerate(steps):
                self.validation_step(step, f"{path}/validation_steps/{index}")

        budget = self.object(
            node.get("attempt_budget"),
            f"{path}/attempt_budget",
            {"transient_retries", "substantive_attempts", "max_uses"},
        )
        if budget is not None:
            self.integer(budget.get("transient_retries"), f"{path}/attempt_budget/transient_retries", 0, 1)
            self.integer(budget.get("substantive_attempts"), f"{path}/attempt_budget/substantive_attempts", 1, 2)
            self.integer(budget.get("max_uses"), f"{path}/attempt_budget/max_uses", 0, 1)

        requirements = self.object(
            node.get("requirements"),
            f"{path}/requirements",
            {
                "required_integrator_class",
                "minimum_child_effort",
                "minimum_integrator_effort",
                "allowed_model_effort_pairs",
                "fallback_pairs",
            },
        )
        if requirements is not None:
            self.enum(
                requirements.get("required_integrator_class"),
                WORK_CLASSES,
                f"{path}/requirements/required_integrator_class",
            )
            self.enum(
                requirements.get("minimum_child_effort"),
                CHILD_EFFORTS,
                f"{path}/requirements/minimum_child_effort",
            )
            self.enum(
                requirements.get("minimum_integrator_effort"),
                CHILD_EFFORTS,
                f"{path}/requirements/minimum_integrator_effort",
            )
            for list_name, minimum in (("allowed_model_effort_pairs", 1), ("fallback_pairs", 0)):
                pairs = requirements.get(list_name)
                pair_path = f"{path}/requirements/{list_name}"
                if not isinstance(pairs, list):
                    self.error("SCHEMA_TYPE", pair_path, "Expected an array.")
                else:
                    if len(pairs) < minimum:
                        self.error("SCHEMA_MIN_ITEMS", pair_path, f"Expected at least {minimum} item(s).")
                    seen_pairs: set[tuple[str, str, str]] = set()
                    for index, pair in enumerate(pairs):
                        self.pair(pair, f"{pair_path}/{index}")
                        key = _pair_key(pair)
                        if key is not None:
                            if key in seen_pairs:
                                self.error(
                                    "SCHEMA_DUPLICATE_ITEM",
                                    f"{pair_path}/{index}",
                                    f"Duplicate pair {key}.",
                                    node_id,
                                )
                            seen_pairs.add(key)
                        if list_name == "allowed_model_effort_pairs" and isinstance(pair, dict) and pair.get("effort") == "ultra":
                            self.error(
                                "SCHEMA_VALUE",
                                f"{pair_path}/{index}/effort",
                                "Explicit child allowlists may not contain Ultra.",
                                node_id,
                            )

        selection = self.object(
            node.get("selection"),
            f"{path}/selection",
            {
                "origin",
                "requested_pair",
                "selected_pair",
                "fallback_reason",
            },
        )
        if selection is not None:
            self.enum(selection.get("origin"), SELECTION_ORIGINS, f"{path}/selection/origin")
            requested = selection.get("requested_pair")
            if requested is not None:
                self.pair(requested, f"{path}/selection/requested_pair")
            self.pair(selection.get("selected_pair"), f"{path}/selection/selected_pair")
            reason = selection.get("fallback_reason")
            if reason is not None:
                self.enum(reason, FALLBACK_REASONS, f"{path}/selection/fallback_reason")
        dispatch = node.get("dispatch")
        if dispatch is not None:
            self.dispatch(dispatch, f"{path}/dispatch")
        result = node.get("result")
        if result is not None:
            self.result_attestation(result, f"{path}/result")
        if "economy_evaluation" in node:
            self.economy_evaluation(
                node.get("economy_evaluation"),
                f"{path}/economy_evaluation",
            )
        if "read_only_control" in node:
            control = self.object(
                node["read_only_control"],
                f"{path}/read_only_control",
                {"declared", "enforcement"},
            )
            if control is not None:
                if not isinstance(control.get("declared"), bool):
                    self.error("SCHEMA_TYPE", f"{path}/read_only_control/declared", "Expected a boolean.")
                self.enum(
                    control.get("enforcement"),
                    READ_ONLY_ENFORCEMENT,
                    f"{path}/read_only_control/enforcement",
                )

    def validate(self, plan: Any) -> list[Issue]:
        root = self.object(
            plan,
            "",
            {
                "schema_version",
                "ledger_phase",
                "profile",
                "metric_source",
                "metric_as_of",
                "evidence_id_or_window",
                "orchestration",
                "runtime",
                "nodes",
            },
            {"child_policy"},
        )
        if root is None:
            return _sort_issues(self.errors)
        if root.get("schema_version") != SCHEMA_VERSION:
            self.error(
                "SCHEMA_VERSION",
                "/schema_version",
                f"Expected '{SCHEMA_VERSION}'.",
            )
        self.enum(root.get("ledger_phase"), LEDGER_PHASES, "/ledger_phase")
        self.enum(root.get("profile"), PROFILES, "/profile")
        if "child_policy" in root:
            self.enum(root.get("child_policy"), CHILD_POLICIES, "/child_policy")
        self.enum(root.get("metric_source"), METRIC_SOURCES, "/metric_source")
        for field_name in ("metric_as_of", "evidence_id_or_window"):
            value = root.get(field_name)
            if value is not None:
                self.string(value, f"/{field_name}")

        orchestration = self.object(root.get("orchestration"), "/orchestration", {"state", "parent"})
        if orchestration is not None:
            self.enum(orchestration.get("state"), ORCHESTRATION_STATES, "/orchestration/state")
            parent = self.object(
                orchestration.get("parent"),
                "/orchestration/parent",
                {"model", "family", "effort", "integrator_class"},
            )
            if parent is not None:
                self.model_identifier(parent.get("model"), "/orchestration/parent/model")
                self.enum(parent.get("family"), FAMILIES, "/orchestration/parent/family")
                self.enum(parent.get("effort"), EFFORTS, "/orchestration/parent/effort")
                self.enum(
                    parent.get("integrator_class"),
                    WORK_CLASSES | {"unknown"},
                    "/orchestration/parent/integrator_class",
                )

        runtime = self.object(
            root.get("runtime"),
            "/runtime",
            {"max_concurrent_children", "available_pairs"},
            {"catalog_snapshot"},
        )
        if runtime is not None:
            limit = runtime.get("max_concurrent_children")
            if limit is not None:
                self.integer(limit, "/runtime/max_concurrent_children")
            pairs = runtime.get("available_pairs")
            if not isinstance(pairs, list):
                self.error("SCHEMA_TYPE", "/runtime/available_pairs", "Expected an array.")
            else:
                seen_pairs: set[tuple[str, str, str]] = set()
                for index, pair in enumerate(pairs):
                    self.runtime_pair(pair, f"/runtime/available_pairs/{index}")
                    key = _pair_key(pair)
                    if key is not None:
                        if key in seen_pairs:
                            self.error(
                                "SCHEMA_DUPLICATE_ITEM",
                                f"/runtime/available_pairs/{index}",
                                f"Duplicate runtime pair {key}.",
                            )
                        seen_pairs.add(key)
            if "catalog_snapshot" in runtime:
                snapshot = self.object(
                    runtime.get("catalog_snapshot"),
                    "/runtime/catalog_snapshot",
                    {"captured_at", "evidence_ref", "available_pairs_sha256"},
                )
                if snapshot is not None:
                    captured_at = snapshot.get("captured_at")
                    self.string(captured_at, "/runtime/catalog_snapshot/captured_at")
                    if isinstance(captured_at, str) and not _valid_metric_as_of(captured_at):
                        self.error(
                            "SCHEMA_FORMAT",
                            "/runtime/catalog_snapshot/captured_at",
                            "captured_at must be an ISO 8601 date or timezone-aware timestamp.",
                        )
                    evidence_ref = snapshot.get("evidence_ref")
                    self.string(evidence_ref, "/runtime/catalog_snapshot/evidence_ref")
                    if isinstance(evidence_ref, str) and (
                        evidence_ref != evidence_ref.strip()
                        or _contains_invisible_or_control(evidence_ref)
                    ):
                        self.error(
                            "SCHEMA_PATTERN",
                            "/runtime/catalog_snapshot/evidence_ref",
                            "evidence_ref may not contain surrounding whitespace or invisible/control characters.",
                        )
                    available_pairs_sha256 = snapshot.get("available_pairs_sha256")
                    self.string(
                        available_pairs_sha256,
                        "/runtime/catalog_snapshot/available_pairs_sha256",
                    )
                    if isinstance(available_pairs_sha256, str) and not re.fullmatch(
                        r"[0-9a-f]{64}", available_pairs_sha256
                    ):
                        self.error(
                            "SCHEMA_PATTERN",
                            "/runtime/catalog_snapshot/available_pairs_sha256",
                            "available_pairs_sha256 must be a lowercase SHA-256 hex digest.",
                        )

        nodes = root.get("nodes")
        if not isinstance(nodes, list):
            self.error("SCHEMA_TYPE", "/nodes", "Expected an array.")
        else:
            for index, node in enumerate(nodes):
                self.node(node, f"/nodes/{index}")
        return _sort_issues(self.errors)


class SemanticValidator:
    def __init__(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.nodes: list[dict[str, Any]] = plan["nodes"]
        self.errors: list[Issue] = []
        self.warnings: list[Issue] = []
        self.node_index: dict[str, int] = {}
        self.nodes_by_id: dict[str, dict[str, Any]] = {}
        self.cycle_nodes: set[str] = set()
        self.selected_pair_valid: dict[str, bool] = {}
        self.confirmed_child_count = 0
        self.unresolved_dispatch_count = 0
        self.dispatch_blocked_count = 0

    def error(
        self,
        code: str,
        path: str,
        message: str,
        node_id: str | None = None,
        related: Iterable[str] = (),
    ) -> None:
        self.errors.append(Issue(code, path, message, node_id, tuple(sorted(related))))

    def warn(
        self,
        code: str,
        path: str,
        message: str,
        node_id: str | None = None,
    ) -> None:
        self.warnings.append(Issue(code, path, message, node_id))

    def _runtime_pairs(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        return {_pair_key(pair): pair for pair in self.plan["runtime"]["available_pairs"]}  # type: ignore[misc]

    def _validate_child_policy(self) -> None:
        """Enforce hard candidate-pool constraints independently of ranking profiles."""
        if self.plan.get("child_policy", "adaptive") != "luna_max_only":
            return

        runtime_pairs = self._runtime_pairs()
        has_dispatch_events = any(node["dispatch"] is not None for node in self.nodes_by_id.values())
        if has_dispatch_events and "catalog_snapshot" not in self.plan["runtime"]:
            self.error(
                "CHILD_POLICY_RUNTIME_SNAPSHOT_REQUIRED",
                "/runtime/catalog_snapshot",
                (
                    "Luna-Max-only execution requires an immutable dispatch-time runtime catalog "
                    "snapshot with captured_at and evidence_ref."
                ),
            )
        snapshot = self.plan["runtime"].get("catalog_snapshot")
        if snapshot is not None:
            expected_digest = _runtime_catalog_sha256(self.plan["runtime"]["available_pairs"])
            if snapshot["available_pairs_sha256"] != expected_digest:
                self.error(
                    "CHILD_POLICY_RUNTIME_SNAPSHOT_DIGEST_MISMATCH",
                    "/runtime/catalog_snapshot/available_pairs_sha256",
                    (
                        "The Luna-Max-only catalog snapshot digest does not match the canonical "
                        "runtime.available_pairs contents."
                    ),
                )
        if LUNA_MAX_PAIR_KEY not in runtime_pairs:
            for node_id, node in self.nodes_by_id.items():
                if node["lifecycle_state"] in {"dispatched", "completed"}:
                    self.error(
                        "CHILD_POLICY_LUNA_MAX_UNAVAILABLE",
                        self._node_path(node_id, "lifecycle_state"),
                        (
                            "A dispatched or completed Luna-Max-only child requires the exact "
                            "gpt-5.6-luna / max pair in the runtime catalog. Keep an unavailable "
                            "target planned or record only a rejected dispatch_blocked attempt."
                        ),
                        node_id,
                    )

        def require_luna_max(pair: Any, path: str, node_id: str) -> None:
            if pair is not None and _pair_key(pair) != LUNA_MAX_PAIR_KEY:
                self.error(
                    "CHILD_POLICY_PAIR_FORBIDDEN",
                    path,
                    (
                        "child_policy='luna_max_only' permits only the exact pair "
                        "('gpt-5.6-luna', 'luna', 'max') in every child routing field."
                    ),
                    node_id,
                )

        for node_id, node in self.nodes_by_id.items():
            path = self._node_path(node_id)
            requirements = node["requirements"]
            selection = node["selection"]
            allowed_pairs = requirements["allowed_model_effort_pairs"]
            fallback_pairs = requirements["fallback_pairs"]

            retry_metadata = {"work_unit_id", "retry_of", "retry_kind"}
            missing_retry_metadata = sorted(retry_metadata - node.keys())
            if missing_retry_metadata:
                self.error(
                    "CHILD_POLICY_RETRY_METADATA_REQUIRED",
                    path,
                    (
                        "Luna-Max-only nodes require explicit work_unit_id, retry_of, and "
                        f"retry_kind fields; missing {missing_retry_metadata}."
                    ),
                    node_id,
                )

            eligible_shape = (
                node["work_class"] == "structured"
                and node["context_scope"] == "bounded"
                and node["oracle"] in {"deterministic", "strong"}
                and node["risk"] not in {"high", "irreversible"}
                and node["access_mode"] != "external_write"
                and node["role"] not in {"architect", "diagnostician", "reviewer"}
            )
            if not eligible_shape:
                self.error(
                    "CHILD_POLICY_NODE_MUST_STAY_PARENT",
                    path,
                    (
                        "Luna-Max-only children must be structured, bounded, strongly verifiable, "
                        "non-high-risk, non-external-write leaves and may not be architects, "
                        "diagnosticians, or reviewers. Keep this node in the parent or rerun "
                        "without children=luna-max."
                    ),
                    node_id,
                )

            if len(allowed_pairs) != 1 or _pair_key(allowed_pairs[0]) != LUNA_MAX_PAIR_KEY:
                self.error(
                    "CHILD_POLICY_ALLOWED_SET_INVALID",
                    f"{path}/requirements/allowed_model_effort_pairs",
                    "Luna-Max-only mode requires the singleton allowed set [gpt-5.6-luna / max].",
                    node_id,
                )
            for pair_index, candidate in enumerate(allowed_pairs):
                require_luna_max(
                    candidate,
                    f"{path}/requirements/allowed_model_effort_pairs/{pair_index}",
                    node_id,
                )

            if fallback_pairs:
                self.error(
                    "CHILD_POLICY_FALLBACK_FORBIDDEN",
                    f"{path}/requirements/fallback_pairs",
                    (
                        "Luna-Max-only mode has no child fallback pair. Runtime unavailability or "
                        "a substantive failure returns the node to the parent."
                    ),
                    node_id,
                )
            for pair_index, candidate in enumerate(fallback_pairs):
                require_luna_max(
                    candidate,
                    f"{path}/requirements/fallback_pairs/{pair_index}",
                    node_id,
                )

            if requirements["minimum_child_effort"] != "max":
                self.error(
                    "CHILD_POLICY_MINIMUM_EFFORT_INVALID",
                    f"{path}/requirements/minimum_child_effort",
                    "Luna-Max-only mode requires minimum_child_effort='max'.",
                    node_id,
                )
            if node["attempt_budget"]["substantive_attempts"] != 1:
                self.error(
                    "CHILD_POLICY_SUBSTANTIVE_RETRY_FORBIDDEN",
                    f"{path}/attempt_budget/substantive_attempts",
                    (
                        "Luna-Max-only mode permits no Luna-to-Luna substantive repair loop; "
                        "set substantive_attempts to 1."
                    ),
                    node_id,
                )
            if node["attempt_budget"]["max_uses"] != 1:
                self.error(
                    "CHILD_POLICY_MAX_BUDGET_INVALID",
                    f"{path}/attempt_budget/max_uses",
                    "Luna-Max-only child nodes require max_uses=1.",
                    node_id,
                )

            if selection["origin"] in {"fallback", "inherited"}:
                self.error(
                    "CHILD_POLICY_SELECTION_ORIGIN_FORBIDDEN",
                    f"{path}/selection/origin",
                    "Luna-Max-only mode forbids fallback and inherited child selection.",
                    node_id,
                )
            require_luna_max(
                selection["requested_pair"],
                f"{path}/selection/requested_pair",
                node_id,
            )
            require_luna_max(
                selection["selected_pair"],
                f"{path}/selection/selected_pair",
                node_id,
            )

            dispatch = node["dispatch"]
            if dispatch is not None:
                allowed_attempts = 1 + node["attempt_budget"]["transient_retries"]
                if len(dispatch["attempts"]) > allowed_attempts:
                    self.error(
                        "CHILD_POLICY_ATTEMPT_BUDGET_EXCEEDED",
                        f"{path}/dispatch/attempts",
                        (
                            "Luna-Max-only dispatch history exceeds the declared transient retry "
                            f"budget; at most {allowed_attempts} attempt(s) are allowed."
                        ),
                        node_id,
                    )
                for attempt_index, attempt in enumerate(dispatch["attempts"]):
                    attempt_path = f"{path}/dispatch/attempts/{attempt_index}"
                    if "event_seq" not in attempt:
                        self.error(
                            "CHILD_POLICY_EVENT_SEQUENCE_REQUIRED",
                            f"{attempt_path}/event_seq",
                            (
                                "Every Luna-Max-only dispatch attempt requires a global event_seq "
                                "so fail-stop ordering is mechanically auditable."
                            ),
                            node_id,
                        )
                    if attempt["mode"] != "explicit":
                        self.error(
                            "CHILD_POLICY_EXPLICIT_DISPATCH_REQUIRED",
                            f"{attempt_path}/mode",
                            "Luna-Max-only mode forbids inheritance and requires explicit dispatch.",
                            node_id,
                        )
                    require_luna_max(
                        attempt["requested_pair"],
                        f"{attempt_path}/requested_pair",
                        node_id,
                    )
                    if (
                        attempt["model"] != LUNA_MAX_PAIR_KEY[0]
                        or attempt["reasoning_effort"] != LUNA_MAX_PAIR_KEY[2]
                    ):
                        self.error(
                            "CHILD_POLICY_EXPLICIT_ARGUMENTS_REQUIRED",
                            attempt_path,
                            (
                                "Every Luna-Max-only spawn attempt must explicitly pass "
                                "model='gpt-5.6-luna' and reasoning_effort='max'."
                            ),
                            node_id,
                        )
                    require_luna_max(
                        attempt["effective_pair"],
                        f"{attempt_path}/effective_pair",
                        node_id,
                    )

            result = node["result"]
            if result is not None:
                if "event_seq" not in result:
                    self.error(
                        "CHILD_POLICY_EVENT_SEQUENCE_REQUIRED",
                        f"{path}/result/event_seq",
                        (
                            "Every Luna-Max-only child result requires a global event_seq so "
                            "dispatches that occur after failure can be rejected."
                        ),
                        node_id,
                    )
                missing_failure_fields = sorted(
                    {"failure_classification", "failure_evidence"} - result.keys()
                )
                if missing_failure_fields:
                    self.error(
                        "CHILD_POLICY_FAILURE_ATTESTATION_REQUIRED",
                        f"{path}/result",
                        (
                            "Luna-Max-only results require parent-verified failure_classification "
                            f"and failure_evidence fields; missing {missing_failure_fields}."
                        ),
                        node_id,
                    )
                else:
                    failure_classification = result["failure_classification"]
                    failure_evidence = result["failure_evidence"]
                    if result["status"] == "success":
                        if failure_classification != "none":
                            self.error(
                                "CHILD_POLICY_FAILURE_CLASSIFICATION_INVALID",
                                f"{path}/result/failure_classification",
                                "A successful Luna-Max-only result requires failure_classification='none'.",
                                node_id,
                            )
                        if failure_evidence:
                            self.error(
                                "CHILD_POLICY_FAILURE_EVIDENCE_INVALID",
                                f"{path}/result/failure_evidence",
                                "A successful Luna-Max-only result requires an empty failure_evidence list.",
                                node_id,
                            )
                    else:
                        if failure_classification == "none":
                            self.error(
                                "CHILD_POLICY_FAILURE_CLASSIFICATION_INVALID",
                                f"{path}/result/failure_classification",
                                "A non-success Luna-Max-only result requires a concrete failure classification.",
                                node_id,
                            )
                        if not failure_evidence:
                            self.error(
                                "CHILD_POLICY_FAILURE_EVIDENCE_REQUIRED",
                                f"{path}/result/failure_evidence",
                                "A non-success Luna-Max-only result requires evidence for its failure classification.",
                                node_id,
                            )
                require_luna_max(
                    result["assigned_pair_echo"],
                    f"{path}/result/assigned_pair_echo",
                    node_id,
                )

        self._validate_luna_max_retry_graph()
        self._validate_luna_max_event_sequence()
        self._validate_luna_max_dependency_readiness()
        self._validate_luna_max_fail_stop()

    def _validate_luna_max_retry_graph(self) -> None:
        """Validate declared work-unit identity and the single transient retry exception."""
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        metadata_fields = {"work_unit_id", "retry_of", "retry_kind"}

        for node_id, node in self.nodes_by_id.items():
            if not metadata_fields <= node.keys():
                continue
            path = self._node_path(node_id)
            work_unit_id = node["work_unit_id"]
            retry_kind = node["retry_kind"]
            retry_of = node["retry_of"]
            groups[work_unit_id].append(node)

            if retry_kind == "none" and retry_of is not None:
                self.error(
                    "CHILD_POLICY_RETRY_RELATION_INVALID",
                    f"{path}/retry_of",
                    "retry_kind='none' requires retry_of=null.",
                    node_id,
                )
            elif retry_kind == "transient" and retry_of is None:
                self.error(
                    "CHILD_POLICY_RETRY_RELATION_INVALID",
                    f"{path}/retry_of",
                    "retry_kind='transient' requires the prior node ID in retry_of.",
                    node_id,
                )
            elif retry_kind == "substantive":
                self.error(
                    "CHILD_POLICY_SUBSTANTIVE_RETRY_FORBIDDEN",
                    f"{path}/retry_kind",
                    "Luna-Max-only mode forbids substantive cross-node rework.",
                    node_id,
                )

        contract_fields = (
            "role",
            "objective",
            "why_delegate",
            "work_class",
            "risk",
            "context_scope",
            "oracle",
            "access_mode",
            "known_facts",
            "hypotheses",
            "owned_mutable_surfaces",
            "read_only_surfaces",
            "write_conflict_groups",
            "forbidden_actions",
            "deliverables",
            "acceptance_criteria",
            "validation_steps",
            "expected_evidence",
            "recovery_steps",
            "stop_conditions",
            "escalate_when",
            "requirements",
            "selection",
            "read_only_control",
            "review_of",
        )

        signature_owner: dict[str, tuple[str, str]] = {}
        for work_unit_id, nodes in groups.items():
            for node in nodes:
                signature = json.dumps(
                    {field_name: node.get(field_name) for field_name in contract_fields},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                previous = signature_owner.get(signature)
                if previous is None:
                    signature_owner[signature] = (work_unit_id, node["id"])
                elif previous[0] != work_unit_id:
                    self.error(
                        "CHILD_POLICY_WORK_UNIT_ID_CHANGED",
                        self._node_path(node["id"], "work_unit_id"),
                        (
                            "Nodes with an identical Luna-Max-only contract must share one "
                            "work_unit_id; changing only the work-unit identity cannot hide rework."
                        ),
                        node["id"],
                        (previous[1],),
                    )

        for work_unit_id, nodes in groups.items():
            initial_nodes = [node for node in nodes if node["retry_kind"] == "none"]
            retry_nodes = [node for node in nodes if node["retry_kind"] == "transient"]
            related_ids = tuple(node["id"] for node in nodes)

            if len(initial_nodes) != 1:
                self.error(
                    "CHILD_POLICY_WORK_UNIT_INITIAL_INVALID",
                    "/nodes",
                    (
                        f"Work unit '{work_unit_id}' requires exactly one retry_kind='none' "
                        f"initial node; found {len(initial_nodes)}."
                    ),
                    related=related_ids,
                )
            if len(nodes) > 2 or len(retry_nodes) > 1:
                self.error(
                    "CHILD_POLICY_WORK_UNIT_RETRY_LIMIT",
                    "/nodes",
                    f"Work unit '{work_unit_id}' permits at most one transient retry node.",
                    related=related_ids,
                )
            if len(initial_nodes) != 1:
                continue

            initial = initial_nodes[0]
            initial_id = initial["id"]
            initial_budget = initial["attempt_budget"]["transient_retries"]
            initial_attempt_count = (
                len(initial["dispatch"]["attempts"])
                if initial["dispatch"] is not None
                else 0
            )
            total_attempt_count = sum(
                len(node["dispatch"]["attempts"])
                if node["dispatch"] is not None
                else 0
                for node in nodes
            )
            allowed_work_unit_attempts = 1 + initial_budget
            if total_attempt_count > allowed_work_unit_attempts:
                self.error(
                    "CHILD_POLICY_WORK_UNIT_ATTEMPT_BUDGET_EXCEEDED",
                    "/nodes",
                    (
                        f"Work unit '{work_unit_id}' records {total_attempt_count} dispatch "
                        f"attempts but permits at most {allowed_work_unit_attempts}."
                    ),
                    related=related_ids,
                )

            for retry in retry_nodes:
                retry_id = retry["id"]
                retry_path = self._node_path(retry_id)
                prior_id = retry["retry_of"]
                prior = self.nodes_by_id.get(prior_id)
                if prior is None:
                    self.error(
                        "CHILD_POLICY_RETRY_TARGET_UNKNOWN",
                        f"{retry_path}/retry_of",
                        f"Retry target '{prior_id}' does not exist.",
                        retry_id,
                    )
                    continue
                if prior_id != initial_id or prior.get("work_unit_id") != work_unit_id:
                    self.error(
                        "CHILD_POLICY_RETRY_TARGET_MISMATCH",
                        f"{retry_path}/retry_of",
                        "A transient retry must point directly to its work unit's initial node.",
                        retry_id,
                        (prior_id,),
                    )
                if retry["executor_id"] != prior["executor_id"]:
                    self.error(
                        "CHILD_POLICY_RETRY_EXECUTOR_CHANGED",
                        f"{retry_path}/executor_id",
                        "An unchanged transient retry must keep the same executor_id.",
                        retry_id,
                        (prior_id,),
                    )
                expected_dependencies = set(prior["depends_on"]) | {prior_id}
                if set(retry["depends_on"]) != expected_dependencies:
                    self.error(
                        "CHILD_POLICY_RETRY_DEPENDENCIES_CHANGED",
                        f"{retry_path}/depends_on",
                        (
                            "A transient retry must depend on the initial node and preserve its "
                            "original dependencies exactly."
                        ),
                        retry_id,
                        (prior_id,),
                    )
                prior_result = prior["result"]
                if (
                    prior["lifecycle_state"] != "completed"
                    or prior_result is None
                    or prior_result["status"] != "failed"
                ):
                    self.error(
                        "CHILD_POLICY_RETRY_PRIOR_NOT_FAILED",
                        f"{retry_path}/retry_of",
                        (
                            "A cross-node transient retry requires a completed prior child whose "
                            "result status is 'failed'. Runtime dispatch rejections retry inside "
                            "the same node instead."
                        ),
                        retry_id,
                        (prior_id,),
                    )
                elif prior_result.get("failure_classification") != "transient":
                    self.error(
                        "CHILD_POLICY_RETRY_PRIOR_NOT_TRANSIENT",
                        f"{retry_path}/retry_of",
                        (
                            "A Luna-Max-only retry requires the parent to classify the failed "
                            "initial result as transient with supporting failure evidence."
                        ),
                        retry_id,
                        (prior_id,),
                    )
                changed_fields = [
                    field_name
                    for field_name in contract_fields
                    if retry.get(field_name) != prior.get(field_name)
                ]
                if changed_fields:
                    self.error(
                        "CHILD_POLICY_RETRY_CONTRACT_CHANGED",
                        retry_path,
                        (
                            "A transient retry must preserve the work contract; changed fields: "
                            f"{changed_fields}."
                        ),
                        retry_id,
                        (prior_id,),
                    )
                if initial_budget != 1 or retry["attempt_budget"]["transient_retries"] != 0:
                    self.error(
                        "CHILD_POLICY_RETRY_BUDGET_INVALID",
                        f"{retry_path}/attempt_budget/transient_retries",
                        (
                            "The initial node must declare one transient retry and the retry node "
                            "must declare zero remaining retries."
                        ),
                        retry_id,
                        (prior_id,),
                    )
                if initial_attempt_count >= allowed_work_unit_attempts:
                    self.error(
                        "CHILD_POLICY_RETRY_BUDGET_EXHAUSTED",
                        f"{retry_path}/retry_of",
                        "The initial node already consumed the work unit's dispatch-attempt budget.",
                        retry_id,
                        (prior_id,),
                    )
                retry_dispatch = retry["dispatch"]
                retry_attempt_sequences = (
                    [
                        attempt.get("event_seq")
                        for attempt in retry_dispatch["attempts"]
                        if _is_int(attempt.get("event_seq"))
                    ]
                    if retry_dispatch is not None
                    else []
                )
                prior_result_sequence = (
                    prior_result.get("event_seq") if prior_result is not None else None
                )
                if (
                    retry_attempt_sequences
                    and _is_int(prior_result_sequence)
                    and min(retry_attempt_sequences) <= prior_result_sequence
                ):
                    self.error(
                        "CHILD_POLICY_RETRY_EVENT_ORDER",
                        f"{retry_path}/dispatch/attempts",
                        (
                            "Every transient-retry spawn event must occur after the failed "
                            "initial result event recorded in retry_of."
                        ),
                        retry_id,
                        (prior_id,),
                    )

    def _validate_luna_max_event_sequence(self) -> None:
        """Validate the append-only global order used by Luna-Max-only fail-stop."""
        events: list[tuple[int, str, str]] = []
        for node_id, node in self.nodes_by_id.items():
            dispatch = node["dispatch"]
            attempt_sequences: list[int] = []
            if dispatch is not None:
                for attempt_index, attempt in enumerate(dispatch["attempts"]):
                    event_seq = attempt.get("event_seq")
                    if not _is_int(event_seq):
                        continue
                    path = self._node_path(
                        node_id,
                        f"dispatch/attempts/{attempt_index}/event_seq",
                    )
                    events.append((event_seq, node_id, path))
                    attempt_sequences.append(event_seq)
                if attempt_sequences != sorted(attempt_sequences):
                    self.error(
                        "CHILD_POLICY_EVENT_SEQUENCE_ORDER",
                        self._node_path(node_id, "dispatch/attempts"),
                        "Dispatch-attempt event_seq values must increase with attempt_index.",
                        node_id,
                    )

            result = node["result"]
            if result is not None and _is_int(result.get("event_seq")):
                result_sequence = result["event_seq"]
                result_path = self._node_path(node_id, "result/event_seq")
                events.append((result_sequence, node_id, result_path))
                if attempt_sequences and result_sequence <= max(attempt_sequences):
                    self.error(
                        "CHILD_POLICY_RESULT_EVENT_ORDER",
                        result_path,
                        "A child result event_seq must be later than every dispatch attempt for that node.",
                        node_id,
                    )

        sequence_owners: dict[int, list[tuple[str, str]]] = defaultdict(list)
        for event_seq, node_id, path in events:
            sequence_owners[event_seq].append((node_id, path))
        duplicate_sequences = {
            event_seq: owners
            for event_seq, owners in sequence_owners.items()
            if len(owners) > 1
        }
        for event_seq, owners in sorted(duplicate_sequences.items()):
            related = tuple(node_id for node_id, _ in owners)
            for node_id, path in owners:
                self.error(
                    "CHILD_POLICY_EVENT_SEQUENCE_DUPLICATE",
                    path,
                    f"Global Luna-Max-only event_seq {event_seq} is duplicated.",
                    node_id,
                    related,
                )

        if events and not duplicate_sequences:
            observed = sorted(sequence_owners)
            expected = list(range(1, len(events) + 1))
            if observed != expected:
                self.error(
                    "CHILD_POLICY_EVENT_SEQUENCE_GAP",
                    "/nodes",
                    (
                        "Luna-Max-only event_seq values must form one append-only contiguous "
                        f"sequence starting at 1; observed {observed}."
                    ),
                    related=(node_id for _, node_id, _ in events),
                )

    def _validate_luna_max_fail_stop(self) -> None:
        """Forbid any post-failure spawn except the failed initial's valid transient retry."""
        barriers: list[tuple[int, dict[str, Any]]] = []
        for node in self.nodes_by_id.values():
            dispatch = node["dispatch"]
            if node["lifecycle_state"] == "dispatch_blocked" and dispatch is not None:
                attempt_sequences = [
                    attempt.get("event_seq")
                    for attempt in dispatch["attempts"]
                    if _is_int(attempt.get("event_seq"))
                ]
                if attempt_sequences:
                    barriers.append((max(attempt_sequences), node))
                continue

            result = node["result"]
            if (
                node["lifecycle_state"] == "completed"
                and result is not None
                and result["status"] != "success"
                and _is_int(result.get("event_seq"))
            ):
                barriers.append((result["event_seq"], node))

        earliest_barrier = min(barriers, key=lambda item: item[0]) if barriers else None
        for node_id, node in self.nodes_by_id.items():
            dispatch = node["dispatch"]
            if dispatch is None or earliest_barrier is None:
                continue

            for attempt_index, attempt in enumerate(dispatch["attempts"]):
                event_seq = attempt.get("event_seq")
                if not _is_int(event_seq):
                    continue
                fence_sequence, fence_node = earliest_barrier
                if event_seq <= fence_sequence:
                    continue

                retry_of = node.get("retry_of")
                is_direct_transient_retry = (
                    node.get("retry_kind") == "transient"
                    and fence_node["id"] == retry_of
                    and fence_node["work_unit_id"] == node.get("work_unit_id")
                    and fence_node["lifecycle_state"] == "completed"
                    and fence_node["result"] is not None
                    and fence_node["result"]["status"] == "failed"
                    and fence_node["result"].get("failure_classification") == "transient"
                )
                if is_direct_transient_retry:
                    # The retry-graph validator separately proves that this is the one
                    # unchanged, budgeted retry of the failed initial node.
                    continue

                self.error(
                    "CHILD_POLICY_FAIL_STOP_DISPATCH_FORBIDDEN",
                    self._node_path(
                        node_id,
                        f"dispatch/attempts/{attempt_index}/event_seq",
                    ),
                    (
                        "Luna-Max-only fail-stop forbids every spawn attempt recorded after a "
                        "child completed without success or a node became dispatch_blocked. "
                        "Only the failed initial node's valid direct transient retry may dispatch; "
                        "keep all other follow-up work in the parent."
                    ),
                    node_id,
                    (fence_node["id"],),
                )

    def _validate_luna_max_dependency_readiness(self) -> None:
        """Require every Luna-Max-only spawn to follow acceptance of its dependencies."""
        for node_id, node in self.nodes_by_id.items():
            dispatch = node["dispatch"]
            if dispatch is None:
                continue
            attempt_sequences = [
                attempt.get("event_seq")
                for attempt in dispatch["attempts"]
                if _is_int(attempt.get("event_seq"))
            ]
            if not attempt_sequences:
                continue

            for dependency_id in node["depends_on"]:
                dependency = self.nodes_by_id.get(dependency_id)
                if dependency is None:
                    continue
                dependency_result = dependency["result"]
                is_retry_trigger = (
                    node.get("retry_kind") == "transient"
                    and node.get("retry_of") == dependency_id
                )
                if is_retry_trigger:
                    dependency_ready = (
                        dependency["lifecycle_state"] == "completed"
                        and dependency_result is not None
                        and dependency_result["status"] == "failed"
                        and dependency_result.get("failure_classification") == "transient"
                    )
                else:
                    dependency_ready = (
                        dependency["lifecycle_state"] == "completed"
                        and dependency_result is not None
                        and dependency_result["status"] == "success"
                    )

                if not dependency_ready:
                    self.error(
                        "CHILD_POLICY_DEPENDENCY_NOT_ACCEPTED",
                        self._node_path(node_id, "depends_on"),
                        (
                            f"Dependency '{dependency_id}' must have an accepted completed result "
                            "before this Luna-Max-only node may attempt dispatch."
                        ),
                        node_id,
                        (dependency_id,),
                    )
                    continue

                dependency_result_sequence = dependency_result.get("event_seq")
                if (
                    _is_int(dependency_result_sequence)
                    and min(attempt_sequences) <= dependency_result_sequence
                ):
                    self.error(
                        "CHILD_POLICY_DEPENDENCY_EVENT_ORDER",
                        self._node_path(node_id, "dispatch/attempts"),
                        (
                            f"Every dispatch attempt must occur after dependency '{dependency_id}' "
                            "recorded its accepted result event."
                        ),
                        node_id,
                        (dependency_id,),
                    )

    def _node_path(self, node_id: str, suffix: str = "") -> str:
        base = f"/nodes/{self.node_index[node_id]}"
        return f"{base}/{suffix}" if suffix else base

    def _build_index(self) -> None:
        counts = Counter(node["id"] for node in self.nodes)
        for index, node in enumerate(self.nodes):
            node_id = node["id"]
            if counts[node_id] > 1:
                self.error(
                    "NODE_ID_DUPLICATE",
                    f"/nodes/{index}/id",
                    f"Node ID '{node_id}' is duplicated.",
                    node_id,
                )
                continue
            self.node_index[node_id] = index
            self.nodes_by_id[node_id] = node

    def _validate_orchestration(self) -> None:
        orchestration = self.plan["orchestration"]
        state = orchestration["state"]
        parent = orchestration["parent"]
        effort = parent["effort"]
        child_count = len(self.nodes)

        if state == "unknown" and child_count:
            self.error(
                "ORCH_UNKNOWN_CHILD",
                "/orchestration/state",
                "Unknown orchestration state must fail closed with zero manual children.",
            )
        if (state == "ultra_owned" or effort == "ultra") and child_count:
            self.error(
                "ORCH_ULTRA_CHILD",
                "/nodes",
                "An Ultra-owned parent must have zero manually spawned children.",
            )
        if effort == "ultra" and state != "ultra_owned":
            self.error(
                "ORCH_PARENT_STATE_MISMATCH",
                "/orchestration/state",
                "Parent effort is Ultra, so orchestration state must be 'ultra_owned'.",
            )
        if state == "ultra_owned" and effort not in {"ultra", "unknown"}:
            self.error(
                "ORCH_PARENT_STATE_MISMATCH",
                "/orchestration/parent/effort",
                "State 'ultra_owned' conflicts with a known non-Ultra parent effort.",
            )
        if state == "manual_allowed":
            if (
                parent["model"] == "unknown"
                or effort == "unknown"
                or parent["family"] == "unknown"
                or parent["integrator_class"] == "unknown"
            ):
                self.error(
                    "ORCH_MANUAL_PARENT_UNRESOLVED",
                    "/orchestration/parent",
                    "Manual routing requires known parent family, effort, and integrator class.",
                )
            if effort == "ultra":
                self.error(
                    "ORCH_MANUAL_PARENT_ULTRA",
                    "/orchestration/parent/effort",
                    "Manual routing cannot use an Ultra parent.",
                )
            parent_key = (parent["model"], parent["family"], parent["effort"])
            parent_runtime_entry = self._runtime_pairs().get(parent_key)
            if parent_runtime_entry is None:
                self.error(
                    "PARENT_RUNTIME_PAIR_UNAVAILABLE",
                    "/orchestration/parent",
                    f"Parent pair {parent_key} is not in the runtime catalog.",
                )
            elif parent["integrator_class"] not in parent_runtime_entry["eligible_work_classes"]:
                self.error(
                    "PARENT_RUNTIME_CLASS_MISMATCH",
                    "/orchestration/parent/integrator_class",
                    f"Parent runtime pair does not declare '{parent['integrator_class']}' eligibility.",
                )

        family_class_ceiling = {"luna": "structured", "terra": "general"}
        ceiling = family_class_ceiling.get(parent["family"])
        if ceiling is not None and parent["integrator_class"] in CLASS_RANK:
            if CLASS_RANK[parent["integrator_class"]] > CLASS_RANK[ceiling]:
                self.error(
                    "PARENT_FAMILY_CLASS_MISMATCH",
                    "/orchestration/parent/integrator_class",
                    f"Parent family '{parent['family']}' cannot claim integrator class '{parent['integrator_class']}'.",
                )

        parent_family_diagnostic = _model_family_diagnostic(parent["model"], parent["family"])
        if parent_family_diagnostic is not None and parent["model"] != "unknown":
            self.error(
                "PARENT_MODEL_FAMILY_MISMATCH",
                "/orchestration/parent/family",
                parent_family_diagnostic,
            )

        limit = self.plan["runtime"]["max_concurrent_children"]
        if child_count and limit is None:
            self.error(
                "RUNTIME_LIMIT_UNKNOWN",
                "/runtime/max_concurrent_children",
                "Manual child routing requires a known child concurrency limit.",
            )

    def _validate_dependencies(self) -> None:
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in self.nodes_by_id}
        indegree: dict[str, int] = {node_id: 0 for node_id in self.nodes_by_id}

        for node_id, node in self.nodes_by_id.items():
            for dep in node["depends_on"]:
                if dep == node_id:
                    self.error(
                        "DAG_SELF_DEPENDENCY",
                        self._node_path(node_id, "depends_on"),
                        f"Node '{node_id}' depends on itself.",
                        node_id,
                    )
                    self.cycle_nodes.add(node_id)
                    continue
                if dep not in self.nodes_by_id:
                    self.error(
                        "DAG_UNKNOWN_DEPENDENCY",
                        self._node_path(node_id, "depends_on"),
                        f"Dependency '{dep}' does not exist.",
                        node_id,
                    )
                    continue
                adjacency[dep].append(node_id)
                indegree[node_id] += 1

        queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
        visited: list[str] = []
        while queue:
            current = queue.popleft()
            visited.append(current)
            for successor in sorted(adjacency[current]):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    queue.append(successor)

        if len(visited) != len(self.nodes_by_id):
            cyclic = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
            self.cycle_nodes.update(cyclic)
            self.error(
                "DAG_CYCLE",
                "/nodes",
                f"Dependency graph contains a cycle involving: {', '.join(cyclic)}.",
                related=cyclic,
            )

        for node_id, node in self.nodes_by_id.items():
            if node_id in self.cycle_nodes:
                continue
            for dep in node["depends_on"]:
                if dep in self.nodes_by_id and dep not in self.cycle_nodes:
                    if self.nodes_by_id[dep]["wave"] >= node["wave"]:
                        self.error(
                            "DAG_WAVE_ORDER",
                            self._node_path(node_id, "wave"),
                            f"Dependency '{dep}' must be in an earlier wave than '{node_id}'.",
                            node_id,
                            (dep,),
                        )

    def _is_reachable(self, start: str, target: str) -> bool:
        stack = [start]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(
                node_id
                for node_id, node in self.nodes_by_id.items()
                if current in node["depends_on"]
            )
        return False

    def _validate_concurrency_and_conflicts(self) -> None:
        waves: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for node in self.nodes:
            waves[node["wave"]].append(node)

        limit = self.plan["runtime"]["max_concurrent_children"]
        if limit is not None:
            for wave, members in sorted(waves.items()):
                if len(members) > limit:
                    self.error(
                        "CONCURRENCY_LIMIT_EXCEEDED",
                        "/nodes",
                        f"Wave {wave} has {len(members)} children, exceeding limit {limit}.",
                        related=(node["id"] for node in members),
                    )

        writers = [node for node in self.nodes if node["access_mode"] != "read_only"]
        for node in writers:
            node_id = node["id"]
            if not node["owned_mutable_surfaces"]:
                self.error(
                    "WRITE_SURFACE_MISSING",
                    self._node_path(node_id, "owned_mutable_surfaces"),
                    "A write node must declare at least one mutable surface.",
                    node_id,
                )
            if not node["write_conflict_groups"]:
                self.error(
                    "WRITE_CONFLICT_GROUP_MISSING",
                    self._node_path(node_id, "write_conflict_groups"),
                    "A write node must declare at least one semantic conflict group.",
                    node_id,
                )
            for index, surface in enumerate(node["owned_mutable_surfaces"]):
                surface_path = self._node_path(node_id, f"owned_mutable_surfaces/{index}")
                if any(character in surface for character in "*?[]"):
                    self.error(
                        "SURFACE_GLOB_UNSUPPORTED",
                        surface_path,
                        "Mutable surfaces must be canonical paths/resources, not globs.",
                        node_id,
                    )
                if surface != surface.strip():
                    self.error(
                        "SURFACE_NONCANONICAL_WHITESPACE",
                        surface_path,
                        "Mutable surfaces may not contain leading or trailing whitespace.",
                        node_id,
                    )
                normalized_input = surface.strip().replace("\\", "/")
                if re.match(r"^[A-Za-z]:[^/]", normalized_input):
                    self.error(
                        "SURFACE_DRIVE_RELATIVE_UNSUPPORTED",
                        surface_path,
                        "Drive-relative paths are ambiguous; use an absolute drive path or a repository-relative path.",
                        node_id,
                    )
                segments = [segment for segment in normalized_input.split("/") if segment]
                if "." in segments or ".." in segments:
                    self.error(
                        "SURFACE_NONCANONICAL",
                        surface_path,
                        "Mutable surface contains '.' or '..'; declare its canonical form.",
                        node_id,
                    )
                surface_kind, _ = _surface_kind_and_value(surface)
                if surface_kind == "path":
                    is_drive_path = re.match(r"^[A-Za-z]:/", normalized_input) is not None
                    path_segments = [segment for segment in normalized_input.split("/") if segment]
                    for segment_index, segment in enumerate(path_segments):
                        if is_drive_path and segment_index == 0:
                            continue
                        if segment.endswith((".", " ")):
                            self.error(
                                "SURFACE_WINDOWS_TRAILING_ALIAS",
                                surface_path,
                                "Path segments may not end in a dot or space because Win32 aliases them.",
                                node_id,
                            )
                            break
                        if ":" in segment:
                            self.error(
                                "SURFACE_WINDOWS_ADS_UNSUPPORTED",
                                surface_path,
                                "Windows alternate-data-stream path syntax is not a supported mutable surface.",
                                node_id,
                            )
                            break

        for left_index, left in enumerate(writers):
            for right in writers[left_index + 1 :]:
                shared_surfaces = {
                    f"{left_surface} <-> {right_surface}"
                    for left_surface in left["owned_mutable_surfaces"]
                    for right_surface in right["owned_mutable_surfaces"]
                    if _surfaces_overlap(left_surface, right_surface)
                }
                left_groups = {group.strip().casefold() for group in left["write_conflict_groups"]}
                right_groups = {group.strip().casefold() for group in right["write_conflict_groups"]}
                shared_groups = left_groups & right_groups
                if not shared_surfaces and not shared_groups:
                    continue
                overlap = sorted(shared_surfaces | shared_groups)
                left_id, right_id = left["id"], right["id"]
                if left["wave"] == right["wave"]:
                    self.error(
                        "WRITE_CONFLICT_OVERLAP",
                        self._node_path(right_id, "write_conflict_groups"),
                        f"Parallel writers '{left_id}' and '{right_id}' overlap on {overlap}.",
                        right_id,
                        (left_id,),
                    )
                elif not self._is_reachable(left_id, right_id) and not self._is_reachable(right_id, left_id):
                    self.error(
                        "WRITE_CONFLICT_UNORDERED",
                        self._node_path(right_id, "depends_on"),
                        f"Writers '{left_id}' and '{right_id}' overlap on {overlap} without a dependency order.",
                        right_id,
                        (left_id,),
                    )

    def _validate_pair_for_node(
        self,
        node_id: str,
        node: dict[str, Any],
        pair: dict[str, Any],
        path: str,
        runtime_pairs: dict[tuple[str, str, str], dict[str, Any]],
        source: str,
        minimum_effort: str,
        allow_runtime_unavailable: bool = False,
    ) -> bool:
        source_code = source.upper()
        key = _pair_key(pair)
        valid = True
        family_diagnostic = _model_family_diagnostic(pair["model"], pair["family"])
        if family_diagnostic is not None:
            valid = False
            self.error(
                f"{source_code}_MODEL_FAMILY_MISMATCH",
                f"{path}/family",
                family_diagnostic,
                node_id,
            )
        if pair["effort"] == "ultra":
            valid = False
            self.error(
                "CHILD_ULTRA_FORBIDDEN",
                f"{path}/effort",
                "Explicit child nodes and their candidates may not use Ultra.",
                node_id,
            )
        if _policy_denied(pair):
            valid = False
            self.error(
                f"{source_code}_POLICY_DENIED",
                path,
                "V2-certified plans exclude Luna below xhigh, Terra below high, and all child Ultra pairs.",
                node_id,
            )
        if pair["effort"] in EFFORT_RANK and EFFORT_RANK[pair["effort"]] < EFFORT_RANK[minimum_effort]:
            valid = False
            self.error(
                f"{source_code}_BELOW_MINIMUM_EFFORT",
                f"{path}/effort",
                f"Pair effort '{pair['effort']}' is below derived minimum '{minimum_effort}'.",
                node_id,
            )

        runtime_entry = runtime_pairs.get(key)
        if runtime_entry is None:
            if not allow_runtime_unavailable:
                valid = False
                self.error(
                    f"{source_code}_RUNTIME_PAIR_UNAVAILABLE",
                    path,
                    f"Pair {key} is not in the runtime catalog.",
                    node_id,
                )
        elif node["work_class"] not in runtime_entry["eligible_work_classes"]:
            valid = False
            self.error(
                f"{source_code}_WORK_CLASS_MISMATCH",
                path,
                f"Runtime pair does not declare eligibility for work class '{node['work_class']}'.",
                node_id,
            )
        elif node["risk"] in {"high", "irreversible"} and "critical" not in runtime_entry["eligible_work_classes"]:
            valid = False
            self.error(
                f"{source_code}_RISK_ELIGIBILITY_MISMATCH",
                path,
                "High/irreversible-risk work requires a runtime pair that declares critical-work eligibility.",
                node_id,
            )

        family = pair["family"]
        if family == "luna" and node["work_class"] != "structured":
            valid = False
            self.error(
                f"{source_code}_LUNA_WORK_CLASS_MISMATCH",
                path,
                "Luna is eligible only for structured work in V2.",
                node_id,
            )
        if family == "terra" and node["work_class"] in {"open", "critical"}:
            valid = False
            self.error(
                f"{source_code}_TERRA_WORK_CLASS_MISMATCH",
                path,
                "Terra is not eligible for open or critical work in V2.",
                node_id,
            )
        if family == "luna" and node["oracle"] not in {"deterministic", "strong"}:
            valid = False
            self.error(
                f"{source_code}_LUNA_ORACLE_INSUFFICIENT",
                path,
                "Luna requires a deterministic or strong acceptance oracle.",
                node_id,
            )
        if family == "luna" and node["risk"] in {"high", "irreversible"}:
            valid = False
            self.error(
                f"{source_code}_LUNA_HIGH_RISK",
                path,
                "Luna may not own high or irreversible risk work.",
                node_id,
            )
        if family == "terra" and node["risk"] in {"high", "irreversible"}:
            valid = False
            self.error(
                f"{source_code}_TERRA_HIGH_RISK",
                path,
                "Terra may not own high or irreversible risk work in V2.",
                node_id,
            )
        if family == "luna" and node["access_mode"] != "read_only":
            if node["context_scope"] != "bounded" or node["oracle"] not in {"deterministic", "strong"}:
                valid = False
                self.error(
                    f"{source_code}_LUNA_WRITE_NOT_BOUNDED",
                    path,
                    "Luna writes require bounded context and a deterministic or strong oracle.",
                    node_id,
                )
        if node["role"] == "reviewer" and family != "sol":
            valid = False
            self.error(
                f"{source_code}_REVIEWER_SOL_REQUIRED",
                path,
                "Independent reviewer candidates must use the Sol family.",
                node_id,
            )
        return valid

    def _pair_has_policy_rejection(
        self,
        node: dict[str, Any],
        pair: dict[str, Any],
        runtime_pairs: dict[tuple[str, str, str], dict[str, Any]],
        minimum_effort: str,
    ) -> bool:
        key = _pair_key(pair)
        if key is None or _model_family_diagnostic(pair["model"], pair["family"]) is not None:
            return False
        if _policy_denied(pair):
            return True
        if EFFORT_RANK[pair["effort"]] < EFFORT_RANK[minimum_effort]:
            return True

        runtime_entry = runtime_pairs.get(key)
        if runtime_entry is None:
            return False
        if node["work_class"] not in runtime_entry["eligible_work_classes"]:
            return True
        if node["risk"] in {"high", "irreversible"} and "critical" not in runtime_entry["eligible_work_classes"]:
            return True

        family = pair["family"]
        if family == "luna":
            if node["work_class"] != "structured":
                return True
            if node["oracle"] not in {"deterministic", "strong"}:
                return True
            if node["risk"] in {"high", "irreversible"}:
                return True
            if node["access_mode"] != "read_only" and node["context_scope"] != "bounded":
                return True
        if family == "terra" and (
            node["work_class"] in {"open", "critical"}
            or node["risk"] in {"high", "irreversible"}
        ):
            return True
        return node["role"] == "reviewer" and family != "sol"

    def _validate_selection(self) -> None:
        runtime_pairs = self._runtime_pairs()
        parent = self.plan["orchestration"]["parent"]

        for index, runtime_pair in enumerate(self.plan["runtime"]["available_pairs"]):
            family_diagnostic = _model_family_diagnostic(runtime_pair["model"], runtime_pair["family"])
            if family_diagnostic is not None:
                self.error(
                    "RUNTIME_MODEL_FAMILY_MISMATCH",
                    f"/runtime/available_pairs/{index}/family",
                    family_diagnostic,
                )

        for node_id, node in self.nodes_by_id.items():
            path = self._node_path(node_id)
            requirements = node["requirements"]
            selection = node["selection"]
            selected = selection["selected_pair"]
            selected_key = _pair_key(selected)
            allowed_pairs = requirements["allowed_model_effort_pairs"]
            fallback_pairs = requirements["fallback_pairs"]
            allowed = {_pair_key(pair) for pair in allowed_pairs}
            fallback = {_pair_key(pair) for pair in fallback_pairs}
            allow_luna_max_unavailable = (
                self.plan.get("child_policy", "adaptive") == "luna_max_only"
                and node["lifecycle_state"] in {"planned", "dispatch_blocked"}
            )

            derived_class, derived_child_effort, derived_integrator_effort = _derived_contract_floors(node)
            declared_class = requirements["required_integrator_class"]
            declared_child_effort = requirements["minimum_child_effort"]
            declared_integrator_effort = requirements["minimum_integrator_effort"]

            if node["risk"] in {"high", "irreversible"} and node["work_class"] != "critical":
                self.error(
                    "DERIVED_WORK_CLASS_UNDERDECLARED",
                    f"{path}/work_class",
                    (
                        f"Risk '{node['risk']}' requires work_class='critical'; "
                        f"got '{node['work_class']}'."
                    ),
                    node_id,
                )

            if CLASS_RANK[declared_class] < CLASS_RANK[derived_class]:
                self.error(
                    "DERIVED_REQUIRED_INTEGRATOR_CLASS_UNDERDECLARED",
                    f"{path}/requirements/required_integrator_class",
                    (
                        f"Declared class '{declared_class}' is below the derived '{derived_class}' floor "
                        f"for work_class='{node['work_class']}', risk='{node['risk']}'."
                    ),
                    node_id,
                )
            if EFFORT_RANK[declared_child_effort] < EFFORT_RANK[derived_child_effort]:
                self.error(
                    "DERIVED_MINIMUM_CHILD_EFFORT_UNDERDECLARED",
                    f"{path}/requirements/minimum_child_effort",
                    (
                        f"Declared effort '{declared_child_effort}' is below the derived "
                        f"'{derived_child_effort}' floor for work_class='{node['work_class']}', "
                        f"risk='{node['risk']}'."
                    ),
                    node_id,
                )
            if EFFORT_RANK[declared_integrator_effort] < EFFORT_RANK[derived_integrator_effort]:
                self.error(
                    "DERIVED_MINIMUM_INTEGRATOR_EFFORT_UNDERDECLARED",
                    f"{path}/requirements/minimum_integrator_effort",
                    (
                        f"Declared effort '{declared_integrator_effort}' is below the derived "
                        f"'{derived_integrator_effort}' floor for work_class='{node['work_class']}', "
                        f"risk='{node['risk']}'."
                    ),
                    node_id,
                )

            effective_child_effort = max(
                (declared_child_effort, derived_child_effort),
                key=EFFORT_RANK.__getitem__,
            )
            effective_integrator_class = max(
                (declared_class, derived_class),
                key=CLASS_RANK.__getitem__,
            )
            effective_integrator_effort = max(
                (declared_integrator_effort, derived_integrator_effort),
                key=EFFORT_RANK.__getitem__,
            )

            for pair_index, pair in enumerate(allowed_pairs):
                self._validate_pair_for_node(
                    node_id,
                    node,
                    pair,
                    f"{path}/requirements/allowed_model_effort_pairs/{pair_index}",
                    runtime_pairs,
                    "allowed",
                    effective_child_effort,
                    allow_luna_max_unavailable
                    and _pair_key(pair) == LUNA_MAX_PAIR_KEY,
                )

            for pair_index, pair in enumerate(fallback_pairs):
                pair_path = f"{path}/requirements/fallback_pairs/{pair_index}"
                if _pair_key(pair) not in allowed:
                    self.error(
                        "FALLBACK_PAIR_NOT_ALLOWED",
                        pair_path,
                        "Every fallback pair must also be in allowed_model_effort_pairs.",
                        node_id,
                    )
                self._validate_pair_for_node(
                    node_id,
                    node,
                    pair,
                    pair_path,
                    runtime_pairs,
                    "fallback",
                    effective_child_effort,
                    allow_luna_max_unavailable
                    and _pair_key(pair) == LUNA_MAX_PAIR_KEY,
                )

            selected_valid = self._validate_pair_for_node(
                node_id,
                node,
                selected,
                f"{path}/selection/selected_pair",
                runtime_pairs,
                "selected",
                effective_child_effort,
                allow_luna_max_unavailable
                and selected_key == LUNA_MAX_PAIR_KEY,
            )
            if selected_key not in allowed:
                selected_valid = False
                self.error(
                    "SELECTED_PAIR_NOT_ALLOWED",
                    f"{path}/selection/selected_pair",
                    "Selected pair is not in allowed_model_effort_pairs.",
                    node_id,
                )

            origin = selection["origin"]
            requested = selection["requested_pair"]
            requested_key = _pair_key(requested)
            if requested is not None:
                requested_family_diagnostic = _model_family_diagnostic(
                    requested["model"], requested["family"]
                )
                if requested_family_diagnostic is not None:
                    selected_valid = False
                    self.error(
                        "REQUESTED_MODEL_FAMILY_MISMATCH",
                        f"{path}/selection/requested_pair/family",
                        requested_family_diagnostic,
                        node_id,
                    )
                if _policy_denied(requested):
                    selected_valid = False
                    self.error(
                        "REQUESTED_POLICY_DENIED",
                        f"{path}/selection/requested_pair",
                        "A V2 plan may not embed Luna below xhigh, Terra below high, or a child Ultra request.",
                        node_id,
                    )
            if origin == "fallback":
                if requested_key is None or selection["fallback_reason"] is None:
                    selected_valid = False
                    self.error(
                        "FALLBACK_REQUEST_MISSING",
                        f"{path}/selection",
                        "Fallback selection requires requested_pair and fallback_reason.",
                        node_id,
                    )
                if requested_key == selected_key:
                    selected_valid = False
                    self.error(
                        "FALLBACK_NO_CHANGE",
                        f"{path}/selection/selected_pair",
                        "Fallback selected the same pair that was requested.",
                        node_id,
                    )
                if selected_key not in fallback:
                    selected_valid = False
                    self.error(
                        "FALLBACK_SELECTION_NOT_ENUMERATED",
                        f"{path}/selection/selected_pair",
                        "Fallback selection must be explicitly listed in fallback_pairs.",
                        node_id,
                    )
                if (
                    requested_key is not None
                    and selection["fallback_reason"] == "unavailable"
                    and requested_key in runtime_pairs
                ):
                    selected_valid = False
                    self.error(
                        "FALLBACK_REASON_FALSE_UNAVAILABLE",
                        f"{path}/selection/fallback_reason",
                        f"Requested pair {requested_key} is present in the runtime catalog.",
                        node_id,
                    )
                if (
                    requested is not None
                    and selection["fallback_reason"] == "policy_rejection"
                    and not self._pair_has_policy_rejection(
                        node,
                        requested,
                        runtime_pairs,
                        effective_child_effort,
                    )
                ):
                    selected_valid = False
                    self.error(
                        "FALLBACK_REASON_FALSE_POLICY_REJECTION",
                        f"{path}/selection/fallback_reason",
                        "The requested pair does not violate a deterministic V2 policy or semantic floor.",
                        node_id,
                    )
            elif origin == "explicit_user":
                if requested_key is None:
                    selected_valid = False
                    self.error(
                        "EXPLICIT_REQUEST_MISSING",
                        f"{path}/selection/requested_pair",
                        "Explicit user selection requires requested_pair.",
                        node_id,
                    )
                elif requested_key != selected_key:
                    selected_valid = False
                    self.error(
                        "EXPLICIT_REQUEST_CHANGED",
                        f"{path}/selection/selected_pair",
                        "Explicit user selection must preserve the requested pair; use fallback origin for substitutions.",
                        node_id,
                    )
            elif selection["requested_pair"] is not None:
                selected_valid = False
                self.error(
                    "UNEXPECTED_REQUESTED_PAIR",
                    f"{path}/selection/requested_pair",
                    f"Selection origin '{origin}' must not include requested_pair.",
                    node_id,
                )
            if origin == "inherited":
                parent_key = (parent["model"], parent["family"], parent["effort"])
                if selected_key != parent_key:
                    selected_valid = False
                    self.error(
                        "INHERITED_PAIR_MISMATCH",
                        f"{path}/selection/selected_pair",
                        f"Inherited selected pair {selected_key} does not match parent pair {parent_key}.",
                        node_id,
                    )
            if origin != "fallback" and selection["fallback_reason"] is not None:
                selected_valid = False
                self.error(
                    "NON_FALLBACK_REASON_PRESENT",
                    f"{path}/selection/fallback_reason",
                    "fallback_reason is only valid for origin 'fallback'.",
                    node_id,
                )
            if parent["integrator_class"] in CLASS_RANK:
                if CLASS_RANK[parent["integrator_class"]] < CLASS_RANK[effective_integrator_class]:
                    self.error(
                        "PARENT_INTEGRATOR_CLASS_INSUFFICIENT",
                        f"{path}/requirements/required_integrator_class",
                        (
                            f"Parent integrator class '{parent['integrator_class']}' is below the "
                            f"effective '{effective_integrator_class}' floor."
                        ),
                        node_id,
                    )
            if parent["effort"] in EFFORT_RANK:
                if EFFORT_RANK[parent["effort"]] < EFFORT_RANK[effective_integrator_effort]:
                    self.error(
                        "PARENT_INTEGRATOR_EFFORT_INSUFFICIENT",
                        f"{path}/requirements/minimum_integrator_effort",
                        (
                            f"Parent effort '{parent['effort']}' is below the effective "
                            f"'{effective_integrator_effort}' floor."
                        ),
                        node_id,
                    )
            self.selected_pair_valid[node_id] = selected_valid

    def _validate_observability(self) -> None:
        ledger_phase = self.plan["ledger_phase"]
        parent = self.plan["orchestration"]["parent"]
        parent_pair = {
            "model": parent["model"],
            "family": parent["family"],
            "effort": parent["effort"],
        }
        seen_receipt_refs: dict[str, tuple[str, int]] = {}

        states = {node["lifecycle_state"] for node in self.nodes}
        if ledger_phase == "planning" and states - {"planned"}:
            self.error(
                "LEDGER_PLANNING_STATE_MISMATCH",
                "/ledger_phase",
                "A planning ledger may contain only planned nodes.",
            )
        if ledger_phase == "active" and self.nodes and states == {"planned"}:
            self.error(
                "LEDGER_ACTIVE_WITHOUT_DISPATCH",
                "/ledger_phase",
                "An active ledger must contain at least one dispatched or terminal node.",
            )
        if ledger_phase == "finalized" and states & {"planned", "dispatched"}:
            self.error(
                "LEDGER_FINALIZED_WITH_OPEN_NODE",
                "/ledger_phase",
                "A finalized ledger may contain only completed or dispatch_blocked nodes.",
            )

        for node_id, node in self.nodes_by_id.items():
            path = self._node_path(node_id)
            lifecycle_state = node["lifecycle_state"]
            dispatch = node["dispatch"]
            result = node["result"]
            selection = node["selection"]
            selected_pair = selection["selected_pair"]
            selected_key = _pair_key(selected_pair)

            if lifecycle_state == "planned":
                if dispatch is not None:
                    self.error(
                        "PLANNED_NODE_HAS_DISPATCH",
                        f"{path}/dispatch",
                        "A planned node must not claim a runtime dispatch receipt.",
                        node_id,
                    )
                if result is not None:
                    self.error(
                        "PLANNED_NODE_HAS_RESULT",
                        f"{path}/result",
                        "A planned node cannot contain a child result attestation.",
                        node_id,
                    )
                continue

            if dispatch is None:
                self.error(
                    "DISPATCH_RECORD_MISSING",
                    f"{path}/dispatch",
                    f"Lifecycle state '{lifecycle_state}' requires a dispatch record.",
                    node_id,
                )
                continue

            attempts = dispatch["attempts"]
            effective_attempt_number = dispatch["effective_attempt"]
            accepted_attempts: list[dict[str, Any]] = []
            attempts_by_number: dict[int, dict[str, Any]] = {}

            for position, attempt in enumerate(attempts, start=1):
                attempt_path = f"{path}/dispatch/attempts/{position - 1}"
                attempt_number = attempt["attempt_index"]
                requested_pair = attempt["requested_pair"]
                requested_key = _pair_key(requested_pair)
                mode = attempt["mode"]
                receipt_status = attempt["receipt_status"]
                confirmation_status = attempt["confirmation_status"]

                if attempt_number != position:
                    self.error(
                        "DISPATCH_ATTEMPT_SEQUENCE_INVALID",
                        f"{attempt_path}/attempt_index",
                        f"Expected attempt_index {position}, got {attempt_number}.",
                        node_id,
                    )
                attempts_by_number[attempt_number] = attempt

                family_diagnostic = _model_family_diagnostic(
                    requested_pair["model"], requested_pair["family"]
                )
                if family_diagnostic is not None:
                    self.error(
                        "DISPATCH_REQUEST_MODEL_FAMILY_MISMATCH",
                        f"{attempt_path}/requested_pair/family",
                        family_diagnostic,
                        node_id,
                    )

                expected_task_name = _expected_task_name(node_id, attempt_number, requested_pair)
                if attempt["task_name"] != expected_task_name:
                    self.error(
                        "DISPATCH_TASK_NAME_MISMATCH",
                        f"{attempt_path}/task_name",
                        f"Expected pair-first task_name '{expected_task_name}' so the model and effort survive right-side UI truncation.",
                        node_id,
                    )
                expected_agent_label = _expected_agent_label(node["role"], requested_pair)
                if attempt["agent_label"] != expected_agent_label:
                    self.error(
                        "DISPATCH_AGENT_LABEL_MISMATCH",
                        f"{attempt_path}/agent_label",
                        f"Expected agent_label '{expected_agent_label}'.",
                        node_id,
                    )

                receipt_ref = attempt["receipt_ref"]
                if (
                    not isinstance(receipt_ref, str)
                    or not receipt_ref.strip()
                    or _contains_invisible_or_control(receipt_ref)
                    or not RECEIPT_REF_RE.fullmatch(receipt_ref)
                ):
                    self.error(
                        "DISPATCH_RECEIPT_REF_MISSING",
                        f"{attempt_path}/receipt_ref",
                        "Every attempted spawn requires a visible 'spawn_agent:<reference>' receipt or rejection reference.",
                        node_id,
                    )
                elif receipt_ref in seen_receipt_refs:
                    previous_node, previous_attempt = seen_receipt_refs[receipt_ref]
                    self.error(
                        "DISPATCH_RECEIPT_REF_DUPLICATE",
                        f"{attempt_path}/receipt_ref",
                        (
                            f"Receipt reference '{receipt_ref}' is already used by "
                            f"node '{previous_node}' attempt {previous_attempt}."
                        ),
                        node_id,
                        (previous_node,),
                    )
                else:
                    seen_receipt_refs[receipt_ref] = (node_id, attempt_number)

                model_set = attempt["model"] is not None
                effort_set = attempt["reasoning_effort"] is not None
                if mode == "explicit":
                    if not model_set or not effort_set:
                        self.error(
                            "DISPATCH_EXPLICIT_PAIR_INCOMPLETE",
                            attempt_path,
                            "Explicit dispatch must supply both model and reasoning_effort; a model-only default is unresolved.",
                            node_id,
                        )
                    else:
                        if attempt["model"] != requested_pair["model"]:
                            self.error(
                                "DISPATCH_MODEL_ARGUMENT_MISMATCH",
                                f"{attempt_path}/model",
                                "The spawn model argument must match requested_pair.model.",
                                node_id,
                            )
                        if attempt["reasoning_effort"] != requested_pair["effort"]:
                            self.error(
                                "DISPATCH_EFFORT_ARGUMENT_MISMATCH",
                                f"{attempt_path}/reasoning_effort",
                                "The spawn reasoning_effort argument must match requested_pair.effort.",
                                node_id,
                            )
                    if attempt["fork_turns"] == "all":
                        self.error(
                            "DISPATCH_EXPLICIT_FULL_HISTORY_FORBIDDEN",
                            f"{attempt_path}/fork_turns",
                            "Full-history forks inherit the parent pair and cannot carry explicit overrides.",
                            node_id,
                        )
                    if selection["origin"] == "inherited":
                        self.error(
                            "INHERITED_SELECTION_NOT_INHERITED_DISPATCH",
                            f"{attempt_path}/mode",
                            "An inherited selection must use inherit_parent dispatch mode.",
                            node_id,
                        )
                else:
                    if model_set or effort_set:
                        self.error(
                            "DISPATCH_INHERIT_OVERRIDE_PRESENT",
                            attempt_path,
                            "inherit_parent dispatch must omit both model and reasoning_effort.",
                            node_id,
                        )
                    if attempt["fork_turns"] != "all":
                        self.error(
                            "DISPATCH_INHERIT_REQUIRES_FULL_HISTORY",
                            f"{attempt_path}/fork_turns",
                            "Verified inheritance requires the full-history fork guaranteed by the current collaboration contract.",
                            node_id,
                        )
                    if requested_key != _pair_key(parent_pair):
                        self.error(
                            "DISPATCH_INHERITED_PARENT_MISMATCH",
                            f"{attempt_path}/requested_pair",
                            "Inherited dispatch requested_pair must exactly match the known parent pair.",
                            node_id,
                        )
                    if selection["origin"] != "inherited":
                        self.error(
                            "INHERITED_DISPATCH_ORIGIN_MISMATCH",
                            f"{path}/selection/origin",
                            "inherit_parent dispatch requires selection.origin='inherited'.",
                            node_id,
                        )

                if confirmation_status in {"default-unresolved", "inherited-unresolved"}:
                    self.unresolved_dispatch_count += 1
                    self.error(
                        "UNRESOLVED_DISPATCH_FORBIDDEN",
                        f"{attempt_path}/confirmation_status",
                        "Unresolved model/effort status may be recorded for audit but cannot form a valid V2 dispatch.",
                        node_id,
                    )

                if receipt_status == "rejected":
                    if attempt["effective_pair"] is not None:
                        self.error(
                            "REJECTED_DISPATCH_HAS_EFFECTIVE_PAIR",
                            f"{attempt_path}/effective_pair",
                            "A rejected spawn cannot claim an effective pair.",
                            node_id,
                        )
                    if confirmation_status != "runtime-rejected":
                        self.error(
                            "REJECTED_DISPATCH_STATUS_MISMATCH",
                            f"{attempt_path}/confirmation_status",
                            "A rejected spawn must use confirmation_status='runtime-rejected'.",
                            node_id,
                        )
                    continue

                accepted_attempts.append(attempt)
                if position != len(attempts):
                    self.error(
                        "ACCEPTED_DISPATCH_NOT_LAST",
                        f"{attempt_path}/receipt_status",
                        "Rejected attempts may precede acceptance, but no attempt may follow the accepted child.",
                        node_id,
                    )
                effective_pair = attempt["effective_pair"]
                if effective_pair is None:
                    self.error(
                        "ACCEPTED_DISPATCH_EFFECTIVE_PAIR_MISSING",
                        f"{attempt_path}/effective_pair",
                        "An accepted spawn must record its effective model and effort.",
                        node_id,
                    )
                    continue
                if _pair_key(effective_pair) != requested_key:
                    self.error(
                        "DISPATCH_EFFECTIVE_PAIR_MISMATCH",
                        f"{attempt_path}/effective_pair",
                        "The effective pair must match the exact accepted explicit pair or known inherited pair.",
                        node_id,
                    )
                expected_confirmation = (
                    "fallback-confirmed"
                    if selection["origin"] == "fallback"
                    else "confirmed-inherited"
                    if mode == "inherit_parent"
                    else "confirmed-explicit"
                )
                if confirmation_status != expected_confirmation:
                    self.error(
                        "ACCEPTED_DISPATCH_CONFIRMATION_MISMATCH",
                        f"{attempt_path}/confirmation_status",
                        f"Expected confirmation_status='{expected_confirmation}'.",
                        node_id,
                    )

            if len(accepted_attempts) > 1:
                self.error(
                    "MULTIPLE_ACCEPTED_DISPATCHES",
                    f"{path}/dispatch/attempts",
                    "A node represents one spawned child and may have at most one accepted dispatch.",
                    node_id,
                )

            effective_attempt = (
                attempts_by_number.get(effective_attempt_number)
                if isinstance(effective_attempt_number, int)
                else None
            )
            if effective_attempt_number is not None and effective_attempt is None:
                self.error(
                    "EFFECTIVE_ATTEMPT_UNKNOWN",
                    f"{path}/dispatch/effective_attempt",
                    "effective_attempt must reference an existing dispatch attempt.",
                    node_id,
                )
            if effective_attempt is not None and effective_attempt["receipt_status"] != "accepted":
                self.error(
                    "EFFECTIVE_ATTEMPT_NOT_ACCEPTED",
                    f"{path}/dispatch/effective_attempt",
                    "effective_attempt must reference the accepted spawn receipt.",
                    node_id,
                )
            if accepted_attempts and effective_attempt not in accepted_attempts:
                self.error(
                    "ACCEPTED_DISPATCH_NOT_EFFECTIVE",
                    f"{path}/dispatch/effective_attempt",
                    "The accepted spawn must be selected as effective_attempt.",
                    node_id,
                )
            if not accepted_attempts and effective_attempt_number is not None:
                self.error(
                    "EFFECTIVE_ATTEMPT_WITHOUT_ACCEPTANCE",
                    f"{path}/dispatch/effective_attempt",
                    "No runtime-accepted spawn exists for effective_attempt.",
                    node_id,
                )

            if effective_attempt is not None and effective_attempt["effective_pair"] is not None:
                if _pair_key(effective_attempt["effective_pair"]) != selected_key:
                    self.error(
                        "DISPATCH_SELECTION_MISMATCH",
                        f"{path}/dispatch/effective_attempt",
                        "The runtime-effective pair must match selection.selected_pair.",
                        node_id,
                    )
                if effective_attempt["confirmation_status"] in {
                    "confirmed-explicit",
                    "confirmed-inherited",
                    "fallback-confirmed",
                }:
                    self.confirmed_child_count += 1

            if selection["origin"] != "fallback":
                for attempt in attempts:
                    if _pair_key(attempt["requested_pair"]) != selected_key:
                        self.error(
                            "NON_FALLBACK_DISPATCH_PAIR_CHANGED",
                            f"{path}/dispatch/attempts",
                            "Only a fallback selection may attempt a pair different from selected_pair.",
                            node_id,
                        )
                        break
            else:
                original_key = _pair_key(selection["requested_pair"])
                for attempt in attempts:
                    attempt_key = _pair_key(attempt["requested_pair"])
                    if attempt_key not in {original_key, selected_key}:
                        self.error(
                            "FALLBACK_DISPATCH_PAIR_UNDECLARED",
                            f"{path}/dispatch/attempts",
                            "Fallback attempts may reference only selection.requested_pair or selection.selected_pair.",
                            node_id,
                        )
                        break

            if lifecycle_state in {"dispatched", "completed"}:
                if effective_attempt is None or effective_attempt["receipt_status"] != "accepted":
                    self.error(
                        "NODE_ACCEPTED_DISPATCH_MISSING",
                        f"{path}/dispatch/effective_attempt",
                        f"Lifecycle state '{lifecycle_state}' requires one accepted effective dispatch.",
                        node_id,
                    )
            if lifecycle_state == "dispatch_blocked":
                self.dispatch_blocked_count += 1
                if accepted_attempts or effective_attempt_number is not None:
                    self.error(
                        "DISPATCH_BLOCKED_HAS_ACCEPTANCE",
                        f"{path}/dispatch",
                        "dispatch_blocked requires all attempts to be rejected and no effective_attempt.",
                        node_id,
                    )
                if result is not None:
                    self.error(
                        "DISPATCH_BLOCKED_HAS_RESULT",
                        f"{path}/result",
                        "A child that was never spawned cannot return a result attestation.",
                        node_id,
                    )

            if lifecycle_state == "dispatched" and result is not None:
                self.error(
                    "DISPATCHED_NODE_HAS_RESULT",
                    f"{path}/result",
                    "Move the node to completed before recording its result attestation.",
                    node_id,
                )
            if lifecycle_state == "completed":
                if result is None:
                    self.error(
                        "COMPLETED_NODE_RESULT_MISSING",
                        f"{path}/result",
                        "A completed node requires the child's routing attestation.",
                        node_id,
                    )
                elif effective_attempt is not None:
                    if result["dispatch_attempt"] != effective_attempt_number:
                        self.error(
                            "RESULT_ATTEMPT_MISMATCH",
                            f"{path}/result/dispatch_attempt",
                            "The result must identify the effective dispatch attempt.",
                            node_id,
                        )
                    if result["agent_label"] != effective_attempt["agent_label"]:
                        self.error(
                            "RESULT_AGENT_LABEL_MISMATCH",
                            f"{path}/result/agent_label",
                            "The child-returned label must echo the effective dispatch label.",
                            node_id,
                        )
                    if _pair_key(result["assigned_pair_echo"]) != _pair_key(
                        effective_attempt["effective_pair"]
                    ):
                        self.error(
                            "RESULT_PAIR_ECHO_MISMATCH",
                            f"{path}/result/assigned_pair_echo",
                            "The child-assigned pair echo disagrees with the runtime-effective pair.",
                            node_id,
                        )
                    if (
                        result["confirmation_status_echo"]
                        != effective_attempt["confirmation_status"]
                    ):
                        self.error(
                            "RESULT_CONFIRMATION_ECHO_MISMATCH",
                            f"{path}/result/confirmation_status_echo",
                            "The child confirmation-status echo disagrees with the dispatch receipt.",
                            node_id,
                        )
            elif lifecycle_state != "dispatch_blocked" and result is not None:
                self.error(
                    "RESULT_WITHOUT_COMPLETED_STATE",
                    f"{path}/result",
                    "Only a completed node may contain a child result attestation.",
                    node_id,
                )

    def _validate_evidence_and_review(self) -> None:
        reviewers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in self.nodes:
            if node["role"] == "reviewer":
                for reviewed in node.get("review_of", []):
                    reviewers[reviewed].append(node)

        reviewer_contract_valid: dict[str, bool] = {}
        for node_id, node in self.nodes_by_id.items():
            path = self._node_path(node_id)
            steps = node["validation_steps"]
            for step_index, step in enumerate(steps):
                if step["kind"] == "pre_state" and step["phase"] != "pre":
                    self.error(
                        "VALIDATION_PHASE_MISMATCH",
                        f"{path}/validation_steps/{step_index}/phase",
                        "pre_state validation must use phase 'pre'.",
                        node_id,
                    )
                if step["kind"] == "post_state" and step["phase"] != "post":
                    self.error(
                        "VALIDATION_PHASE_MISMATCH",
                        f"{path}/validation_steps/{step_index}/phase",
                        "post_state validation must use phase 'post'.",
                        node_id,
                    )
            if not steps:
                self.error(
                    "NODE_VALIDATION_MISSING",
                    f"{path}/validation_steps",
                    "Every delegated node requires at least one validation step.",
                    node_id,
                )
            if not node["acceptance_criteria"]:
                self.error(
                    "NODE_ACCEPTANCE_MISSING",
                    f"{path}/acceptance_criteria",
                    "Every delegated node requires acceptance criteria.",
                    node_id,
                )

            if node["access_mode"] != "read_only":
                required_post = any(
                    step["required"]
                    and step["phase"] == "post"
                    and step["kind"] in WRITE_POST_VALIDATION_KINDS
                    for step in steps
                )
                if not required_post:
                    self.error(
                        "WRITE_POST_VALIDATION_MISSING",
                        f"{path}/validation_steps",
                        "A write node requires at least one required post-validation step.",
                        node_id,
                    )
                if node["risk"] == "irreversible" and not node.get("recovery_steps"):
                    self.error(
                        "IRREVERSIBLE_RECOVERY_MISSING",
                        f"{path}/recovery_steps",
                        "Irreversible work requires explicit recovery or rollback steps.",
                        node_id,
                    )

            if node["role"] == "reviewer":
                contract_valid = self.selected_pair_valid.get(node_id, False)
                if node["work_class"] != "critical":
                    contract_valid = False
                    self.error(
                        "REVIEWER_WORK_CLASS_INVALID",
                        f"{path}/work_class",
                        "Reviewer work_class must be 'critical'.",
                        node_id,
                    )
                if node["risk"] != "high":
                    contract_valid = False
                    self.error(
                        "REVIEWER_RISK_INVALID",
                        f"{path}/risk",
                        "Reviewer risk must be declared as 'high'.",
                        node_id,
                    )
                if node["oracle"] != "strong":
                    contract_valid = False
                    self.error(
                        "REVIEWER_ORACLE_INSUFFICIENT",
                        f"{path}/oracle",
                        "Reviewer oracle must be 'strong'.",
                        node_id,
                    )
                if node["access_mode"] != "read_only":
                    contract_valid = False
                    self.error(
                        "REVIEWER_NOT_READ_ONLY",
                        f"{path}/access_mode",
                        "Reviewer must use read_only access mode.",
                        node_id,
                    )
                if node["owned_mutable_surfaces"] or node["write_conflict_groups"]:
                    contract_valid = False
                    self.error(
                        "REVIEWER_MUTABLE_OWNERSHIP",
                        path,
                        "Reviewer may not own mutable surfaces or write conflict groups.",
                        node_id,
                    )
                control = node.get("read_only_control")
                if not control or control.get("declared") is not True:
                    contract_valid = False
                    self.error(
                        "REVIEWER_CONTROL_MISSING",
                        f"{path}/read_only_control",
                        "Reviewer must declare a read-only enforcement control.",
                        node_id,
                    )
                elif control["enforcement"] == "instruction_pre_post_check":
                    has_pre = any(
                        step["required"] and step["phase"] == "pre" and step["kind"] == "pre_state"
                        for step in steps
                    )
                    has_post = any(
                        step["required"] and step["phase"] == "post" and step["kind"] == "post_state"
                        for step in steps
                    )
                    if not has_pre or not has_post:
                        contract_valid = False
                        self.error(
                            "REVIEWER_GUARD_MISSING",
                            f"{path}/validation_steps",
                            "Instruction-only reviewer requires required pre_state and post_state guards.",
                            node_id,
                        )
                    self.warn(
                        "REVIEWER_INSTRUCTION_ONLY",
                        f"{path}/read_only_control/enforcement",
                        "Read-only is prompt-constrained, not sandbox-enforced.",
                        node_id,
                    )
                reviewer_contract_valid[node_id] = contract_valid

                for reviewed in node.get("review_of", []):
                    if reviewed not in self.nodes_by_id:
                        self.error(
                            "REVIEW_UNKNOWN_TARGET",
                            f"{path}/review_of",
                            f"Reviewer target '{reviewed}' does not exist.",
                            node_id,
                        )
                        continue
                    reviewed_node = self.nodes_by_id[reviewed]
                    if node["executor_id"] == reviewed_node["executor_id"]:
                        self.error(
                            "REVIEWER_EXECUTOR_NOT_INDEPENDENT",
                            f"{path}/executor_id",
                            f"Reviewer and reviewed node '{reviewed}' must use different executors.",
                            node_id,
                            (reviewed,),
                        )
                    if not self._is_reachable(reviewed, node_id):
                        self.error(
                            "REVIEW_ORDER_MISSING",
                            f"{path}/depends_on",
                            f"Reviewer must be downstream of reviewed node '{reviewed}'.",
                            node_id,
                            (reviewed,),
                        )

        for node_id, node in self.nodes_by_id.items():
            if node["role"] == "reviewer" or node["risk"] not in {"high", "irreversible"}:
                continue
            qualified_reviewers = [
                reviewer
                for reviewer in reviewers.get(node_id, [])
                if reviewer_contract_valid.get(reviewer["id"], False)
                and reviewer["executor_id"] != node["executor_id"]
                and self._is_reachable(node_id, reviewer["id"])
            ]
            if not qualified_reviewers:
                self.error(
                    "HIGH_RISK_REVIEW_MISSING",
                    self._node_path(node_id),
                    "Every high/irreversible-risk node requires a qualified downstream independent Sol reviewer.",
                    node_id,
                )

    def _economy_candidate_keys(self, node: dict[str, Any]) -> list[tuple[str, str, str]]:
        origin = node["selection"]["origin"]
        source_pairs = (
            node["requirements"]["fallback_pairs"]
            if origin == "fallback"
            else node["requirements"]["allowed_model_effort_pairs"]
        )
        return [key for pair in source_pairs if (key := _pair_key(pair)) is not None]

    def _validate_economy_profile(self) -> None:
        profile = self.plan["profile"]
        metric_source = self.plan["metric_source"]

        for node_id, node in self.nodes_by_id.items():
            path = self._node_path(node_id)
            evaluation = node.get("economy_evaluation")
            origin = node["selection"]["origin"]

            if profile != "economy":
                if evaluation is not None:
                    self.error(
                        "ECONOMY_EVALUATION_UNEXPECTED",
                        f"{path}/economy_evaluation",
                        "economy_evaluation is valid only when profile='economy'.",
                        node_id,
                    )
                continue

            if origin in {"explicit_user", "inherited"}:
                if evaluation is not None:
                    self.error(
                        "ECONOMY_EVALUATION_NOT_APPLICABLE",
                        f"{path}/economy_evaluation",
                        (
                            f"Selection origin '{origin}' constrains the pair outside economy ranking; "
                            "omit economy_evaluation so the report cannot imply that cost selected it."
                        ),
                        node_id,
                    )
                self.warn(
                    "ECONOMY_PROFILE_BYPASSED_BY_SELECTION_ORIGIN",
                    f"{path}/selection/origin",
                    f"Selection origin '{origin}' bypasses economy pair ranking for this node.",
                    node_id,
                )
                continue

            if evaluation is None:
                self.error(
                    "ECONOMY_EVALUATION_REQUIRED",
                    f"{path}/economy_evaluation",
                    (
                        "Automatic and fallback selections under profile='economy' require an auditable "
                        "qualitative or quantitative economy_evaluation."
                    ),
                    node_id,
                )
                continue

            rationale = evaluation["rationale"]
            if (
                rationale != rationale.strip()
                or _contains_invisible_or_control(rationale)
                or not _has_visible_base(rationale)
            ):
                self.error(
                    "ECONOMY_RATIONALE_INVALID",
                    f"{path}/economy_evaluation/rationale",
                    "Economy rationale must contain visible text without surrounding whitespace or control characters.",
                    node_id,
                )

            if evaluation["delegation_decision"] != "delegate":
                self.error(
                    "ECONOMY_DELEGATION_DECISION_INVALID",
                    f"{path}/economy_evaluation/delegation_decision",
                    (
                        "A node in the child ledger must have delegation_decision='delegate'. "
                        "Keep parent-preferred work out of nodes."
                    ),
                    node_id,
                )

            expected_keys = self._economy_candidate_keys(node)
            expected_set = set(expected_keys)
            selected_key = _pair_key(node["selection"]["selected_pair"])
            mode = evaluation["mode"]

            if mode == "qualitative":
                for field_name in (
                    "formula_version",
                    "cost_unit",
                    "cohort_id",
                    "parent_estimate",
                ):
                    if evaluation[field_name] is not None:
                        self.error(
                            "ECONOMY_QUALITATIVE_FIELD_INVALID",
                            f"{path}/economy_evaluation/{field_name}",
                            f"Qualitative economy evaluation requires {field_name}=null.",
                            node_id,
                        )
                if metric_source in {"runtime", "local_telemetry"}:
                    self.error(
                        "ECONOMY_QUALITATIVE_SOURCE_INVALID",
                        "/metric_source",
                        (
                            f"metric_source '{metric_source}' represents comparable measurements and "
                            "requires mode='quantitative'. Use none/community_prior when no comparable "
                            "numeric cost evidence exists."
                        ),
                        node_id,
                    )
                if evaluation["candidate_estimates"]:
                    self.error(
                        "ECONOMY_QUALITATIVE_ESTIMATES_FORBIDDEN",
                        f"{path}/economy_evaluation/candidate_estimates",
                        "Qualitative evaluation cannot include numeric candidate estimates.",
                        node_id,
                    )
                if evaluation["tie_break"] != "declared_order":
                    self.error(
                        "ECONOMY_QUALITATIVE_TIE_BREAK_INVALID",
                        f"{path}/economy_evaluation/tie_break",
                        "Qualitative evaluation requires tie_break='declared_order'.",
                        node_id,
                    )
                order_keys = [
                    key
                    for candidate in evaluation["qualitative_order"]
                    if (key := _pair_key(candidate)) is not None
                ]
                if len(order_keys) != len(expected_keys) or set(order_keys) != expected_set:
                    self.error(
                        "ECONOMY_QUALITATIVE_CANDIDATE_SET_MISMATCH",
                        f"{path}/economy_evaluation/qualitative_order",
                        (
                            "Qualitative order must contain every economy-ranked candidate exactly once. "
                            f"Expected {sorted(expected_set)}, got {sorted(set(order_keys))}."
                        ),
                        node_id,
                    )
                if not order_keys or order_keys[0] != selected_key:
                    self.error(
                        "ECONOMY_QUALITATIVE_SELECTED_NOT_FIRST",
                        f"{path}/economy_evaluation/qualitative_order",
                        "The selected pair must be first in the declared qualitative economy order.",
                        node_id,
                    )
                self.warn(
                    "ECONOMY_QUALITATIVE_EVALUATION",
                    f"{path}/economy_evaluation/mode",
                    "Economy ordering is qualitative; do not claim a measured cost optimum.",
                    node_id,
                )
                continue

            if metric_source not in {"runtime", "local_telemetry"}:
                self.error(
                    "ECONOMY_QUANTITATIVE_SOURCE_INSUFFICIENT",
                    "/metric_source",
                    (
                        "Quantitative economy evaluation requires comparable runtime or local_telemetry data; "
                        f"metric_source is '{metric_source}'."
                    ),
                    node_id,
                )
            if evaluation["formula_version"] != ECONOMY_FORMULA_VERSION:
                self.error(
                    "ECONOMY_FORMULA_VERSION_INVALID",
                    f"{path}/economy_evaluation/formula_version",
                    f"Quantitative economy evaluation requires '{ECONOMY_FORMULA_VERSION}'.",
                    node_id,
                )
            for field_name in ("cost_unit", "cohort_id"):
                value = evaluation[field_name]
                if (
                    not isinstance(value, str)
                    or value != value.strip()
                    or _contains_invisible_or_control(value)
                    or not _has_visible_base(value)
                ):
                    self.error(
                        "ECONOMY_QUANTITATIVE_FIELD_REQUIRED",
                        f"{path}/economy_evaluation/{field_name}",
                        f"Quantitative economy evaluation requires a visible {field_name} string.",
                        node_id,
                    )
            parent_estimate = evaluation["parent_estimate"]
            if not isinstance(parent_estimate, dict):
                self.error(
                    "ECONOMY_QUANTITATIVE_FIELD_REQUIRED",
                    f"{path}/economy_evaluation/parent_estimate",
                    "Quantitative economy evaluation requires a complete parent_estimate cost vector.",
                    node_id,
                )
            if evaluation["tie_break"] != "pair_key_lexicographic":
                self.error(
                    "ECONOMY_QUANTITATIVE_TIE_BREAK_INVALID",
                    f"{path}/economy_evaluation/tie_break",
                    "Quantitative evaluation requires tie_break='pair_key_lexicographic'.",
                    node_id,
                )
            if evaluation["qualitative_order"]:
                self.error(
                    "ECONOMY_QUANTITATIVE_ORDER_FORBIDDEN",
                    f"{path}/economy_evaluation/qualitative_order",
                    "Quantitative evaluation must derive ranking from candidate estimates, not a declared order.",
                    node_id,
                )

            estimates = evaluation["candidate_estimates"]
            estimate_keys = [
                key for estimate in estimates if (key := _pair_key(estimate["pair"])) is not None
            ]
            if len(estimate_keys) != len(expected_keys) or set(estimate_keys) != expected_set:
                self.error(
                    "ECONOMY_CANDIDATE_SET_MISMATCH",
                    f"{path}/economy_evaluation/candidate_estimates",
                    (
                        "Quantitative estimates must cover every economy-ranked candidate exactly once. "
                        f"Expected {sorted(expected_set)}, got {sorted(set(estimate_keys))}."
                    ),
                    node_id,
                )

            root_evidence = self.plan["evidence_id_or_window"]
            evidence_prefix = f"{root_evidence}#" if isinstance(root_evidence, str) else None
            seen_evidence_refs: set[str] = set()

            def validate_evidence_ref(evidence_ref: str, evidence_path: str, subject: str) -> None:
                if (
                    evidence_ref != evidence_ref.strip()
                    or _contains_invisible_or_control(evidence_ref)
                    or not _has_visible_base(evidence_ref)
                ):
                    self.error(
                        "ECONOMY_EVIDENCE_REF_INVALID",
                        evidence_path,
                        f"{subject} evidence_ref must contain visible text without surrounding whitespace or control characters.",
                        node_id,
                    )
                if evidence_prefix is not None and (
                    not evidence_ref.startswith(evidence_prefix)
                    or len(evidence_ref) == len(evidence_prefix)
                ):
                    self.error(
                        "ECONOMY_EVIDENCE_WINDOW_MISMATCH",
                        evidence_path,
                        (
                            f"{subject} evidence_ref must be namespaced under the root evidence window "
                            f"as '{evidence_prefix}<record-id>'."
                        ),
                        node_id,
                    )
                if evidence_ref in seen_evidence_refs:
                    self.error(
                        "ECONOMY_EVIDENCE_REF_DUPLICATE",
                        evidence_path,
                        f"Economy evidence_ref '{evidence_ref}' is reused within the node evaluation.",
                        node_id,
                    )
                seen_evidence_refs.add(evidence_ref)

            parent_total: Decimal | None = None
            if isinstance(parent_estimate, dict):
                parent_path = f"{path}/economy_evaluation/parent_estimate"
                actual_parent = self.plan["orchestration"]["parent"]
                actual_parent_key = (
                    actual_parent["model"],
                    actual_parent["family"],
                    actual_parent["effort"],
                )
                parent_key = _pair_key(parent_estimate["pair"])
                if parent_key != actual_parent_key:
                    self.error(
                        "ECONOMY_PARENT_PAIR_MISMATCH",
                        f"{parent_path}/pair",
                        (
                            f"Parent estimate pair {parent_key} does not match the actual orchestration "
                            f"parent pair {actual_parent_key}."
                        ),
                        node_id,
                    )
                validate_evidence_ref(
                    parent_estimate["evidence_ref"],
                    f"{parent_path}/evidence_ref",
                    "Parent",
                )
                parent_total = _economy_expected_total(parent_estimate)
                parent_declared_total = Decimal(str(parent_estimate["expected_total_cost"])).quantize(
                    ECONOMY_QUANTUM,
                    rounding=ROUND_HALF_EVEN,
                )
                if parent_total != parent_declared_total:
                    self.error(
                        "ECONOMY_PARENT_TOTAL_MISMATCH",
                        f"{parent_path}/expected_total_cost",
                        (
                            f"Declared parent expected_total_cost {parent_declared_total} does not match "
                            f"the '{ECONOMY_FORMULA_VERSION}' result {parent_total}."
                        ),
                        node_id,
                    )

            totals: dict[tuple[str, str, str], Decimal] = {}
            for estimate_index, estimate in enumerate(estimates):
                estimate_path = f"{path}/economy_evaluation/candidate_estimates/{estimate_index}"
                key = _pair_key(estimate["pair"])
                evidence_ref = estimate["evidence_ref"]
                validate_evidence_ref(
                    evidence_ref,
                    f"{estimate_path}/evidence_ref",
                    "Candidate",
                )
                computed_total = _economy_expected_total(estimate)
                declared_total = Decimal(str(estimate["expected_total_cost"])).quantize(
                    ECONOMY_QUANTUM,
                    rounding=ROUND_HALF_EVEN,
                )
                if computed_total != declared_total:
                    self.error(
                        "ECONOMY_TOTAL_MISMATCH",
                        f"{estimate_path}/expected_total_cost",
                        (
                            f"Declared expected_total_cost {declared_total} does not match the "
                            f"'{ECONOMY_FORMULA_VERSION}' result {computed_total}."
                        ),
                        node_id,
                    )
                if key is not None:
                    totals[key] = computed_total

            if selected_key in totals and totals:
                minimum_total = min(totals.values())
                tied_minima = sorted(key for key, total in totals.items() if total == minimum_total)
                deterministic_winner = tied_minima[0]
                if selected_key != deterministic_winner:
                    self.error(
                        "ECONOMY_SELECTED_NOT_MINIMUM",
                        f"{path}/selection/selected_pair",
                        (
                            f"Selected pair {selected_key} is not the deterministic minimum-cost candidate; "
                            f"expected {deterministic_winner} at {minimum_total}."
                        ),
                        node_id,
                    )
                selected_cost = totals[selected_key]
                if parent_total is not None and selected_cost >= parent_total:
                    self.error(
                        "ECONOMY_DELEGATION_NOT_BENEFICIAL",
                        f"{path}/economy_evaluation/parent_estimate/expected_total_cost",
                        (
                            f"Selected child expected cost {selected_cost} is not lower than parent "
                            f"expected cost {parent_total}; keep this work in the parent."
                        ),
                        node_id,
                    )

    def _validate_metric_claim(self) -> None:
        profile = self.plan["profile"]
        source = self.plan["metric_source"]
        metric_as_of = self.plan["metric_as_of"]
        evidence_id_or_window = self.plan["evidence_id_or_window"]
        if source == "none":
            if metric_as_of is not None:
                self.error(
                    "METRIC_AS_OF_WITHOUT_SOURCE",
                    "/metric_as_of",
                    "metric_as_of must be null when metric_source is 'none'.",
                )
            if evidence_id_or_window is not None:
                self.error(
                    "METRIC_EVIDENCE_WITHOUT_SOURCE",
                    "/evidence_id_or_window",
                    "evidence_id_or_window must be null when metric_source is 'none'.",
                )
        else:
            if not isinstance(metric_as_of, str) or not metric_as_of.strip():
                self.error(
                    "METRIC_AS_OF_REQUIRED",
                    "/metric_as_of",
                    f"metric_source '{source}' requires a non-empty metric_as_of value.",
                )
            elif not _valid_metric_as_of(metric_as_of):
                self.error(
                    "METRIC_AS_OF_INVALID",
                    "/metric_as_of",
                    "metric_as_of must be an ISO 8601 date or a timezone-aware timestamp.",
                )
            if not isinstance(evidence_id_or_window, str) or not evidence_id_or_window.strip():
                self.error(
                    "METRIC_EVIDENCE_REQUIRED",
                    "/evidence_id_or_window",
                    f"metric_source '{source}' requires a non-empty evidence_id_or_window value.",
                )
            elif (
                _contains_invisible_or_control(evidence_id_or_window)
                or not _has_visible_base(evidence_id_or_window)
            ):
                self.error(
                    "METRIC_EVIDENCE_INVALID",
                    "/evidence_id_or_window",
                    "evidence_id_or_window must contain a visible base character and no invisible/control characters.",
                )
        if profile in {"latency", "economy"} and source in {"community_prior", "none"}:
            self.warn(
                "QUALITATIVE_OPTIMIZATION_ONLY",
                "/metric_source",
                f"Profile '{profile}' lacks runtime/local telemetry; do not claim quantitative optimization.",
            )

    def validate(self) -> tuple[list[Issue], list[Issue], dict[str, Any]]:
        self._build_index()
        if any(issue.code == "NODE_ID_DUPLICATE" for issue in self.errors):
            wave_counts = Counter(node["wave"] for node in self.nodes)
            stats = {
                "node_count": len(self.nodes),
                "manual_child_count": len(self.nodes),
                "max_child_wave_width": max(wave_counts.values(), default=0),
                "confirmed_child_count": 0,
                "unresolved_dispatch_count": 0,
                "dispatch_blocked_count": 0,
            }
            return _sort_issues(self.errors), [], stats
        self._validate_orchestration()
        self._validate_dependencies()
        self._validate_concurrency_and_conflicts()
        self._validate_child_policy()
        self._validate_selection()
        self._validate_economy_profile()
        self._validate_observability()
        self._validate_evidence_and_review()
        self._validate_metric_claim()
        wave_counts = Counter(node["wave"] for node in self.nodes)
        stats = {
            "node_count": len(self.nodes),
            "manual_child_count": len(self.nodes),
            "max_child_wave_width": max(wave_counts.values(), default=0),
            "confirmed_child_count": self.confirmed_child_count,
            "unresolved_dispatch_count": self.unresolved_dispatch_count,
            "dispatch_blocked_count": self.dispatch_blocked_count,
        }
        return _sort_issues(self.errors), _sort_issues(self.warnings), stats


def validate_plan(plan: Any) -> tuple[int, dict[str, Any]]:
    structural_errors = StructureValidator().validate(plan)
    if structural_errors:
        return 2, {
            "valid": False,
            "errors": [issue.as_dict() for issue in structural_errors],
            "warnings": [],
            "stats": {
                "node_count": 0,
                "manual_child_count": 0,
                "max_child_wave_width": 0,
                "confirmed_child_count": 0,
                "unresolved_dispatch_count": 0,
                "dispatch_blocked_count": 0,
            },
        }

    semantic_errors, warnings, stats = SemanticValidator(plan).validate()
    return (3 if semantic_errors else 0), {
        "valid": not semantic_errors,
        "errors": [issue.as_dict() for issue in semantic_errors],
        "warnings": [issue.as_dict() for issue in warnings],
        "stats": stats,
    }


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_routing_report(plan: dict[str, Any]) -> str:
    """Render the mandatory user-visible per-child routing receipt table."""
    headers = (
        "agent",
        "role",
        "requested pair",
        "effective pair",
        "confirmation",
        "receipt",
        "result",
        "purpose",
    )
    rows: list[tuple[str, ...]] = []
    for node in plan["nodes"]:
        dispatch = node["dispatch"]
        attempts = dispatch["attempts"] if dispatch is not None else []
        attempt_by_number = {
            attempt["attempt_index"]: attempt for attempt in attempts
        }
        effective_attempt = attempt_by_number.get(
            dispatch["effective_attempt"] if dispatch is not None else None
        )
        shown_attempt = effective_attempt or (attempts[-1] if attempts else None)
        receipt_chain = "; ".join(
            (
                (f"e{attempt['event_seq']} " if "event_seq" in attempt else "")
                + f"a{attempt['attempt_index']} {attempt['receipt_status']} {attempt['receipt_ref']}"
            )
            for attempt in attempts
        )
        requested_pair = node["selection"]["requested_pair"] or node["selection"]["selected_pair"]
        if node["result"] is not None:
            result_status = node["result"]["status"]
            failure_classification = node["result"].get("failure_classification")
            if failure_classification not in {None, "none"}:
                result_status = f"{result_status}/{failure_classification}"
            result_text = (
                f"{result_status} (e{node['result']['event_seq']})"
                if "event_seq" in node["result"]
                else result_status
            )
        else:
            result_text = node["lifecycle_state"]
        rows.append(
            (
                shown_attempt["agent_label"] if shown_attempt is not None else "not dispatched",
                node["role"],
                _pair_text(requested_pair),
                _pair_text(effective_attempt["effective_pair"])
                if effective_attempt is not None
                else "—",
                shown_attempt["confirmation_status"] if shown_attempt is not None else "planned",
                receipt_chain or "—",
                result_text,
                node["objective"],
            )
    )
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_markdown_cell(value) for value in row) + " |"
        for row in rows
    )
    lines.extend(
        [
            "",
            f"Profile: `{plan['profile']}`",
            f"Metric source: `{plan['metric_source']}`",
            f"Child policy: `{plan.get('child_policy', 'adaptive')}`",
        ]
    )
    if plan["metric_source"] != "none":
        lines.append(
            "Metric evidence: "
            f"`{plan['metric_as_of']}` / `{plan['evidence_id_or_window']}`"
        )
    elif plan["profile"] in {"latency", "economy"}:
        lines.append("Optimization claim: qualitative only; no quantitative metric source.")

    if plan["profile"] == "economy":
        economy_headers = (
            "node",
            "mode",
            "selected pair",
            "child expected cost",
            "parent expected cost",
            "unit",
            "decision",
            "basis",
        )
        economy_rows: list[tuple[Any, ...]] = []
        for node in plan["nodes"]:
            evaluation = node.get("economy_evaluation")
            selected_pair = node["selection"]["selected_pair"]
            if evaluation is None:
                economy_rows.append(
                    (
                        node["id"],
                        f"bypassed:{node['selection']['origin']}",
                        _pair_text(selected_pair),
                        "—",
                        "—",
                        "—",
                        "constrained",
                        "Profile did not select this pair.",
                    )
                )
                continue
            selected_key = _pair_key(selected_pair)
            selected_estimate = next(
                (
                    estimate
                    for estimate in evaluation["candidate_estimates"]
                    if _pair_key(estimate["pair"]) == selected_key
                ),
                None,
            )
            economy_rows.append(
                (
                    node["id"],
                    evaluation["mode"],
                    _pair_text(selected_pair),
                    selected_estimate["expected_total_cost"]
                    if selected_estimate is not None
                    else "qualitative",
                    evaluation["parent_estimate"]["expected_total_cost"]
                    if evaluation["parent_estimate"] is not None
                    else "—",
                    evaluation["cost_unit"] if evaluation["cost_unit"] is not None else "—",
                    evaluation["delegation_decision"],
                    evaluation["rationale"],
                )
            )
        lines.extend(
            [
                "",
                "Economy decisions:",
                "| " + " | ".join(economy_headers) + " |",
                "| " + " | ".join("---" for _ in economy_headers) + " |",
            ]
        )
        lines.extend(
            "| " + " | ".join(_markdown_cell(value) for value in row) + " |"
            for row in economy_rows
        )
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="Path to an Adaptive Agent Routing V2 JSON ledger.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON output.")
    parser.add_argument(
        "--report",
        action="store_true",
        help="After successful finalized-ledger validation, emit the mandatory Markdown routing report.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        with args.plan.open("r", encoding="utf-8") as handle:
            plan = json.load(handle, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, json.JSONDecodeError, DuplicateJSONKeyError) as exc:
        result = {
            "valid": False,
            "errors": [
                {
                    "code": "JSON_INPUT_ERROR",
                    "path": str(args.plan),
                    "message": str(exc),
                }
            ],
            "warnings": [],
            "stats": {
                "node_count": 0,
                "manual_child_count": 0,
                "max_child_wave_width": 0,
                "confirmed_child_count": 0,
                "unresolved_dispatch_count": 0,
                "dispatch_blocked_count": 0,
            },
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":") if args.compact else None, indent=None if args.compact else 2))
        return 2

    try:
        exit_code, result = validate_plan(plan)
    except Exception as exc:  # Defensive CLI boundary; semantic code is covered by tests.
        result = {
            "valid": False,
            "errors": [
                {
                    "code": "VALIDATOR_INTERNAL_ERROR",
                    "path": "",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            ],
            "warnings": [],
            "stats": {
                "node_count": 0,
                "manual_child_count": 0,
                "max_child_wave_width": 0,
                "confirmed_child_count": 0,
                "unresolved_dispatch_count": 0,
                "dispatch_blocked_count": 0,
            },
        }
        exit_code = 4

    if args.report and exit_code == 0:
        if plan["ledger_phase"] != "finalized":
            result = {
                "valid": False,
                "errors": [
                    {
                        "code": "REPORT_LEDGER_NOT_FINALIZED",
                        "path": "/ledger_phase",
                        "message": "The user-visible routing report requires ledger_phase='finalized'.",
                    }
                ],
                "warnings": [],
                "stats": result["stats"],
            }
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":") if args.compact else None,
                    indent=None if args.compact else 2,
                )
            )
            return 3
        print(render_routing_report(plan))
        return 0

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":") if args.compact else None, indent=None if args.compact else 2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
