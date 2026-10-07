# Agent V2

```text
Incoming message
      ↓
Perception
      ↓
Semantic Frame
      ↓
Context / World State
      ↓
Execution Contract
      ↓
Goals
      ↓
Planner
      ↓
Policy + Validators
      ↓
Tools
      ↓
Observations
      ↓
Semantic Effect Verification
      ↓
Renderer
```

The critical design principle is **current-turn authority**: stale booking context must not overrule an explicit new request. The legacy implementation also contains state-purge, provenance, idempotency, payment-continuation, multi-resource and handoff guards. These are preserved until covered by dedicated regression tests and extracted.
