from __future__ import annotations

import copy
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate-routing-plan.py"
DOCUMENTED_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1] / "references" / "routing-plan.example.json"
)
SPEC = importlib.util.spec_from_file_location("validate_routing_plan", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def pair(model: str, family: str, effort: str) -> dict[str, str]:
    return {"model": model, "family": family, "effort": effort}


def runtime_pair(model: str, family: str, effort: str, classes: list[str]) -> dict[str, object]:
    return {
        "model": model,
        "family": family,
        "effort": effort,
        "eligible_work_classes": classes,
    }


ALL_CLASSES = ["structured", "general", "open", "critical"]


def task_slug(model: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")


def accepted_explicit_dispatch(
    node: dict[str, object],
    selected: dict[str, str] | None = None,
    *,
    confirmation_status: str | None = None,
    receipt_ref: str = "spawn_agent:agent-001",
    event_seq: int = 1,
) -> dict[str, object]:
    selected_pair = selected or node["selection"]["selected_pair"]  # type: ignore[index]
    origin = node["selection"]["origin"]  # type: ignore[index]
    confirmation = confirmation_status or (
        "fallback-confirmed" if origin == "fallback" else "confirmed-explicit"
    )
    node_id = node["id"]
    role = node["role"]
    return {
        "attempts": [
            {
                "attempt_index": 1,
                "event_seq": event_seq,
                "mode": "explicit",
                "task_name": f"{task_slug(selected_pair['model'])}_{selected_pair['effort']}_{node_id}_a1",
                "agent_label": f"{role} ({selected_pair['model']}, {selected_pair['effort']})",
                "fork_turns": "none",
                "requested_pair": copy.deepcopy(selected_pair),
                "model": selected_pair["model"],
                "reasoning_effort": selected_pair["effort"],
                "receipt_status": "accepted",
                "receipt_ref": receipt_ref,
                "effective_pair": copy.deepcopy(selected_pair),
                "confirmation_status": confirmation,
            }
        ],
        "effective_attempt": 1,
    }


def complete_node_with_explicit_dispatch(
    node: dict[str, object],
    *,
    receipt_ref: str = "spawn_agent:agent-001",
    dispatch_event_seq: int = 1,
    result_event_seq: int = 2,
) -> None:
    dispatch = accepted_explicit_dispatch(
        node,
        receipt_ref=receipt_ref,
        event_seq=dispatch_event_seq,
    )
    attempt = dispatch["attempts"][0]  # type: ignore[index]
    node["lifecycle_state"] = "completed"
    node["dispatch"] = dispatch
    node["result"] = {
        "status": "success",
        "event_seq": result_event_seq,
        "failure_classification": "none",
        "failure_evidence": [],
        "dispatch_attempt": 1,
        "agent_label": attempt["agent_label"],
        "assigned_pair_echo": copy.deepcopy(attempt["effective_pair"]),
        "confirmation_status_echo": attempt["confirmation_status"],
    }


def mark_transient_failure(node: dict[str, object], evidence: str = "One-off process termination.") -> None:
    result = node["result"]  # type: ignore[assignment]
    result["status"] = "failed"  # type: ignore[index]
    result["failure_classification"] = "transient"  # type: ignore[index]
    result["failure_evidence"] = [evidence]  # type: ignore[index]


def base_node() -> dict[str, object]:
    luna_xhigh = pair("gpt-5.6-luna", "luna", "xhigh")
    terra_high = pair("gpt-5.6-terra", "terra", "high")
    sol_high = pair("gpt-5.6-sol", "sol", "high")
    return {
        "id": "json_convert",
        "executor_id": "executor_json_convert",
        "wave": 0,
        "role": "structured_operator",
        "objective": "Convert a bounded JSON batch and verify the output schema.",
        "why_delegate": "The batch is bounded and has a deterministic schema oracle.",
        "work_class": "structured",
        "risk": "low",
        "context_scope": "bounded",
        "oracle": "deterministic",
        "access_mode": "read_only",
        "depends_on": [],
        "known_facts": ["The input and output schemas are fixed."],
        "hypotheses": [],
        "owned_mutable_surfaces": [],
        "read_only_surfaces": ["input/batch.json", "schemas/output.json"],
        "write_conflict_groups": [],
        "forbidden_actions": ["Do not modify source data or schemas."],
        "deliverables": ["A schema-conformant conversion report."],
        "acceptance_criteria": ["Every output record validates against the schema."],
        "validation_steps": [
            {"id": "schema_check", "kind": "schema", "phase": "post", "required": True}
        ],
        "expected_evidence": ["Schema validation result for every output record."],
        "attempt_budget": {"transient_retries": 1, "substantive_attempts": 2, "max_uses": 1},
        "recovery_steps": ["Discard generated output and retain the original input."],
        "stop_conditions": ["Stop after the schema check passes or the attempt budget is exhausted."],
        "escalate_when": ["Escalate if the input violates the declared schema."],
        "requirements": {
            "required_integrator_class": "general",
            "minimum_child_effort": "high",
            "minimum_integrator_effort": "high",
            "allowed_model_effort_pairs": [luna_xhigh, terra_high, sol_high],
            "fallback_pairs": [terra_high],
        },
        "selection": {
            "origin": "automatic",
            "requested_pair": None,
            "selected_pair": luna_xhigh,
            "fallback_reason": None,
        },
        "lifecycle_state": "planned",
        "dispatch": None,
        "result": None,
    }


def base_plan() -> dict[str, object]:
    available: list[dict[str, object]] = []
    for effort in ("low", "medium", "high", "xhigh", "max"):
        available.append(runtime_pair("gpt-5.6-luna", "luna", effort, ["structured"]))
        available.append(runtime_pair("gpt-5.6-terra", "terra", effort, ["structured", "general"]))
        available.append(runtime_pair("gpt-5.6-sol", "sol", effort, ALL_CLASSES))
    return {
        "schema_version": "aar.routing-ledger.v2",
        "ledger_phase": "planning",
        "profile": "balanced",
        "child_policy": "adaptive",
        "metric_source": "none",
        "metric_as_of": None,
        "evidence_id_or_window": None,
        "orchestration": {
            "state": "manual_allowed",
            "parent": {
                "model": "gpt-5.6-sol",
                "family": "sol",
                "effort": "xhigh",
                "integrator_class": "critical",
            },
        },
        "runtime": {"max_concurrent_children": 3, "available_pairs": available},
        "nodes": [base_node()],
    }


def luna_max_only_plan() -> dict[str, object]:
    plan = base_plan()
    plan["child_policy"] = "luna_max_only"
    plan["runtime"]["catalog_snapshot"] = {  # type: ignore[index]
        "captured_at": "2026-08-21T00:00:00+08:00",
        "evidence_ref": "collaboration-tool:model-catalog:test-snapshot",
        "available_pairs_sha256": MODULE._runtime_catalog_sha256(  # type: ignore[attr-defined]
            plan["runtime"]["available_pairs"]  # type: ignore[index]
        ),
    }
    node = plan["nodes"][0]  # type: ignore[index]
    luna_max = pair("gpt-5.6-luna", "luna", "max")
    node["requirements"] = {  # type: ignore[index]
        "required_integrator_class": "general",
        "minimum_child_effort": "max",
        "minimum_integrator_effort": "high",
        "allowed_model_effort_pairs": [copy.deepcopy(luna_max)],
        "fallback_pairs": [],
    }
    node["selection"] = {  # type: ignore[index]
        "origin": "automatic",
        "requested_pair": None,
        "selected_pair": copy.deepcopy(luna_max),
        "fallback_reason": None,
    }
    node["attempt_budget"] = {  # type: ignore[index]
        "transient_retries": 1,
        "substantive_attempts": 1,
        "max_uses": 1,
    }
    node["work_unit_id"] = "json_convert"
    node["retry_of"] = None
    node["retry_kind"] = "none"
    return plan


def economy_candidates(node: dict[str, object]) -> list[dict[str, str]]:
    origin = node["selection"]["origin"]  # type: ignore[index]
    field_name = "fallback_pairs" if origin == "fallback" else "allowed_model_effort_pairs"
    return copy.deepcopy(node["requirements"][field_name])  # type: ignore[index,return-value]


def economy_estimate(
    candidate: dict[str, str],
    initial_cost: float,
    *,
    sample_size: int = 12,
    evidence_window: str = "economy-regression-window-001",
    evidence_subject: str = "candidate",
) -> dict[str, object]:
    retry_probability = 0.1
    retry_cost = initial_cost
    rework_probability = 0.05
    rework_cost = initial_cost * 1.5
    review_cost = 0.1
    escalation_probability = 0.02
    escalation_cost = initial_cost * 2.0
    coordination_cost = 0.1
    expected_total = round(
        initial_cost
        + retry_probability * retry_cost
        + rework_probability * rework_cost
        + review_cost
        + escalation_probability * escalation_cost
        + coordination_cost,
        6,
    )
    return {
        "pair": copy.deepcopy(candidate),
        "sample_size": sample_size,
        "evidence_ref": (
            f"{evidence_window}#{evidence_subject}:{candidate['model']}:{candidate['effort']}"
        ),
        "initial_cost": initial_cost,
        "retry_probability": retry_probability,
        "retry_cost_if_triggered": retry_cost,
        "rework_probability": rework_probability,
        "rework_cost_if_triggered": rework_cost,
        "review_cost": review_cost,
        "escalation_probability": escalation_probability,
        "escalation_cost_if_triggered": escalation_cost,
        "coordination_cost": coordination_cost,
        "expected_total_cost": expected_total,
    }


def attach_qualitative_economy(plan: dict[str, object]) -> None:
    plan["profile"] = "economy"
    for node in plan["nodes"]:  # type: ignore[index]
        origin = node["selection"]["origin"]  # type: ignore[index]
        if origin in {"explicit_user", "inherited"}:
            node.pop("economy_evaluation", None)
            continue
        candidates = economy_candidates(node)
        selected = node["selection"]["selected_pair"]  # type: ignore[index]
        ordered = [copy.deepcopy(selected)] + [
            candidate for candidate in candidates if candidate != selected
        ]
        node["economy_evaluation"] = {
            "mode": "qualitative",
            "formula_version": None,
            "cost_unit": None,
            "cohort_id": None,
            "parent_estimate": None,
            "candidate_estimates": [],
            "qualitative_order": ordered,
            "tie_break": "declared_order",
            "delegation_decision": "delegate",
            "rationale": "The bounded child contract is expected to save more work than its coordination overhead.",
        }


def attach_quantitative_economy(plan: dict[str, object]) -> None:
    plan["profile"] = "economy"
    plan["metric_source"] = "local_telemetry"
    plan["metric_as_of"] = "2026-08-21T08:00:00+08:00"
    evidence_window = "economy-regression-window-001"
    plan["evidence_id_or_window"] = evidence_window
    for node in plan["nodes"]:  # type: ignore[index]
        origin = node["selection"]["origin"]  # type: ignore[index]
        if origin in {"explicit_user", "inherited"}:
            node.pop("economy_evaluation", None)
            continue
        candidates = economy_candidates(node)
        selected = node["selection"]["selected_pair"]  # type: ignore[index]
        ordered = [copy.deepcopy(selected)] + [
            candidate for candidate in candidates if candidate != selected
        ]
        estimates = [
            economy_estimate(candidate, 1.0 + index, evidence_window=evidence_window)
            for index, candidate in enumerate(ordered)
        ]
        parent = plan["orchestration"]["parent"]  # type: ignore[index]
        parent_pair = pair(parent["model"], parent["family"], parent["effort"])
        parent_estimate = economy_estimate(
            parent_pair,
            float(len(ordered) + 2),
            evidence_window=evidence_window,
            evidence_subject="parent",
        )
        node["economy_evaluation"] = {
            "mode": "quantitative",
            "formula_version": "expected-total-cost-v1",
            "cost_unit": "normalized-cost-unit",
            "cohort_id": "same-contract-same-tool-surface",
            "parent_estimate": parent_estimate,
            "candidate_estimates": estimates,
            "qualitative_order": [],
            "tie_break": "pair_key_lexicographic",
            "delegation_decision": "delegate",
            "rationale": "Comparable local observations put the selected child below the parent baseline.",
        }


def refresh_catalog_snapshot(plan: dict[str, object]) -> None:
    snapshot = plan["runtime"]["catalog_snapshot"]  # type: ignore[index]
    snapshot["available_pairs_sha256"] = MODULE._runtime_catalog_sha256(  # type: ignore[index,attr-defined]
        plan["runtime"]["available_pairs"]  # type: ignore[index]
    )


def error_codes(result: dict[str, object]) -> set[str]:
    return {item["code"] for item in result["errors"]}  # type: ignore[index]


def warning_codes(result: dict[str, object]) -> set[str]:
    return {item["code"] for item in result["warnings"]}  # type: ignore[index]


def validate(plan: dict[str, object]) -> tuple[int, dict[str, object]]:
    return MODULE.validate_plan(plan)


def make_writer(node_id: str, wave: int = 0) -> dict[str, object]:
    node = base_node()
    node.update(
        {
            "id": node_id,
            "executor_id": f"executor_{node_id}",
            "wave": wave,
            "role": "implementer",
            "objective": f"Implement {node_id}.",
            "work_class": "general",
            "risk": "medium",
            "context_scope": "repository",
            "oracle": "strong",
            "access_mode": "workspace_write",
            "owned_mutable_surfaces": [f"src/{node_id}.ts"],
            "read_only_surfaces": ["tests/"],
            "write_conflict_groups": [f"module:{node_id}"],
            "deliverables": [f"Implemented and validated {node_id}."],
            "acceptance_criteria": ["Target behavior passes."],
            "validation_steps": [
                {"id": "target_test", "kind": "test", "phase": "post", "required": True}
            ],
        }
    )
    terra_high = pair("gpt-5.6-terra", "terra", "high")
    sol_high = pair("gpt-5.6-sol", "sol", "high")
    node["requirements"] = {
        "required_integrator_class": "general",
        "minimum_child_effort": "high",
        "minimum_integrator_effort": "high",
        "allowed_model_effort_pairs": [terra_high, sol_high],
        "fallback_pairs": [sol_high],
    }
    node["selection"] = {
        "origin": "automatic",
        "requested_pair": None,
        "selected_pair": terra_high,
        "fallback_reason": None,
    }
    return node


def make_reviewer(node_id: str, wave: int, review_of: list[str]) -> dict[str, object]:
    node = base_node()
    sol_xhigh = pair("gpt-5.6-sol", "sol", "xhigh")
    node.update(
        {
            "id": node_id,
            "executor_id": f"executor_{node_id}",
            "wave": wave,
            "role": "reviewer",
            "objective": "Review high-risk behavior independently.",
            "work_class": "critical",
            "risk": "high",
            "context_scope": "repository",
            "oracle": "strong",
            "access_mode": "read_only",
            "depends_on": list(review_of),
            "owned_mutable_surfaces": [],
            "read_only_surfaces": ["src/", "tests/"],
            "write_conflict_groups": [],
            "review_of": list(review_of),
            "read_only_control": {"declared": True, "enforcement": "sandbox"},
            "acceptance_criteria": ["Every finding cites a mechanism and evidence."],
            "validation_steps": [
                {"id": "evidence_review", "kind": "evidence_review", "phase": "post", "required": True}
            ],
            "requirements": {
                "required_integrator_class": "critical",
                "minimum_child_effort": "xhigh",
                "minimum_integrator_effort": "xhigh",
                "allowed_model_effort_pairs": [sol_xhigh],
                "fallback_pairs": [],
            },
            "selection": {
                "origin": "automatic",
                "requested_pair": None,
                "selected_pair": sol_xhigh,
                "fallback_reason": None,
            },
        }
    )
    return node


def make_high_risk_writer(node_id: str, wave: int = 0) -> dict[str, object]:
    node = make_writer(node_id, wave)
    sol_xhigh = pair("gpt-5.6-sol", "sol", "xhigh")
    node["work_class"] = "critical"
    node["risk"] = "high"
    node["requirements"] = {
        "required_integrator_class": "critical",
        "minimum_child_effort": "xhigh",
        "minimum_integrator_effort": "xhigh",
        "allowed_model_effort_pairs": [sol_xhigh],
        "fallback_pairs": [],
    }
    node["selection"] = {
        "origin": "automatic",
        "requested_pair": None,
        "selected_pair": sol_xhigh,
        "fallback_reason": None,
    }
    return node


def make_high_risk_reader(node_id: str, wave: int = 0) -> dict[str, object]:
    node = make_high_risk_writer(node_id, wave)
    node.update(
        {
            "role": "diagnostician",
            "objective": f"Inspect high-risk behavior for {node_id} without writing.",
            "access_mode": "read_only",
            "owned_mutable_surfaces": [],
            "read_only_surfaces": ["src/", "config/", "tests/"],
            "write_conflict_groups": [],
        }
    )
    return node


REQUIRED_NODE_FIELDS = {
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


class RoutingPlanValidationTests(unittest.TestCase):
    def test_documented_routing_plan_example_is_valid(self) -> None:
        plan = json.loads(DOCUMENTED_EXAMPLE_PATH.read_text(encoding="utf-8"))
        code, result = validate(plan)
        self.assertEqual(0, code, result)
        self.assertTrue(result["valid"])

    def test_valid_json_batch_plan(self) -> None:
        code, result = validate(base_plan())
        self.assertEqual(0, code)
        self.assertTrue(result["valid"])

    def test_child_policy_defaults_to_adaptive_for_existing_v2_ledgers(self) -> None:
        plan = base_plan()
        del plan["child_policy"]

        code, result = validate(plan)

        self.assertEqual(0, code, result)
    def test_child_policy_rejects_unknown_values(self) -> None:
        cases = (("cheap-ish", "SCHEMA_ENUM"), ("luna-max", "SCHEMA_ENUM"), (None, "SCHEMA_TYPE"))
        for value, expected_code in cases:
            with self.subTest(value=value):
                plan = base_plan()
                plan["child_policy"] = value

                code, result = validate(plan)

                self.assertEqual(2, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_luna_max_only_planning_ledger_is_valid(self) -> None:
        code, result = validate(luna_max_only_plan())

        self.assertEqual(0, code, result)
        self.assertTrue(result["valid"])

    def test_luna_max_only_requires_auditable_retry_metadata(self) -> None:
        for field_name in ("work_unit_id", "retry_of", "retry_kind"):
            with self.subTest(field=field_name):
                plan = luna_max_only_plan()
                del plan["nodes"][0][field_name]  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("CHILD_POLICY_RETRY_METADATA_REQUIRED", error_codes(result))

    def test_luna_max_only_completed_dispatch_is_exact_and_reported(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(node)

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        report = MODULE.render_routing_report(plan)
        self.assertTrue(report.startswith("| agent |"), report)
        self.assertIn("Child policy: `luna_max_only`", report)
        self.assertIn("gpt-5.6-luna / max", report)
        self.assertIn("e1 a1 accepted", report)
        self.assertIn("success (e2)", report)
        self.assertEqual(
            "gpt_5_6_luna_max_json_convert_a1",
            node["dispatch"]["attempts"][0]["task_name"],  # type: ignore[index]
        )

    def test_luna_max_only_dispatch_requires_frozen_runtime_snapshot(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        del plan["runtime"]["catalog_snapshot"]  # type: ignore[index]
        complete_node_with_explicit_dispatch(plan["nodes"][0])  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_RUNTIME_SNAPSHOT_REQUIRED", error_codes(result))

        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        plan["runtime"]["catalog_snapshot"]["available_pairs_sha256"] = "0" * 64  # type: ignore[index]
        complete_node_with_explicit_dispatch(plan["nodes"][0])  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_RUNTIME_SNAPSHOT_DIGEST_MISMATCH", error_codes(result))

    def test_luna_max_only_is_orthogonal_to_profile(self) -> None:
        for profile in ("balanced", "latency", "economy", "quality"):
            with self.subTest(profile=profile):
                plan = luna_max_only_plan()
                plan["profile"] = profile
                if profile == "economy":
                    attach_qualitative_economy(plan)

                code, result = validate(plan)

                self.assertEqual(0, code, result)
                selected = plan["nodes"][0]["selection"]["selected_pair"]  # type: ignore[index]
                self.assertEqual(pair("gpt-5.6-luna", "luna", "max"), selected)
                if profile in {"latency", "economy"}:
                    self.assertIn("QUALITATIVE_OPTIMIZATION_ONLY", warning_codes(result))

    def test_luna_max_only_rejects_non_luna_max_pairs_at_every_layer(self) -> None:
        foreign = pair("gpt-5.6-terra", "terra", "high")
        locations = (
            "allowed",
            "fallback",
            "selected",
            "requested",
            "dispatch_requested",
            "effective",
            "echo",
        )
        for location in locations:
            with self.subTest(location=location):
                plan = luna_max_only_plan()
                node = plan["nodes"][0]  # type: ignore[index]
                if location == "allowed":
                    node["requirements"]["allowed_model_effort_pairs"].append(  # type: ignore[index]
                        copy.deepcopy(foreign)
                    )
                elif location == "fallback":
                    node["requirements"]["fallback_pairs"] = [copy.deepcopy(foreign)]  # type: ignore[index]
                elif location == "selected":
                    node["selection"]["selected_pair"] = copy.deepcopy(foreign)  # type: ignore[index]
                elif location == "requested":
                    node["selection"].update(  # type: ignore[index]
                        {"origin": "explicit_user", "requested_pair": copy.deepcopy(foreign)}
                    )
                else:
                    plan["ledger_phase"] = "finalized"
                    complete_node_with_explicit_dispatch(node)
                    attempt = node["dispatch"]["attempts"][0]  # type: ignore[index]
                    if location == "dispatch_requested":
                        attempt["requested_pair"] = copy.deepcopy(foreign)
                    elif location == "effective":
                        attempt["effective_pair"] = copy.deepcopy(foreign)
                    else:
                        node["result"]["assigned_pair_echo"] = copy.deepcopy(foreign)  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("CHILD_POLICY_PAIR_FORBIDDEN", error_codes(result))

    def test_luna_max_only_rejects_luna_xhigh_and_other_max_families(self) -> None:
        candidates = (
            pair("gpt-5.6-luna", "luna", "xhigh"),
            pair("gpt-5.6-terra", "terra", "max"),
            pair("gpt-5.6-sol", "sol", "max"),
        )
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                plan = luna_max_only_plan()
                node = plan["nodes"][0]  # type: ignore[index]
                node["requirements"]["allowed_model_effort_pairs"] = [  # type: ignore[index]
                    copy.deepcopy(candidate)
                ]
                node["selection"]["selected_pair"] = copy.deepcopy(candidate)  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("CHILD_POLICY_PAIR_FORBIDDEN", error_codes(result))

    def test_luna_max_only_forbids_fallback_even_to_luna_max(self) -> None:
        plan = luna_max_only_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        luna_max = copy.deepcopy(node["selection"]["selected_pair"])  # type: ignore[index]
        node["requirements"]["fallback_pairs"] = [luna_max]  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FALLBACK_FORBIDDEN", error_codes(result))

    def test_luna_max_only_forbids_inherited_dispatch(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "active"
        node = plan["nodes"][0]  # type: ignore[index]
        node["lifecycle_state"] = "dispatched"
        node["dispatch"] = accepted_explicit_dispatch(node)
        attempt = node["dispatch"]["attempts"][0]  # type: ignore[index]
        attempt.update(
            {
                "mode": "inherit_parent",
                "fork_turns": "all",
                "model": None,
                "reasoning_effort": None,
            }
        )

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_EXPLICIT_DISPATCH_REQUIRED", error_codes(result))
        self.assertIn("CHILD_POLICY_EXPLICIT_ARGUMENTS_REQUIRED", error_codes(result))

    def test_luna_max_only_requires_both_exact_spawn_arguments(self) -> None:
        for field_name in ("model", "reasoning_effort"):
            with self.subTest(field=field_name):
                plan = luna_max_only_plan()
                plan["ledger_phase"] = "active"
                node = plan["nodes"][0]  # type: ignore[index]
                node["lifecycle_state"] = "dispatched"
                node["dispatch"] = accepted_explicit_dispatch(node)
                node["dispatch"]["attempts"][0][field_name] = None  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("CHILD_POLICY_EXPLICIT_ARGUMENTS_REQUIRED", error_codes(result))

    def test_luna_max_only_cannot_dispatch_when_runtime_pair_is_unavailable(self) -> None:
        plan = luna_max_only_plan()
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            item
            for item in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (item["model"] == "gpt-5.6-luna" and item["effort"] == "max")
        ]
        refresh_catalog_snapshot(plan)
        plan["ledger_phase"] = "finalized"
        complete_node_with_explicit_dispatch(plan["nodes"][0])  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_LUNA_MAX_UNAVAILABLE", error_codes(result))

    def test_luna_max_only_can_stay_entirely_in_parent_when_unavailable(self) -> None:
        plan = luna_max_only_plan()
        plan["nodes"] = []
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            item
            for item in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (item["model"] == "gpt-5.6-luna" and item["effort"] == "max")
        ]
        refresh_catalog_snapshot(plan)

        code, result = validate(plan)

        self.assertEqual(0, code, result)

    def test_luna_max_only_can_record_an_unavailable_target_as_planned(self) -> None:
        plan = luna_max_only_plan()
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            item
            for item in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (item["model"] == "gpt-5.6-luna" and item["effort"] == "max")
        ]
        refresh_catalog_snapshot(plan)

        code, result = validate(plan)

        self.assertEqual(0, code, result)

    def test_luna_max_only_runtime_rejection_can_finalize_as_dispatch_blocked(self) -> None:
        plan = luna_max_only_plan()
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            item
            for item in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (item["model"] == "gpt-5.6-luna" and item["effort"] == "max")
        ]
        refresh_catalog_snapshot(plan)
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(node)
        attempt = dispatch["attempts"][0]  # type: ignore[index]
        attempt.update(
            {
                "receipt_status": "rejected",
                "receipt_ref": "spawn_agent:error-luna-max-unavailable",
                "effective_pair": None,
                "confirmation_status": "runtime-rejected",
            }
        )
        dispatch["effective_attempt"] = None
        node["lifecycle_state"] = "dispatch_blocked"
        node["dispatch"] = dispatch

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        self.assertIn("runtime-rejected", MODULE.render_routing_report(plan))

    def test_luna_max_only_rejected_dispatch_can_retry_once_then_succeed(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(
            node,
            receipt_ref="spawn_agent:agent-after-transient-retry",
        )
        accepted = dispatch["attempts"][0]  # type: ignore[index]
        rejected = copy.deepcopy(accepted)
        rejected.update(
            {
                "receipt_status": "rejected",
                "receipt_ref": "spawn_agent:error-transient-dispatch",
                "effective_pair": None,
                "confirmation_status": "runtime-rejected",
            }
        )
        accepted.update(
            {
                "attempt_index": 2,
                "event_seq": 2,
                "task_name": "gpt_5_6_luna_max_json_convert_a2",
            }
        )
        dispatch["attempts"] = [rejected, accepted]
        dispatch["effective_attempt"] = 2
        node["lifecycle_state"] = "completed"
        node["dispatch"] = dispatch
        node["result"] = {
            "status": "success",
            "event_seq": 3,
            "failure_classification": "none",
            "failure_evidence": [],
            "dispatch_attempt": 2,
            "agent_label": accepted["agent_label"],
            "assigned_pair_echo": copy.deepcopy(accepted["effective_pair"]),
            "confirmation_status_echo": accepted["confirmation_status"],
        }

        code, result = validate(plan)

        self.assertEqual(0, code, result)

    def test_luna_max_only_allows_one_declared_cross_node_transient_retry(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-initial-failed",
        )
        mark_transient_failure(initial)

        retry = copy.deepcopy(initial)
        retry.update(
            {
                "id": "json_convert_retry",
                "wave": 1,
                "depends_on": ["json_convert"],
                "retry_of": "json_convert",
                "retry_kind": "transient",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        retry["attempt_budget"]["transient_retries"] = 0  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            retry,
            receipt_ref="spawn_agent:agent-transient-retry",
            dispatch_event_seq=3,
            result_event_seq=4,
        )
        plan["nodes"].append(retry)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        report = MODULE.render_routing_report(plan)
        self.assertIn("failed/transient (e2)", report)
        self.assertIn("success (e4)", report)

    def test_luna_max_only_retry_must_dispatch_after_initial_failure_result(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-initial-failed-late",
            dispatch_event_seq=1,
            result_event_seq=4,
        )
        mark_transient_failure(initial)

        retry = copy.deepcopy(initial)
        retry.update(
            {
                "id": "json_convert_retry",
                "wave": 1,
                "depends_on": ["json_convert"],
                "retry_of": "json_convert",
                "retry_kind": "transient",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        retry["attempt_budget"]["transient_retries"] = 0  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            retry,
            receipt_ref="spawn_agent:agent-premature-retry",
            dispatch_event_seq=2,
            result_event_seq=3,
        )
        plan["nodes"].append(retry)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_RETRY_EVENT_ORDER", error_codes(result))

    def test_luna_max_only_only_earliest_failure_can_authorize_retry(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        first = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            first,
            receipt_ref="spawn_agent:agent-first-failure",
            dispatch_event_seq=1,
            result_event_seq=3,
        )
        mark_transient_failure(first)

        sibling = copy.deepcopy(first)
        sibling.update(
            {
                "id": "schema_inventory",
                "executor_id": "executor_schema_inventory",
                "wave": 0,
                "depends_on": [],
                "objective": "Inventory an independent bounded schema directory.",
                "why_delegate": "The directory has an exact manifest oracle.",
                "work_unit_id": "schema_inventory",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            sibling,
            receipt_ref="spawn_agent:agent-second-failure",
            dispatch_event_seq=2,
            result_event_seq=4,
        )
        mark_transient_failure(sibling)

        sibling_retry = copy.deepcopy(sibling)
        sibling_retry.update(
            {
                "id": "schema_inventory_retry",
                "wave": 1,
                "depends_on": ["schema_inventory"],
                "retry_of": "schema_inventory",
                "retry_kind": "transient",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        sibling_retry["attempt_budget"]["transient_retries"] = 0  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            sibling_retry,
            receipt_ref="spawn_agent:agent-second-failure-retry",
            dispatch_event_seq=5,
            result_event_seq=6,
        )
        plan["nodes"].extend([sibling, sibling_retry])  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FAIL_STOP_DISPATCH_FORBIDDEN", error_codes(result))

    def test_luna_max_only_retry_requires_transient_failure_evidence(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-validation-failed",
        )
        initial["result"].update(  # type: ignore[index]
            {
                "status": "failed",
                "failure_classification": "validation_failure",
                "failure_evidence": ["The deterministic schema assertion failed."],
            }
        )

        retry = copy.deepcopy(initial)
        retry.update(
            {
                "id": "json_convert_retry",
                "wave": 1,
                "depends_on": ["json_convert"],
                "retry_of": "json_convert",
                "retry_kind": "transient",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        retry["attempt_budget"]["transient_retries"] = 0  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            retry,
            receipt_ref="spawn_agent:agent-invalid-retry",
            dispatch_event_seq=3,
            result_event_seq=4,
        )
        plan["nodes"].append(retry)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_RETRY_PRIOR_NOT_TRANSIENT", error_codes(result))

    def test_luna_max_only_dependency_must_finish_before_downstream_dispatch(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        upstream = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            upstream,
            receipt_ref="spawn_agent:agent-upstream",
            dispatch_event_seq=1,
            result_event_seq=3,
        )

        downstream = copy.deepcopy(upstream)
        downstream.update(
            {
                "id": "schema_summary",
                "executor_id": "executor_schema_summary",
                "wave": 1,
                "depends_on": ["json_convert"],
                "objective": "Summarize the accepted conversion into a bounded schema report.",
                "why_delegate": "The summary has an exact schema oracle.",
                "work_unit_id": "schema_summary",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            downstream,
            receipt_ref="spawn_agent:agent-premature-downstream",
            dispatch_event_seq=2,
            result_event_seq=4,
        )
        plan["nodes"].append(downstream)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_DEPENDENCY_EVENT_ORDER", error_codes(result))

    def test_luna_max_only_dependency_ready_event_order_is_valid(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        upstream = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            upstream,
            receipt_ref="spawn_agent:agent-upstream",
            dispatch_event_seq=1,
            result_event_seq=2,
        )

        downstream = copy.deepcopy(upstream)
        downstream.update(
            {
                "id": "schema_summary",
                "executor_id": "executor_schema_summary",
                "wave": 1,
                "depends_on": ["json_convert"],
                "objective": "Summarize the accepted conversion into a bounded schema report.",
                "why_delegate": "The summary has an exact schema oracle.",
                "work_unit_id": "schema_summary",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            downstream,
            receipt_ref="spawn_agent:agent-ready-downstream",
            dispatch_event_seq=3,
            result_event_seq=4,
        )
        plan["nodes"].append(downstream)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(0, code, result)

    def test_luna_max_only_failure_blocks_disguised_later_work_unit(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-initial-failed",
        )
        mark_transient_failure(initial)

        disguised = copy.deepcopy(initial)
        disguised.update(
            {
                "id": "metadata_extract",
                "executor_id": "executor_metadata_extract",
                "wave": 1,
                "depends_on": [],
                "objective": "Extract the same bounded records into a normalized report.",
                "why_delegate": "The normalized report has an exact schema oracle.",
                "work_unit_id": "metadata_extract",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            disguised,
            receipt_ref="spawn_agent:agent-disguised-follow-up",
            dispatch_event_seq=3,
            result_event_seq=4,
        )
        plan["nodes"].append(disguised)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FAIL_STOP_DISPATCH_FORBIDDEN", error_codes(result))

    def test_luna_max_only_failed_retry_seals_all_later_waves(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-initial-failed",
        )
        mark_transient_failure(initial)

        retry = copy.deepcopy(initial)
        retry.update(
            {
                "id": "json_convert_retry",
                "wave": 1,
                "depends_on": ["json_convert"],
                "retry_of": "json_convert",
                "retry_kind": "transient",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        retry["attempt_budget"]["transient_retries"] = 0  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            retry,
            receipt_ref="spawn_agent:agent-transient-retry-failed",
            dispatch_event_seq=3,
            result_event_seq=4,
        )
        mark_transient_failure(retry)

        later = copy.deepcopy(initial)
        later.update(
            {
                "id": "schema_summary",
                "executor_id": "executor_schema_summary",
                "wave": 2,
                "depends_on": [],
                "objective": "Summarize a separate bounded schema inventory.",
                "why_delegate": "The inventory has an exact count oracle.",
                "work_unit_id": "schema_summary",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            later,
            receipt_ref="spawn_agent:agent-post-retry-follow-up",
            dispatch_event_seq=5,
            result_event_seq=6,
        )
        plan["nodes"].extend([retry, later])  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FAIL_STOP_DISPATCH_FORBIDDEN", error_codes(result))

    def test_luna_max_only_same_wave_precommitted_children_can_finish(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-parallel-failed",
            dispatch_event_seq=1,
            result_event_seq=3,
        )
        mark_transient_failure(initial)

        sibling = copy.deepcopy(initial)
        sibling.update(
            {
                "id": "schema_inventory",
                "executor_id": "executor_schema_inventory",
                "wave": 0,
                "depends_on": [],
                "objective": "Inventory an independent bounded schema directory.",
                "why_delegate": "The directory has an exact manifest oracle.",
                "work_unit_id": "schema_inventory",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            sibling,
            receipt_ref="spawn_agent:agent-parallel-success",
            dispatch_event_seq=2,
            result_event_seq=4,
        )
        plan["nodes"].append(sibling)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(0, code, result)

    def test_luna_max_only_same_wave_dispatch_after_failure_is_rejected(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-same-wave-failed",
            dispatch_event_seq=1,
            result_event_seq=2,
        )
        mark_transient_failure(initial)

        late_sibling = copy.deepcopy(initial)
        late_sibling.update(
            {
                "id": "late_schema_inventory",
                "executor_id": "executor_late_schema_inventory",
                "wave": 0,
                "depends_on": [],
                "objective": "Inventory a separate bounded schema directory.",
                "why_delegate": "The directory has an exact manifest oracle.",
                "work_unit_id": "late_schema_inventory",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            late_sibling,
            receipt_ref="spawn_agent:agent-same-wave-after-failure",
            dispatch_event_seq=3,
            result_event_seq=4,
        )
        plan["nodes"].append(late_sibling)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FAIL_STOP_DISPATCH_FORBIDDEN", error_codes(result))

    def test_luna_max_only_requires_event_sequence_on_attempts_and_results(self) -> None:
        for location in ("attempt", "result"):
            with self.subTest(location=location):
                plan = luna_max_only_plan()
                plan["ledger_phase"] = "finalized"
                node = plan["nodes"][0]  # type: ignore[index]
                complete_node_with_explicit_dispatch(node)
                if location == "attempt":
                    del node["dispatch"]["attempts"][0]["event_seq"]  # type: ignore[index]
                else:
                    del node["result"]["event_seq"]  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("CHILD_POLICY_EVENT_SEQUENCE_REQUIRED", error_codes(result))

    def test_luna_max_only_requires_failure_classification_and_evidence(self) -> None:
        for field_name in ("failure_classification", "failure_evidence"):
            with self.subTest(field=field_name):
                plan = luna_max_only_plan()
                plan["ledger_phase"] = "finalized"
                node = plan["nodes"][0]  # type: ignore[index]
                complete_node_with_explicit_dispatch(node)
                del node["result"][field_name]  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("CHILD_POLICY_FAILURE_ATTESTATION_REQUIRED", error_codes(result))

        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(node)
        node["result"]["status"] = "failed"  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FAILURE_CLASSIFICATION_INVALID", error_codes(result))
        self.assertIn("CHILD_POLICY_FAILURE_EVIDENCE_REQUIRED", error_codes(result))

        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(node)
        node["result"]["failure_evidence"] = ["Not a failure."]  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FAILURE_EVIDENCE_INVALID", error_codes(result))

    def test_luna_max_only_failure_evidence_must_be_visible(self) -> None:
        for invisible_text in ("\u200b", "\u2800"):
            with self.subTest(evidence=repr(invisible_text)):
                plan = luna_max_only_plan()
                plan["ledger_phase"] = "finalized"
                node = plan["nodes"][0]  # type: ignore[index]
                complete_node_with_explicit_dispatch(node)
                node["result"].update(  # type: ignore[index]
                    {
                        "status": "failed",
                        "failure_classification": "transient",
                        "failure_evidence": [invisible_text],
                    }
                )

                code, result = validate(plan)

                self.assertEqual(2, code, result)
                self.assertIn("SCHEMA_PATTERN", error_codes(result))

    def test_luna_max_only_event_sequence_is_unique_contiguous_and_ordered(self) -> None:
        cases = (
            ("duplicate", 1, 1, "CHILD_POLICY_EVENT_SEQUENCE_DUPLICATE"),
            ("gap", 1, 3, "CHILD_POLICY_EVENT_SEQUENCE_GAP"),
            ("result_before_dispatch", 2, 1, "CHILD_POLICY_RESULT_EVENT_ORDER"),
        )
        for name, dispatch_sequence, result_sequence, expected_code in cases:
            with self.subTest(case=name):
                plan = luna_max_only_plan()
                plan["ledger_phase"] = "finalized"
                node = plan["nodes"][0]  # type: ignore[index]
                complete_node_with_explicit_dispatch(
                    node,
                    dispatch_event_seq=dispatch_sequence,
                    result_event_seq=result_sequence,
                )

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_luna_max_only_dispatch_blocked_seals_later_waves(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        blocked = plan["nodes"][0]  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(blocked)
        attempt = dispatch["attempts"][0]  # type: ignore[index]
        attempt.update(
            {
                "receipt_status": "rejected",
                "receipt_ref": "spawn_agent:error-runtime-rejected",
                "effective_pair": None,
                "confirmation_status": "runtime-rejected",
            }
        )
        dispatch["effective_attempt"] = None
        blocked["lifecycle_state"] = "dispatch_blocked"
        blocked["dispatch"] = dispatch

        later = copy.deepcopy(blocked)
        later.update(
            {
                "id": "schema_inventory",
                "executor_id": "executor_schema_inventory",
                "wave": 1,
                "depends_on": [],
                "objective": "Inventory an independent bounded schema directory.",
                "why_delegate": "The directory has an exact manifest oracle.",
                "work_unit_id": "schema_inventory",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        complete_node_with_explicit_dispatch(
            later,
            receipt_ref="spawn_agent:agent-after-runtime-rejection",
            dispatch_event_seq=2,
            result_event_seq=3,
        )
        plan["nodes"].append(later)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_FAIL_STOP_DISPATCH_FORBIDDEN", error_codes(result))

    def test_luna_max_only_failure_may_leave_later_nodes_unspawned(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "active"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-initial-failed",
        )
        mark_transient_failure(initial)

        planned = copy.deepcopy(initial)
        planned.update(
            {
                "id": "schema_inventory",
                "executor_id": "executor_schema_inventory",
                "wave": 1,
                "depends_on": [],
                "objective": "Inventory an independent bounded schema directory.",
                "why_delegate": "The directory has an exact manifest oracle.",
                "work_unit_id": "schema_inventory",
                "retry_of": None,
                "retry_kind": "none",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        plan["nodes"].append(planned)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(0, code, result)

    def test_luna_max_only_rejects_cross_node_substantive_rework(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        initial = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            initial,
            receipt_ref="spawn_agent:agent-initial-failed",
        )
        mark_transient_failure(initial)

        rework = copy.deepcopy(initial)
        rework.update(
            {
                "id": "json_convert_rework",
                "wave": 1,
                "depends_on": ["json_convert"],
                "retry_of": "json_convert",
                "retry_kind": "substantive",
                "lifecycle_state": "planned",
                "dispatch": None,
                "result": None,
            }
        )
        rework["attempt_budget"]["transient_retries"] = 0  # type: ignore[index]
        complete_node_with_explicit_dispatch(
            rework,
            receipt_ref="spawn_agent:agent-substantive-rework",
        )
        plan["nodes"].append(rework)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_SUBSTANTIVE_RETRY_FORBIDDEN", error_codes(result))

    def test_luna_max_only_rejects_duplicate_initial_nodes_for_one_work_unit(self) -> None:
        plan = luna_max_only_plan()
        second = copy.deepcopy(plan["nodes"][0])  # type: ignore[index]
        second.update(
            {
                "id": "json_convert_again",
                "wave": 1,
                "depends_on": ["json_convert"],
            }
        )
        plan["nodes"].append(second)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_WORK_UNIT_INITIAL_INVALID", error_codes(result))

    def test_luna_max_only_cannot_rename_an_identical_contract_as_a_new_work_unit(self) -> None:
        plan = luna_max_only_plan()
        disguised_rework = copy.deepcopy(plan["nodes"][0])  # type: ignore[index]
        disguised_rework.update(
            {
                "id": "json_convert_disguised",
                "wave": 1,
                "depends_on": ["json_convert"],
                "work_unit_id": "json_convert_disguised",
            }
        )
        plan["nodes"].append(disguised_rework)  # type: ignore[union-attr]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_WORK_UNIT_ID_CHANGED", error_codes(result))

    def test_luna_max_only_rejects_more_than_one_transient_retry(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(node)
        first = dispatch["attempts"][0]  # type: ignore[index]
        attempts = []
        for attempt_index in (1, 2, 3):
            attempt = copy.deepcopy(first)
            attempt.update(
                {
                    "attempt_index": attempt_index,
                    "event_seq": attempt_index,
                    "task_name": f"gpt_5_6_luna_max_json_convert_a{attempt_index}",
                    "receipt_status": "rejected",
                    "receipt_ref": f"spawn_agent:error-transient-{attempt_index}",
                    "effective_pair": None,
                    "confirmation_status": "runtime-rejected",
                }
            )
            attempts.append(attempt)
        dispatch["attempts"] = attempts
        dispatch["effective_attempt"] = None
        node["lifecycle_state"] = "dispatch_blocked"
        node["dispatch"] = dispatch

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_ATTEMPT_BUDGET_EXCEEDED", error_codes(result))

    def test_luna_max_only_dispatch_history_respects_declared_zero_retry_budget(self) -> None:
        plan = luna_max_only_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        node["attempt_budget"]["transient_retries"] = 0  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(node)
        first = dispatch["attempts"][0]  # type: ignore[index]
        attempts = []
        for attempt_index in (1, 2):
            attempt = copy.deepcopy(first)
            attempt.update(
                {
                    "attempt_index": attempt_index,
                    "event_seq": attempt_index,
                    "task_name": f"gpt_5_6_luna_max_json_convert_a{attempt_index}",
                    "receipt_status": "rejected",
                    "receipt_ref": f"spawn_agent:error-transient-{attempt_index}",
                    "effective_pair": None,
                    "confirmation_status": "runtime-rejected",
                }
            )
            attempts.append(attempt)
        dispatch["attempts"] = attempts
        dispatch["effective_attempt"] = None
        node["lifecycle_state"] = "dispatch_blocked"
        node["dispatch"] = dispatch

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_ATTEMPT_BUDGET_EXCEEDED", error_codes(result))

    def test_luna_max_only_requires_one_declared_max_use(self) -> None:
        plan = luna_max_only_plan()
        plan["nodes"][0]["attempt_budget"]["max_uses"] = 0  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_MAX_BUDGET_INVALID", error_codes(result))

    def test_luna_max_only_forbids_substantive_luna_rework_loop(self) -> None:
        plan = luna_max_only_plan()
        plan["nodes"][0]["attempt_budget"]["substantive_attempts"] = 2  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("CHILD_POLICY_SUBSTANTIVE_RETRY_FORBIDDEN", error_codes(result))

    def test_luna_max_only_keeps_unbounded_or_non_structured_work_in_parent(self) -> None:
        mutations = (
            ("work_class", "general"),
            ("context_scope", "cross_system"),
            ("oracle", "weak"),
            ("access_mode", "external_write"),
            ("role", "diagnostician"),
        )
        for field_name, value in mutations:
            with self.subTest(field=field_name):
                plan = luna_max_only_plan()
                plan["nodes"][0][field_name] = value  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("CHILD_POLICY_NODE_MUST_STAY_PARENT", error_codes(result))

    def test_complete_node_contract_is_required(self) -> None:
        for field_name in sorted(REQUIRED_NODE_FIELDS):
            with self.subTest(field=field_name):
                plan = base_plan()
                del plan["nodes"][0][field_name]  # type: ignore[index]
                code, result = validate(plan)
                self.assertEqual(2, code, result)
                matching_paths = {
                    item["path"]
                    for item in result["errors"]  # type: ignore[index]
                    if item["code"] == "SCHEMA_REQUIRED"
                }
                self.assertIn(f"/nodes/0/{field_name}", matching_paths)

    def test_nested_contract_fields_are_required(self) -> None:
        nested_fields = {
            "attempt_budget": {"transient_retries", "substantive_attempts", "max_uses"},
            "requirements": {
                "required_integrator_class",
                "minimum_child_effort",
                "minimum_integrator_effort",
                "allowed_model_effort_pairs",
                "fallback_pairs",
            },
            "selection": {"origin", "requested_pair", "selected_pair", "fallback_reason"},
        }
        for section, fields in nested_fields.items():
            for field_name in sorted(fields):
                with self.subTest(section=section, field=field_name):
                    plan = base_plan()
                    del plan["nodes"][0][section][field_name]  # type: ignore[index]
                    code, result = validate(plan)
                    self.assertEqual(2, code, result)
                    matching_paths = {
                        item["path"]
                        for item in result["errors"]  # type: ignore[index]
                        if item["code"] == "SCHEMA_REQUIRED"
                    }
                    self.assertIn(f"/nodes/0/{section}/{field_name}", matching_paths)

    def test_root_runtime_and_validation_contract_fields_are_required(self) -> None:
        contracts = (
            (
                (),
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
            ),
            (("orchestration",), {"state", "parent"}),
            (("orchestration", "parent"), {"model", "family", "effort", "integrator_class"}),
            (("runtime",), {"max_concurrent_children", "available_pairs"}),
            (
                ("runtime", "available_pairs", 0),
                {"model", "family", "effort", "eligible_work_classes"},
            ),
            (("nodes", 0, "validation_steps", 0), {"id", "kind", "phase", "required"}),
        )
        for tokens, fields in contracts:
            for field_name in sorted(fields):
                with self.subTest(path=tokens, field=field_name):
                    plan = base_plan()
                    target = plan
                    for token in tokens:
                        target = target[token]  # type: ignore[index,assignment]
                    del target[field_name]  # type: ignore[index]
                    code, result = validate(plan)
                    self.assertEqual(2, code, result)
                    prefix = "" if not tokens else "/" + "/".join(str(token) for token in tokens)
                    matching_paths = {
                        item["path"]
                        for item in result["errors"]  # type: ignore[index]
                        if item["code"] == "SCHEMA_REQUIRED"
                    }
                    self.assertIn(f"{prefix}/{field_name}", matching_paths)

    def test_metric_source_requires_as_of_and_evidence_metadata(self) -> None:
        plan = base_plan()
        plan["metric_source"] = "runtime"
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        codes = error_codes(result)
        self.assertIn("METRIC_AS_OF_REQUIRED", codes)
        self.assertIn("METRIC_EVIDENCE_REQUIRED", codes)

    def test_none_metric_source_rejects_metric_metadata(self) -> None:
        plan = base_plan()
        plan["metric_as_of"] = "2026-08-20T20:00:00+08:00"
        plan["evidence_id_or_window"] = "run-2026-08-20-001"
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        codes = error_codes(result)
        self.assertIn("METRIC_AS_OF_WITHOUT_SOURCE", codes)
        self.assertIn("METRIC_EVIDENCE_WITHOUT_SOURCE", codes)

    def test_metric_source_with_complete_metadata_is_valid(self) -> None:
        plan = base_plan()
        plan["metric_source"] = "local_telemetry"
        plan["metric_as_of"] = "2026-08-20T20:00:00+08:00"
        plan["evidence_id_or_window"] = "routing-eval-window-2026-08-01..2026-08-20"
        code, result = validate(plan)
        self.assertEqual(0, code, result)

    def test_metric_metadata_rejects_malformed_or_invisible_values(self) -> None:
        cases = (
            ("not-a-timestamp", "run-001", "METRIC_AS_OF_INVALID"),
            ("2026-08-20T20:00:00", "run-001", "METRIC_AS_OF_INVALID"),
            ("\u200b", "run-001", "METRIC_AS_OF_INVALID"),
            ("2026-08-20", "\u200b", "METRIC_EVIDENCE_INVALID"),
            ("2026-08-20", "\u0301", "METRIC_EVIDENCE_INVALID"),
            ("2026-08-20", "\ufe0f", "METRIC_EVIDENCE_INVALID"),
        )
        for metric_as_of, evidence, expected_code in cases:
            with self.subTest(metric_as_of=metric_as_of, evidence=evidence):
                plan = base_plan()
                plan["metric_source"] = "runtime"
                plan["metric_as_of"] = metric_as_of
                plan["evidence_id_or_window"] = evidence

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_economy_requires_an_auditable_evaluation_for_ranked_nodes(self) -> None:
        plan = base_plan()
        plan["profile"] = "economy"

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_EVALUATION_REQUIRED", error_codes(result))

    def test_qualitative_economy_records_complete_order_without_cost_claim(self) -> None:
        plan = base_plan()
        attach_qualitative_economy(plan)

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        self.assertIn("ECONOMY_QUALITATIVE_EVALUATION", warning_codes(result))
        self.assertIn("QUALITATIVE_OPTIMIZATION_ONLY", warning_codes(result))
        report = MODULE.render_routing_report(plan)
        self.assertIn("Profile: `economy`", report)
        self.assertIn("Metric source: `none`", report)
        self.assertIn("Economy decisions:", report)
        self.assertIn("qualitative", report)

    def test_qualitative_economy_rejects_comparable_metric_sources(self) -> None:
        for source in ("runtime", "local_telemetry"):
            with self.subTest(source=source):
                plan = base_plan()
                attach_qualitative_economy(plan)
                plan["metric_source"] = source
                plan["metric_as_of"] = "2026-08-21T08:00:00+08:00"
                plan["evidence_id_or_window"] = "economy-regression-window-001"

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("ECONOMY_QUALITATIVE_SOURCE_INVALID", error_codes(result))

    def test_qualitative_economy_requires_complete_order_and_selected_first(self) -> None:
        for mutation, expected_code in (
            ("missing_candidate", "ECONOMY_QUALITATIVE_CANDIDATE_SET_MISMATCH"),
            ("selected_not_first", "ECONOMY_QUALITATIVE_SELECTED_NOT_FIRST"),
        ):
            with self.subTest(mutation=mutation):
                plan = base_plan()
                attach_qualitative_economy(plan)
                order = plan["nodes"][0]["economy_evaluation"]["qualitative_order"]  # type: ignore[index]
                if mutation == "missing_candidate":
                    order.pop()
                else:
                    order[0], order[1] = order[1], order[0]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_quantitative_economy_recomputes_cost_and_reports_evidence(self) -> None:
        plan = base_plan()
        attach_quantitative_economy(plan)

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        self.assertNotIn("ECONOMY_QUALITATIVE_EVALUATION", warning_codes(result))
        report = MODULE.render_routing_report(plan)
        self.assertIn("Metric source: `local_telemetry`", report)
        self.assertIn("economy-regression-window-001", report)
        self.assertIn("normalized-cost-unit", report)

    def test_quantitative_economy_rejects_untrusted_metric_sources(self) -> None:
        for source in ("none", "community_prior"):
            with self.subTest(source=source):
                plan = base_plan()
                attach_quantitative_economy(plan)
                plan["metric_source"] = source
                if source == "none":
                    plan["metric_as_of"] = None
                    plan["evidence_id_or_window"] = None

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn("ECONOMY_QUANTITATIVE_SOURCE_INSUFFICIENT", error_codes(result))

    def test_quantitative_economy_rejects_formula_mismatch(self) -> None:
        plan = base_plan()
        attach_quantitative_economy(plan)
        estimate = plan["nodes"][0]["economy_evaluation"]["candidate_estimates"][0]  # type: ignore[index]
        estimate["expected_total_cost"] += 0.25

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_TOTAL_MISMATCH", error_codes(result))

    def test_quantitative_economy_binds_and_recomputes_parent_baseline(self) -> None:
        for mutation, expected_code in (
            ("pair", "ECONOMY_PARENT_PAIR_MISMATCH"),
            ("total", "ECONOMY_PARENT_TOTAL_MISMATCH"),
        ):
            with self.subTest(mutation=mutation):
                plan = base_plan()
                attach_quantitative_economy(plan)
                parent_estimate = plan["nodes"][0]["economy_evaluation"]["parent_estimate"]  # type: ignore[index]
                if mutation == "pair":
                    parent_estimate["pair"] = pair("gpt-5.6-terra", "terra", "high")
                else:
                    parent_estimate["expected_total_cost"] += 0.25

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_quantitative_economy_binds_unique_records_to_root_evidence_window(self) -> None:
        for mutation, expected_code in (
            ("foreign_window", "ECONOMY_EVIDENCE_WINDOW_MISMATCH"),
            ("duplicate", "ECONOMY_EVIDENCE_REF_DUPLICATE"),
        ):
            with self.subTest(mutation=mutation):
                plan = base_plan()
                attach_quantitative_economy(plan)
                evaluation = plan["nodes"][0]["economy_evaluation"]  # type: ignore[index]
                estimates = evaluation["candidate_estimates"]
                if mutation == "foreign_window":
                    estimates[0]["evidence_ref"] = "another-window#candidate:luna"
                else:
                    estimates[1]["evidence_ref"] = estimates[0]["evidence_ref"]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_quantitative_economy_rejects_non_minimum_selection(self) -> None:
        plan = base_plan()
        attach_quantitative_economy(plan)
        evaluation = plan["nodes"][0]["economy_evaluation"]  # type: ignore[index]
        estimates = evaluation["candidate_estimates"]
        estimates[1] = economy_estimate(estimates[1]["pair"], 0.5)  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_SELECTED_NOT_MINIMUM", error_codes(result))

    def test_quantitative_economy_rejects_non_beneficial_delegation(self) -> None:
        plan = base_plan()
        attach_quantitative_economy(plan)
        evaluation = plan["nodes"][0]["economy_evaluation"]  # type: ignore[index]
        selected_estimate = evaluation["candidate_estimates"][0]  # type: ignore[index]
        parent_estimate = evaluation["parent_estimate"]
        for field_name in (
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
        ):
            parent_estimate[field_name] = selected_estimate[field_name]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_DELEGATION_NOT_BENEFICIAL", error_codes(result))

    def test_quantitative_economy_requires_exact_candidate_coverage(self) -> None:
        plan = base_plan()
        attach_quantitative_economy(plan)
        plan["nodes"][0]["economy_evaluation"]["candidate_estimates"].pop()  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_CANDIDATE_SET_MISMATCH", error_codes(result))

    def test_quantitative_economy_rejects_non_finite_or_negative_inputs(self) -> None:
        cases = (
            ("retry_probability", float("nan"), "SCHEMA_TYPE"),
            ("coordination_cost", -0.1, "SCHEMA_VALUE"),
            ("review_cost", 0.1234567, "SCHEMA_VALUE"),
            ("initial_cost", 1e300, "SCHEMA_VALUE"),
            ("initial_cost", 10**309, "SCHEMA_VALUE"),
        )
        for field_name, value, expected_code in cases:
            with self.subTest(field=field_name):
                plan = base_plan()
                attach_quantitative_economy(plan)
                estimate = plan["nodes"][0]["economy_evaluation"]["candidate_estimates"][0]  # type: ignore[index]
                estimate[field_name] = value

                code, result = validate(plan)

                self.assertEqual(2, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_quantitative_economy_uses_deterministic_tie_break(self) -> None:
        plan = base_plan()
        attach_quantitative_economy(plan)
        node = plan["nodes"][0]  # type: ignore[index]
        evaluation = node["economy_evaluation"]
        evaluation["candidate_estimates"] = [
            economy_estimate(candidate, 1.0) for candidate in economy_candidates(node)
        ]
        node["selection"]["selected_pair"] = pair("gpt-5.6-terra", "terra", "high")  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_SELECTED_NOT_MINIMUM", error_codes(result))

    def test_quantitative_economy_does_not_treat_large_absolute_gap_as_a_tie(self) -> None:
        plan = base_plan()
        attach_quantitative_economy(plan)
        node = plan["nodes"][0]  # type: ignore[index]
        evaluation = node["economy_evaluation"]
        candidates = economy_candidates(node)
        evaluation["candidate_estimates"] = [
            economy_estimate(candidates[0], 1e12 + 500.0),
            economy_estimate(candidates[1], 1e12),
            economy_estimate(candidates[2], 2e12),
        ]
        parent = plan["orchestration"]["parent"]  # type: ignore[index]
        evaluation["parent_estimate"] = economy_estimate(
            pair(parent["model"], parent["family"], parent["effort"]),
            1e13,
            evidence_subject="parent",
        )

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_SELECTED_NOT_MINIMUM", error_codes(result))

    def test_economy_explicit_selection_is_visible_as_a_profile_bypass(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        node["selection"]["origin"] = "explicit_user"  # type: ignore[index]
        node["selection"]["requested_pair"] = copy.deepcopy(  # type: ignore[index]
            node["selection"]["selected_pair"]  # type: ignore[index]
        )
        attach_qualitative_economy(plan)

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        self.assertIn(
            "ECONOMY_PROFILE_BYPASSED_BY_SELECTION_ORIGIN",
            warning_codes(result),
        )
        self.assertIn("bypassed:explicit_user", MODULE.render_routing_report(plan))

    def test_economy_fallback_ranks_the_complete_fallback_set(self) -> None:
        plan = base_plan()
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            candidate
            for candidate in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (candidate["family"] == "luna" and candidate["effort"] == "max")
        ]
        node = plan["nodes"][0]  # type: ignore[index]
        selected = pair("gpt-5.6-terra", "terra", "high")
        node["requirements"]["fallback_pairs"] = [copy.deepcopy(selected)]  # type: ignore[index]
        node["selection"] = {
            "origin": "fallback",
            "requested_pair": pair("gpt-5.6-luna", "luna", "max"),
            "selected_pair": copy.deepcopy(selected),
            "fallback_reason": "unavailable",
        }
        attach_quantitative_economy(plan)

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        estimates = node["economy_evaluation"]["candidate_estimates"]  # type: ignore[index]
        self.assertEqual([selected], [estimate["pair"] for estimate in estimates])

    def test_economy_inherited_selection_is_visible_as_a_profile_bypass(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        parent_pair = pair("gpt-5.6-sol", "sol", "xhigh")
        node["requirements"]["allowed_model_effort_pairs"].append(  # type: ignore[index]
            copy.deepcopy(parent_pair)
        )
        node["selection"] = {
            "origin": "inherited",
            "requested_pair": None,
            "selected_pair": copy.deepcopy(parent_pair),
            "fallback_reason": None,
        }
        attach_qualitative_economy(plan)

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        self.assertIn(
            "ECONOMY_PROFILE_BYPASSED_BY_SELECTION_ORIGIN",
            warning_codes(result),
        )
        self.assertIn("bypassed:inherited", MODULE.render_routing_report(plan))

    def test_economy_evaluation_is_rejected_under_other_profiles(self) -> None:
        plan = base_plan()
        attach_qualitative_economy(plan)
        plan["profile"] = "balanced"

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ECONOMY_EVALUATION_UNEXPECTED", error_codes(result))

    def test_economy_evaluation_schema_requires_every_cost_input(self) -> None:
        evaluation_fields = {
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
        }
        estimate_fields = {
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
        }
        for scope, fields in (
            ("evaluation", evaluation_fields),
            ("estimate", estimate_fields),
            ("parent_estimate", estimate_fields),
        ):
            for field_name in sorted(fields):
                with self.subTest(scope=scope, field=field_name):
                    plan = base_plan()
                    attach_quantitative_economy(plan)
                    evaluation = plan["nodes"][0]["economy_evaluation"]  # type: ignore[index]
                    if scope == "evaluation":
                        target = evaluation
                    elif scope == "parent_estimate":
                        target = evaluation["parent_estimate"]
                    else:
                        target = evaluation["candidate_estimates"][0]  # type: ignore[index]
                    del target[field_name]

                    code, result = validate(plan)

                    self.assertEqual(2, code, result)
                    self.assertIn("SCHEMA_REQUIRED", error_codes(result))

    def test_unknown_state_with_child_fails_closed(self) -> None:
        plan = base_plan()
        plan["orchestration"]["state"] = "unknown"  # type: ignore[index]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("ORCH_UNKNOWN_CHILD", error_codes(result))

    def test_unknown_state_without_child_is_valid(self) -> None:
        plan = base_plan()
        plan["nodes"] = []
        plan["orchestration"] = {
            "state": "unknown",
            "parent": {
                "model": "unknown",
                "family": "unknown",
                "effort": "unknown",
                "integrator_class": "unknown",
            },
        }
        plan["runtime"]["max_concurrent_children"] = None  # type: ignore[index]
        code, result = validate(plan)
        self.assertEqual(0, code)
        self.assertTrue(result["valid"])

    def test_ultra_parent_with_child_rejected(self) -> None:
        plan = base_plan()
        plan["orchestration"] = {
            "state": "ultra_owned",
            "parent": {
                "model": "gpt-5.6-sol",
                "family": "sol",
                "effort": "ultra",
                "integrator_class": "critical",
            },
        }
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("ORCH_ULTRA_CHILD", error_codes(result))

    def test_ultra_parent_without_child_is_valid(self) -> None:
        plan = base_plan()
        plan["nodes"] = []
        plan["orchestration"] = {
            "state": "ultra_owned",
            "parent": {
                "model": "gpt-5.6-sol",
                "family": "sol",
                "effort": "ultra",
                "integrator_class": "critical",
            },
        }
        code, _ = validate(plan)
        self.assertEqual(0, code)

    def test_family_specific_effort_floor_denies_luna_below_xhigh_and_terra_below_high(self) -> None:
        denied_efforts = {
            "luna": ("low", "medium", "high"),
            "terra": ("low", "medium"),
        }
        for family, efforts in denied_efforts.items():
            for effort in efforts:
                with self.subTest(family=family, effort=effort):
                    plan = base_plan()
                    node = plan["nodes"][0]  # type: ignore[index]
                    selected = pair(f"gpt-5.6-{family}", family, effort)
                    node["requirements"]["minimum_child_effort"] = effort  # type: ignore[index]
                    node["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
                    node["selection"]["selected_pair"] = selected  # type: ignore[index]
                    code, result = validate(plan)
                    self.assertEqual(3, code)
                    self.assertIn("SELECTED_POLICY_DENIED", error_codes(result))

    def test_family_specific_deny_matrix_covers_every_selection_origin(self) -> None:
        denied_efforts = {
            "luna": ("low", "medium", "high"),
            "terra": ("low", "medium"),
        }
        for origin in ("automatic", "fallback", "inherited", "explicit_user"):
            for family, efforts in denied_efforts.items():
                for effort in efforts:
                    with self.subTest(origin=origin, family=family, effort=effort):
                        plan = base_plan()
                        node = plan["nodes"][0]  # type: ignore[index]
                        selected = pair(f"gpt-5.6-{family}", family, effort)
                        node["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
                        selection = {
                            "origin": origin,
                            "requested_pair": None,
                            "selected_pair": selected,
                            "fallback_reason": None,
                        }
                        if origin == "fallback":
                            requested = pair(f"gpt-5.6-preview-{family}", family, "max")
                            node["requirements"]["fallback_pairs"].append(selected)  # type: ignore[index]
                            selection["requested_pair"] = requested
                            selection["fallback_reason"] = "unavailable"
                        elif origin == "inherited":
                            plan["orchestration"]["parent"] = {  # type: ignore[index]
                                "model": f"gpt-5.6-{family}",
                                "family": family,
                                "effort": effort,
                                "integrator_class": "structured" if family == "luna" else "general",
                            }
                        elif origin == "explicit_user":
                            selection["requested_pair"] = selected
                        node["selection"] = selection

                        code, result = validate(plan)

                        self.assertEqual(3, code, result)
                        self.assertIn("SELECTED_POLICY_DENIED", error_codes(result))

    def test_family_specific_floor_keeps_luna_xhigh_and_terra_high(self) -> None:
        for selected in (
            pair("gpt-5.6-luna", "luna", "xhigh"),
            pair("gpt-5.6-terra", "terra", "high"),
        ):
            with self.subTest(selected=selected):
                plan = base_plan()
                node = plan["nodes"][0]  # type: ignore[index]
                node["selection"]["selected_pair"] = selected  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(0, code, result)

    def test_explicit_policy_denied_selection_cannot_self_authorize(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        selected = pair("gpt-5.6-luna", "luna", "high")
        node["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
        node["selection"] = {
            "origin": "explicit_user",
            "requested_pair": selected,
            "selected_pair": selected,
            "fallback_reason": None,
        }
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("SELECTED_POLICY_DENIED", error_codes(result))

    def test_plan_cannot_embed_its_own_policy_authorization(self) -> None:
        plan = base_plan()
        plan["nodes"][0]["selection"]["policy_exception_acknowledged"] = True  # type: ignore[index]
        code, result = validate(plan)
        self.assertEqual(2, code, result)
        self.assertIn("SCHEMA_UNKNOWN_FIELD", error_codes(result))

    def test_explicit_high_risk_terra_medium_remains_semantically_insufficient(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("high_risk_impl", 0)
        selected = pair("gpt-5.6-terra", "terra", "medium")
        writer["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
        writer["selection"] = {
            "origin": "explicit_user",
            "requested_pair": selected,
            "selected_pair": selected,
            "fallback_reason": None,
        }
        reviewer = make_reviewer("strong_review", 1, ["high_risk_impl"])
        plan["nodes"] = [writer, reviewer]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        codes = error_codes(result)
        self.assertIn("SELECTED_POLICY_DENIED", codes)
        self.assertIn("SELECTED_BELOW_MINIMUM_EFFORT", codes)
        self.assertIn("SELECTED_TERRA_HIGH_RISK", codes)

    def test_fallback_cannot_restore_terra_medium(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        requested = pair("gpt-5.6-luna", "luna", "max")
        selected = pair("gpt-5.6-terra", "terra", "medium")
        node["requirements"]["minimum_child_effort"] = "medium"  # type: ignore[index]
        node["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
        node["requirements"]["fallback_pairs"] = [selected]  # type: ignore[index]
        node["selection"] = {
            "origin": "fallback",
            "requested_pair": requested,
            "selected_pair": selected,
            "fallback_reason": "unavailable",
        }
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("FALLBACK_POLICY_DENIED", error_codes(result))
        self.assertIn("SELECTED_POLICY_DENIED", error_codes(result))

    def test_every_allowed_candidate_is_validated_even_when_not_selected(self) -> None:
        cases = (
            (
                pair("gpt-5.6-preview-terra", "terra", "max"),
                "ALLOWED_RUNTIME_PAIR_UNAVAILABLE",
            ),
            (
                pair("gpt-5.6-terra", "terra", "medium"),
                "ALLOWED_POLICY_DENIED",
            ),
        )
        for candidate, expected_code in cases:
            with self.subTest(candidate=candidate, expected_code=expected_code):
                plan = base_plan()
                plan["nodes"][0]["requirements"]["allowed_model_effort_pairs"].append(candidate)  # type: ignore[index]
                code, result = validate(plan)
                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_every_fallback_candidate_is_validated_even_when_not_selected(self) -> None:
        cases = (
            (
                pair("gpt-5.6-preview-terra", "terra", "max"),
                "FALLBACK_RUNTIME_PAIR_UNAVAILABLE",
            ),
            (
                pair("gpt-5.6-terra", "terra", "medium"),
                "FALLBACK_POLICY_DENIED",
            ),
        )
        for candidate, expected_code in cases:
            with self.subTest(candidate=candidate, expected_code=expected_code):
                plan = base_plan()
                node = plan["nodes"][0]  # type: ignore[index]
                node["requirements"]["allowed_model_effort_pairs"].append(candidate)  # type: ignore[index]
                node["requirements"]["fallback_pairs"].append(candidate)  # type: ignore[index]
                code, result = validate(plan)
                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_fallback_candidates_must_be_a_subset_of_allowed_candidates(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        node["requirements"]["allowed_model_effort_pairs"] = [  # type: ignore[index]
            pair("gpt-5.6-luna", "luna", "xhigh")
        ]
        node["requirements"]["fallback_pairs"] = [  # type: ignore[index]
            pair("gpt-5.6-terra", "terra", "high")
        ]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("FALLBACK_PAIR_NOT_ALLOWED", error_codes(result))

    def test_unavailable_fallback_reason_must_be_true(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        requested = pair("gpt-5.6-luna", "luna", "max")
        selected = pair("gpt-5.6-terra", "terra", "max")
        node["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
        node["requirements"]["fallback_pairs"] = [selected]  # type: ignore[index]
        node["selection"] = {
            "origin": "fallback",
            "requested_pair": requested,
            "selected_pair": selected,
            "fallback_reason": "unavailable",
        }
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("FALLBACK_REASON_FALSE_UNAVAILABLE", error_codes(result))

    def test_policy_rejection_fallback_reason_must_be_true(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        requested = pair("gpt-5.6-sol", "sol", "max")
        selected = pair("gpt-5.6-terra", "terra", "high")
        node["selection"] = {
            "origin": "fallback",
            "requested_pair": requested,
            "selected_pair": selected,
            "fallback_reason": "policy_rejection",
        }

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("FALLBACK_REASON_FALSE_POLICY_REJECTION", error_codes(result))

    def test_semantically_rejected_requested_pair_can_use_policy_fallback(self) -> None:
        plan = base_plan()
        writer = make_writer("bounded_implementation")
        writer["selection"] = {
            "origin": "fallback",
            "requested_pair": pair("gpt-5.6-luna", "luna", "xhigh"),
            "selected_pair": pair("gpt-5.6-sol", "sol", "high"),
            "fallback_reason": "policy_rejection",
        }
        plan["nodes"] = [writer]

        code, result = validate(plan)

        self.assertEqual(0, code, result)

    def test_denied_requested_pair_cannot_enter_a_certified_plan(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        selected = pair("gpt-5.6-sol", "sol", "high")
        node["requirements"]["fallback_pairs"] = [selected]  # type: ignore[index]
        node["selection"] = {
            "origin": "fallback",
            "requested_pair": pair("gpt-5.6-luna", "luna", "high"),
            "selected_pair": selected,
            "fallback_reason": "policy_rejection",
        }

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("REQUESTED_POLICY_DENIED", error_codes(result))

    def test_invalid_open_work_fallback_is_rejected_while_latent(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        sol_high = pair("gpt-5.6-sol", "sol", "high")
        luna_xhigh = pair("gpt-5.6-luna", "luna", "xhigh")
        node.update({"work_class": "open", "context_scope": "repository", "oracle": "strong"})
        node["requirements"] = {
            "required_integrator_class": "open",
            "minimum_child_effort": "high",
            "minimum_integrator_effort": "xhigh",
            "allowed_model_effort_pairs": [sol_high, luna_xhigh],
            "fallback_pairs": [luna_xhigh],
        }
        node["selection"] = {
            "origin": "automatic",
            "requested_pair": None,
            "selected_pair": sol_high,
            "fallback_reason": None,
        }
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("FALLBACK_WORK_CLASS_MISMATCH", error_codes(result))

    def test_latent_high_risk_candidates_must_meet_risk_and_effort_floors(self) -> None:
        defects = (
            (
                pair("gpt-5.6-terra", "terra", "xhigh"),
                {
                    "WORK_CLASS_MISMATCH",
                    "TERRA_WORK_CLASS_MISMATCH",
                    "TERRA_HIGH_RISK",
                },
            ),
            (
                pair("gpt-5.6-sol", "sol", "high"),
                {"BELOW_MINIMUM_EFFORT"},
            ),
        )
        for source, candidate, suffixes in (
            (source, candidate, suffixes)
            for source in ("ALLOWED", "FALLBACK")
            for candidate, suffixes in defects
        ):
            with self.subTest(source=source, candidate=candidate):
                plan = base_plan()
                writer = make_high_risk_writer("permissions_change", 0)
                reviewer = make_reviewer("permissions_review", 1, ["permissions_change"])
                writer["requirements"]["allowed_model_effort_pairs"].append(candidate)  # type: ignore[index]
                if source == "FALLBACK":
                    writer["requirements"]["fallback_pairs"].append(candidate)  # type: ignore[index]
                plan["nodes"] = [writer, reviewer]
                code, result = validate(plan)
                self.assertEqual(3, code, result)
                codes = error_codes(result)
                for suffix in suffixes:
                    self.assertIn(f"{source}_{suffix}", codes)

    def test_luna_max_unavailable_selected_is_rejected(self) -> None:
        plan = base_plan()
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            item
            for item in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (item["family"] == "luna" and item["effort"] == "max")
        ]
        node = plan["nodes"][0]  # type: ignore[index]
        selected = pair("gpt-5.6-luna", "luna", "max")
        node["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
        node["selection"]["selected_pair"] = selected  # type: ignore[index]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("SELECTED_RUNTIME_PAIR_UNAVAILABLE", error_codes(result))

    def test_luna_max_unavailable_can_use_enumerated_terra_max(self) -> None:
        plan = base_plan()
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            item
            for item in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (item["family"] == "luna" and item["effort"] == "max")
        ]
        node = plan["nodes"][0]  # type: ignore[index]
        requested = pair("gpt-5.6-luna", "luna", "max")
        selected = pair("gpt-5.6-terra", "terra", "max")
        node["requirements"]["allowed_model_effort_pairs"].append(selected)  # type: ignore[index]
        node["requirements"]["fallback_pairs"] = [selected]  # type: ignore[index]
        node["selection"] = {
            "origin": "fallback",
            "requested_pair": requested,
            "selected_pair": selected,
            "fallback_reason": "unavailable",
        }
        code, result = validate(plan)
        self.assertEqual(0, code, result)

    def test_unknown_root_cause_cannot_route_to_luna(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        node.update({"work_class": "open", "oracle": "weak", "context_scope": "repository"})
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("SELECTED_LUNA_WORK_CLASS_MISMATCH", error_codes(result))
        self.assertIn("SELECTED_LUNA_ORACLE_INSUFFICIENT", error_codes(result))

    def test_same_wave_public_api_conflict_is_rejected(self) -> None:
        plan = base_plan()
        first = make_writer("api_contract")
        second = make_writer("api_implementation")
        first["write_conflict_groups"] = ["public-api:user"]
        second["write_conflict_groups"] = ["public-api:user"]
        plan["nodes"] = [first, second]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("WRITE_CONFLICT_OVERLAP", error_codes(result))

    def test_serial_public_api_conflict_is_valid(self) -> None:
        plan = base_plan()
        first = make_writer("api_contract", 0)
        second = make_writer("api_implementation", 1)
        first["write_conflict_groups"] = ["public-api:user"]
        second["write_conflict_groups"] = ["public-api:user"]
        second["depends_on"] = ["api_contract"]
        plan["nodes"] = [first, second]
        code, result = validate(plan)
        self.assertEqual(0, code, result)

    def test_noncanonical_path_alias_cannot_hide_a_parallel_write_conflict(self) -> None:
        plan = base_plan()
        first = make_writer("writer_a")
        second = make_writer("writer_b")
        first["owned_mutable_surfaces"] = ["src/foo.ts"]
        second["owned_mutable_surfaces"] = ["src/../src/foo.ts"]
        plan["nodes"] = [first, second]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("SURFACE_NONCANONICAL", error_codes(result))
        self.assertIn("WRITE_CONFLICT_OVERLAP", error_codes(result))

    def test_case_separator_and_directory_aliases_overlap(self) -> None:
        aliases = (
            ("src/Foo.ts", "src/foo.ts"),
            (r"src\foo.ts", "src/foo.ts"),
            ("src", "src/foo.ts"),
            ("src/module", "src/module/file.ts"),
        )
        for left_surface, right_surface in aliases:
            with self.subTest(left=left_surface, right=right_surface):
                plan = base_plan()
                first = make_writer("writer_a")
                second = make_writer("writer_b")
                first["owned_mutable_surfaces"] = [left_surface]
                second["owned_mutable_surfaces"] = [right_surface]
                plan["nodes"] = [first, second]
                code, result = validate(plan)
                self.assertEqual(3, code, result)
                self.assertIn("WRITE_CONFLICT_OVERLAP", error_codes(result))

    def test_windows_path_alias_forms_are_rejected(self) -> None:
        cases = (
            ("src/foo.ts.", "SURFACE_WINDOWS_TRAILING_ALIAS"),
            ("src/foo.ts:stream", "SURFACE_WINDOWS_ADS_UNSUPPORTED"),
            ("C:src/foo.ts", "SURFACE_DRIVE_RELATIVE_UNSUPPORTED"),
        )
        for surface, expected_code in cases:
            with self.subTest(surface=surface):
                plan = base_plan()
                writer = make_writer("writer_alias")
                writer["owned_mutable_surfaces"] = [surface]
                plan["nodes"] = [writer]

                code, result = validate(plan)

                self.assertEqual(3, code, result)
                self.assertIn(expected_code, error_codes(result))

    def test_directory_prefix_without_a_path_boundary_does_not_overlap(self) -> None:
        plan = base_plan()
        first = make_writer("writer_a")
        second = make_writer("writer_b")
        first["owned_mutable_surfaces"] = ["src/module"]
        second["owned_mutable_surfaces"] = ["src/module2/file.ts"]
        plan["nodes"] = [first, second]
        code, result = validate(plan)
        self.assertEqual(0, code, result)

    def test_write_requires_post_validation(self) -> None:
        plan = base_plan()
        writer = make_writer("implementation")
        writer["validation_steps"] = [
            {"id": "pre_diff", "kind": "diff", "phase": "pre", "required": True}
        ]
        plan["nodes"] = [writer]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("WRITE_POST_VALIDATION_MISSING", error_codes(result))

    def test_pre_state_labeled_as_post_is_not_write_validation(self) -> None:
        plan = base_plan()
        writer = make_writer("implementation")
        writer["validation_steps"] = [
            {"id": "fake_post", "kind": "pre_state", "phase": "post", "required": True}
        ]
        plan["nodes"] = [writer]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("VALIDATION_PHASE_MISMATCH", error_codes(result))
        self.assertIn("WRITE_POST_VALIDATION_MISSING", error_codes(result))

    def test_instruction_only_reviewer_needs_and_reports_guards(self) -> None:
        plan = base_plan()
        reviewer = make_reviewer("security_review", 0, [])
        reviewer["read_only_control"] = {
            "declared": True,
            "enforcement": "instruction_pre_post_check",
        }
        reviewer["validation_steps"] = [
            {"id": "before", "kind": "pre_state", "phase": "pre", "required": True},
            {"id": "after", "kind": "post_state", "phase": "post", "required": True},
        ]
        plan["nodes"] = [reviewer]
        code, result = validate(plan)
        self.assertEqual(0, code, result)
        self.assertIn("REVIEWER_INSTRUCTION_ONLY", warning_codes(result))

    def test_high_risk_write_requires_downstream_reviewer(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("permissions_change")
        plan["nodes"] = [writer]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("HIGH_RISK_REVIEW_MISSING", error_codes(result))

    def test_high_risk_write_with_independent_reviewer_is_valid(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("permissions_change", 0)
        reviewer = make_reviewer("permissions_review", 1, ["permissions_change"])
        plan["nodes"] = [writer, reviewer]
        code, result = validate(plan)
        self.assertEqual(0, code, result)

    def test_high_risk_contract_floors_are_derived_not_trusted(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("permissions_change", 0)
        writer["requirements"].update(  # type: ignore[union-attr]
            {
                "required_integrator_class": "general",
                "minimum_child_effort": "high",
                "minimum_integrator_effort": "high",
            }
        )
        reviewer = make_reviewer("permissions_review", 1, ["permissions_change"])
        plan["nodes"] = [writer, reviewer]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertEqual(
            {
                "DERIVED_REQUIRED_INTEGRATOR_CLASS_UNDERDECLARED",
                "DERIVED_MINIMUM_CHILD_EFFORT_UNDERDECLARED",
                "DERIVED_MINIMUM_INTEGRATOR_EFFORT_UNDERDECLARED",
            },
            error_codes(result),
            result,
        )

    def test_high_risk_work_class_is_derived_not_self_declared(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("permissions_change", 0)
        writer["work_class"] = "general"
        reviewer = make_reviewer("permissions_review", 1, ["permissions_change"])
        plan["nodes"] = [writer, reviewer]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("DERIVED_WORK_CLASS_UNDERDECLARED", error_codes(result))

    def test_weak_reviewer_and_underdeclared_floors_cannot_recreate_high_risk_bypass(self) -> None:
        plan = base_plan()
        plan["orchestration"]["parent"] = {  # type: ignore[index]
            "model": "gpt-5.6-terra",
            "family": "terra",
            "effort": "high",
            "integrator_class": "general",
        }
        writer = make_high_risk_writer("permissions_change", 0)
        writer["requirements"].update(  # type: ignore[union-attr]
            {
                "required_integrator_class": "general",
                "minimum_child_effort": "high",
                "minimum_integrator_effort": "high",
            }
        )
        reviewer = make_reviewer("weak_review", 1, ["permissions_change"])
        luna_xhigh = pair("gpt-5.6-luna", "luna", "xhigh")
        reviewer.update({"work_class": "structured", "risk": "low", "oracle": "deterministic"})
        reviewer["requirements"] = {
            "required_integrator_class": "general",
            "minimum_child_effort": "high",
            "minimum_integrator_effort": "high",
            "allowed_model_effort_pairs": [luna_xhigh],
            "fallback_pairs": [],
        }
        reviewer["selection"] = {
            "origin": "automatic",
            "requested_pair": None,
            "selected_pair": luna_xhigh,
            "fallback_reason": None,
        }
        plan["nodes"] = [writer, reviewer]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        codes = error_codes(result)
        expected = {
            "ALLOWED_REVIEWER_SOL_REQUIRED",
            "DERIVED_REQUIRED_INTEGRATOR_CLASS_UNDERDECLARED",
            "DERIVED_MINIMUM_CHILD_EFFORT_UNDERDECLARED",
            "DERIVED_MINIMUM_INTEGRATOR_EFFORT_UNDERDECLARED",
            "PARENT_INTEGRATOR_CLASS_INSUFFICIENT",
            "PARENT_INTEGRATOR_EFFORT_INSUFFICIENT",
            "SELECTED_REVIEWER_SOL_REQUIRED",
            "REVIEWER_WORK_CLASS_INVALID",
            "REVIEWER_RISK_INVALID",
            "REVIEWER_ORACLE_INSUFFICIENT",
            "HIGH_RISK_REVIEW_MISSING",
        }
        self.assertEqual(expected, codes, result)

    def test_high_risk_read_only_work_still_requires_independent_review(self) -> None:
        plan = base_plan()
        plan["nodes"] = [make_high_risk_reader("security_diagnosis")]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("HIGH_RISK_REVIEW_MISSING", error_codes(result))

    def test_high_risk_reviewer_must_use_a_different_executor(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("permissions_change", 0)
        reviewer = make_reviewer("permissions_review", 1, ["permissions_change"])
        reviewer["executor_id"] = writer["executor_id"]
        plan["nodes"] = [writer, reviewer]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("REVIEWER_EXECUTOR_NOT_INDEPENDENT", error_codes(result))

    def test_high_risk_reviewer_must_be_read_only(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("permissions_change", 0)
        reviewer = make_reviewer("permissions_review", 1, ["permissions_change"])
        reviewer.update(
            {
                "access_mode": "workspace_write",
                "owned_mutable_surfaces": ["reviews/permissions.md"],
                "write_conflict_groups": ["review:permissions"],
            }
        )
        plan["nodes"] = [writer, reviewer]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("REVIEWER_NOT_READ_ONLY", error_codes(result))

    def test_high_risk_reviewer_quality_contract_is_enforced(self) -> None:
        defects = (
            (
                "work_class",
                {
                    "DERIVED_WORK_CLASS_UNDERDECLARED",
                    "REVIEWER_WORK_CLASS_INVALID",
                    "HIGH_RISK_REVIEW_MISSING",
                },
            ),
            (
                "risk",
                {"REVIEWER_RISK_INVALID", "HIGH_RISK_REVIEW_MISSING"},
            ),
            (
                "oracle",
                {"REVIEWER_ORACLE_INSUFFICIENT", "HIGH_RISK_REVIEW_MISSING"},
            ),
            (
                "family",
                {
                    "ALLOWED_REVIEWER_SOL_REQUIRED",
                    "ALLOWED_TERRA_HIGH_RISK",
                    "ALLOWED_TERRA_WORK_CLASS_MISMATCH",
                    "ALLOWED_WORK_CLASS_MISMATCH",
                    "SELECTED_REVIEWER_SOL_REQUIRED",
                    "SELECTED_TERRA_HIGH_RISK",
                    "SELECTED_TERRA_WORK_CLASS_MISMATCH",
                    "SELECTED_WORK_CLASS_MISMATCH",
                    "HIGH_RISK_REVIEW_MISSING",
                },
            ),
            (
                "effort",
                {
                    "ALLOWED_BELOW_MINIMUM_EFFORT",
                    "SELECTED_BELOW_MINIMUM_EFFORT",
                    "HIGH_RISK_REVIEW_MISSING",
                },
            ),
        )
        for defect, expected_codes in defects:
            with self.subTest(defect=defect):
                plan = base_plan()
                writer = make_high_risk_writer("permissions_change", 0)
                reviewer = make_reviewer("permissions_review", 1, ["permissions_change"])
                if defect == "work_class":
                    reviewer["work_class"] = "general"
                elif defect == "risk":
                    reviewer["risk"] = "medium"
                elif defect == "oracle":
                    reviewer["oracle"] = "deterministic"
                elif defect == "family":
                    terra_xhigh = pair("gpt-5.6-terra", "terra", "xhigh")
                    reviewer["requirements"]["allowed_model_effort_pairs"] = [terra_xhigh]  # type: ignore[index]
                    reviewer["requirements"]["fallback_pairs"] = []  # type: ignore[index]
                    reviewer["selection"]["selected_pair"] = terra_xhigh  # type: ignore[index]
                elif defect == "effort":
                    sol_high = pair("gpt-5.6-sol", "sol", "high")
                    reviewer["requirements"]["allowed_model_effort_pairs"] = [sol_high]  # type: ignore[index]
                    reviewer["requirements"]["fallback_pairs"] = []  # type: ignore[index]
                    reviewer["selection"]["selected_pair"] = sol_high  # type: ignore[index]
                plan["nodes"] = [writer, reviewer]
                code, result = validate(plan)
                self.assertEqual(3, code, result)
                self.assertEqual(expected_codes, error_codes(result), result)

    def test_declared_reviewer_must_be_downstream(self) -> None:
        plan = base_plan()
        writer = make_high_risk_writer("permissions_change", 0)
        reviewer = make_reviewer("permissions_review", 0, ["permissions_change"])
        reviewer["depends_on"] = []
        plan["nodes"] = [writer, reviewer]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertIn("REVIEW_ORDER_MISSING", error_codes(result))
        self.assertIn("HIGH_RISK_REVIEW_MISSING", error_codes(result))

    def test_luna_write_requires_bounded_context(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        node.update(
            {
                "access_mode": "workspace_write",
                "context_scope": "repository",
                "owned_mutable_surfaces": ["out/data.json"],
                "write_conflict_groups": ["generated:data"],
            }
        )
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("SELECTED_LUNA_WRITE_NOT_BOUNDED", error_codes(result))

    def test_dag_cycle_is_rejected(self) -> None:
        plan = base_plan()
        first = base_node()
        second = base_node()
        first.update({"id": "first", "wave": 0, "depends_on": ["second"]})
        second.update({"id": "second", "wave": 1, "depends_on": ["first"]})
        plan["nodes"] = [first, second]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("DAG_CYCLE", error_codes(result))

    def test_duplicate_writer_ids_are_reported_without_internal_error(self) -> None:
        plan = base_plan()
        plan["nodes"] = [make_writer("duplicate"), make_writer("duplicate")]
        code, result = validate(plan)
        self.assertEqual(3, code, result)
        self.assertFalse(result["valid"])
        self.assertIn("NODE_ID_DUPLICATE", error_codes(result))
        self.assertNotIn("VALIDATOR_INTERNAL_ERROR", error_codes(result))

    def test_executor_ids_must_be_canonical_before_independence_checks(self) -> None:
        for executor_id in ("executor_alias ", "Executor_Alias", "executor-alias"):
            with self.subTest(executor_id=executor_id):
                plan = base_plan()
                plan["nodes"][0]["executor_id"] = executor_id  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(2, code, result)
                self.assertIn("SCHEMA_PATTERN", error_codes(result))

    def test_concurrency_limit_is_enforced(self) -> None:
        plan = base_plan()
        nodes = []
        for index in range(4):
            node = base_node()
            node["id"] = f"batch_{index}"
            nodes.append(node)
        plan["nodes"] = nodes
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("CONCURRENCY_LIMIT_EXCEEDED", error_codes(result))

    def test_parent_integrator_floor_is_enforced(self) -> None:
        plan = base_plan()
        plan["orchestration"]["parent"] = {  # type: ignore[index]
            "model": "gpt-5.6-terra",
            "family": "terra",
            "effort": "high",
            "integrator_class": "general",
        }
        node = plan["nodes"][0]  # type: ignore[index]
        node["requirements"]["required_integrator_class"] = "critical"  # type: ignore[index]
        node["requirements"]["minimum_integrator_effort"] = "xhigh"  # type: ignore[index]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("PARENT_INTEGRATOR_CLASS_INSUFFICIENT", error_codes(result))
        self.assertIn("PARENT_INTEGRATOR_EFFORT_INSUFFICIENT", error_codes(result))

    def test_runtime_model_family_spoof_is_rejected(self) -> None:
        plan = base_plan()
        plan["runtime"]["available_pairs"].append(  # type: ignore[index]
            runtime_pair("gpt-5.6-luna", "sol", "xhigh", ALL_CLASSES)
        )
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("RUNTIME_MODEL_FAMILY_MISMATCH", error_codes(result))

    def test_model_identifiers_are_canonical_in_every_plan_location(self) -> None:
        for location in ("parent", "runtime", "allowed", "fallback", "selected", "requested"):
            with self.subTest(location=location):
                plan = base_plan()
                node = plan["nodes"][0]  # type: ignore[index]
                if location == "parent":
                    plan["orchestration"]["parent"]["model"] = "gpt-5.6-sol "  # type: ignore[index]
                elif location == "runtime":
                    plan["runtime"]["available_pairs"][0]["model"] = "gpt-5.6-luna "  # type: ignore[index]
                elif location == "allowed":
                    node["requirements"]["allowed_model_effort_pairs"][0]["model"] = "gpt-5.6-luna "  # type: ignore[index]
                elif location == "fallback":
                    node["requirements"]["fallback_pairs"][0]["model"] = "gpt-5.6-terra "  # type: ignore[index]
                elif location == "selected":
                    node["selection"]["selected_pair"]["model"] = "gpt-5.6-luna "  # type: ignore[index]
                else:
                    node["selection"] = {
                        "origin": "explicit_user",
                        "requested_pair": pair("gpt-5.6-luna ", "luna", "xhigh"),
                        "selected_pair": pair("gpt-5.6-luna", "luna", "xhigh"),
                        "fallback_reason": None,
                    }

                code, result = validate(plan)

                self.assertEqual(2, code, result)
                self.assertIn("SCHEMA_PATTERN", error_codes(result))

    def test_ambiguous_and_noncanonical_family_slugs_are_rejected(self) -> None:
        for model in ("gpt-5.6-luna2", "gpt-5.6-sol-luna"):
            with self.subTest(model=model):
                plan = base_plan()
                plan["runtime"]["available_pairs"].append(  # type: ignore[index]
                    runtime_pair(model, "sol", "high", ALL_CLASSES)
                )
                code, result = validate(plan)
                self.assertEqual(3, code, result)
                self.assertIn("RUNTIME_MODEL_FAMILY_MISMATCH", error_codes(result))

    def test_family_spoof_is_rejected_in_allowed_and_selected_candidates(self) -> None:
        for model in ("gpt-5.6-luna2", "gpt-5.6-sol-luna"):
            with self.subTest(model=model):
                plan = base_plan()
                node = plan["nodes"][0]  # type: ignore[index]
                spoof = pair(model, "sol", "high")
                node["requirements"]["allowed_model_effort_pairs"].append(spoof)  # type: ignore[index]
                node["selection"]["selected_pair"] = spoof  # type: ignore[index]
                code, result = validate(plan)
                self.assertEqual(3, code, result)
                codes = error_codes(result)
                self.assertIn("ALLOWED_MODEL_FAMILY_MISMATCH", codes)
                self.assertIn("SELECTED_MODEL_FAMILY_MISMATCH", codes)

    def test_inherited_pair_must_match_parent(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        node["selection"]["origin"] = "inherited"  # type: ignore[index]
        code, result = validate(plan)
        self.assertEqual(3, code)
        self.assertIn("INHERITED_PAIR_MISMATCH", error_codes(result))

    def test_explicit_model_and_effort_form_a_confirmed_visible_chain(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(node)

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        self.assertEqual(1, result["stats"]["confirmed_child_count"])
        report = MODULE.render_routing_report(plan)
        self.assertIn("structured_operator (gpt-5.6-luna, xhigh)", report)
        self.assertIn("gpt-5.6-luna / xhigh", report)
        self.assertIn("confirmed-explicit", report)
        self.assertIn("spawn_agent:agent-001", report)

    def test_explicit_model_without_effort_is_unresolved_and_invalid(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "active"
        node = plan["nodes"][0]  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(node, confirmation_status="default-unresolved")
        dispatch["attempts"][0]["reasoning_effort"] = None  # type: ignore[index]
        node["lifecycle_state"] = "dispatched"
        node["dispatch"] = dispatch

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        codes = error_codes(result)
        self.assertIn("DISPATCH_EXPLICIT_PAIR_INCOMPLETE", codes)
        self.assertIn("UNRESOLVED_DISPATCH_FORBIDDEN", codes)
        self.assertEqual(1, result["stats"]["unresolved_dispatch_count"])

    def test_exact_known_parent_pair_can_be_confirmed_by_full_history_inheritance(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        parent_pair = pair("gpt-5.6-sol", "sol", "xhigh")
        node["requirements"]["allowed_model_effort_pairs"].append(parent_pair)  # type: ignore[index]
        node["selection"] = {
            "origin": "inherited",
            "requested_pair": None,
            "selected_pair": parent_pair,
            "fallback_reason": None,
        }
        label = "structured_operator (gpt-5.6-sol, xhigh)"
        node["lifecycle_state"] = "completed"
        node["dispatch"] = {
            "attempts": [
                {
                    "attempt_index": 1,
                    "mode": "inherit_parent",
                    "task_name": "gpt_5_6_sol_xhigh_json_convert_a1",
                    "agent_label": label,
                    "fork_turns": "all",
                    "requested_pair": copy.deepcopy(parent_pair),
                    "model": None,
                    "reasoning_effort": None,
                    "receipt_status": "accepted",
                    "receipt_ref": "spawn_agent:agent-inherited-001",
                    "effective_pair": copy.deepcopy(parent_pair),
                    "confirmation_status": "confirmed-inherited",
                }
            ],
            "effective_attempt": 1,
        }
        node["result"] = {
            "status": "success",
            "dispatch_attempt": 1,
            "agent_label": label,
            "assigned_pair_echo": copy.deepcopy(parent_pair),
            "confirmation_status_echo": "confirmed-inherited",
        }

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        self.assertIn("confirmed-inherited", MODULE.render_routing_report(plan))

    def test_unresolved_inheritance_cannot_be_presented_as_verified(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        parent_pair = pair("gpt-5.6-sol", "sol", "xhigh")
        node["requirements"]["allowed_model_effort_pairs"].append(parent_pair)  # type: ignore[index]
        node["selection"] = {
            "origin": "inherited",
            "requested_pair": None,
            "selected_pair": parent_pair,
            "fallback_reason": None,
        }
        label = "structured_operator (gpt-5.6-sol, xhigh)"
        node["lifecycle_state"] = "completed"
        node["dispatch"] = {
            "attempts": [
                {
                    "attempt_index": 1,
                    "mode": "inherit_parent",
                    "task_name": "gpt_5_6_sol_xhigh_json_convert_a1",
                    "agent_label": label,
                    "fork_turns": "all",
                    "requested_pair": copy.deepcopy(parent_pair),
                    "model": None,
                    "reasoning_effort": None,
                    "receipt_status": "accepted",
                    "receipt_ref": "spawn_agent:agent-inherited-unknown",
                    "effective_pair": copy.deepcopy(parent_pair),
                    "confirmation_status": "inherited-unresolved",
                }
            ],
            "effective_attempt": 1,
        }
        node["result"] = {
            "status": "success",
            "dispatch_attempt": 1,
            "agent_label": label,
            "assigned_pair_echo": copy.deepcopy(parent_pair),
            "confirmation_status_echo": "inherited-unresolved",
        }

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("UNRESOLVED_DISPATCH_FORBIDDEN", error_codes(result))

    def test_fallback_report_contains_requested_and_effective_pairs(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "finalized"
        plan["runtime"]["available_pairs"] = [  # type: ignore[index]
            item
            for item in plan["runtime"]["available_pairs"]  # type: ignore[index]
            if not (item["family"] == "luna" and item["effort"] == "max")
        ]
        node = plan["nodes"][0]  # type: ignore[index]
        luna_max = pair("gpt-5.6-luna", "luna", "max")
        terra_max = pair("gpt-5.6-terra", "terra", "max")
        node["requirements"]["allowed_model_effort_pairs"] = [terra_max]  # type: ignore[index]
        node["requirements"]["fallback_pairs"] = [terra_max]  # type: ignore[index]
        node["selection"] = {
            "origin": "fallback",
            "requested_pair": luna_max,
            "selected_pair": terra_max,
            "fallback_reason": "unavailable",
        }
        complete_node_with_explicit_dispatch(node)
        dispatch = node["dispatch"]  # type: ignore[assignment]
        accepted = dispatch["attempts"][0]  # type: ignore[index]
        accepted.update(
            {
                "attempt_index": 2,
                "task_name": "gpt_5_6_terra_max_json_convert_a2",
                "receipt_ref": "spawn_agent:agent-fallback-002",
            }
        )
        rejected = {
            "attempt_index": 1,
            "mode": "explicit",
            "task_name": "gpt_5_6_luna_max_json_convert_a1",
            "agent_label": "structured_operator (gpt-5.6-luna, max)",
            "fork_turns": "none",
            "requested_pair": copy.deepcopy(luna_max),
            "model": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "receipt_status": "rejected",
            "receipt_ref": "spawn_agent:error-luna-max-unavailable",
            "effective_pair": None,
            "confirmation_status": "runtime-rejected",
        }
        dispatch["attempts"] = [rejected, accepted]  # type: ignore[index]
        dispatch["effective_attempt"] = 2  # type: ignore[index]
        node["result"]["dispatch_attempt"] = 2  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        report = MODULE.render_routing_report(plan)
        self.assertIn("gpt-5.6-luna / max", report)
        self.assertIn("gpt-5.6-terra / max", report)
        self.assertIn("fallback-confirmed", report)
        self.assertIn("a1 rejected spawn_agent:error-luna-max-unavailable", report)
        self.assertIn("a2 accepted spawn_agent:agent-fallback-002", report)

    def test_child_pair_echo_must_match_dispatch_receipt(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        complete_node_with_explicit_dispatch(node)
        node["result"]["assigned_pair_echo"] = pair("gpt-5.6-sol", "sol", "high")  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("RESULT_PAIR_ECHO_MISMATCH", error_codes(result))

    def test_task_name_cannot_hide_model_or_effort(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "active"
        node = plan["nodes"][0]  # type: ignore[index]
        node["lifecycle_state"] = "dispatched"
        node["dispatch"] = accepted_explicit_dispatch(node)
        node["dispatch"]["attempts"][0]["task_name"] = "json_convert_worker"  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("DISPATCH_TASK_NAME_MISMATCH", error_codes(result))

    def test_task_name_starts_with_model_and_effort_for_narrow_ui(self) -> None:
        plan = base_plan()
        node = plan["nodes"][0]  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(node)
        task_name = dispatch["attempts"][0]["task_name"]  # type: ignore[index]

        self.assertEqual("gpt_5_6_luna_xhigh_json_convert_a1", task_name)
        self.assertTrue(task_name.startswith("gpt_5_6_luna_xhigh_"))

    def test_pair_at_truncated_suffix_is_rejected(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "active"
        node = plan["nodes"][0]  # type: ignore[index]
        node["lifecycle_state"] = "dispatched"
        node["dispatch"] = accepted_explicit_dispatch(node)
        node["dispatch"]["attempts"][0]["task_name"] = "json_convert_a1_gpt_5_6_luna_xhigh"  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("DISPATCH_TASK_NAME_MISMATCH", error_codes(result))

    def test_explicit_override_cannot_use_full_history_fork(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "active"
        node = plan["nodes"][0]  # type: ignore[index]
        node["lifecycle_state"] = "dispatched"
        node["dispatch"] = accepted_explicit_dispatch(node)
        node["dispatch"]["attempts"][0]["fork_turns"] = "all"  # type: ignore[index]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("DISPATCH_EXPLICIT_FULL_HISTORY_FORBIDDEN", error_codes(result))

    def test_runtime_rejection_is_visible_but_not_claimed_as_effective(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "finalized"
        node = plan["nodes"][0]  # type: ignore[index]
        selected = node["selection"]["selected_pair"]  # type: ignore[index]
        node["lifecycle_state"] = "dispatch_blocked"
        node["dispatch"] = {
            "attempts": [
                {
                    "attempt_index": 1,
                    "mode": "explicit",
                    "task_name": "gpt_5_6_luna_xhigh_json_convert_a1",
                    "agent_label": "structured_operator (gpt-5.6-luna, xhigh)",
                    "fork_turns": "none",
                    "requested_pair": copy.deepcopy(selected),
                    "model": selected["model"],
                    "reasoning_effort": selected["effort"],
                    "receipt_status": "rejected",
                    "receipt_ref": "spawn_agent:error-unsupported-pair",
                    "effective_pair": None,
                    "confirmation_status": "runtime-rejected",
                }
            ],
            "effective_attempt": None,
        }

        code, result = validate(plan)

        self.assertEqual(0, code, result)
        report = MODULE.render_routing_report(plan)
        self.assertIn("runtime-rejected", report)
        self.assertIn("| — |", report)

    def test_dispatch_receipt_references_are_unique_across_children(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "active"
        first = base_node()
        second = base_node()
        second["id"] = "json_convert_two"
        second["executor_id"] = "executor_json_convert_two"
        for node in (first, second):
            node["lifecycle_state"] = "dispatched"
            node["dispatch"] = accepted_explicit_dispatch(
                node, receipt_ref="spawn_agent:duplicate-agent-ref"
            )
        plan["nodes"] = [first, second]

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("DISPATCH_RECEIPT_REF_DUPLICATE", error_codes(result))

    def test_no_dispatch_attempt_may_follow_acceptance(self) -> None:
        plan = base_plan()
        plan["ledger_phase"] = "active"
        node = plan["nodes"][0]  # type: ignore[index]
        dispatch = accepted_explicit_dispatch(node)
        accepted = dispatch["attempts"][0]  # type: ignore[index]
        rejected = copy.deepcopy(accepted)
        rejected.update(
            {
                "attempt_index": 2,
                "task_name": "gpt_5_6_luna_xhigh_json_convert_a2",
                "receipt_status": "rejected",
                "receipt_ref": "spawn_agent:error-after-acceptance",
                "effective_pair": None,
                "confirmation_status": "runtime-rejected",
            }
        )
        dispatch["attempts"].append(rejected)  # type: ignore[union-attr]
        node["lifecycle_state"] = "dispatched"
        node["dispatch"] = dispatch

        code, result = validate(plan)

        self.assertEqual(3, code, result)
        self.assertIn("ACCEPTED_DISPATCH_NOT_LAST", error_codes(result))

    def test_report_requires_a_finalized_ledger(self) -> None:
        plan = base_plan()
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "ledger.json"
            ledger_path.write_text(json.dumps(plan), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = MODULE.main([str(ledger_path), "--report"])

        result = json.loads(output.getvalue())
        self.assertEqual(3, code, result)
        self.assertIn("REPORT_LEDGER_NOT_FINALIZED", error_codes(result))

    def test_cli_report_contains_every_verification_column(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = MODULE.main([str(DOCUMENTED_EXAMPLE_PATH), "--report"])

        report = output.getvalue()
        self.assertEqual(0, code, report)
        for column in (
            "agent",
            "role",
            "requested pair",
            "effective pair",
            "confirmation",
            "receipt",
            "result",
            "purpose",
        ):
            self.assertIn(column, report)
        self.assertIn("gpt-5.6-terra / high", report)

    def test_final_result_cannot_omit_model_or_effort_echo(self) -> None:
        for field_name in ("model", "effort"):
            with self.subTest(field=field_name):
                plan = base_plan()
                plan["ledger_phase"] = "finalized"
                node = plan["nodes"][0]  # type: ignore[index]
                complete_node_with_explicit_dispatch(node)
                del node["result"]["assigned_pair_echo"][field_name]  # type: ignore[index]

                code, result = validate(plan)

                self.assertEqual(2, code, result)
                self.assertIn("SCHEMA_REQUIRED", error_codes(result))

    def test_strict_56_is_not_a_supported_profile(self) -> None:
        plan = base_plan()
        plan["profile"] = "strict-5.6"
        code, result = validate(plan)
        self.assertEqual(2, code)
        self.assertIn("SCHEMA_ENUM", error_codes(result))

    def test_selection_only_v2_draft_schema_is_rejected(self) -> None:
        plan = base_plan()
        plan["schema_version"] = "aar.routing-plan.v2"

        code, result = validate(plan)

        self.assertEqual(2, code, result)
        self.assertIn("SCHEMA_VERSION", error_codes(result))

    def test_unknown_field_is_rejected(self) -> None:
        plan = base_plan()
        plan["modle"] = "typo"
        code, result = validate(plan)
        self.assertEqual(2, code)
        self.assertIn("SCHEMA_UNKNOWN_FIELD", error_codes(result))

    def test_cli_rejects_duplicate_json_object_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "duplicate.json"
            plan_path.write_text(
                '{"schema_version":"aar.routing-ledger.v2","schema_version":"shadow"}',
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                code = MODULE.main([str(plan_path)])

        result = json.loads(output.getvalue())
        self.assertEqual(2, code, result)
        self.assertIn("JSON_INPUT_ERROR", error_codes(result))
        self.assertIn("Duplicate JSON object key", result["errors"][0]["message"])

    def test_diagnostics_are_deterministic(self) -> None:
        plan = base_plan()
        plan["orchestration"]["state"] = "unknown"  # type: ignore[index]
        first = validate(copy.deepcopy(plan))
        second = validate(copy.deepcopy(plan))
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True),
            json.dumps(second, ensure_ascii=False, sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
