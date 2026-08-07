# Incident Response Runbook

**Document Owner:** Platform Engineering
**Effective Date:** March 15, 2026
**Access Scope (suggested):** shared

## Severity Levels

| Severity | Definition | Response Time | Example |
|----------|-----------|----------------|---------|
| SEV1 | Full outage or data loss affecting all customers | 15 minutes | API returning 5xx for all requests |
| SEV2 | Major functionality degraded for a subset of customers | 30 minutes | Chat streaming failing for one region |
| SEV3 | Minor functionality impaired, workaround available | 4 hours | Slow document upload (>30s) |
| SEV4 | Cosmetic or non-urgent issue | Next business day | Dashboard chart mislabeled |

## Roles During an Incident

- **Incident Commander (IC):** Coordinates response, owns communication, makes
  the call on mitigation vs. rollback. Does not personally debug.
- **Ops Lead:** Executes technical mitigation steps (rollbacks, scaling,
  failover) under IC direction.
- **Scribe:** Maintains the incident timeline in the incident channel.

## Immediate Steps (First 15 Minutes)

1. Acknowledge the page and open an incident channel (`#incident-<date>-<slug>`).
2. Declare severity using the table above. When in doubt, declare higher and
   downgrade later.
3. Post an initial status update within 10 minutes, even if it's "still
   investigating."
4. Check the observability dashboard for error rate, latency (p50/p95/p99),
   and saturation (CPU, memory, connection pool usage).

## Common Mitigations

- **Provider failover:** If the primary LLM provider (OpenAI) is degraded,
  confirm `FailoverLLMProvider` has switched to the fallback (Anthropic). Check
  logs for `provider_failover_triggered`.
- **Database connection exhaustion:** Check Postgres `pg_stat_activity` for
  connection count against `max_connections`. Restart the API pods to release
  stale connections if the pool is exhausted.
- **Vector store unavailable:** ChromaDB outages degrade RAG retrieval but
  should not take down chat entirely — verify the retrieval agent's fallback
  path (empty context, not an exception) is engaged.
- **Rollback:** `docker compose up --build -d` after checking out the last
  known-good commit is the fastest rollback path for this deployment model.

## Postmortem Requirements

Every SEV1 and SEV2 incident requires a blameless postmortem within 5 business
days, including a timeline, root cause, and at least 2 concrete action items
with owners and due dates.
