# Routing Policy

Read this reference when a node needs an explicit model/effort decision, parent inheritance, a fallback, or a non-default profile.

## Authority boundary

OpenAI's current product guidance describes Sol for complex/open-ended work, Terra as the everyday workhorse, and Luna as fast and affordable for clear/repeatable work. It describes higher reasoning effort as a time/usage versus depth tradeoff, Max as more reasoning time for one task, and Ultra as subagent-based parallel work.

This Skill adds a local conservative policy. The following are workflow rules, not OpenAI capability claims:

- every V2-certified child route excludes Luna `low`/`medium`/`high` and Terra `low`/`medium`;
- Luna code writes require bounded context and a deterministic or strong oracle;
- Sol `xhigh` is the normal deep-work preference, while Max is exceptional;
- a fixed `strict-5.6` mapping is not supported in V2.

## Child policy is separate from profile

Resolve the child policy before enumerating candidates:

| Invocation | Ledger value | Child candidate pool |
| --- | --- | --- |
| no `children=` modifier | `adaptive` | Normal semantic Sol/Terra/Luna candidates |
| `children=luna-max` | `luna_max_only` | Exact `gpt-5.6-luna / max` only |

`child_policy` qualifies candidates; `profile` ranks candidates that already qualify. The two controls are orthogonal. Existing V2 ledgers without `child_policy` are interpreted as `adaptive`, but new ledgers should record it explicitly.

`luna_max_only` is a hard child boundary, not a claim that Luna Max can replace every family. Only structured, bounded, deterministic/strong-oracle, non-high-risk, non-external-write leaves may be declared as child nodes. General/open/critical work, cross-system or unknown context, high/irreversible risk, architects, diagnosticians, reviewers, and unknown-root-cause work stay in the parent. If that leaves zero nodes, the policy is still satisfied.

## Contract dimensions

Classify the node before considering a model name.

### Work class

| Value | Meaning | Default eligible families |
| --- | --- | --- |
| `structured` | Closed input/output, repeatable steps, explicit done condition | Luna, Terra, Sol |
| `general` | Bounded implementation/debugging/integration with ordinary judgment | Terra, Sol |
| `open` | Unknown root cause, architecture, open research, broad synthesis | Sol |
| `critical` | Security, permissions, concurrency, migration, irreversible behavior, high-risk final judgment | Sol |

### Context scope

| Value | Meaning |
| --- | --- |
| `bounded` | Required context is explicitly listed and stable |
| `repository` | Correctness depends on repository-wide contracts or discovery |
| `cross_system` | Correctness depends on multiple systems, live services, or external state |
| `unknown` | The required context has not been established |

Luna code writes require `bounded`. A small file does not imply bounded context.

### Oracle strength

| Value | Meaning |
| --- | --- |
| `deterministic` | Schema, exact comparison, target test, compiler, or other decisive check |
| `strong` | Several independent checks provide high confidence |
| `weak` | Review or indirect evidence leaves material ambiguity |
| `none` | No meaningful acceptance oracle exists yet |

Luna requires `deterministic` or `strong`. Improve the contract or use a broader family when the oracle is weak. Do not delegate with `none` unless the child is explicitly tasked with constructing the oracle and cannot claim task completion.

### Risk

Use `low`, `medium`, `high`, or `irreversible`. Risk considers blast radius, permissions, data loss, public contracts, concurrency, external side effects, and how observable failure would be. Short edits can be high risk.

In a V2-certified plan, `high` or `irreversible` risk requires `work_class: critical`. The validator derives the critical child, reviewer, and integrator floors independently; a node cannot weaken them by declaring a lower class or requirement.

## Generate explicit requirements

For every delegated node, enumerate rather than infer:

```yaml
work_class: general
context_scope: repository
oracle: strong
risk: medium
requirements:
  required_integrator_class: general
  minimum_child_effort: high
  minimum_integrator_effort: high
  allowed_model_effort_pairs:
    - {model: gpt-5.6-terra, family: terra, effort: high}
    - {model: gpt-5.6-terra, family: terra, effort: xhigh}
    - {model: gpt-5.6-sol, family: sol, effort: high}
  fallback_pairs:
    - {model: gpt-5.6-sol, family: sol, effort: high}
```

The model names above are examples, not a permanent catalog. Build the list from the models and efforts exposed by the current collaboration tool. Every allowed pair must satisfy the node's semantic and assurance requirements before ranking begins.

Do not use free-text substitutes such as `strongest available`, `equivalent`, or `next best`. If a runtime adds a new model, add it to the node's explicit list only after the runtime description establishes the relevant semantic band.

For `luna_max_only`, the requirements are deliberately singular:

