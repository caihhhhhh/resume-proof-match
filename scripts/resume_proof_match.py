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
import tempfile
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "assets" / "manifest-template.json"
QA_KEYS = ("text", "facts", "pagination", "visual")
QA_STATES = ("pending", "passed", "failed")
# Markers that indicate a text review reads as a complete resume (bilingual).
RESUME_SECTION_MARKERS = (
    "experience", "education", "skills", "summary", "employment",
    "work history", "projects", "certifications",
    "工作经历", "教育背景", "技能", "个人简介", "求职意向", "项目经历",
)
MIN_REVIEW_CHARS = 400
COVER_QA_KEYS = ("text", "facts")
COVER_MIN_CHARS = 300
COVER_GREETINGS = ("hi ", "hi,", "dear ", "hello ", "您好", "你好")
COVER_CLOSINGS = (
    "best regards", "kind regards", "sincerely", "best,", "regards,",
    "此致", "顺颂", "谢谢",
)
WORKSPACE_FORMAT = "resume-proof-match-workspace"
WORKSPACE_FORMAT_VERSION = 1
KEYWORD_DISCLAIMER = "Keyword coverage only; not an ATS pass probability."
KEYWORD_STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have in is it its of on or that the to was were will with you your
    的 和 与 在 对 为 等 及 或 将 被 把 由 这 那 个 一 不 也 都
    """.split()
)
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
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
    (application_dir / "cover-letter.md").write_text(
        "# Cover letter draft\n\nStatus: awaiting complete draft and explicit approval.\n",
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
        confidence = match.get("confidence")
        if confidence is not None and confidence not in ("high", "medium", "low"):
            errors.append(f"{label}.confidence must be one of high, medium, low")
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
    lowered = text.casefold()
    has_section = any(marker in lowered for marker in RESUME_SECTION_MARKERS)
    if (
        len(text) < MIN_REVIEW_CHARS
        or "awaiting complete review" in lowered
        or not has_section
    ):
        raise RuntimeError(
            "Text review is incomplete; replace the placeholder with the complete resume "
            f"(at least {MIN_REVIEW_CHARS} characters and a recognizable resume section)."
        )
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


def inspect_file(
    path: Path,
    required: list[str],
    forbid: list[str],
    max_pages: int | None,
    case_sensitive: bool,
) -> tuple[str, int | None, list[str]]:
    """Shared text/pagination check. Returns (text, pages, failures)."""
    text, pages = extract_text(path)
    haystack = text if case_sensitive else text.casefold()
    failures: list[str] = []
    for value in required:
        needle = value if case_sensitive else value.casefold()
        if needle not in haystack:
            failures.append(f"missing required text: {value}")
    for value in forbid:
        needle = value if case_sensitive else value.casefold()
        if needle in haystack:
            failures.append(f"found forbidden text: {value}")
    if not text.strip():
        failures.append("no extractable text")
    if max_pages is not None and pages is not None and pages > max_pages:
        failures.append(f"page count {pages} exceeds limit {max_pages}")
    return text, pages, failures


def command_inspect(args: argparse.Namespace) -> int:
    path = args.file.resolve()
    if not path.is_file():
        raise RuntimeError(f"File not found: {path}")
    text, pages, failures = inspect_file(
        path, args.required, args.forbid, args.max_pages, args.case_sensitive
    )
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

    paths = [path.resolve() for path in args.file]
    if any(not path.is_file() for path in paths):
        raise RuntimeError("Every --file value must be an existing file.")
    if getattr(args, "from_inspect", False):
        for path in paths:
            _, pages, failures = inspect_file(
                path,
                getattr(args, "required", []),
                getattr(args, "forbid", []),
                getattr(args, "max_pages", None),
                getattr(args, "case_sensitive", False),
            )
            if failures:
                raise RuntimeError(
                    f"from-inspect failed for {path.name}: {'; '.join(failures)}"
                )
            if args.text is None:
                args.text = "passed"
            if args.pagination is None and pages is not None:
                args.pagination = "passed"

    changed = False
    for key in QA_KEYS:
        value = getattr(args, key)
        if value:
            manifest["qa"][key] = value
            changed = True
    if not changed:
        raise RuntimeError("Provide at least one QA result.")
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
    manifest = ensure_cover_track(load_manifest(application_dir))
    _, _, _, matching_errors = validate_matching(application_dir)
    if matching_errors:
        raise RuntimeError("Delivery blocked: matching data is invalid.")

    files = [path.resolve() for path in args.file]
    if not files:
        raise RuntimeError("Provide delivery files with --file.")
    if any(not path.is_file() for path in files):
        raise RuntimeError("Delivery blocked: a requested file is missing.")

    resume_binding = (manifest.get("qa") or {}).get("binding") or {}
    cover_binding = (manifest.get("cover_qa") or {}).get("binding") or {}
    resume_files = resume_binding.get("files") or {}
    cover_files = cover_binding.get("files") or {}
    for path in files:
        key = str(path)
        if key in resume_files:
            try:
                _, approved_hash = verify_approval(application_dir, manifest)
            except RuntimeError as exc:
                raise RuntimeError(f"Delivery blocked: {exc}") from exc
            if resume_binding.get("approved_text_sha256") != approved_hash:
                raise RuntimeError("Delivery blocked: resume QA is stale for the approved text.")
            if resume_files[key] != sha256(path):
                raise RuntimeError("Delivery blocked: an output file changed after QA.")
        elif key in cover_files:
            try:
                _, cover_hash = verify_cover_approval(application_dir, manifest)
            except RuntimeError as exc:
                raise RuntimeError(f"Delivery blocked: {exc}") from exc
            if cover_binding.get("approved_text_sha256") != cover_hash:
                raise RuntimeError("Delivery blocked: cover letter QA is stale for the approved text.")
            if cover_files[key] != sha256(path):
                raise RuntimeError("Delivery blocked: an output file changed after QA.")
        else:
            raise RuntimeError(f"Delivery blocked: file has no QA binding: {path.name}")

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


def alpha_terms(text: str, min_length: int) -> list[str]:
    terms = []
    for token in TOKEN_RE.findall(text):
        if not re.fullmatch(r"[A-Za-z0-9_]+", token):
            continue
        term = token.casefold()
        if len(term) >= min_length and term not in KEYWORD_STOPWORDS:
            terms.append(term)
    return terms


def longest_common_phrases(jd_run: str, haystack: str, max_size: int = 8) -> tuple[list[str], list[str]]:
    """Greedy longest-first common substrings (>=2 chars) between a JD CJK run and
    the resume. No word segmenter needed. Returns (present phrases, uncovered phrases)."""
    work = jd_run
    present: list[str] = []
    for size in range(min(len(work), max_size), 1, -1):
        i = 0
        while i + size <= len(work):
            chunk = work[i : i + size]
            if "\ufffd" not in chunk and chunk in haystack:
                present.append(chunk)
                work = work[:i] + "\ufffd" * size + work[i + size :]
                i += size
            else:
                i += 1
    uncovered = re.findall(r"[\u4e00-\u9fff]{2,}", work)
    return present, uncovered


def collect_keywords(jd: dict, haystack: str, min_length: int) -> list[dict]:
    """Deterministic JD keyword candidates. English: tokens minus stopwords.
    Chinese: longest common phrases with the resume (present) plus the JD phrases
    the resume does not cover (uncovered) — no segmenter required."""
    terms: dict[str, dict] = {}

    def register(term: str, requirement_id: str | None) -> None:
        entry = terms.setdefault(term, {"term": term, "requirement_ids": []})
        if requirement_id and requirement_id not in entry["requirement_ids"]:
            entry["requirement_ids"].append(requirement_id)

    for requirement in jd.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        requirement_id = requirement.get("id")
        source = f"{requirement.get('statement', '')} {requirement.get('source_text', '')}"
        for term in alpha_terms(source, min_length):
            register(term, requirement_id)
        for run in re.findall(r"[\u4e00-\u9fff]{2,}", source):
            present, uncovered = longest_common_phrases(run, haystack)
            for phrase in present + uncovered:
                register(phrase, requirement_id)
    for term, entry in terms.items():
        if re.fullmatch(r"[a-z0-9_]+", term):
            entry["present"] = (
                re.search(r"(?<![a-z0-9_])" + re.escape(term) + r"(?![a-z0-9_])", haystack)
                is not None
            )
        else:
            entry["present"] = term in haystack
    return sorted(terms.values(), key=lambda item: item["term"])


def command_keywords(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = load_manifest(application_dir)
    jd = read_json(workspace_file(application_dir, manifest, "jd_analysis"))
    if not jd.get("requirements"):
        raise RuntimeError("jd-analysis.json needs at least one requirement")
    if args.resume:
        resume_path = Path(args.resume).resolve()
    else:
        resume_path = workspace_file(application_dir, manifest, "text_review")
    if not resume_path.is_file():
        raise RuntimeError(f"Resume file not found: {resume_path}")
    text, _ = extract_text(resume_path)
    haystack = text.casefold()
    if not haystack.strip():
        raise RuntimeError("Resume file has no extractable text")

    keywords = collect_keywords(jd, haystack, args.min_length)
    present = [keyword for keyword in keywords if keyword["present"]]
    missing = [keyword for keyword in keywords if not keyword["present"]]
    by_requirement: dict[str, dict[str, list[str]]] = {}
    for keyword in keywords:
        for requirement_id in keyword["requirement_ids"]:
            bucket = by_requirement.setdefault(requirement_id, {"present": [], "missing": []})
            bucket["present" if keyword["present"] else "missing"].append(keyword["term"])
    result = {
        "resume": str(resume_path),
        "keywords_total": len(keywords),
        "keywords_present": [item["term"] for item in present],
        "keywords_missing": [item["term"] for item in missing],
        "coverage": round(len(present) / len(keywords), 3) if keywords else 0.0,
        "by_requirement": by_requirement,
        "disclaimer": KEYWORD_DISCLAIMER,
    }
    if args.write:
        report_path = workspace_file(application_dir, manifest, "match_report")
        report = read_json(report_path)
        report["keyword_coverage"] = result
        write_json(report_path, report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


RECOMMENDATION_RANK = {"apply": 0, "consider": 1, "low priority": 2}
COMPARE_DISCLAIMER = "Ranking is a decision aid only; not an ATS pass probability."


def summarize_application(application_dir: Path) -> dict:
    summary: dict = {"application_dir": str(application_dir), "slug": application_dir.name}
    try:
        manifest = load_manifest(application_dir)
    except RuntimeError as exc:
        summary.update(ok=False, errors=[str(exc)])
        return summary
    jd, ledger, report, errors = validate_matching(application_dir)
    application = manifest.get("application") or {}
    summary.update(
        company=application.get("company"),
        role=application.get("role"),
        status=manifest.get("status"),
        ok=not errors,
        errors=errors,
    )
    if errors:
        return summary
    scores = calculate_scores(jd, ledger, report)
    keyword_coverage = report.get("keyword_coverage") or {}
    summary.update(
        role_fit=scores["role_fit"],
        evidence_coverage=scores["evidence_coverage"],
        document_readiness=scores["document_readiness"],
        band=scores["band"],
        recommendation=scores["recommendation"],
        must_have_gaps=scores["unsupported_must_have"],
        conflicts=scores["conflicts"],
        keyword_coverage=keyword_coverage.get("coverage"),
        outcome=(manifest.get("outcome") or {}).get("status"),
    )
    return summary


def render_compare_table(ranked: list[dict], invalid: list[dict]) -> str:
    lines = [
        f"{'Rank':<4} {'Application':<28} {'Fit':>3} {'Evid':>4} {'Doc':>3} "
        f"{'Band':<7} {'Recommendation':<12} {'Gaps':>4} {'Flags':<8} {'Outcome':<9} {'Status':<9}",
        "-" * 106,
    ]
    for rank, summary in enumerate(ranked, 1):
        flags = "conflict" if summary["conflicts"] else ""
        lines.append(
            f"{rank:<4} {summary['slug'][:28]:<28} {summary['role_fit']:>3} "
            f"{summary['evidence_coverage']:>4} {summary['document_readiness']:>3} "
            f"{summary['band']:<7} {summary['recommendation']:<12} "
            f"{len(summary['must_have_gaps']):>4} {flags:<8} "
            f"{summary.get('outcome') or '-':<9} {summary['status'] or '-':<9}"
        )
    for summary in invalid:
        lines.append(
            f"{'-':<4} {summary['slug'][:28]:<28} {'invalid: ' + '; '.join(summary['errors'])[:58]}"
        )
    return "\n".join(lines)


def command_compare(args: argparse.Namespace) -> int:
    raw = [Path(item).resolve() for item in args.application_dirs]
    if len(raw) < 2:
        raise RuntimeError("compare needs at least two application directories")
    if len({str(path) for path in raw}) != len(raw):
        raise RuntimeError("compare needs distinct application directories")
    summaries = [summarize_application(path) for path in raw]
    ranked = sorted(
        (item for item in summaries if item["ok"]),
        key=lambda item: (
            RECOMMENDATION_RANK[item["recommendation"]],
            -item["role_fit"],
            -item["evidence_coverage"],
        ),
    )
    invalid = [item for item in summaries if not item["ok"]]
    result = {
        "ranking": [item["slug"] for item in ranked],
        "applications": summaries,
        "disclaimer": COMPARE_DISCLAIMER,
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_compare_table(ranked, invalid))
        print(f"\n{COMPARE_DISCLAIMER}")
    return 0


def ensure_cover_track(manifest: dict) -> dict:
    """Fill cover-letter track defaults for manifests created before it existed."""
    manifest.setdefault("files", {}).setdefault("cover_letter", "cover-letter.md")
    manifest.setdefault("cover_approval", None)
    cover_qa = manifest.setdefault("cover_qa", {})
    cover_qa.setdefault("text", "pending")
    cover_qa.setdefault("facts", "pending")
    cover_qa.setdefault("binding", None)
    manifest.setdefault("cover_status", "draft")
    return manifest


def verify_cover_approval(application_dir: Path, manifest: dict) -> tuple[Path, str]:
    cover_path = application_dir / manifest["files"]["cover_letter"]
    approval = manifest.get("cover_approval") or {}
    approved_hash = approval.get("approved_text_sha256")
    if not cover_path.is_file() or sha256(cover_path) != approved_hash:
        raise RuntimeError("Approved cover letter changed; obtain approval again.")
    if approval.get("matching_sha256") != matching_hashes(application_dir, manifest):
        raise RuntimeError("Matching evidence changed; review the cover letter and approve again.")
    return cover_path, approved_hash


def command_cover_approve(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = ensure_cover_track(load_manifest(application_dir))
    _, _, _, errors = validate_matching(application_dir)
    if errors:
        raise RuntimeError("Matching data is invalid; run score and fix its failures before approval.")
    cover_path = application_dir / manifest["files"]["cover_letter"]
    if not cover_path.is_file():
        raise RuntimeError(f"Cover letter not found: {cover_path}; draft it first.")
    letter = cover_path.read_text(encoding="utf-8").strip()
    lowered = letter.casefold()
    if (
        len(letter) < COVER_MIN_CHARS
        or not any(mark in lowered for mark in COVER_GREETINGS)
        or not any(mark in lowered for mark in COVER_CLOSINGS)
    ):
        raise RuntimeError(
            "Cover letter is incomplete; it needs a greeting, a closing, and "
            f"at least {COVER_MIN_CHARS} characters of real content."
        )
    manifest["cover_status"] = "approved"
    manifest["cover_approval"] = {
        "approved_at": utc_now(),
        "approved_by": args.approved_by,
        "approved_text_sha256": sha256(cover_path),
        "matching_sha256": matching_hashes(application_dir, manifest),
    }
    manifest["cover_qa"] = {key: "pending" for key in COVER_QA_KEYS} | {"binding": None}
    write_json(manifest_path(application_dir), manifest)
    print(f"COVER APPROVED {cover_path}")
    return 0


def command_cover_qa(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = ensure_cover_track(load_manifest(application_dir))
    if manifest.get("cover_status") not in {"approved", "cover-qa-passed"}:
        raise RuntimeError("Approve the cover letter before recording QA.")
    _, approved_hash = verify_cover_approval(application_dir, manifest)

    changed = False
    for key in COVER_QA_KEYS:
        value = getattr(args, key)
        if value:
            manifest["cover_qa"][key] = value
            changed = True
    if not changed:
        raise RuntimeError("Provide at least one QA result.")
    paths = [path.resolve() for path in args.file]
    if any(not path.is_file() for path in paths):
        raise RuntimeError("Every --file value must be an existing file.")
    manifest["cover_qa"]["binding"] = {
        "approved_text_sha256": approved_hash,
        "files": output_hashes(paths),
        "recorded_at": utc_now(),
    }
    if all(manifest["cover_qa"].get(key) == "passed" for key in COVER_QA_KEYS):
        manifest["cover_status"] = "cover-qa-passed"
    write_json(manifest_path(application_dir), manifest)
    print(json.dumps(manifest["cover_qa"], indent=2))
    return 0


def command_export(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = load_manifest(application_dir)
    entries: list[tuple[str, Path]] = [("manifest.json", manifest_path(application_dir))]
    for name in (manifest.get("files") or {}).values():
        path = application_dir / name
        if path.is_file():
            entries.append((name, path))
    if len(entries) <= 1:
        raise RuntimeError("Nothing to export: the workspace has no files.")
    output = Path(args.output).resolve() if args.output else Path.cwd() / f"{application_dir.name}.zip"
    if output.exists() and not args.force:
        raise RuntimeError(f"Export blocked: {output} already exists; use --force.")
    meta = {
        "format": WORKSPACE_FORMAT,
        "version": WORKSPACE_FORMAT_VERSION,
        "exported_at": utc_now(),
        "application": manifest.get("application"),
    }
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("export.json", json.dumps(meta, ensure_ascii=False, indent=2))
        for name, path in entries:
            archive.write(path, arcname=name)
    print(str(output))
    return 0


def command_import(args: argparse.Namespace) -> int:
    archive_path = Path(args.archive).resolve()
    if not archive_path.is_file():
        raise RuntimeError(f"Archive not found: {archive_path}")
    if not zipfile.is_zipfile(archive_path):
        raise RuntimeError("Import blocked: not a zip archive.")
    root = args.output_root.resolve()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                if not str((tmpdir / member).resolve()).startswith(str(tmpdir)):
                    raise RuntimeError("Import blocked: unsafe paths in archive.")
            archive.extractall(tmpdir)
        meta_path = tmpdir / "export.json"
        if not meta_path.is_file():
            raise RuntimeError("Import blocked: not a ResumeProof workspace archive.")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("format") != WORKSPACE_FORMAT:
            raise RuntimeError("Import blocked: unknown workspace format.")
        if meta.get("version") != WORKSPACE_FORMAT_VERSION:
            raise RuntimeError(
                f"Import blocked: unsupported workspace version {meta.get('version')}."
            )
        manifest_file = tmpdir / "manifest.json"
        if not manifest_file.is_file():
            raise RuntimeError("Import blocked: manifest.json missing from archive.")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        missing = [
            name
            for name in (manifest.get("files") or {}).values()
            if not (tmpdir / name).is_file()
        ]
        if missing:
            raise RuntimeError(f"Import blocked: archive is missing files: {', '.join(missing)}.")
        slug = args.slug or safe_name(archive_path.stem)
        dest = root / slug
        if dest.exists():
            if not args.force:
                raise RuntimeError(
                    f"Import blocked: {dest} already exists; use --force or --slug."
                )
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        for item in tmpdir.iterdir():
            if item.name == "export.json":
                continue
            shutil.copy2(item, dest / item.name)
    _, _, _, errors = validate_matching(dest)
    print(str(dest))
    for error in errors:
        print(f"WARNING: {error}")
    return 0


def _lower_first(value: str) -> str:
    value = value.strip().rstrip(".")
    return value[:1].lower() + value[1:] if value else value


def command_interview(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = load_manifest(application_dir)
    jd, ledger, report, errors = validate_matching(application_dir)
    if errors:
        raise RuntimeError("Matching data is invalid; run score and fix its failures first.")
    application = manifest.get("application") or {}
    company = application.get("company") or "the company"
    role = application.get("role") or "the role"

    claim_map = {claim["id"]: claim for claim in ledger.get("claims", [])}

    def weight(requirement: dict) -> int:
        return requirement.get("importance", 1) * (
            2 if requirement.get("type") == "must-have" else 1
        )

    req_map = {req["id"]: req for req in jd.get("requirements", [])}
    matches = sorted(
        report.get("matches", []),
        key=lambda m: weight(req_map.get(m.get("requirement_id"), {})),
        reverse=True,
    )
    lines = [
        f"# Interview prep — {role} @ {company}",
        "",
        "_Generated from your evidence ledger. Every answer bullet traces to a claim ID; "
        "do not invent beyond them._",
        "",
        "## Behavioral questions (answer from confirmed evidence)",
        "",
    ]
    number = 0
    for match in matches:
        if match.get("status") != "supported":
            continue
        req = req_map.get(match.get("requirement_id"), {})
        confirmed = [
            claim_map[cid]
            for cid in match.get("claim_ids", [])
            if claim_map.get(cid, {}).get("status") == "confirmed"
        ]
        if not confirmed:
            continue
        number += 1
        lines.append(f"### {number}. \"Tell me about a time you {_lower_first(req.get('statement', ''))}.\"")
        lines.append(
            f"- Requirement: `{req.get('id')}` ({req.get('type')}, importance {req.get('importance')})"
        )
        for claim in confirmed:
            lines.append(
                f"- Evidence `{claim['id']}`: {claim.get('statement')} _(source: {claim.get('source')})_"
            )
        lines.append("- Talk track: Situation → Task → Action → Result, using only the evidence above.")
        lines.append("")
    if number == 0:
        lines.append("_No supported requirements yet — confirm more evidence first._")
        lines.append("")

    lines.append("## Likely questions on gaps (name the gap, bridge with transferables)")
    lines.append("")
    gap_number = 0
    for match in matches:
        req = req_map.get(match.get("requirement_id"), {})
        if req.get("type") == "must-have" and match.get("status") == "unsupported":
            gap_number += 1
            lines.append(
                f"### {gap_number}. \"How would you handle {_lower_first(req.get('statement', ''))} "
                f"with limited direct experience?\""
            )
            lines.append(f"- Gap: `{req.get('id')}` (must-have, importance {req.get('importance')})")
            lines.append(
                "- Honest framing: name the gap in one sentence, then bridge with the closest "
                "transferable evidence you actually have."
            )
            lines.append("")
    if gap_number == 0:
        lines.append("_No unsupported must-haves. Nice._")
        lines.append("")

    lines.append("## Clarifications to prepare (needs-confirmation claims)")
    lines.append("")
    pending = [
        claim
        for claim in ledger.get("claims", [])
        if claim.get("status") == "needs-confirmation"
    ]
    if pending:
        for claim in pending:
            lines.append(f"- `{claim['id']}`: {claim.get('statement')} — nail this down before the interview.")
    else:
        lines.append("_Nothing pending._")
    lines.append("")
    lines.append("## Questions to ask them")
    lines.append("")
    lines.append("- What does success look like in the first 90 days for this role?")
    lines.append("- What is the biggest challenge facing the team right now?")
    lines.append("- How is performance measured for this position?")
    lines.append("")
    document = "\n".join(lines)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(document, encoding="utf-8")
        print(str(output.resolve()))
    else:
        print(document)
    return 0


def command_status(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = ensure_cover_track(load_manifest(application_dir))
    application = manifest.get("application") or {}
    jd, ledger, report, errors = validate_matching(application_dir)
    status = {
        "slug": application_dir.name,
        "company": application.get("company"),
        "role": application.get("role"),
        "language": application.get("language"),
        "status": manifest.get("status"),
        "cover_status": manifest.get("cover_status"),
        "approval": bool((manifest.get("approval") or {}).get("approved_text_sha256")),
        "cover_approval": bool((manifest.get("cover_approval") or {}).get("approved_text_sha256")),
        "qa": {key: (manifest.get("qa") or {}).get(key) for key in QA_KEYS},
        "cover_qa": {key: (manifest.get("cover_qa") or {}).get(key) for key in COVER_QA_KEYS},
        "outcome": manifest.get("outcome"),
        "matching_valid": not errors,
        "matching_errors": errors,
        "scores": None,
    }
    if not errors:
        status["scores"] = calculate_scores(jd, ledger, report)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def command_extract(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    if not path.is_file():
        raise RuntimeError(f"File not found: {path}")
    text, pages = extract_text(path)
    if not text.strip():
        raise RuntimeError("No extractable text found.")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(str(output.resolve()))
    else:
        print(text)
    return 0


OUTCOME_STATUSES = ("applied", "rejected", "ghosted", "interview", "offer", "withdrawn")


def command_outcome(args: argparse.Namespace) -> int:
    application_dir = args.application_dir.resolve()
    manifest = ensure_cover_track(load_manifest(application_dir))
    entry = {
        "status": args.status,
        "date": args.date or utc_now()[:10],
        "note": args.note or "",
        "updated_at": utc_now(),
    }
    manifest["outcome"] = entry
    history = manifest.setdefault("outcome_history", [])
    history.append(entry)
    write_json(manifest_path(application_dir), manifest)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
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
    qa.add_argument(
        "--from-inspect",
        action="store_true",
        help="Run the inspect checks on each file and record text/pagination from the result",
    )
    qa.add_argument("--required", action="append", default=[])
    qa.add_argument("--forbid", action="append", default=[])
    qa.add_argument("--max-pages", type=int, default=None)
    qa.add_argument("--case-sensitive", action="store_true")
    qa.set_defaults(func=command_qa)

    deliver = commands.add_parser("deliver", help="Atomically deliver approved, QA-bound files")
    deliver.add_argument("application_dir", type=Path)
    deliver.add_argument("--file", type=Path, action="append", required=True)
    deliver.add_argument("--delivery-dir", type=Path, default=Path("Resume_Output/Delivery"))
    deliver.add_argument("--force", action="store_true")
    deliver.set_defaults(func=command_deliver)

    keywords = commands.add_parser("keywords", help="Check JD keyword coverage in a resume file")
    keywords.add_argument("application_dir", type=Path)
    keywords.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Resume file to check; defaults to the approved text review",
    )
    keywords.add_argument("--min-length", type=int, default=3)
    keywords.add_argument(
        "--write", action="store_true", help="Persist coverage into match-report.json"
    )
    keywords.set_defaults(func=command_keywords)

    compare = commands.add_parser("compare", help="Rank multiple applications by fit signals")
    compare.add_argument("application_dirs", nargs="+")
    compare.add_argument("--format", choices=("table", "json"), default="table")
    compare.add_argument("--output", type=Path, default=None)
    compare.set_defaults(func=command_compare)

    cover_approve = commands.add_parser("cover-approve", help="Hash-lock the approved cover letter")
    cover_approve.add_argument("application_dir", type=Path)
    cover_approve.add_argument("--approved-by", default="user-confirmed")
    cover_approve.set_defaults(func=command_cover_approve)

    cover_qa = commands.add_parser("cover-qa", help="Bind cover letter QA to approved text and files")
    cover_qa.add_argument("application_dir", type=Path)
    cover_qa.add_argument("--file", type=Path, action="append", required=True)
    for key in COVER_QA_KEYS:
        cover_qa.add_argument(f"--{key}", choices=QA_STATES)
    cover_qa.set_defaults(func=command_cover_qa)

    export = commands.add_parser("export", help="Pack a workspace into a portable zip archive")
    export.add_argument("application_dir", type=Path)
    export.add_argument("--output", type=Path, default=None)
    export.add_argument("--force", action="store_true")
    export.set_defaults(func=command_export)

    import_cmd = commands.add_parser("import", help="Restore a workspace from an exported archive")
    import_cmd.add_argument("archive", type=Path)
    import_cmd.add_argument("--output-root", type=Path, default=Path("Resume_Output/Applications"))
    import_cmd.add_argument("--slug")
    import_cmd.add_argument("--force", action="store_true")
    import_cmd.set_defaults(func=command_import)

    interview = commands.add_parser("interview", help="Generate interview prep from the evidence ledger")
    interview.add_argument("application_dir", type=Path)
    interview.add_argument("--output", type=Path, default=None)
    interview.set_defaults(func=command_interview)

    status = commands.add_parser("status", help="Show the full state of an application workspace")
    status.add_argument("application_dir", type=Path)
    status.set_defaults(func=command_status)

    extract = commands.add_parser("extract", help="Extract text from a resume file (PDF/HTML/TXT)")
    extract.add_argument("file", type=Path)
    extract.add_argument("--output", type=Path, default=None)
    extract.set_defaults(func=command_extract)

    outcome = commands.add_parser("outcome", help="Record what happened after delivery")
    outcome.add_argument("application_dir", type=Path)
    outcome.add_argument("--status", choices=OUTCOME_STATUSES, required=True)
    outcome.add_argument("--note", default="")
    outcome.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to today")
    outcome.set_defaults(func=command_outcome)

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
