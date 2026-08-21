---
name: adaptive-agent-routing
description: Explicit-only, contract-first routing of Codex work across Sol, Terra, and Luna subagents using live runtime capabilities, exact model/effort receipts, bounded orchestration, auditable Economy evaluation, evidence-based verification, failure-aware escalation, and an optional Luna-Max-only child policy. Use only when the user explicitly invokes $adaptive-agent-routing or selects it; small tasks may remain in the parent.
---

# Adaptive Agent Routing V2

Route by task semantics, risk, and verifiability. Do not route by a fixed leaderboard or by model name alone.

Use the current runtime catalog as the availability source of truth. OpenAI's current product positioning is the starting point:

- Sol: complex, open-ended, or high-value work needing judgment and polish.
- Terra: the everyday workhorse.
- Luna: fast and affordable for clear, specific, repeatable work.
- Higher effort generally trades more time and usage for deeper reasoning; Max gives one task more reasoning time.
- Ultra uses subagents to parallelize complex work.

V2 then adds local eligibility and orchestration constraints. Its user-selected quality policy is deliberately stricter than the general product guidance: V2-certified children exclude Luna `low`/`medium`/`high` and Terra `low`/`medium` across automatic selection, fallback, inheritance, and explicit-user provenance. This is a conservative expected-total-cost hypothesis intended to reduce retries and rework, not a proven universal ordering or a claim that those pairs are incapable.

Model/effort observability is a hard correctness invariant, not a cosmetic label. Every actual child must have a traceable chain from the selected pair through the exact spawn arguments and accepted runtime receipt to the child's assigned-pair echo and the final per-child report. A planned pair alone never proves execution.

## Activation and authority

1. Activate only when the user explicitly invokes `$adaptive-agent-routing` or selects it in the UI.
2. Invocation authorizes the root to decide whether delegation helps; it does not require spawning.
3. A later instruction not to use subagents overrides the invocation.
4. Apply only to the current task. Do not persist routing choices into `AGENTS.md`, `config.toml`, custom agents, MCP configuration, or future tasks.
5. Do not activate from a spawned child. Children are leaves and must not invoke this skill or spawn agents.
6. Delegation does not expand the user's scope, permissions, write authority, or approval for external or destructive actions.
7. Preserve an explicit user model/effort pin when the runtime supports it. Treat policy-excluded pins as outside V2 certification and do not encode them in a V2 routing plan. Keep that work in the pinned parent, use another pair only with user authority, or stop and explain the conflict; do not silently override the user.
8. A pin on the parent does not automatically authorize children. Use child origin `explicit_user` only when the user's pin explicitly covers delegated children and the pair is otherwise V2-permitted; an excluded child pair remains uncertifiable.

Supported profiles are `balanced` (default), `latency`, `economy`, and `quality`. Profiles rank already-qualified candidates; they never weaken capability, permission, safety, or verification floors. When the invocation omits `profile=`, resolve and record `profile: balanced`; do not treat omission as an unrecorded state.

Supported child policies are independent from profiles:

- `adaptive` is the default when no child-policy modifier is present and preserves the normal Sol/Terra/Luna candidate pool; the resolved profile still ranks those qualified candidates.
- `luna_max_only` is activated only by the exact invocation modifier `children=luna-max`. It is a hard child candidate-pool restriction, not a ranking profile.

Invocation grammar is:

```text
$adaptive-agent-routing [profile=<balanced|latency|economy|quality>] [children=luna-max] <task>
```

Each modifier may appear at most once and the two modifiers may appear in either order immediately after the Skill name:

```text
$adaptive-agent-routing children=luna-max <task>
$adaptive-agent-routing profile=economy children=luna-max <task>
```

Record the resolved profile and `child_policy: adaptive | luna_max_only` in new routing ledgers. Existing V2 ledgers that omit `child_policy` remain equivalent to `adaptive`. Reject unknown, duplicate, or conflicting `profile=`/`children=` values before routing; do not silently reinterpret them as defaults.

