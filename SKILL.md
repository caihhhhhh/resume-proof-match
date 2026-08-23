---
name: resume-proof-match
description: End-to-end, evidence-first resume and job-description workflow that explains fit, traces every claim, drafts truthful tailored resumes, requires complete-text approval, verifies formatted files, and delivers versioned outputs. Use when a user provides a resume and JD, asks whether a role is worth applying for, wants gap analysis or resume optimization, or requests final resume files.
---

# ResumeProof Match

Turn a resume and target JD into an explainable application decision and, when requested, an approved and verified final resume.

## Non-negotiable rules

- Never invent or inflate skills, ownership, dates, metrics, employers, education, or outcomes.
- Keep exact identity, company, title, education, date, award, and certificate fields unchanged unless the user explicitly corrects them.
- Never present a score as an ATS pass probability.
- Never generate or overwrite HTML, DOCX, or PDF before the user explicitly approves the complete text draft.
- Never upload, publish, apply, email, or copy files to Desktop without explicit authorization for that action.

## Workflow

1. Collect the base resume, complete JD, supporting evidence, target language, output preference, and any user constraints. If either resume or JD is missing, request it.
2. Create an application workspace with \`python scripts/resume_proof_match.py new\`.
3. Read [references/matching.md](references/matching.md). Extract each JD requirement with its original source text and classify it as \`must-have\`, \`nice-to-have\`, or \`must-not\`.
4. Build \`evidence-ledger.json\`. Mark claims as \`confirmed\`, \`needs-confirmation\`, or \`unsupported\`; plans, forecasts, and team results are not personal achievements without attribution evidence.
5. Map every JD requirement to claim IDs in \`match-report.json\`. Run the CLI \`score\` command; do not estimate the totals manually.
6. Report three separate signals:
   - role fit: evidence-backed coverage of JD requirements;
   - evidence coverage: how much of the proposed case is backed by confirmed claims;
   - document readiness: clarity, structure, keyword expression, and extractability.
7. Surface hard conflicts, strongest evidence, material gaps, and quick wins. Ask only questions that could change a hard gate, a high-weight requirement, or a proposed resume claim.
8. If the user wants optimization, propose factual edits and label each one \`supported\`, \`needs-confirmation\`, or \`unsupported\`. Let the user choose which to adopt.
9. Draft the entire tailored resume in plain text. Separate full-time work and internships when mixing them could imply instability. Present the complete draft and wait for explicit approval.
10. After approval, save the exact draft as \`text-review.md\` and run the CLI \`approve\` command. Use available document tools to create the editable source and PDF without changing the approved meaning.
11. Validate extraction, facts, page count, language, and visual layout. Record each QA result with \`qa\`.
12. Deliver with \`deliver\`; it must block if matching data is invalid, approval is missing or stale, QA is incomplete or stale, or destination files would be overwritten without \`--force\`.

## Output order

Return the smallest useful response in this order:

1. recommendation: apply, consider, or low priority;
2. hard gates and conflicts;
3. role fit, evidence coverage, and document readiness as separate values;
4. strongest matched evidence;
5. material gaps and targeted clarification questions;
6. quick wins and proposed edits;
7. complete text-review draft only after the user chooses edits;
8. formatted files only after explicit full-text approval.

For schemas, scoring, and state rules, read [references/matching.md](references/matching.md). For file generation, QA, and delivery details, read [references/delivery.md](references/delivery.md).