```yaml
child_policy: luna_max_only
work_unit_id: json_convert
retry_kind: none
retry_of: null
requirements:
  required_integrator_class: general
  minimum_child_effort: max
  minimum_integrator_effort: high
  allowed_model_effort_pairs:
    - {model: gpt-5.6-luna, family: luna, effort: max}
  fallback_pairs: []
attempt_budget:
  transient_retries: 1
  substantive_attempts: 1
  max_uses: 1
```

The parent and integrator remain governed by their own capability floor; the policy constrains children only. Every Luna-Max-only node must keep a stable `work_unit_id`. A single genuine transient retry uses `retry_kind: transient`, points `retry_of` to the failed initial node, preserves the same executor and contract, and has zero retry budget remaining. A new work-unit ID must never be used to disguise substantive rework.

## Choose family, then effort

```text
if work is open, root cause is unknown, judgment is critical, or risk is high:
    Sol band
elif input/output is closed, context is bounded, work is repeatable,
     and the oracle is deterministic or strong:
    Luna band
else:
    Terra band
```

Choose effort independently. The table below is V2's local operational interpretation, not an OpenAI capability boundary:

| Effort | Use |
| --- | --- |
| `low` | Straightforward one- or two-step work; V2 does not certify Luna/Terra children at this effort |
| `medium` | Ordinary multi-step balance; V2 does not certify Luna/Terra children at this effort |
| `high` | Non-trivial writes, multiple sources, edge cases, or meaningful checking; eligible for Terra/Sol but still below the local Luna floor |
| `xhigh` | Difficult diagnosis, architecture, high coupling, weak oracle, or high risk |
| `max` | Hardest bounded single node, or concrete evidence that `xhigh` is insufficient |
| `ultra` | Root orchestration only; never an explicit child pair |

Normal V2 preferences:

| Work shape | Preferred band |
| --- | --- |
| Exact extraction/classification/transformation | Luna `xhigh` |
| Isolated, precisely testable code leaf | Luna `xhigh`; Max only when bounded and non-critical-path latency is acceptable |
| Broad read-only scan | Terra `high`; `xhigh` when cross-module judgment is needed |
| Ordinary implementation/debugging | Terra `high`/`xhigh` |
| Difficult but still bounded implementation | Terra `xhigh`; Max rarely |
| Unknown-root-cause diagnosis or architecture | Sol `high`/`xhigh` |
| Security, migration, concurrency, or final critical review | Sol `xhigh`; Max only for the hardest single review |

OpenAI positions Luna as fast and affordable. V2 nevertheless does not assume that every Luna × effort combination has lower end-to-end wall-clock latency for every workload; family, effort, tool waits, and task shape all matter.

## Automatic pair policy

Apply this after semantic eligibility and again after every fallback:

```yaml
automatic_pair_policy:
  deny:
    - {family: luna, effort: low}
    - {family: luna, effort: medium}
    - {family: luna, effort: high}
    - {family: terra, effort: low}
    - {family: terra, effort: medium}
    - {family: any, effort: ultra}
```

The same deny list applies to automatic selection, automatic fallback, automatic inheritance, and V2-certified explicit children. A known inherited pair must pass it; otherwise select an explicit qualified pair or keep the node in the parent. A user pin on the parent counts as `explicit_user` for a child only when the user's stated scope explicitly covers delegated children.

At the execution-authority layer, preserve an explicit user pin when the runtime accepts it, but treat an excluded pin as outside V2 certification. Do not place Luna below `xhigh` or Terra below `high` in a V2 routing plan or use `explicit_user` as a plan-local authorization claim; keep the work in the pinned parent, use a qualified user-approved child pair, or report that V2 cannot certify the delegation. For permitted pairs, `selection.origin: explicit_user` records provenance only and never weakens semantic, safety, or verification gates.

## Parent integrator floor

The parent must be capable of evaluating the evidence it receives. For each node, compare the known parent state with `required_integrator_class` and `minimum_integrator_effort`.

Recommended floors:

| Child work | Integrator floor |
| --- | --- |
| Structured, deterministic, low risk | `general` / `high` |
| General write or weakly deterministic result | `general` / `high` |
| Open diagnosis or architecture | `open` / `xhigh` |
| Critical/high-risk judgment | `critical` / `xhigh` |

If the parent pair or integrator class cannot be established for open/critical work, fail closed. A strong child reviewer does not make a weak or unknown parent capable of adjudicating an ambiguous result.

## Runtime filtering and fallback

1. Read the current spawn tool's model and effort catalog.
2. Intersect it with the node's enumerated allowed pairs.
3. Reapply the automatic deny policy.
4. Remove pairs that violate work class, context, oracle, risk, parent integrator, or orchestration constraints.
5. Rank the remaining pairs using the selected profile and declared metric source.