`strict-5.6` is retired because its fixed mapping selected Terra `medium`, which conflicts with V2. If an invocation requests `strict-5.6`, do not route or silently reinterpret it. Ask the user to migrate to one of the supported profiles or to an explicit model/effort pin.

## Read references progressively

Load only the detail needed for the current decision:

- Read [references/routing-policy.md](references/routing-policy.md) when choosing or overriding a family/effort pair, applying a non-default profile, inheriting the parent pair, or resolving a fallback.
- Read [references/contracts-and-orchestration.md](references/contracts-and-orchestration.md) before any write delegation, two or more children, dependency chains, parallel work, or uncertain/Ultra parent orchestration.
- Read [references/validation-and-failure.md](references/validation-and-failure.md) for risk at least `medium`, reviewers, validation failure, retries, recovery, or stopping decisions.
- Read [references/calibration-and-evaluation.md](references/calibration-and-evaluation.md) only when maintaining this policy, using community/local performance evidence, or claiming `latency`, `economy`, or `quality` optimization.

Do not load every reference by default.

## Root state machine

### 1. AUTHORITY

Resolve user scope, profile, child policy, model/effort pins, safety constraints, mutable surfaces, and whether children are allowed. Stop or keep the action in the parent when required authority is missing.

### 2. ORCHESTRATION

Establish the parent's actual orchestration state before manual fan-out:

- `MANUAL_ALLOWED`: the parent is known not to be Ultra and the root can integrate the result.
- `ULTRA_OWNED`: the parent is already Ultra; do not manually spawn another layer.
- `ORCHESTRATION_UNKNOWN`: Ultra state or integrator capability cannot be established; fail closed and do not manually fan out.

Exactly one orchestration layer may be active. Explicit children never use Ultra.

### 3. DELEGATION_GATE

Delegate only when a stable contract exists and at least one benefit materially exceeds handoff and integration cost:

- useful parallelism;
- meaningful context or tool-surface isolation;
- a coherent multi-action implementation bundle;
- independent review value;
- independently verifiable evidence collection.

Keep tiny/local work, final synthesis, tightly coupled work, and work without a usable acceptance oracle in the parent. If a task would justify only Luna below `xhigh` or Terra below `high`, normally keep it in the parent rather than paying delegation overhead.

Under `luna_max_only`, also keep every non-structured, unbounded, cross-system, external-write, high/irreversible-risk, weak-oracle, architect, diagnostician, reviewer, unknown-root-cause, or open-ended node in the parent. The modifier constrains children; it does not make unsuitable work safe for Luna or require a child to be created.

### 4. CONTRACT

For every proposed child, define the objective, dependencies, known facts and hypotheses, owned/read-only surfaces, semantic conflict groups, forbidden actions, deliverables, acceptance criteria, validation, attempt budget, stop conditions, and escalation triggers. Under `luna_max_only`, also assign a stable `work_unit_id` and explicit `retry_kind`/`retry_of` metadata so renaming a node cannot hide a retry. Once execution begins, append a globally unique, contiguous `event_seq` to every spawn attempt and child result immediately when that event is recorded; never renumber earlier events.

Do not delegate a node whose completion cannot be verified. Build a dependency DAG before parallel dispatch. Keep unstable interfaces and shared mutable conflict groups serial.

### 5. CLASSIFY

Classify each node independently:

| Work class | Typical work | Automatic family band |
| --- | --- | --- |
| `structured` | Extraction, transformation, exact checks, isolated mechanical edits | Luna, Terra, or Sol |
| `general` | Bounded implementation, ordinary debugging, integration, tool-heavy execution | Terra or Sol |
| `open` | Unknown-root-cause diagnosis, architecture, open research, major synthesis | Sol |
| `critical` | Security, permissions, concurrency, migration, irreversible behavior, final high-risk review | Sol |

Task length and file count do not determine the class. A short permission edit may be critical; a large deterministic conversion may be structured.

For a V2-certified plan, classify every `high` or `irreversible` node as `critical`; the validator derives this floor rather than trusting weaker declarations.

### 6. ENUMERATE

