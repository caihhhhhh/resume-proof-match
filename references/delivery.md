# Approval, QA, and delivery

## Approval

\`text-review.md\` must contain the complete resume, not an outline or selected section. The \`approve\` command records its SHA-256 hash. Any later wording change invalidates approval and requires another complete review.

Layout-only changes may proceed after approval if they preserve the exact meaning. If fitting the page requires deleting, combining, or rewriting content, return to text review.

## Generation

Use the document tools available in the host environment. Prefer a simple, readable layout and no more than two A4 pages unless the user requests otherwise. Optimize for human scanning first and reliable text extraction second.

Keep the editable source next to the PDF. Do not bundle personal data or populated evidence files in the public Skill repository.

## QA

Run \`inspect\` for extractable text, required or forbidden terms, and page count when the file format is supported. Record these checks separately:

- \`text\`: required content is extractable and forbidden or stale text is absent;
- \`facts\`: names, dates, metrics, tools, and claims match the approved text and evidence ledger;
- \`pagination\`: page count meets the requested limit;
- \`visual\`: every page was inspected for spacing, clipping, alignment, and density.

The \`qa\` command binds passing QA to both the approved-text hash and the supplied output files. Regenerating a file makes previous QA stale.

## Delivery

Use \`deliver\` only after all checks pass. It performs a full preflight before copying any file, so a collision or missing file cannot leave a partial delivery. Existing files require explicit \`--force\`.

Desktop delivery, uploads, applications, messages, and publication are independent external actions and require explicit user authorization.
