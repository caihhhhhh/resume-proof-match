# Changelog

All notable changes to ResumeProof Match are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `status`: one JSON snapshot of a workspace (approvals, QA, scores, outcome).
- `extract`: pull text from a resume file (PDF/HTML/TXT) for the ledger step.
- `qa --from-inspect`: run inspect checks and record text/pagination from the
  result instead of self-reporting them.
- `outcome`: record post-delivery results (applied/rejected/ghosted/interview/
  offer/withdrawn) with history; `compare` now shows it.
- Document readiness rubric in `references/matching.md` (score bands + required
  one-line justification per dimension).
- `export` / `import`: pack a workspace into a portable zip and restore it
  elsewhere (byte-identical roundtrip; approval/QA hashes stay valid).
  `references/workspace-exchange.md` documents the format for the web app.
- `interview`: generate an interview prep doc from the evidence ledger —
  behavioral questions from confirmed claims, honest gap bridging, pending
  clarifications, and questions to ask. Every bullet traces to a claim ID.
- Cover letter track: `cover-letter.md` per application, `cover-approve`
  (hash-lock, requires greeting/closing/minimum content), `cover-qa`
  (text + facts checks bound to file hashes), and `deliver` now accepts
  files bound to either the resume or the cover letter QA. Old manifests
  get the new keys backfilled automatically.
- `compare` CLI command: rank multiple application workspaces side by side by
  recommendation, role fit, and evidence coverage. Prints a comparison table
  (or JSON with `--format json`, saved with `--output`); invalid workspaces
  are listed with their errors instead of silently dropped.
- `keywords` CLI command: deterministic JD keyword coverage check for a resume
  file (English tokens with word boundaries; Chinese longest-common-phrase
  matching without a word segmenter). Always labeled as coverage only, never
  an ATS pass probability; `--write` persists it into `match-report.json`.
- `AGENSI_LISTING.md`: ready-to-use marketplace listing copy (title, pitch, feature
  list, requirements, demo links).
- README: CI / Codex / Claude Code / Python / License badges, FAQ section, and a
  cross-link to the free governance-only `resume-proof` base skill.
- `.gitattributes`: normalizes line endings to LF across platforms.

### Changed
- `confidence` on match entries (`high` / `medium` / `low`) is now validated by the
  CLI and documented in `references/matching.md`.
- The approval gate now requires the text review to read as a complete resume:
  minimum length plus at least one recognizable resume section marker
  (bilingual EN/ZH), instead of a bare character count.

## [1.0.0] - 2026-09-02

- Initial public release.
- End-to-end evidence-first workflow: JD requirement extraction, claim-to-source
  evidence ledger, explainable match report with deterministic scoring, mandatory
  complete-text approval, hash-bound QA, and protected delivery.
- CLI commands: `new`, `score`, `approve`, `inspect`, `qa`, `deliver`, `safety`
  (Python standard library only; optional `pypdf`/`pdftotext` for PDF inspection).
- Three separate signals: role fit, evidence coverage, document readiness.
  Scores are decision aids, never ATS pass probabilities.