Record work class, risk, context scope, and oracle strength as node-level contract fields. Then enumerate the nested requirements, including minimum child/integrator effort, required integrator class, and `allowed_model_effort_pairs`. Do not use free text such as "any equivalent strong model" as a capability check.

Family and effort are separate decisions:

- family follows openness, coupling, and judgment needs;
- effort follows difficulty, risk, edge cases, and verification weakness.

Normal automatic starting points are Luna `xhigh` for structured work, Terra `high`/`xhigh` for general work, Sol `high`/`xhigh` for open work, and Sol `xhigh` for critical review. Use Max only for an exceptionally hard, bounded single node or after concrete evidence that `xhigh` was insufficient.

### 7. FILTER

Intersect the enumerated pairs with the live runtime catalog, then apply all hard policies:

- exclude Luna `low`/`medium`/`high` and Terra `low`/`medium` from every V2-certified child route, including automatic selection, fallback, inheritance, and explicit-user provenance;
- exclude Ultra from every explicit child;
- exclude Luna from open/critical work, unknown root causes, cross-system integration, weakly bounded context, and high-risk judgment;
- require bounded context plus a deterministic or strong oracle for Luna code writes;
- require the known inherited parent pair to satisfy the same enumerated requirements before inheriting it;
- require the parent integrator to meet each high-risk node's integrator floor.

An excluded pair cannot re-enter through fallback. If no qualified pair remains, keep the node in a qualified parent, restructure it, improve its oracle, or report a blocker.

When `child_policy: luna_max_only` is active, apply these additional hard rules after classifying the node:

- the only child pair is exactly `{model: gpt-5.6-luna, family: luna, effort: max}`;
- every child node has that singleton `allowed_model_effort_pairs`, an empty `fallback_pairs`, `minimum_child_effort: max`, `substantive_attempts: 1`, and `max_uses: 1`;
- the exact Luna Max pair may remain as the desired target in `planned` or a rejected `dispatch_blocked` node, but it must be present in the live runtime catalog before a node can be `dispatched` or `completed`;
- fallback and inherited selection origins are forbidden;
- a catalog-missing Luna Max target remains unspawned; an exact explicit attempt rejected by the runtime may become `dispatch_blocked`. Never substitute Terra, Sol, Luna `xhigh`, a model default, or another Luna child.

For Luna-Max-only execution, capture `runtime.available_pairs` immediately before the first spawn attempt and preserve that dispatch-time snapshot through final audit. Record `runtime.catalog_snapshot.captured_at`, `evidence_ref`, and the validator's canonical `available_pairs_sha256`; any ledger with a dispatch event requires them, and the digest must match the catalog contents. Do not replace the snapshot with a later catalog that omits an already accepted pair. If availability changes before remaining planned work is dispatched, stop those spawns and start a newly validated ledger rather than rewriting historical availability evidence.

### 8. RANK

Rank only the surviving candidates according to the selected profile and the evidence source. Record `METRIC_SOURCE` as one of `runtime`, `local_telemetry`, `community_prior`, or `none`, plus `METRIC_AS_OF` and `EVIDENCE_ID_OR_WINDOW` whenever the source is not `none`.

- `balanced`: prefer reliable first-pass completion while considering critical-path latency and total cost.
- `latency`: use observed wall-clock evidence; without it, disclose that the choice is qualitative.
- `economy`: compare expected total cost including retry, review, rework, escalation, and coordination; sticker price alone is insufficient.
- `quality`: prefer a higher conservative quality band and stronger independent validation, not Max everywhere.

Community observations are low-confidence tie-breakers only. They cannot override semantic eligibility or establish capability, price, latency, or an SLA. The current seed is `community_prior / 2026-08-20 / user-supplied-screenshots-v1`.

For every `economy` node whose selection origin is `automatic` or `fallback`, add `economy_evaluation` before dispatch:

