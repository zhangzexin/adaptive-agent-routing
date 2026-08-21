# Validation and Failure

Read this reference for risk at least `medium`, any delegated write, an independent reviewer, validation failure, retry, recovery, or stopping decision.

## Evidence contract

Acceptance criteria describe observable outcomes. Validation steps describe how to obtain evidence for them. Neither may be replaced by a vague instruction such as "check the work."

Useful evidence includes:

- exact file/diff inspection;
- target compiler or test results with exit codes;
- schema or deterministic comparison results;
- rendered artifact inspection when layout matters;
- reproducible commands and bounded logs;
- before/after external-state evidence when authorized;
- reviewer findings with precise locations, mechanisms, impact, and confidence.

Running a command proves only that the command ran. State exactly which behavior its result covers and what remains untested.

## Risk-based minimum validation

| Risk | Minimum evidence |
| --- | --- |
| `low` | Exact count/schema/diff or another decisive local check; parent inspects the result |
| `medium` | Targeted test/compile/render plus parent diff/artifact inspection |
| `high` | Integration or cross-boundary validation, independent reviewer, and parent evidence review |
| `irreversible` | Design review, explicit recovery/rollback plan, authorized execution, post-state evidence, and independent final review |

Use the smallest validation that actually covers the changed behavior. More commands do not compensate for a weak oracle.

## Independent review triggers

Require an independent deep reviewer for:

- security, privacy, authentication, authorization, or permissions;
- concurrency, ordering, races, or distributed state;
- data migration, destructive behavior, or difficult rollback;
- public APIs, schemas, or cross-module contracts;
- a still-uncertain root cause or important unverified assumption;
- high blast radius with thin test coverage;
- two substantive validation failures;
- conflicting implementer and validator conclusions;
- evidence the parent cannot adjudicate deterministically.

The reviewer must be a separate work unit from the implementer and default to Sol `xhigh`; use Max only for an exceptionally hard single review. Return findings to the original owner when possible, then repeat affected validation.

## Read-only enforcement levels

`agents/openai.yaml` configures this Skill's UI and invocation policy; it does not create a sandboxed custom reviewer.

Report one of these enforcement levels:

- `sandbox`: a Codex custom agent or runtime policy actually enforces `sandbox_mode = "read-only"`;
- `instruction_pre_post_check`: the dispatch packet prohibits writes, and the parent compares relevant worktree/external state before and after the review.

Instruction-only review is a logical constraint, not a sandbox guarantee. The plan validator may require pre/post checks, but it cannot prove that no write occurred.

A reviewer response should use:

```yaml
status: clear | findings | blocked
enforcement: sandbox | instruction_pre_post_check
findings:
  - location:
    mechanism:
    impact:
    conditions:
    evidence:
    confidence: high | medium | low
    recommended_repair_or_test:
unverified_areas:
```

Avoid style-only findings unless they mask a correctness, security, maintenance, or operational risk.

## Parent acceptance

The parent accepts a node only after:

1. confirming the selected pair, spawn arguments/inheritance mode, accepted receipt, effective pair, child routing echo, and pair-first task name all agree;
2. checking actual changed state and ownership;
3. mapping each acceptance criterion to concrete evidence;
4. confirming required validation exited successfully and covered the intended behavior;
5. resolving or disclosing deviations and partial results;
6. clearing required reviewer findings;
7. confirming integration with other accepted nodes.

Do not accept based on a child's `success` label, its self-reported model label, a plausible explanation, or majority vote among reviewers. The child pair echo proves only that the assignment reached the child; accepted explicit arguments or guaranteed inheritance provide the runtime routing evidence. Conflicting reviewers require stronger evidence or a sufficiently capable adjudicator.

## Failure classification

Classify before retrying or upgrading:

| Failure class | Response |
| --- | --- |
| `transient` | Retry once with the same owner, contract, and pair |
| `missing_context` | Repair the dossier; do not automatically raise effort |
| `bad_decomposition` | Merge nodes or rebuild the DAG/conflict groups |
| `weak_oracle` | Improve acceptance criteria or validation before more implementation |
| `reasoning_failure` | Raise effort one step within the same eligible family |
| `scope_became_open` | Reclassify Luna -> Terra/Sol or Terra -> Sol and regenerate allowed pairs |
| `permission_or_decision` | Stop and return to the parent/user; no model upgrade grants authority |
| `interrupted_partial_write` | Inspect processes, diffs, ownership, and external state before resuming |
| `runtime_unavailable` | Refilter the enumerated fallback pairs; never restore Luna below `xhigh` or Terra below `high` |
| `runtime_receipt_mismatch` | Stop acceptance, preserve the receipt and child echo, correct the ledger or reroute with a new explicit pair; never relabel silently |
| `model_effort_unresolved` | Do not spawn or accept; select an explicit qualified pair or keep the node in the known parent |

An unchanged retry is appropriate only for a genuinely transient failure such as a one-off network response or process crash. A deterministic test failure is evidence, not a transient event.

## Attempt budgets

Default ceilings per node:

- at most one unchanged transient retry;
- at most one same-band substantive repair;
- at most one capability escalation after new evidence;
- at most one Max use;
- after the same substantive failure twice, replan or escalate to a deep diagnostician instead of adding equal workers;
- after two review/repair rounds without new evidence, stop and report the unresolved risk.

These are ceilings, not targets. Stop sooner when authority, safety, time, or evidence requires it. A user-supplied stricter budget wins.

## Interrupted work recovery

When a child is interrupted or fails after possible mutation:

1. pause dependent writers;
2. inspect the actual worktree, relevant processes, generated artifacts, and authorized external state;
3. identify which changes are complete, partial, or unverifiable;
4. preserve the original owner when safe, or make an explicit ownership handoff;
5. restore a valid contract and validation plan before continuing;
6. never assume that a failed tool call made no changes.

Do not discard user or sibling changes while recovering. Destructive rollback still requires the same authorization as any other destructive action.

## Completion and stopping

Completion requires all mandatory nodes to be accepted, all required criteria to have evidence, integration validation to pass, review gates to be clear, the routing ledger to be finalized and valid, and the generated per-child model/effort report to disclose every confirmed pair, rejection, and fallback.

Stop additional dispatch when:

- expected value no longer exceeds coordination cost;
- a user decision, credential, permission, or new authority is required;
- the user's budget or time boundary is reached;
- the same failure survives replan or escalation;
- two iterations produce no new evidence;
- the remaining work cannot form a stable, verifiable contract;
- no runtime pair satisfies the enumerated capability floor.

Partial work, budget exhaustion, and retry exhaustion must be reported as partial or blocked, never as complete.
