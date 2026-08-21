# Calibration and Evaluation

Read this reference only when maintaining the policy, using benchmark or telemetry evidence, evaluating a non-default optimization profile, or forward-testing the Skill.

## Evidence status

```yaml
status: cold-start prior
evidence_snapshot_date: 2026-08-20
policy_revision_date: 2026-08-21
source_kind: user-provided community screenshots
confidence: low
official: false
reproducible: unknown
runtime_comparability: unknown
```

The community-data component of the initial performance-sensitive ranking preferences is a low-confidence cold-start prior, not a model-capability ranking. Safety, permission, semantic eligibility, orchestration, and verification rules do not derive from these screenshots.

The screenshots do not establish the benchmark task distribution, scoring implementation, variance, retry policy, environment, context sizes, or sufficient reproduction details. Their scores, sample counts, durations, and reported costs can drift. The screenshot date is the observation date, not a model release date.

These observations are not OpenAI documentation and must not be presented as authoritative capability, intelligence, pricing, latency, or service-level claims. The community "recommended scenarios" panel is also a derived opinion, not official guidance.

## Provisional signals used for the cold start

The supplied snapshots provisionally support only coarse hypotheses for conservative experimentation:

- The supplied screenshots displayed a large reported-score gap between Luna/Terra `low`/`medium` and `high`, especially in the software-engineering view; this is a hypothesis-generating observation, not a measured failure-rate estimate.
- OpenAI positions Luna as fast and affordable, while the supplied snapshot showed some high-effort Luna rows with longer end-to-end duration than some Terra alternatives. V2 therefore does not assume a universal wall-clock ordering across every Luna × effort combination.
- Sol `xhigh` appeared close to Sol Max/Ultra on the shown software-engineering samples while using materially less reported time and cost. V2 adopts `xhigh` as a conservative deep-work preference and keeps Max exceptional; the snapshot does not establish a universal ordering.
- Several rows had small samples, so small score differences and exact rankings are not stable enough to become hard rules.

Do not preserve or optimize around exact screenshot scores inside the core router. Semantic eligibility and validation requirements remain authoritative even when a community score is higher.

## Why Luna below xhigh and Terra below high are excluded automatically

V2 excludes Luna `low`/`medium`/`high` and Terra `low`/`medium` from every certified child route, including automatic selection, fallback, inheritance, and explicit-user provenance.

The 2026-08-21 revision raised Luna's local floor from `high` to `xhigh` at the user's direction to prioritize first-pass reliability and avoid repeat-work cost. This is a policy choice informed by workflow experience, not a benchmark-proven universal threshold or an OpenAI capability limit.

This is a user-selected expected-total-cost policy and quality floor. It assumes that savings on the first invocation may be outweighed by verification, rework, retries, review, and escalation:

```text
E[C_total] =
    C_initial
  + P(retry) * E[C_retry | retry]
  + P(rework) * E[C_rework | rework]
  + P(escalation) * E[C_escalation | escalation]
  + review_cost
  + coordination_cost

E[T_node] =
    T_initial
  + P(retry) * E[T_retry | retry]
  + P(rework) * E[T_rework | rework]
  + P(escalation) * E[T_escalation | escalation]

critical_path_time =
    max(total elapsed time across all required dependency paths)
```

The screenshots do not provide the failure probabilities needed to prove this equation numerically. The exclusion is a conservative and reversible workflow policy, not a claim that these combinations cannot do useful work. Tasks simple enough to justify only those pairs normally remain in the parent, avoiding delegation overhead entirely.

An explicit user selection may still be honored by the execution layer when supported, but an excluded pair remains outside V2 certification and must not be embedded in a routing plan. A policy-excluded pin on the parent does not authorize child inheritance; keep the work in the pinned parent, obtain authority for a qualified child pair, or report that the delegation cannot be certified.

## Luna Max only is a budget-control policy, not a benchmark conclusion

`children=luna-max` maps to `child_policy: luna_max_only` and restricts every created child to exact Luna Max while leaving unsuitable work in the parent. It is a user-selected resource-allocation strategy. The current cold-start screenshots do not prove how it affects Plus quotas, billing, wall-clock time, first-pass success, or expected total cost for a particular workload.

Evaluate this mode by end-to-end outcomes rather than the child call alone: parent-local work retained, number of child attempts, first-pass acceptance, rework avoided, critical-path time, and any runtime-exposed usage. A lower-cost family can still be a poor choice if decomposition or verification overhead dominates; therefore the mode never relaxes semantic eligibility, risk gates, or parent integration requirements.

## Metric-source discipline