- Use `mode: qualitative` only when comparable cost data is absent and `metric_source` is `none` or `community_prior`. Set formula/cost/cohort/parent fields to null, leave `candidate_estimates` empty, list every ranked candidate exactly once in `qualitative_order`, put the selected pair first, use `tie_break: declared_order`, and disclose that no measured optimum is claimed.
- Use `mode: quantitative` when `metric_source` is `runtime | local_telemetry`; those sources may not fall back to qualitative mode. Bind all candidates and the actual orchestration parent to one visible `cost_unit`, comparable `cohort_id`, and unique records under `EVIDENCE_ID_OR_WINDOW#<record-id>`. Give every estimate a positive sample size, initial cost, retry/rework/escalation probability and conditional cost, review cost, coordination cost, and recomputable `expected_total_cost`. The parent estimate pair must equal the actual parent pair. Use formula version `expected-total-cost-v1` and `tie_break: pair_key_lexicographic`.
- Quantitative costs are finite, non-negative, at most `10^15`, use at most six decimal places, and are recomputed with decimal fixed-point half-even rounding. Selection is dispatchable only when the chosen pair is the exact six-decimal deterministic minimum over the complete candidate set and its expected total cost is strictly below the recomputed `parent_estimate` total. Otherwise omit the child node and keep the work in the parent.
- `explicit_user` and `inherited` constrain selection outside Economy ranking. Omit `economy_evaluation` for those nodes and report the profile bypass instead of implying that Economy selected the pair.

The validator recomputes `expected-total-cost-v1` as initial + probability-weighted retry + probability-weighted rework + review + probability-weighted escalation + coordination. Read the exact ledger fields in [references/routing-policy.md](references/routing-policy.md).

Under `luna_max_only`, pair ranking is intentionally degenerate because only one child pair can survive. Economy still compares that child against the parent baseline (quantitatively when comparable evidence exists, otherwise qualitatively) and helps decide which qualified nodes merit scarce concurrency, but it cannot change the child pair.

### 9. RESOLVE_AND_DISPATCH

Inspect the current collaboration tool schema and live model/effort catalog before each spawn. Before dispatch, announce the child purpose, exact planned `<model>, <effort>` pair, dispatch mode, and user-visible label. Do not hide the pair behind a role-only name.

Use exactly one of these verifiable dispatch modes:

- `explicit`: pass both `model` and `reasoning_effort`. Use `fork_turns: "none"` or a supported positive history slice and provide a self-contained dossier. Never pass only the model: OpenAI's runtime may then use that model's default effort, which does not verify the selected pair.
- `inherit_parent`: omit both overrides only when the exact live parent pair is already known, satisfies the node contract, and the current collaboration contract guarantees full-history inheritance. Use `fork_turns: "all"`. Unknown inheritance is not dispatchable in V2.

Do not combine a full-history fork with explicit overrides. An accepted explicit call confirms the exact supplied pair; an accepted guaranteed inheritance call confirms the known parent pair. A rejected call confirms nothing.

Under `luna_max_only`, use only `explicit`: every attempted spawn must pass both `model: gpt-5.6-luna` and `reasoning_effort: max`, with `fork_turns: "none"` or a supported positive history slice. Inheritance is forbidden even when the parent happens to be Luna Max. Verify the exact pair in the requested pair, spawn arguments, accepted effective pair, child echo, and final report. Record `event_seq` on rejected attempts as well as accepted attempts; a completed result receives the next event sequence after its node's dispatch attempts.

Every spawn `task_name` must be pair-first and encode the model, effort, node, and attempt as `<model-slug>_<effort>_<node>_a<N>`. The pair must occupy the left edge because the desktop task list may truncate the right side and does not guarantee separate model/effort fields. Every user-visible label must be `<role> (<exact-model>, <exact-effort>)`. The encoded name is a UI visibility aid, not runtime proof; record the accepted tool receipt reference and never claim that a later reporting label renamed an immutable runtime task. Existing tasks keep the names they were created with.

In `adaptive`, fallback means re-running FILTER and RANK over the original qualified pair set, not following a fixed string chain. Report the requested pair, selected pair, evidence source, fallback reason, and any new risk. `luna_max_only` has no child fallback.

Every child packet must say it is a leaf, include the full bounded contract, state its assigned model/effort pair and confirmation status, and require those routing fields to be echoed in the result. The echo proves contract continuity, not runtime identity; the accepted spawn arguments or guaranteed inheritance receipt are the runtime evidence. Use the exact dispatch and result envelopes in [references/contracts-and-orchestration.md](references/contracts-and-orchestration.md).

