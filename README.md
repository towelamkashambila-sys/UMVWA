# UMVWA — Build Room Runtime Foundation v0.1

This is the first runnable UMVWA application foundation. It is intentionally portable and does not depend on Replit.

## Current vertical slice
- Workspace + Executive/Assistant identity
- Shared operational reality backed by SQLite persistence
- Canonical WorkItem lifecycle via the verified UMVWA lifecycle registry
- Assignment / acknowledgement / start
- Waiting / blocked / clarification
- Human decision + authority grant
- On Hold / resume
- Evidence-gated completion
- Immutable transition history records
- Executive Driver's Seat projection
- Assistant operational home projection
- Assistant-declared capacity + separate operational load
- Cross-surface event propagation through persisted state/history
- Approved UMVWA logo and landing hero source assets copied unchanged

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=canonical_src uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000

## Test

```bash
PYTHONPATH=canonical_src pytest -q
```

The pre-build Assembly tests are retained separately in the transfer package; this app adds runtime-facing tests around the first real vertical slice.
