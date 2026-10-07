# Open Source Migration Report

## What changed

- Created a new repository tree; the supplied backup is untouched.
- Removed production runtime data, learning datasets, logs and browser profile from the public tree.
- Removed hard-coded credentials and personal admin identifiers from public configuration.
- Added `.env.example`, `.gitignore`, packaging, modern CLI, tests, CI and security documentation.
- Extracted the calendar engine into `domain/reservations/calendar.py`.
- Extracted the event/tournament registration engine into `domain/events/registration.py`.
- Added typed domain models and reusable JSON/CSV/SQLite persistence primitives.
- Added stable Agent V2 and WhatsApp package facades.
- Preserved the mature ordered CANONICAL runtime as an explicit legacy compatibility core rather than rewriting it.

## New architecture

See `README.md` and `docs/architecture.md`.

## Files extracted from WPSetter

The first conservative phase extracts boundaries rather than copying arbitrary function blocks. Agent V2/WhatsApp calls are reachable through structured package modules while their mature implementation remains in the legacy core. Calendar and event registration are fully moved into native domain modules.

## WPSetter before/after line count

- Original: 146,701 lines.
- Root compatibility `WPSetter.py`: 21 lines.
- Preserved historical core: 146,704 lines in `legacy/WPSetter_legacy.py`.

This intentionally does **not** claim that the historical core has already been fully decomposed. The next migration phase is final-binding extraction under characterization/regression coverage.

## Tests before/after

Validation performed on the generated repository:

- `python -m compileall`: passes;
- repository offline tests: **8 passed**;
- security/PII scan: passes;
- `calendario.py --order` smoke test against an isolated runtime: passes;
- editable package build/install with local build tooling: passes;
- `cancheria --help`: passes.

For parity with the supplied backup, the historical offline Agent V2 suites were also compared using an inert OpenAI import stub (no API calls):

- both original and refactored `--agentic-evals` reach the same pre-existing failing invariant: `v125_waiting_branch_has_highest_non_human_priority`;
- both original and refactored `--agentic-evals-e2e` reach the same pre-existing late-payment `TypeError` caused by a test lambda that does not accept `monto_esperado`.

Those failures are therefore baseline debt, not regressions introduced by this refactor.

## Security remediation

- API/email secrets moved to environment variables.
- personal admin phone/name defaults removed;
- `wa_profile/` excluded;
- production JSON/CSV/JSONL/DB/pickle/logs excluded;
- embedded phone literals in legacy test/example code replaced with synthetic values;
- runtime moved under `runtime/`.

## Secrets requiring rotation

Before publishing, rotate:

- the OpenAI API credential that existed in the private backup;
- the email application password that existed in the private backup;
- any browser/session authentication contained in the old `wa_profile/` if the backup was ever exposed outside trusted storage.

No secret values are reproduced here.

## Remaining legacy debt

- Agent V2's ordered CANONICAL chain is still physically contained in `legacy/WPSetter_legacy.py`.
- payment/hold/scheduler/admin logic remains compatibility-backed because of tight side-effect coupling;
- the old visual configurator is retained as a legacy tool and should be redesigned around data-driven configuration;
- additional characterization tests should be captured in an environment with all production dependencies installed.

## Known risks

The largest risk remains changing the order of final CANONICAL bindings. Consult `docs/legacy-canonical-map.md` before moving any duplicated function.

## Recommended next extractions

1. effective Perception binding;
2. ExecutionContract construction;
3. planner/policy/verifier chain;
4. payment/hold service;
5. scheduler/admin notification service;
6. Playwright browser client.

Each extraction should add a regression test first.

## Commands to run locally

```bash
python -m venv .venv
pip install -e ".[dev]"
playwright install chromium
pytest -m "not live and not browser"
python scripts/security_scan.py
cancheria --help
python WPSetter.py --agentic-evals
```

## Checklist before GitHub publication

- [ ] Rotate historical OpenAI credential.
- [ ] Rotate historical email app password.
- [ ] Review `.env.example` only contains placeholders.
- [ ] Run `python scripts/security_scan.py`.
- [ ] Run offline tests.
- [ ] Run legacy Agent V2 invariant/E2E evals in the real environment.
- [ ] Test one disposable WhatsApp profile end-to-end.
- [ ] Choose a license.
- [ ] Add demo GIF/video.
- [ ] Review Git history before first push.
