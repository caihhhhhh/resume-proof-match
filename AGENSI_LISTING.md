# ResumeProof Match — Agensi Listing Copy

> Fill in `PRICE` before submitting. Everything else is ready to paste.

## Listing title

ResumeProof Match — Evidence-First Resume ↔ JD Matching for AI Agents

## Tagline

Know the fit. Prove every claim. Approve before export.

## Short description (for cards / search)

An end-to-end Agent Skill that turns a resume and a job description into an
explainable application decision — then produces a truthful tailored resume
through mandatory full-text approval, hash-bound QA, and protected delivery.
No invented metrics. No fake ATS scores.

## Long description

Most matching tools stop at a score. Most resume generators start writing before
the facts are settled. ResumeProof Match keeps both stages in one auditable
workflow, built for AI agents (Codex, Claude Code, and compatible hosts).

**How it works**

1. Extract every JD requirement with its original wording; classify as
   must-have, nice-to-have, or must-not.
2. Build a claim-to-source evidence ledger: confirmed, needs-confirmation,
   or unsupported. Team results and forecasts are never personal achievements
   without attribution.
3. Map each requirement to claim IDs and compute deterministic scores —
   role fit, evidence coverage, and document readiness stay separate.
4. Propose only truthful edits, each labeled supported / needs-confirmation /
   unsupported. You choose what to adopt.
5. Draft the complete resume in plain text. Nothing is formatted until you
   explicitly approve the full draft.
6. QA (text, facts, pagination, visual) is bound to the approved text by
   SHA-256. Any later change invalidates approval and blocks delivery.

**What makes it different**

- Requirement-level explanations: every conclusion points to JD wording and
  specific resume evidence.
- Three honest signals instead of one blended score.
- Scores are decision aids — never presented as ATS pass probabilities.
- Unsupported claims can never enter a draft.
- Delivery is atomic and checksummed; collisions fail unless explicitly forced.
- Portable: Python standard library only. No accounts, no database, no vector store.

**Try before you buy**

- Live web demo: https://resumeproof.szw19990924.chatgpt.site/match/new
- Open-source repo (MIT): https://github.com/caihhhhhh/resume-proof-match
- Free governance-only version: https://github.com/caihhhhhh/resume-proof

## What's included

- `SKILL.md` — agent workflow with non-negotiable rules
- `scripts/resume_proof_match.py` — deterministic CLI
  (`new` / `score` / `approve` / `inspect` / `qa` / `deliver` / `safety`)
- `references/matching.md` — matching model, scoring contract, suggestion rules
- `references/delivery.md` — approval, QA, and delivery contract
- `examples/sample-application/` — fictional end-to-end worked example
- `tests/` + CI — approval and delivery guard tests
- `agents/openai.yaml` — Codex-facing metadata

## Requirements

- Python 3.10+
- An Agent Skills-compatible host (Codex, Claude Code, etc.)
- Optional: `pypdf` or Poppler for PDF text inspection

## Suggested price

`TODO: set your price` — positioning note: the base `resume-proof` skill stays
free and open-source as the top of funnel; this Match edition is the premium
end-to-end workflow.
