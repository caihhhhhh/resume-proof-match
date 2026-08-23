#!/usr/bin/env python3
"""Deterministic controls for evidence-first resume matching and delivery."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "assets" / "manifest-template.json"
QA_KEYS = ("text", "facts", "pagination", "visual")
QA_STATES = ("pending", "passed", "failed")
POSITIVE_TYPES = ("must-have", "nice-to-have")
REQUIREMENT_TYPES = POSITIVE_TYPES + ("must-not",)
MATCH_STATES = ("supported", "needs-confirmation", "unsupported", "conflict", "not-applicable")
CLAIM_STATES = ("confirmed", "needs-confirmation", "unsupported")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "-", value.strip())
    return re.sub(r"\s+", "-", value).strip(".-") or "application"


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"File not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def manifest_path(application_dir: Path) -> Path:
    return application_dir / "manifest.json"


def load_manifest(application_dir: Path) -> dict:
    return read_json(manifest_path(application_dir))


def workspace_file(application_dir: Path, manifest: dict, key: str) -> Path:
    return application_dir / manifest["files"][key]


def matching_hashes(application_dir: Path, manifest: dict) -> dict[str, str]:
    keys = ("jd_analysis", "evidence_ledger", "match_report")
    return {key: sha256(workspace_file(application_dir, manifest, key)) for key in keys}


def command_new(args: argparse.Namespace) -> int:
    root = args.output_root.resolve()
    folder = args.slug or f"{datetime.now():%Y%m%d}_{safe_name(args.company)}_{safe_name(args.role)}"
    application_dir = root / safe_name(folder)
    if application_dir.exists():
        raise RuntimeError(f"Application folder already exists: {application_dir}")
    application_dir.mkdir(parents=True)

    manifest = deepcopy(read_json(TEMPLATE))
    manifest["application"].update(
        company=args.company,
        role=args.role,
        language=args.language,
        created_at=utc_now(),
    )
    write_json(manifest_path(application_dir), manifest)
    write_json(
        application_dir / "jd-analysis.json",
        {
            "schema_version": 1,
            "job": {"company": args.company, "role": args.role, "language": args.language},
            "requirements": [],
        },
    )
    write_json(application_dir / "evidence-ledger.json", {"schema_version": 1, "claims": []})
    write_json(
        application_dir / "match-report.json",
        {
            "schema_version": 1,
            "matches": [],
            "document_readiness": {
                "structure": 0,
                "clarity": 0,
                "keyword_expression": 0,
                "extractability": 0,
            },
            "scores": None,
            "quick_wins": [],
            "disclaimer": "Decision aid only; not an ATS pass probability.",
        },
    )
    (application_dir / "text-review.md").write_text(
        "# Text review draft\n\nStatus: awaiting complete review and explicit approval.\n",
        encoding="utf-8",
    )
    print(application_dir)
    return 0


def require_text(value: object, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be non-empty text")
        return ""
    return value.strip()


def validate_matching(application_dir: Path) -> tuple[dict, dict, dict, list[str]]:
    manifest = load_manifest(application_dir)
    jd = read_json(workspace_file(application_dir, manifest, "jd_analysis"))
    ledger = read_json(workspace_file(application_dir, manifest, "evidence_ledger"))
    report = read_json(workspace_file(application_dir, manifest, "match_report"))
    errors: list[str] = []

    requirements = jd.get("requirements")
    claims = ledger.get("claims")
    matches = report.get("matches")
    if not isinstance(requirements, list) or not requirements:
        errors.append("jd-analysis.json needs at least one requirement")
        requirements = []
    if not isinstance(claims, list):
        errors.append("evidence-ledger.json claims must be a list")
        claims = []
    if not isinstance(matches, list):
        errors.append("match-report.json matches must be a list")
        matches = []

    requirement_map: dict[str, dict] = {}
    for index, requirement in enumerate(requirements):
        label = f"requirements[{index}]"
        if not isinstance(requirement, dict):
            errors.append(f"{label} must be an object")
            continue
        requirement_id = require_text(requirement.get("id"), f"{label}.id", errors)
        if requirement_id in requirement_map:
            errors.append(f"duplicate requirement id: {requirement_id}")
        requirement_type = requirement.get("type")
        if requirement_type not in REQUIREMENT_TYPES:
            errors.append(f"{label}.type must be one of {', '.join(REQUIREMENT_TYPES)}")
        importance = requirement.get("importance")
        if not isinstance(importance, int) or isinstance(importance, bool) or not 1 <= importance <= 5:
            errors.append(f"{label}.importance must be an integer from 1 to 5")
        require_text(requirement.get("statement"), f"{label}.statement", errors)
        require_text(requirement.get("source_text"), f"{label}.source_text", errors)
        if requirement_id:
            requirement_map[requirement_id] = requirement

    claim_map: dict[str, dict] = {}
    for index, claim in enumerate(claims):
        label = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{label} must be an object")
            continue
        claim_id = require_text(claim.get("id"), f"{label}.id", errors)
        if claim_id in claim_map:
            errors.append(f"duplicate claim id: {claim_id}")
        require_text(claim.get("statement"), f"{label}.statement", errors)
        require_text(claim.get("source"), f"{label}.source", errors)
        if claim.get("status") not in CLAIM_STATES:
            errors.append(f"{label}.status must be one of {', '.join(CLAIM_STATES)}")
        if claim_id:
            claim_map[claim_id] = claim

    match_map: dict[str, dict] = {}
    for index, match in enumerate(matches):
        label = f"matches[{index}]"
        if not isinstance(match, dict):
            errors.append(f"{label} must be an object")
            continue
        requirement_id = require_text(match.get("requirement_id"), f"{label}.requirement_id", errors)
        if requirement_id in match_map:
            errors.append(f"duplicate match for requirement: {requirement_id}")
        if requirement_id and requirement_id not in requirement_map:
            errors.append(f"{label} references unknown requirement: {requirement_id}")
        status = match.get("status")
        if status not in MATCH_STATES:
            errors.append(f"{label}.status must be one of {', '.join(MATCH_STATES)}")
        claim_ids = match.get("claim_ids")
        if not isinstance(claim_ids, list) or any(not isinstance(item, str) for item in claim_ids):
            errors.append(f"{label}.claim_ids must be a list of strings")
            claim_ids = []
        unknown = [claim_id for claim_id in claim_ids if claim_id not in claim_map]
        if unknown:
            errors.append(f"{label} references unknown claims: {', '.join(unknown)}")
        linked = [claim_map[claim_id] for claim_id in claim_ids if claim_id in claim_map]
        if status == "supported" and not any(item.get("status") == "confirmed" for item in linked):
            errors.append(f"{label} supported match needs a confirmed claim")
        if status == "unsupported" and any(item.get("status") == "confirmed" for item in linked):
            errors.append(f"{label} unsupported match cannot reference confirmed claims")
        if status == "needs-confirmation" and not any(
            item.get("status") == "needs-confirmation" for item in linked
        ):
            errors.append(f"{label} needs-confirmation match needs a claim awaiting confirmation")
        if requirement_id:
            match_map[requirement_id] = match

    for requirement_id, requirement in requirement_map.items():
        if requirement["type"] in POSITIVE_TYPES and requirement_id not in match_map:
            errors.append(f"missing match for positive requirement: {requirement_id}")

    readiness = report.get("document_readiness")
    if not isinstance(readiness, dict):
        errors.append("document_readiness must be an object")
    else:
        for key in ("structure", "clarity", "keyword_expression", "extractability"):
            value = readiness.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
                errors.append(f"document_readiness.{key} must be from 0 to 100")

    return jd, ledger, report, errors


def calculate_scores(jd: dict, ledger: dict, report: dict) -> dict:
    claim_map = {claim["id"]: claim for claim in ledger["claims"]}
    match_map = {match["requirement_id"]: match for match in report["matches"]}
    numerator = 0.0
    evidence_numerator = 0.0
    denominator = 0.0
    unsupported_must_have: list[str] = []
    conflicts: list[str] = []

    for requirement in jd["requirements"]:
        match = match_map.get(requirement["id"])
        if requirement["type"] == "must-not":
            if match and match["status"] == "conflict":
                conflicts.append(requirement["id"])
            continue
        if not match or match["status"] == "not-applicable":
            continue
        weight = requirement["importance"] * (2 if requirement["type"] == "must-have" else 1)
        factor = {"supported": 1.0, "needs-confirmation": 0.5, "unsupported": 0.0}.get(
            match["status"], 0.0
        )
        denominator += weight
        numerator += weight * factor

        linked_states = {
            claim_map[claim_id]["status"]
            for claim_id in match.get("claim_ids", [])
            if claim_id in claim_map
        }
        evidence_factor = 1.0 if "confirmed" in linked_states else 0.5 if "needs-confirmation" in linked_states else 0.0
        evidence_numerator += weight * evidence_factor
        if requirement["type"] == "must-have" and match["status"] == "unsupported":
            unsupported_must_have.append(requirement["id"])

    role_fit = round(100 * numerator / denominator) if denominator else 0
    evidence_coverage = round(100 * evidence_numerator / denominator) if denominator else 0
    readiness = report["document_readiness"]
    document_readiness = round(sum(readiness.values()) / len(readiness))
    hard_conflict = bool(conflicts)
    if role_fit >= 80 and not unsupported_must_have and not hard_conflict:
        band = "Strong"
    elif role_fit >= 60 and not hard_conflict:
        band = "Stretch"
    else:
        band = "Weak"

    high_gap = any(
        requirement["type"] == "must-have"
        and requirement["importance"] >= 4
        and match_map.get(requirement["id"], {}).get("status") in {"unsupported", "needs-confirmation"}
        for requirement in jd["requirements"]
    )
    recommendation = (
        "apply" if band == "Strong" or (band == "Stretch" and not high_gap)
        else "consider" if band == "Stretch"
        else "low priority"
    )
    return {
        "role_fit": role_fit,
        "evidence_coverage": evidence_coverage,
        "document_readiness": document_readiness,
        "band": band,
        "recommendation": recommendation,
        "unsupported_must_have": unsupported_must_have,
        "conflicts": conflicts,
        "disclaimer": "Decision aid only; not an ATS pass probability.",
    }


def command_score(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    jd, ledger, report, errors = validate_matching(application_dir)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    scores = calculate_scores(jd, ledger, report)
    if args.write:
        report["scores"] = scores
        manifest = load_manifest(application_dir)
        write_json(workspace_file(application_dir, manifest, "match_report"), report)
    print(json.dumps(scores, ensure_ascii=False, indent=2))
    return 0


def command_approve(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    _, _, _, errors = validate_matching(application_dir)
    if errors:
        raise RuntimeError("Matching data is invalid; run score and fix its failures before approval.")
    manifest = load_manifest(application_dir)
    review = workspace_file(application_dir, manifest, "text_review")
    if not review.is_file():
        raise RuntimeError(f"Text review not found: {review}")
    text = review.read_text(encoding="utf-8").strip()
    if len(text) < 120 or "awaiting complete review" in text.casefold():
        raise RuntimeError("Text review is incomplete; replace the placeholder with the complete resume.")
    manifest["status"] = "approved"
    manifest["approval"] = {
        "approved_at": utc_now(),
        "approved_by": args.approved_by,
        "approved_text_sha256": sha256(review),
        "matching_sha256": matching_hashes(application_dir, manifest),
    }
    manifest["qa"] = {key: "pending" for key in QA_KEYS} | {"binding": None}
    write_json(manifest_path(application_dir), manifest)
    print(f"APPROVED {review}")
    return 0


def output_hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path): sha256(path) for path in paths}


def verify_approval(application_dir: Path, manifest: dict) -> tuple[Path, str]:
    review = workspace_file(application_dir, manifest, "text_review")
    approval = manifest.get("approval") or {}
    approved_hash = approval.get("approved_text_sha256")
    if not review.is_file() or sha256(review) != approved_hash:
        raise RuntimeError("Approved text changed; obtain approval again.")
    if approval.get("matching_sha256") != matching_hashes(application_dir, manifest):
        raise RuntimeError("Matching evidence changed; review the complete text and approve again.")
    return review, approved_hash


def extract_pdf(path: Path) -> tuple[str, int | None]:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages), len(reader.pages)
    except ImportError:
        pass
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise RuntimeError("PDF inspection needs optional pypdf or pdftotext on PATH.")
    result = subprocess.run(
        [pdftotext, "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pages = None
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        info = subprocess.run(
            [pdfinfo, str(path)], check=True, capture_output=True, text=True, errors="replace"
        ).stdout
        match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
        if match:
            pages = int(match.group(1))
    return result.stdout, pages


def extract_text(path: Path) -> tuple[str, int | None]:
    if path.suffix.casefold() == ".pdf":
        return extract_pdf(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.casefold() in {".html", ".htm"}:
        text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text, None


def command_inspect(args: argparse.Namespace) -> int:
    path = args.file.resolve()
    if not path.is_file():
        raise RuntimeError(f"File not found: {path}")
    text, pages = extract_text(path)
    haystack = text if args.case_sensitive else text.casefold()
    failures: list[str] = []
    for value in args.required:
        needle = value if args.case_sensitive else value.casefold()
        if needle not in haystack:
            failures.append(f"missing required text: {value}")
    for value in args.forbid:
        needle = value if args.case_sensitive else value.casefold()
        if needle in haystack:
            failures.append(f"found forbidden text: {value}")
    if not text.strip():
        failures.append("no extractable text")
    if pages is not None and pages > args.max_pages:
        failures.append(f"page count {pages} exceeds limit {args.max_pages}")
    print(f"file: {path}")
    print(f"characters: {len(text.strip())}")
    print(f"pages: {pages if pages is not None else 'not checked'}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS")
    return 0


def command_qa(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = load_manifest(application_dir)
    if manifest.get("status") not in {"approved", "qa-passed"}:
        raise RuntimeError("Approve the complete text before recording QA.")
    _, approved_hash = verify_approval(application_dir, manifest)

    changed = False
    for key in QA_KEYS:
        value = getattr(args, key)
        if value:
            manifest["qa"][key] = value
            changed = True
    if not changed:
        raise RuntimeError("Provide at least one QA result.")
    paths = [path.resolve() for path in args.file]
    if any(not path.is_file() for path in paths):
        raise RuntimeError("Every --file value must be an existing file.")
    manifest["qa"]["binding"] = {
        "approved_text_sha256": approved_hash,
        "files": output_hashes(paths),
        "recorded_at": utc_now(),
    }
    if all(manifest["qa"].get(key) == "passed" for key in QA_KEYS):
        manifest["status"] = "qa-passed"
    write_json(manifest_path(application_dir), manifest)
    print(json.dumps(manifest["qa"], indent=2))
    return 0


def command_deliver(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = load_manifest(application_dir)
    if manifest.get("status") != "qa-passed":
        raise RuntimeError("Delivery blocked: complete text approval and all QA checks are required.")
    _, _, _, matching_errors = validate_matching(application_dir)
    if matching_errors:
        raise RuntimeError("Delivery blocked: matching data is invalid.")
    try:
        _, approved_hash = verify_approval(application_dir, manifest)
    except RuntimeError as exc:
        raise RuntimeError(f"Delivery blocked: {exc}") from exc

    files = [path.resolve() for path in args.file]
    if not files:
        raise RuntimeError("Provide delivery files with --file.")
    if any(not path.is_file() for path in files):
        raise RuntimeError("Delivery blocked: a requested file is missing.")
    binding = manifest.get("qa", {}).get("binding") or {}
    bound_hashes = binding.get("files") or {}
    if binding.get("approved_text_sha256") != approved_hash:
        raise RuntimeError("Delivery blocked: QA is stale for the approved text.")
    if any(bound_hashes.get(str(path)) != sha256(path) for path in files):
        raise RuntimeError("Delivery blocked: an output file changed after QA.")

    delivery_dir = args.delivery_dir.resolve()
    destinations = [delivery_dir / source.name for source in files]
    if len({destination.name.casefold() for destination in destinations}) != len(destinations):
        raise RuntimeError("Delivery blocked: duplicate destination filenames.")
    collisions = [path for path in destinations if path.exists()]
    if collisions and not args.force:
        raise RuntimeError(f"Delivery blocked: file already exists: {collisions[0]}; use --force.")

    delivery_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for source, destination in zip(files, destinations):
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copy2(source, temporary)
            if sha256(temporary) != sha256(source):
                raise RuntimeError(f"Checksum mismatch while staging {source}")
            staged.append((temporary, destination))
        for temporary, destination in staged:
            temporary.replace(destination)
    finally:
        for temporary, _ in staged:
            if temporary.exists():
                temporary.unlink()

    checksums = {destination.name: sha256(destination) for destination in destinations}
    manifest["status"] = "delivered"
    manifest["delivery"] = {
        "directory": str(delivery_dir),
        "delivered_at": utc_now(),
        "checksums": checksums,
    }
    write_json(manifest_path(application_dir), manifest)
    print(json.dumps(manifest["delivery"], indent=2))
    return 0


def command_safety(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    patterns = {
        "Windows user path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.I),
        "Unix user path": re.compile(r"/(?:Users|home)/[^/\s]+"),
        "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "possible phone number": re.compile(
            r"(?<!\w)(?:(?:\+?86[- ]?)?1[3-9]\d{9}|\+\d{1,3}[ -]?(?:\d[ ()-]?){7,14}\d)(?!\d)"
        ),
    }
    extensions = {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".svg"}
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in extensions or ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in patterns.items():
            for match in pattern.finditer(text):
                if match.group(0) not in args.allow:
                    findings.append(f"{path.relative_to(root)}: {label}: {match.group(0)}")
    for finding in findings:
        print(f"FAIL: {finding}")
    if findings:
        return 1
    print("PASS: no obvious personal paths, contacts, or tokens found")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    new = commands.add_parser("new", help="Create an end-to-end application workspace")
    new.add_argument("--company", required=True)
    new.add_argument("--role", required=True)
    new.add_argument("--language", choices=("en", "zh", "bilingual"), default="en")
    new.add_argument("--output-root", type=Path, default=Path("Resume_Output/Applications"))
    new.add_argument("--slug")
    new.set_defaults(func=command_new)

    score = commands.add_parser("score", help="Validate evidence mappings and compute match scores")
    score.add_argument("application_dir", type=Path)
    score.add_argument("--write", action="store_true")
    score.set_defaults(func=command_score)

    approve = commands.add_parser("approve", help="Hash-lock the explicitly approved complete text")
    approve.add_argument("application_dir", type=Path)
    approve.add_argument("--approved-by", default="user-confirmed")
    approve.set_defaults(func=command_approve)

    inspect = commands.add_parser("inspect", help="Check extractable text, keywords, and PDF page count")
    inspect.add_argument("file", type=Path)
    inspect.add_argument("--required", action="append", default=[])
    inspect.add_argument("--forbid", action="append", default=[])
    inspect.add_argument("--max-pages", type=int, default=2)
    inspect.add_argument("--case-sensitive", action="store_true")
    inspect.set_defaults(func=command_inspect)

    qa = commands.add_parser("qa", help="Bind QA results to approved text and output files")
    qa.add_argument("application_dir", type=Path)
    qa.add_argument("--file", type=Path, action="append", required=True)
    for key in QA_KEYS:
        qa.add_argument(f"--{key}", choices=QA_STATES)
    qa.set_defaults(func=command_qa)

    deliver = commands.add_parser("deliver", help="Atomically deliver approved, QA-bound files")
    deliver.add_argument("application_dir", type=Path)
    deliver.add_argument("--file", type=Path, action="append", required=True)
    deliver.add_argument("--delivery-dir", type=Path, default=Path("Resume_Output/Delivery"))
    deliver.add_argument("--force", action="store_true")
    deliver.set_defaults(func=command_deliver)

    safety = commands.add_parser("safety", help="Scan public files for obvious sensitive data")
    safety.add_argument("root", type=Path, nargs="?", default=ROOT)
    safety.add_argument("--allow", action="append", default=[])
    safety.set_defaults(func=command_safety)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
