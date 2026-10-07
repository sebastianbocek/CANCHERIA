# CANCHERIA Open-Source Refactor Plan

## Current Architecture

The source backup contains a 146,701-line `WPSetter.py`, a 2,169-line calendar engine, a 784-line event-registration engine, a 940-line business configuration module, browser automation, scheduler/admin behavior, Agent V2, learning/eval systems, and runtime state stored in CSV/JSON/JSONL/SQLite/pickle files.

## Dependency Map

```text
WhatsApp Web / Playwright ─┐
Admin + Scheduler ─────────┼──> Legacy Agent V2 / orchestration ──> Reservation + Payment + Event domains
OpenAI ────────────────────┘                    │
                                                 └──> CSV / JSON / SQLite runtime state
```

Target direction:

```text
channels + infrastructure + admin -> agent/application -> domain
```

The domain must not import Playwright or OpenAI.

## WPSetter Responsibility Map

Observed responsibilities include:

- browser/session/profile lifecycle;
- inbox and message extraction;
- selector health/adaptation;
- persistent conversation state;
- agent learning and scenario evals;
- Agent V2 perception, semantic grounding, world state, execution contracts, goals, planner, policy, tools, reducer, verifier and renderer;
- bookings, holds, payments, rescheduling, cancellations, recurring bookings and waitlist;
- tournament/event registration;
- admin commands, reports, alerts and human handoff;
- proactive scheduler and reminders.

## Canonical Override Map

`WPSetter.py` has 98 top-level function names with multiple definitions. The generated detailed map lives in `docs/legacy-canonical-map.md`.

## Side Effect Inventory

Primary side effects:

- CSV writes for bookings/contacts/finished bookings;
- JSON/JSONL writes for state, memory, handoff, proactive state and metrics;
- SQLite writes for calendar/canonical state;
- browser navigation and WhatsApp message/media sends;
- email alerts;
- payment/hold state transitions;
- learning-policy persistence.

The refactor keeps these behind compatibility boundaries instead of rewriting them blindly.

## Security Findings

- Hard-coded OpenAI credential found in the original `config.py` — removed from the public tree; **rotate it**.
- Hard-coded email app password found — removed; **rotate it**.
- Personal admin/contact identifiers found — removed from public defaults and moved to environment variables.
- `wa_profile/` contains browser/session data and is excluded entirely.
- Runtime logs/state/learning data are excluded from the public repository.

No secret values are reproduced in this document.

## Proposed Architecture

The public tree uses `src/cancheria/` with explicit `agent/`, `domain/`, `channels/`, `infrastructure/`, `admin/`, `learning/`, `messaging/`, and `config/` boundaries.

The historical production implementation is retained at `legacy/WPSetter_legacy.py` for behavioral compatibility. Stable package facades route to its effective bindings while domains that were already independently separable (`calendario.py` and `event_registration_engine.py`) are moved into real package modules.

## Migration Order

1. sanitize secrets/runtime;
2. establish package + CLI + path boundaries;
3. move calendar and event registration into domain modules;
4. add typed domain/persistence primitives;
5. expose stable Agent V2 and WhatsApp facades;
6. preserve legacy CLI;
7. capture source-contract/characterization tests;
8. incrementally move final CANONICAL bindings out of legacy core under regression coverage.

## Risks

Highest-risk areas are the repeated CANONICAL rebindings, payment/hold side effects, current-turn authority, stale-state purges, resource switching, recurring bookings, and human handoff. They remain compatibility-backed until extracted with behavior tests.

## Baseline Tests

The production OpenAI client was unavailable in this build environment, so an inert local OpenAI stub was used **only to allow the offline suites to import**; any attempted API call would raise immediately. Under that condition:

- original backup `--agentic-evals`: exits 1 with the existing failure `v125_waiting_branch_has_highest_non_human_priority`;
- refactored project `--agentic-evals`: same exit and same existing failure;
- original backup `--agentic-evals-e2e`: reaches the late-payment scenario and raises the existing `analizar_comprobante_senia(..., monto_esperado=...)` lambda-signature `TypeError`;
- refactored project `--agentic-evals-e2e`: reaches the same scenario and raises the same existing `TypeError`.

This parity is important: the observed offline failures are present in the supplied backup and were not introduced by the repository refactor. The new repository's own offline tests pass independently.