Maintain the machine-readable routing ledger through `planned -> dispatched -> completed` or `planned -> dispatch_blocked`. Allowed confirmation statuses are:

- `confirmed-explicit`: both override fields were accepted;
- `confirmed-inherited`: both values are known and the accepted full-history spawn guarantees inheritance;
- `fallback-confirmed`: the accepted pair is a declared fallback;
- `runtime-rejected`: no child was created for that attempt;
- `default-unresolved` and `inherited-unresolved`: audit-only failure states that invalidate V2 dispatch and must never be presented as verified.

For complex manual fan-out or any high-risk plan, serialize the plan as a JSON routing ledger and run it before dispatch, after receipts change, and before final reporting:

```text
python scripts/validate-routing-plan.py <ledger.json>
```

Do not dispatch or accept a child if the validator reports an error for the relevant ledger state. The script checks structural declarations and receipt consistency; it does not prove real model capability, sandbox enforcement, or task correctness.

### 10. EXECUTE_AND_VERIFY

Run only dependency-ready nodes. Maintain one writer per mutable semantic conflict group at a time, reserve capacity for the parent, and keep discovery before dependent design, design before implementation, and implementation before final review.

Under `luna_max_only`, dependency readiness is event-audited: every dispatch attempt must have an `event_seq` later than each dependency's completed `success` result. The sole status exception is the retry edge to its own completed, parent-attested transiently failed initial node; that retry attempt still follows the initial result event. A later wave number alone never proves readiness.

Treat every child result as evidence, not authority. The parent must inspect the actual relevant state: files, diffs, commands, exit codes, tests, rendered artifacts, or cited evidence. Accept a node only when every acceptance criterion has evidence.

Before accepting a child, compare its returned agent label, assigned-pair echo, dispatch-attempt number, and confirmation-status echo with the effective accepted receipt. Any mismatch invalidates the routing chain and must be resolved or reported; never silently rewrite the child's claim.

### 11. REVIEW_OR_REPAIR

Require independent read-only review for high-risk work. Distinguish sandbox-enforced read-only custom agents from prompt-only restrictions; inspect the real worktree/external state around a prompt-only reviewer.

Classify failures before acting: transient failure, missing context, invalid decomposition, weak oracle, reasoning failure, newly open-ended work, permission/authority block, or interrupted partial write. Retry only transient failures unchanged, at most once. Do not fan out more equal workers after repeated substantive failure.

Under `luna_max_only`, one genuinely transient failure may be retried once with the unchanged contract, same executor, same `work_unit_id`, exact same pair, and `retry_kind: transient`. The parent must record `failure_classification: transient` plus non-empty `failure_evidence` on the failed initial result; deterministic validation failures and substantive classifications do not qualify. Point the retry directly to that failed initial node with `retry_of`, reduce its remaining transient retry budget to zero, and ensure every retry spawn `event_seq` is later than the initial failure result. A substantive failure ends child execution for that work unit: inspect any partial state, then repair in the parent, ask the user to leave Luna-Max-only mode, or report the block. Do not assign a new work-unit ID or make cosmetic contract edits to disguise a Luna-Max-to-Luna-Max repair loop. A required independent high-risk reviewer cannot be delegated while every child is constrained to Luna Max; keep that work in a capable parent or rerun without the modifier.

Luna-Max-only execution is globally fail-stop. The earliest completed result whose status is not `success`, or the terminal rejected attempt of a `dispatch_blocked` node, establishes the one failure fence at its `event_seq`. No independent or substantive child spawn may have a later sequence, even if it uses the same wave, a fresh node/work-unit ID, or cosmetically changed text. The only post-fence dispatch exception is the single valid direct transient retry of that earliest failed initial node; a pre-fence sibling that later fails does not open another retry exception. Children whose spawn attempts were recorded before the fence may finish afterward; planned nodes remain unspawned and move to the parent. Run the ledger validator before recording any post-fence attempt.

### 12. INTEGRATE_AND_STOP

