# Access Control & Credential Handling Policy

**Document Owner:** Security Team
**Effective Date:** February 1, 2026
**Access Scope (suggested):** restricted

## Purpose

This policy defines minimum standards for account provisioning, credential
handling, and access review across all internal systems, including the
Multi-Agent Knowledge Assistant platform.

## Account Provisioning

- All employee accounts are provisioned with the `employee` role by default.
  The `admin` role is granted only after written approval from a Security
  team lead and is reviewed quarterly.
- Service accounts (used by CI/CD, integrations) must use dedicated
  credentials, never a human employee's personal login.
- Accounts must be deprovisioned within 24 hours of an employee's last day,
  and access must be suspended immediately upon involuntary termination.

## Credential Handling

- Passwords are stored using bcrypt with a minimum work factor of 12.
- JWTs issued by the platform expire after 24 hours and must be re-issued via
  login; there is no silent refresh.
- API keys (OpenAI, Anthropic) must be stored in environment variables or a
  secrets manager, never committed to source control.
- Any credential suspected of being exposed (e.g., committed to a public
  repository) must be rotated within 1 hour of discovery and reported to
  Security.

## Document Access Scopes

Documents ingested into the knowledge base are tagged with an access scope:

- `shared`: visible to all authenticated employees.
- `restricted`: visible only to users with the `admin` role.

Uploaders are responsible for correctly classifying documents at ingestion
time. Misclassifying a restricted document as shared is treated as a
security incident and must be reported immediately so the document can be
removed from the vector store and re-ingested with the correct scope.

## Access Reviews

- Quarterly access reviews are conducted for all `admin`-role accounts.
- Any account inactive for 90 days is automatically flagged for review and
  may be suspended pending manager confirmation.

## Incident Reporting

Suspected unauthorized access, credential leaks, or policy violations should
be reported immediately to security@example.com or via the #security-incidents
channel. Do not attempt to independently investigate a suspected breach.
