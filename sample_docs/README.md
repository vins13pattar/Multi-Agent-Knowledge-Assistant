# Sample Documents for RAG Testing

Synthetic, fictional documents for exercising the ingestion → chunking →
embedding → retrieval pipeline (`src/rag/documents.py`, `src/rag/store.py`)
and the `access_scope` filtering in `apps/api/main.py`.

| File | Format | Suggested `access_scope` | Topic |
|------|--------|---------------------------|-------|
| `hr_policy_pto.md` | Markdown | `shared` | PTO accrual, requests, carryover |
| `engineering_incident_response_runbook.md` | Markdown | `shared` | Incident severities, roles, mitigations |
| `finance_q3_2026_report.txt` | Text | `restricted` | Revenue, expenses, headcount, risks |
| `security_access_control_policy.md` | Markdown | `restricted` | Provisioning, credentials, access reviews |
| `product_faq.txt` | Text | `shared` | Platform usage FAQ |
| `new_hire_onboarding_guide.md` | Markdown | `shared` | Onboarding checklist and account setup |

The mix of shared/restricted docs lets you confirm an `employee`-role user
never sees `finance_q3_2026_report.txt` or `security_access_control_policy.md`
in retrieval results, while an `admin`-role user sees all six.

## Uploading via the API

Requires the stack running (`docker compose up --build`) and a JWT from
`POST /api/v1/auth/login`.

```bash
TOKEN="<jwt from login>"

for f in sample_docs/*.md sample_docs/*.txt; do
  scope="shared"
  case "$f" in
    *finance_q3_2026_report.txt|*security_access_control_policy.md) scope="restricted" ;;
  esac
  curl -s -X POST "http://localhost:8000/api/v1/documents/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$f" \
    -F "access_scope=$scope"
  echo
done
```

## Suggested Test Queries

- "How many PTO days do I get after 4 years?" → should cite `hr_policy_pto.md`.
- "What's the response time for a SEV2 incident?" → should cite
  `engineering_incident_response_runbook.md`.
- "What was Q3 revenue?" → should return results (with citation) only for an
  `admin` user; an `employee` user should get no matching restricted content.
- "What file types can I upload?" → should cite `product_faq.txt`.
- "What do I need to do in my first week?" → should cite
  `new_hire_onboarding_guide.md`.

## Notes

- All content is fictional and safe to ingest repeatedly; the upload endpoint
  detects duplicate ingests by content hash.
- Only `.pdf`, `.md`, and `.txt` are accepted by `load_document()` — these
  files intentionally cover the two non-PDF formats.
