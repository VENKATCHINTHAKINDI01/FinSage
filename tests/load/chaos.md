# Outage matrix — PRD-007

What each dependency failing should do, and why. **None of these has been
exercised.** They are the assertions a chaos run must check, written down
before the run so the run cannot be graded against whatever it happened to do.

| Dependency | Expected degradation | Why it should hold |
|---|---|---|
| Groq / LLM | Deterministic output only: computations, worksheets and citations, with a notice that explanation is unavailable | `backend.core` cannot import an LLM — the purity contract forbids it — so every figure is computed without one |
| Qdrant | Answers without retrieved context, badged | RAG augments; it does not produce figures |
| Redis | Rate limiting fails OPEN, session lookups fail CLOSED | PRD-003 and PRD-002 make opposite choices deliberately; a Redis outage is the case that proves it |
| Postgres | 503 with a plain message | There is no degraded mode for a missing user record, and inventing one would be worse |
| Source gatherer | Cached facts serve with a staleness badge; ungathered facts become named gaps | PRC-011: the network is never on the answer path |
