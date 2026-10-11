# Workspace exchange format

Contract for moving an application workspace between ResumeProof Match Skill
hosts and the web app (or any other implementation). Version 1.

## Archive

- A plain zip file. Recommended name: `<slug>.zip`.
- Must contain, at the archive root:
  - `export.json` — the format marker (see below);
  - `manifest.json` — the workspace manifest;
  - every file listed in `manifest["files"]` (e.g. `jd-analysis.json`,
    `evidence-ledger.json`, `match-report.json`, `text-review.md`,
    `cover-letter.md`).

## export.json

```json
{
  "format": "resume-proof-match-workspace",
  "version": 1,
  "exported_at": "2026-10-11T10:00:00Z",
  "application": { "company": "Example Co", "role": "Growth Analyst", "language": "en" }
}
```

- `format` must equal `resume-proof-match-workspace`.
- `version` must equal `1`. Bump only with a documented migration.
- Extra keys are allowed and must be ignored by readers.

## Import rules

1. Reject archives without `export.json`, with an unknown `format`, or with an
   unsupported `version`.
2. Reject archives whose `manifest.json` is missing or unparsable.
3. Reject archives missing any file listed in `manifest["files"]`.
4. Never overwrite an existing workspace without explicit user confirmation.
5. After import, re-validate the matching data and surface warnings; do not
   silently repair it.
6. Approval and QA hashes remain valid after import because files are copied
   byte-for-byte. Any byte change invalidates them by design.

## CLI

```bash
# Pack a workspace
python scripts/resume_proof_match.py export <application_dir> --output app.zip

# Restore it elsewhere (or upload the zip to the web app once supported)
python scripts/resume_proof_match.py import app.zip --output-root Resume_Output/Applications --slug my-app
```