Fallback repeats these steps over `fallback_pairs`; it is not a fixed family/effort chain. A globally denied pair cannot be retained even as `selection.requested_pair`; `policy_rejection` provenance is reserved for a globally permitted pair that fails the current node's semantic or assurance rules.

In `luna_max_only`, do not run fallback filtering: `fallback_pairs` is empty, selection origin is never `fallback` or `inherited`, and no other family/effort pair is eligible. If exact Luna Max is absent from the runtime catalog, it may remain only as an unspawned `planned` target or the work may stay entirely in the parent; a `dispatched` or `completed` node requires current availability. If an exact explicit attempt is rejected, record it as `dispatch_blocked`. Never replace it with Terra, Sol, Luna `xhigh`, a default effort, or an unverified alias.

Freeze the Luna-Max-only `runtime.available_pairs` snapshot immediately before its first spawn event, record `runtime.catalog_snapshot.captured_at`, `evidence_ref`, and the canonical `available_pairs_sha256`, and retain that evidence through final audit. The validator rejects a digest that no longer matches the normalized catalog contents. A later live-catalog change does not erase a previously accepted receipt; do not overwrite historical availability. Stop any still-planned spawn and start a newly validated ledger if execution must resume under a different catalog snapshot.

Once Luna-Max-only execution starts, routing eligibility is also time-ordered. Append one global contiguous `event_seq` to each spawn attempt and recorded child result. The earliest non-`success` result or terminal `dispatch_blocked` attempt creates the only failure fence; ranking, a fresh work-unit ID, a same-wave label, or cosmetic contract edits cannot reopen the child pool. Only that earliest failed initial node's one valid direct retry may cross the fence, and only when the parent attested `failure_classification: transient` with evidence and the retry spawn follows the failed result event. A later failure from an already-dispatched sibling does not create another exception.

Examples:

- Luna `xhigh` unavailable for a structured node: a pre-enumerated Terra `high` pair may qualify.
- Luna Max unavailable: do not invent it and do not drop below either family's local floor; choose another listed qualified pair.
- Terra `xhigh` unavailable for bounded implementation: Sol `high` may qualify if explicitly enumerated.
- Sol `xhigh` unavailable for critical work: only an explicitly enumerated runtime model with sufficient open/high-risk semantics qualifies. Otherwise keep the work in a qualified parent or report a blocker.

For every substitution report requested pair, actual pair, selection origin, reason, metric source, and changed risks.

## Profiles rank; they do not qualify

| Profile | Ranking objective |
| --- | --- |
| `balanced` | Reliable first-pass result with reasonable critical-path latency and expected total cost |
| `latency` | Lowest observed critical-path time among qualified candidates |
| `economy` | Lowest expected total cost including retry, review, rework, escalation, and coordination, subject to a lower-than-parent delegation gate |
| `quality` | Highest conservative quality band plus stronger independent evidence |

Record all applicable evidence metadata:

- `METRIC_SOURCE`: `runtime`, `local_telemetry`, `community_prior`, or `none`;
- `METRIC_AS_OF`: ISO 8601 observation date or timezone-aware timestamp when the source is not `none`;
- `EVIDENCE_ID_OR_WINDOW`: benchmark snapshot ID or comparable local observation window.

Source meanings:

- `runtime`: current runtime measurements;
- `local_telemetry`: comparable local task observations;
- `community_prior`: dated, low-confidence external observations;
- `none`: semantic policy only.

With `none`, do not claim quantitative optimization. With `community_prior`, make only a qualitative tie-break and disclose the evidence limitation.

### Economy evaluation contract

Every Economy node selected by `automatic` or `fallback` records an `economy_evaluation`. The evaluated candidate universe is the complete `allowed_model_effort_pairs` set for automatic selection and the complete `fallback_pairs` set for fallback selection. Candidate omission is invalid. `explicit_user` and `inherited` selections bypass Economy ranking; omit the evaluation and report the bypass.

Shared fields:

```json
{
  "mode": "qualitative | quantitative",
  "formula_version": null,
  "cost_unit": null,
  "cohort_id": null,
  "parent_estimate": null,
  "candidate_estimates": [],
  "qualitative_order": [],
  "tie_break": "declared_order | pair_key_lexicographic",
  "delegation_decision": "delegate",
  "rationale": "visible decision basis"
}
```

`nodes` contain only proposed or actual children, so an Economy node must declare `delegation_decision: delegate`. If the decision is `keep_parent`, omit the child node and execute it in the parent. Parent-local work is outside the ledger's node array.

Qualitative mode is valid only when comparable numeric evidence is unavailable and `metric_source` is `none` or `community_prior`. Set `formula_version`, `cost_unit`, `cohort_id`, and `parent_estimate` to null; leave `candidate_estimates` empty; use `tie_break: declared_order`; and put every candidate exactly once in `qualitative_order`, with the selected pair first. This makes the decision reproducible as a declared ordering but does not prove a cost optimum. A root declaration of `runtime` or `local_telemetry` requires quantitative mode rather than allowing a convenient downgrade.

