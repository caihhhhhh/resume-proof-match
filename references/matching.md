# Matching model

## Source model

The workspace contains three structured files:

- \`jd-analysis.json\`: requirements copied from the JD;
- \`evidence-ledger.json\`: resume claims and their sources;
- \`match-report.json\`: the explicit mapping between requirements and claims.

Every requirement needs:

- a stable ID;
- \`type\`: \`must-have\`, \`nice-to-have\`, or \`must-not\`;
- a category;
- importance from 1 to 5;
- a concise statement;
- the original JD wording in \`source_text\`.

Every claim needs:

- a stable ID;
- a factual statement;
- a source that another person could locate;
- \`status\`: \`confirmed\`, \`needs-confirmation\`, or \`unsupported\`;
- an optional caveat that preserves partial ownership or uncertainty.

## Match states

- \`supported\`: at least one referenced claim is confirmed and directly supports the requirement.
- \`needs-confirmation\`: evidence may exist, but the user must confirm a material detail.
- \`unsupported\`: no usable evidence currently supports the requirement.
- \`conflict\`: the candidate violates a \`must-not\` condition or another explicit hard constraint.
- \`not-applicable\`: the requirement is not scoreable for a documented reason.

Do not infer support from keyword overlap alone. A tools list can help locate evidence, but it does not prove depth, ownership, duration, or results.

Each match may also carry two optional fields:

- `confidence`: `high`, `medium`, or `low` — the agent's judgment of how directly
  the linked evidence supports the requirement. Validated by the CLI when present.
- `explanation`: one line stating why the linked evidence does or does not
  support the requirement.

## Deterministic scoring

Only positive requirements are included in role-fit scoring. Weight is:

\`importance * 2\` for must-have requirements and \`importance\` for nice-to-have requirements.

Status factors are:

- supported: 1.0
- needs-confirmation: 0.5
- unsupported: 0
- not-applicable: excluded

Role fit is the weighted mean of those factors. Evidence coverage uses the same weights but counts only confirmed, traceable evidence as 1.0 and evidence awaiting confirmation as 0.5.

Document readiness is the average of structure, clarity, keyword expression, and extractability. Keep it separate from role fit because presentation quality cannot replace missing qualifications.

Bands:

- Strong: role fit at least 80, with no unsupported must-have and no hard conflict.
- Stretch: role fit at least 60 and no hard conflict.
- Weak: below 60 or any hard conflict.

These values are decision aids, not recruiter behavior predictions or ATS pass probabilities.

## Keyword coverage

The CLI `keywords` command checks JD keyword coverage in a resume file without
pretending to predict ATS behavior:

- English: alphanumeric tokens from requirement statements and source text,
  minus stopwords, matched with word boundaries (no stemming).
- Chinese: longest common phrases between each JD run and the resume
  (greedy longest-first, no word segmenter), plus the JD phrases the resume
  does not cover.
- Output: present/missing lists, per-requirement breakdown, and a coverage
  ratio, always labeled "keyword coverage only; not an ATS pass probability."

Use it to spot missing terminology before tailoring. A missing keyword is a
lead for evidence, never proof of a missing qualification.

## Comparing applications

The CLI `compare` command ranks two or more application workspaces by
recommendation first, then role fit, then evidence coverage. Scores are
recomputed deterministically from the workspace files, so the ranking never
depends on stale stored scores. Workspaces that fail validation are shown
with their errors rather than ranked.

## Document readiness rubric

Score each dimension 0–100 and write one line of justification. The rubric
reduces variance; it does not eliminate judgment — scores stay on the agent
side, never in a function.

| Score | structure | clarity | keyword_expression | extractability |
|---|---|---|---|---|
| 90–100 | Conventional sections in logical order, consistent formatting | Every bullet starts with a strong verb and a quantified outcome | JD core terms appear naturally in context | Clean text layer; `inspect` passes |
| 70–89 | Sections present, minor order/format inconsistencies | Mostly clear, a few vague bullets | Most terms present, some feel forced | Extractable with minor artifacts |
| 40–69 | Missing key sections or confusing order | Frequent filler ("responsible for") or missing outcomes | Key terms missing — run `keywords` | Partial extraction (tables/images) |
| 0–39 | No recognizable structure | Unreadable or empty | No overlap with JD terminology | Scanned image, no text layer |

## Recommendations

- \`apply\`: Strong, or Stretch with no unsupported high-importance must-have.
- \`consider\`: Stretch with a supportable gap or unanswered high-impact question.
- \`low priority\`: Weak, a hard conflict, or an unsupported hard gate.

Explain exceptions rather than changing the score to fit a desired recommendation.

## Suggestions

Each proposed resume change must have:

- the original text or insertion location;
- the proposed text;
- linked claim IDs;
- one of \`supported\`, \`needs-confirmation\`, or \`unsupported\`;
- a short reason tied to a JD requirement.

Never place unsupported text into the draft. Ask for confirmation before using a \`needs-confirmation\` suggestion.