Every profile-sensitive ranking records `METRIC_SOURCE`. When the source is not `none`, also record `METRIC_AS_OF` and `EVIDENCE_ID_OR_WINDOW` so stale or incomparable evidence is visible.

| Source | Permitted claim |
| --- | --- |
| `runtime` | Current comparable observed measurements; state the scope |
| `local_telemetry` | Comparable local task history; disclose sample and window |
| `community_prior` | Qualitative cold-start tie-break only |
| `none` | Semantic/policy choice only; no cost or latency optimization claim |

The seeded snapshot identifier is `community_prior / 2026-08-20 / user-supplied-screenshots-v1`.

Do not compare observations from different task shapes, tool surfaces, context sizes, or validation burdens as if they were controlled trials. Sticker price and single-call duration are not expected total cost or critical-path time.

For `profile=economy`, prose provenance is not enough to make a quantitative claim. An automatic/fallback node must bind every ranked candidate and the actual orchestration parent to the strict `economy_evaluation` contract in [routing-policy.md](routing-policy.md#economy-evaluation-contract). Candidate/parent records are unique and namespaced under the root evidence window. The validator uses six-decimal fixed-point arithmetic to recompute the versioned totals, checks complete candidate coverage and a deterministic minimum, verifies the parent pair, and compares the selected child with the recomputed parent baseline. This proves internal arithmetic and provenance consistency, not the truth of external telemetry.

When comparable measurements do not exist, use the qualitative form with `metric_source: none | community_prior`: record the complete candidate order and place the selected pair first, but keep cost/formula/cohort/parent fields null and disclose that no measured optimum exists. Declaring `runtime` or `local_telemetry` requires quantitative mode. A low sticker price, family label, or user screenshot is not enough to populate quantitative fields.

## Local evaluation fields

Do not automatically persist telemetry or source content. When the user explicitly authorizes calibration data collection, record only the minimum structured outcomes needed:

- task class, risk, context scope, oracle strength, write/read-only status, and critical-path status;
- selected model, effort, role, profile, selection origin, and fallback reason;
- exact spawn model/effort arguments or verified inheritance mode, receipt status, effective pair, confirmation status, result-echo match, and Luna-Max-only event/failure-fence order;
- first-pass acceptance;
- validation outcome and failure class;
- reviewer defect count and severity;
- retries, rework, escalation, and family changes;
- actual wall-clock and critical-path time when observable;
- actual billed/credited cost only when the runtime exposes it;
- tool, permission, or external-dependency failure categories;
- explicit user override reason.

Do not store prompts, source code, secrets, personal data, raw logs, or unrelated workspace contents as routing telemetry. Aggregate or redact when possible.

## Calibration lifecycle

1. `cold_start`: use semantic guidance and the low-confidence prior; bias toward quality.
2. `canary`: explore alternatives only on low-risk tasks with deterministic validation and user-authorized observation.
3. `provisional`: allow a bounded task-specific route after enough comparable local evidence.
4. `stable`: promote only after multiple windows preserve the quality floor and material benefit.
5. `rollback`: immediately remove a route after a severe defect, meaningful rework regression, or critical-path regression.

Operational sample bands may be used as conservative heuristics, not statistical guarantees:

- fewer than 20 comparable local tasks: prior only;
- 20-49: provisional and low risk only;
- 50 or more: eligible for a stability review, still subject to severity and distribution checks.

Require an advantage across at least two observation windows before changing a default. Do not change a route because of a 1-3 point community-score difference or a single refresh.

## Promotion and rollback

Promote a candidate only when all are true:

- it meets the task class's quality and capability floors;
- first-pass acceptance is no worse than the current default;
- severe defects do not increase;
- expected total cost or critical-path time improves materially for the declared profile;
- the advantage persists across comparable windows;
- no safety, permission, or verification gate is weakened.

If authorized local evidence later shows that a tightly bounded excluded pair reduces expected total cost without lowering the quality floor, reintroduce it only through an explicit, versioned policy change and targeted tests. Never let a benchmark refresh silently modify the router.

## Forward-test matrix

At minimum, test these behaviors after policy changes:

1. A tiny deterministic task remains in the parent.
2. Unknown-root-cause debugging cannot route to Luna.
3. A batch JSON conversion with a schema can route to Luna `xhigh`.
4. A one-file parser coupled to repository-wide protocol semantics is not treated as bounded Luna work.
5. Luna `low`/`medium`/`high` and Terra `low`/`medium` are rejected for automatic, fallback, and inherited routes, including read-only work.
6. An explicit user pin below the family floor is preserved outside V2 certification rather than silently normalized or self-authorized inside a plan.
7. Parent Ultra produces zero manual children.
8. Unknown orchestration state produces zero manual children.
9. Luna Max unavailable triggers only an enumerated qualified fallback, never Luna below `xhigh` or Terra below `high`.
10. Different files in the same public-API/schema conflict group cannot be parallel writers.
11. A write without required post-validation is rejected.
12. A reviewer is read-only and identifies sandbox versus instruction-only enforcement.
13. A deterministic failure is not retried unchanged; a one-off transient failure may be retried once.
14. A partially interrupted writer is inspected before ownership is transferred.
15. `strict-5.6` returns a migration prompt and performs no legacy routing.
16. Omitting `child_policy` remains backward-compatible with `adaptive`.
17. `luna_max_only` accepts only the exact Luna Max pair in allowed, selected, dispatch, effective, and result-echo fields; Terra, Sol, Luna `xhigh`, fallback, and inheritance are rejected.
18. All supported profiles coexist with `luna_max_only` without changing its exact pair.
19. An unavailable Luna Max target may remain planned or end as a rejected `dispatch_blocked` attempt, but cannot be dispatched/completed or silently substituted.
20. General/open/critical, unbounded/cross-system, weak-oracle, external-write, high-risk, architect/diagnostician, and reviewer nodes remain in the parent under `luna_max_only`.
21. Luna-Max-only requires stable work-unit/retry metadata, allows at most one unchanged linked retry only after a parent-attested transient failure with evidence, rejects changed-contract or substantive rework nodes, and caps total work-unit dispatch attempts.
22. Luna-Max-only spawn attempts and results require one unique, contiguous, append-only global `event_seq`; the earliest failure fence rejects later independent spawns even in the same wave or after cosmetic work-unit changes, while already-dispatched siblings may finish and only that earliest failed initial's one valid later transient retry remains allowed.
23. Luna-Max-only downstream dispatch events occur only after every dependency's accepted result event; wave ordering alone cannot authorize an early spawn, with only the explicitly linked transient-retry edge permitting a failed dependency status.
24. Any Luna-Max-only dispatch freezes a timestamped/evidence-referenced runtime catalog snapshot whose canonical SHA-256 matches `runtime.available_pairs`; later catalog epochs require a new ledger rather than rewriting accepted history.
25. Economy automatic/fallback nodes require an evaluation; other profiles reject that field, while explicit-user/inherited Economy selections visibly bypass ranking.
26. Qualitative Economy covers every candidate exactly once, selects the first declared pair, and emits a no-quantitative-claim warning.
27. Quantitative Economy rejects incomplete candidate coverage, invalid/non-finite/over-precision inputs, formula mismatches, non-namespaced or duplicate evidence records, a parent estimate for the wrong pair, incomparable evidence sources, non-minimum selections, scale-dependent false ties, and child totals that do not beat the recomputed parent baseline.
28. Economy plus `luna_max_only` keeps the exact Luna Max pair while still applying the parent-baseline delegation gate.

Useful invariant tests:

```text
automatic_or_fallback_or_inherited
  => selected Luna is xhigh/max and selected Terra is high/xhigh/max

parent effort == ultra
  => orchestration state == ULTRA_OWNED and manual child count == 0

orchestration state == unknown
  => manual child count == 0

parallel write conflict overlap
  => invalid plan

write node
  => owned surface, conflict group, acceptance criteria, and required post-validation

reviewer
  => read-only with declared enforcement

fallback
  => selected pair is runtime-available and explicitly enumerated

completion
  => parent-verified evidence exists for every required criterion

child_policy == luna_max_only and child exists
  => every pair field == gpt-5.6-luna / max
     and dispatch mode == explicit
     and fallback_pairs == []
     and substantive_attempts == 1
     and max_uses == 1
     and work_unit_id/retry_kind/retry_of are explicit

child_policy == luna_max_only and retry_kind == transient
  => retry_of points to the completed failed initial node
     and initial failure_classification == transient with evidence
     and every retry dispatch event follows the initial result event
     and executor/contract are unchanged
     and remaining transient retries == 0
     and work-unit node count <= 2

child_policy == luna_max_only and failure fence exists
  => no later dispatch event except the earliest failed initial's valid transient retry
     and pre-fence sibling dispatches may record post-fence results
     and a sibling's later failure cannot create a second retry exception

child_policy == luna_max_only and node has dispatch events
  => every ordinary dependency completed successfully before the first attempt event
     and a retry trigger completed as evidenced transient failure before retry dispatch

child_policy == luna_max_only and target unavailable
  => lifecycle in {planned, dispatch_blocked}, never dispatched/completed
```