Quantitative mode requires `metric_source: runtime | local_telemetry`, one visible shared cost unit, one comparable cohort covering the same task shape/tool surface/context/validation burden, and formula version `expected-total-cost-v1`. Every candidate and the parent baseline use the same cost-vector schema. Each candidate estimate is:

```json
{
  "pair": {"model": "gpt-5.6-luna", "family": "luna", "effort": "xhigh"},
  "sample_size": 12,
  "evidence_ref": "telemetry-window#candidate:gpt-5.6-luna:xhigh",
  "initial_cost": 1.0,
  "retry_probability": 0.1,
  "retry_cost_if_triggered": 1.0,
  "rework_probability": 0.05,
  "rework_cost_if_triggered": 1.5,
  "review_cost": 0.1,
  "escalation_probability": 0.02,
  "escalation_cost_if_triggered": 2.0,
  "coordination_cost": 0.1,
  "expected_total_cost": 1.415
}
```

`parent_estimate` has the same fields, including `pair`. Its pair must exactly equal `orchestration.parent`, and its evidence reference uses a distinct parent record such as `telemetry-window#parent:gpt-5.6-sol:xhigh`. Every candidate/parent reference must be unique and begin with the root `evidence_id_or_window` followed by `#<record-id>`; this prevents cross-window or unbound scalar baselines from being presented as the current comparison.

The validator recomputes:

```text
expected-total-cost-v1 =
    initial_cost
  + retry_probability      * retry_cost_if_triggered
  + rework_probability     * rework_cost_if_triggered
  + review_cost
  + escalation_probability * escalation_cost_if_triggered
  + coordination_cost
```

All costs must be finite, non-negative, and no greater than `10^15`; probabilities are in `[0,1]`; sample size is positive. Numeric inputs use at most six decimal places. The validator converts them to decimal fixed-point, computes the formula, and rounds the total to six places using half-even rounding; it does not use a scale-dependent floating-point relative tolerance. `qualitative_order` is empty in quantitative mode. Select the lowest recomputed total; exact six-decimal ties use lexicographic order over normalized `(model, family, effort)`. The selected total must also be strictly below the recomputed same-cohort `parent_estimate` total; otherwise the node stays in the parent. Root `metric_as_of`/`evidence_id_or_window`, unique namespaced candidate/parent `evidence_ref` values, `cohort_id`, and `cost_unit` form the auditable evidence binding. They prove internal arithmetic and provenance consistency, but without access to the referenced telemetry the ledger still cannot self-prove that external measurements are truthful.

In `luna_max_only`, the pair ranking has one member. Economy still records whether the Luna Max child has positive value against the parent baseline and can influence which qualified node should occupy scarce concurrency, but it cannot change the exact child pair. Do not claim that the modifier guarantees a particular quota, billed cost, or wall-clock saving unless the runtime exposes comparable evidence.

## Labels and observability

Treat observability as part of routing correctness:

```text
selection.selected_pair
  -> exact spawn arguments or guaranteed inheritance
  -> accepted/rejected runtime receipt
  -> effective_pair
  -> child assigned-pair echo
  -> generated final routing table
```

For explicit dispatch, set both `model` and `reasoning_effort`. If only the model is supplied, the runtime may apply that model's configured/default effort; record `default-unresolved` and fail closed. An accepted exact pair is `confirmed-explicit`, or `fallback-confirmed` when it is the declared fallback.

`luna_max_only` permits only explicit dispatch with both `model: gpt-5.6-luna` and `reasoning_effort: max`. It forbids inheritance even from a Luna Max parent, because the mode requires a directly auditable child override and must not depend on parent state.

For inheritance, first establish the exact current parent model and effort from available live context. Omit both overrides and use the full-history fork only when the current collaboration contract guarantees inheritance. The accepted result is `confirmed-inherited`. If either the parent pair or inheritance guarantee is unknown, record `inherited-unresolved` for audit and do not spawn.

Full-history forks and explicit overrides are mutually exclusive in the current collaboration contract. Explicit overrides require `fork_turns: "none"` or a supported positive history slice with a self-contained dossier.

Encode every attempted pair in both `<role> (<model>, <effort>)` and the pair-first task name `<model-slug>_<effort>_<node>_a<N>`. The pair must be the leftmost prefix so right-side UI truncation cannot hide it. Do not guess, replace an exact value with `default`, or claim that a reporting label renamed the immutable runtime task. A child echo verifies assignment continuity but is not runtime proof; the accepted spawn receipt is authoritative.