The root owns final integration and user-facing synthesis. Complete only when all required nodes and acceptance criteria have evidence, required review gates are clear, integration validation passes, and fallbacks/risks are disclosed.

Stop dispatching when delegation value falls below coordination cost, new authority is required, the stated budget/time limit is reached, attempts produce no new evidence, or no sufficient runtime pair exists. Budget or retry exhaustion is not completion.

## Hard invariants

1. Only the root coordinates and integrates.
2. Exactly one active subagent orchestration layer.
3. Explicit children never use Ultra, invoke this skill, or spawn agents.
4. One writer per mutable semantic conflict group at a time.
5. No delegation without bounded scope, acceptance, validation, attempt budget, and stop conditions.
6. Family follows task semantics; effort follows difficulty and assurance needs.
7. No V2-certified child route chooses Luna below `xhigh` or Terra below `high`.
8. No silent fallback below an enumerated capability or integrator floor.
9. Child output is evidence; the parent verifies completion.
10. High-risk final review is independent from implementation and read-only by default.
11. Failures are classified before retry, escalation, or family change.
12. Profiles and budgets never weaken permission, safety, or critical correctness gates.
13. Unknown orchestration state or unknown high-risk integrator capability fails closed.
14. Metric claims disclose their evidence source; no data means no quantitative optimization claim.
15. Every actual child exposes its exact model and reasoning effort in the pre-dispatch announcement, the leftmost prefix of its encoded task name, accepted receipt record, result echo, and final report.
16. Explicit dispatch always supplies both `model` and `reasoning_effort`; model-only defaults are unresolved and forbidden.
17. Full-history inheritance is allowed only for a known exact parent pair and never carries explicit overrides.
18. `default-unresolved` and `inherited-unresolved` are failure states, never verified execution.
19. `children=luna-max` maps to `child_policy: luna_max_only` and constrains every actual child and every child pair field to exactly `gpt-5.6-luna / max`.
20. Luna-Max-only dispatch is explicit, has no inheritance or child fallback, and never converts unsuitable work into a Luna node.
21. Omitting `children=luna-max` resolves `child_policy: adaptive`; the selected or defaulted profile still ranks the qualified adaptive candidate pool.
22. Luna-Max-only nodes declare stable work-unit identity; one work unit has one initial node and at most one unchanged, explicitly linked retry whose initial result is parent-classified `transient` with evidence.
23. Luna-Max-only dispatch attempts and results use one append-only global `event_seq`; the earliest non-success result or terminal `dispatch_blocked` attempt fences every later spawn except that earliest failed initial's one valid direct transient retry.
24. Economy automatic/fallback nodes carry a complete auditable evaluation; quantitative totals are recomputable, the selected pair is the deterministic minimum, and its cost is strictly below the parent baseline.
25. Economy never claims that an explicit-user or inherited selection was cost-selected, and qualitative mode never claims a measured optimum.

## Report

Finalize the routing ledger and generate the mandatory user-visible receipt table with:

```text
python scripts/validate-routing-plan.py <ledger.json> --report
```

The final response must include one row per planned child using these columns, even when dispatch was rejected:

```text
agent | role | requested pair | effective pair | confirmation | receipt | result | purpose
```

Do not replace exact model/effort values with family names, role labels, `default`, or `inherits parent`. If no child was created, show no effective pair and `runtime-rejected`; if a fallback succeeded, show both requested and effective pairs. Report validations, policy exceptions, remaining blockers, and risks after the table. Do not expose private reasoning or raw orchestration transcripts.

For `luna_max_only`, the generated receipt and result cells include their `e<event_seq>` markers, and a non-success result includes its parent-attested failure classification. This lets the user audit which spawns preceded or followed a failure fence and why a retry qualified without adding or removing table columns.

State the resolved `profile`, `metric_source`, and `child_policy` immediately after the table so the existing table-first format remains compatible. Under Economy, also show one decision row per child with the evaluation mode, selected pair, child/parent expected costs when quantitative, cost unit, delegation decision, and rationale. Mark qualitative-only and explicit/inherited bypasses visibly.
