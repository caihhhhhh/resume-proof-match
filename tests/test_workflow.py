from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "resume_proof_match", ROOT / "scripts" / "resume_proof_match.py"
)
assert SPEC and SPEC.loader
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


class WorkflowTest(unittest.TestCase):
    def create_application(self, root: Path, slug: str = "sample") -> Path:
        workflow.command_new(
            Namespace(
                company="Example Co",
                role="Growth Analyst",
                language="en",
                output_root=root,
                slug=slug,
            )
        )
        application = root / slug
        (application / "jd-analysis.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "job": {"company": "Example Co", "role": "Growth Analyst", "language": "en"},
                    "requirements": [
                        {
                            "id": "req-001",
                            "type": "must-have",
                            "category": "experience",
                            "importance": 5,
                            "statement": "Own campaign analysis",
                            "source_text": "Analyze campaign performance and identify trends.",
                        },
                        {
                            "id": "req-002",
                            "type": "nice-to-have",
                            "category": "skill",
                            "importance": 2,
                            "statement": "Use SQL",
                            "source_text": "SQL or data querying knowledge.",
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (application / "evidence-ledger.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "claims": [
                        {
                            "id": "claim-001",
                            "statement": "Analyzed campaign performance and adjusted tests.",
                            "source": "base-resume.md#experience",
                            "status": "confirmed",
                            "caveat": None,
                        },
                        {
                            "id": "claim-002",
                            "statement": "May have used SQL for analysis.",
                            "source": "user clarification required",
                            "status": "needs-confirmation",
                            "caveat": "Depth is not confirmed.",
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (application / "match-report.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "matches": [
                        {
                            "requirement_id": "req-001",
                            "status": "supported",
                            "claim_ids": ["claim-001"],
                            "confidence": "high",
                            "explanation": "Direct campaign analysis evidence.",
                        },
                        {
                            "requirement_id": "req-002",
                            "status": "needs-confirmation",
                            "claim_ids": ["claim-002"],
                            "confidence": "low",
                            "explanation": "Tool depth needs confirmation.",
                        },
                    ],
                    "document_readiness": {
                        "structure": 80,
                        "clarity": 80,
                        "keyword_expression": 60,
                        "extractability": 80,
                    },
                    "scores": None,
                    "quick_wins": [],
                    "disclaimer": "Decision aid only; not an ATS pass probability.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return application

    def test_scoring_is_deterministic_and_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            jd, ledger, report, errors = workflow.validate_matching(application)
            self.assertEqual(errors, [])
            scores = workflow.calculate_scores(jd, ledger, report)
            self.assertEqual(scores["role_fit"], 92)
            self.assertEqual(scores["evidence_coverage"], 92)
            self.assertEqual(scores["document_readiness"], 75)
            self.assertEqual(scores["band"], "Strong")

    def test_supported_match_requires_confirmed_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            report_path = application / "match-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["matches"][0]["claim_ids"] = ["claim-002"]
            report_path.write_text(json.dumps(report), encoding="utf-8")
            _, _, _, errors = workflow.validate_matching(application)
            self.assertTrue(any("supported match needs a confirmed claim" in item for item in errors))

    def test_approval_qa_and_stale_output_guards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                workflow.command_approve(
                    Namespace(application_dir=application, approved_by="user-confirmed")
                )

            review = application / "text-review.md"
            review.write_text(
                "# Complete resume\n\n## Experience\n\n"
                + "Growth analyst who uses confirmed campaign evidence to make clear decisions. " * 6,
                encoding="utf-8",
            )
            workflow.command_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            output = application / "resume.pdf"
            output.write_bytes(b"%PDF-1.4\nverified example\n")
            workflow.command_qa(
                Namespace(
                    application_dir=application,
                    file=[output],
                    text="passed",
                    facts="passed",
                    pagination="passed",
                    visual="passed",
                )
            )
            output.write_bytes(output.read_bytes() + b"changed")
            with self.assertRaisesRegex(RuntimeError, "changed after QA"):
                workflow.command_deliver(
                    Namespace(
                        application_dir=application,
                        file=[output],
                        delivery_dir=root / "delivery",
                        force=False,
                    )
                )

    def test_collision_is_checked_before_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            review = application / "text-review.md"
            review.write_text(
                "# Complete resume\n\n## Experience\n\n" + "Evidence-backed result. " * 20,
                encoding="utf-8",
            )
            workflow.command_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            first = application / "resume.pdf"
            second = application / "resume.docx"
            first.write_bytes(b"pdf")
            second.write_bytes(b"docx")
            workflow.command_qa(
                Namespace(
                    application_dir=application,
                    file=[first, second],
                    text="passed",
                    facts="passed",
                    pagination="passed",
                    visual="passed",
                )
            )
            delivery = root / "delivery"
            delivery.mkdir()
            (delivery / second.name).write_bytes(b"existing")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                workflow.command_deliver(
                    Namespace(
                        application_dir=application,
                        file=[first, second],
                        delivery_dir=delivery,
                        force=False,
                    )
                )
            self.assertFalse((delivery / first.name).exists())

    def test_evidence_change_invalidates_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            review = application / "text-review.md"
            review.write_text(
                "# Complete resume\n\n## Experience\n\n" + "Evidence-backed result. " * 20,
                encoding="utf-8",
            )
            workflow.command_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            ledger = application / "evidence-ledger.json"
            value = json.loads(ledger.read_text(encoding="utf-8"))
            value["claims"][0]["statement"] = "Materially changed evidence."
            ledger.write_text(json.dumps(value), encoding="utf-8")
            output = application / "resume.pdf"
            output.write_bytes(b"pdf")
            with self.assertRaisesRegex(RuntimeError, "Matching evidence changed"):
                workflow.command_qa(
                    Namespace(
                        application_dir=application,
                        file=[output],
                        text="passed",
                        facts="passed",
                        pagination="passed",
                        visual="passed",
                    )
                )

    def test_confidence_must_be_valid_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            report_path = application / "match-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["matches"][0]["confidence"] = "extreme"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            _, _, _, errors = workflow.validate_matching(application)
            self.assertTrue(any("confidence" in item for item in errors))
            report["matches"][0]["confidence"] = "medium"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            _, _, _, errors = workflow.validate_matching(application)
            self.assertEqual(errors, [])

    def test_keywords_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            resume = root / "resume.txt"
            resume.write_text(
                "I analyze campaign performance and run Meta ads tests.",
                encoding="utf-8",
            )
            result = workflow.command_keywords(
                Namespace(
                    application_dir=application,
                    resume=resume,
                    min_length=3,
                    write=True,
                )
            )
            self.assertEqual(result, 0)
            report = json.loads((application / "match-report.json").read_text(encoding="utf-8"))
            coverage = report["keyword_coverage"]
            self.assertIn("campaign", coverage["keywords_present"])
            self.assertIn("performance", coverage["keywords_present"])
            self.assertIn("sql", coverage["keywords_missing"])
            self.assertEqual(
                coverage["coverage"],
                round(
                    len(coverage["keywords_present"]) / coverage["keywords_total"], 3
                ),
            )
            self.assertIn("not an ATS pass probability", coverage["disclaimer"])
            self.assertIn("req-001", coverage["by_requirement"])

    def test_keywords_chinese_phrase_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            jd_path = application / "jd-analysis.json"
            jd = json.loads(jd_path.read_text(encoding="utf-8"))
            jd["requirements"] = [
                {
                    "id": "req-zh-1",
                    "type": "must-have",
                    "category": "skill",
                    "importance": 5,
                    "statement": "负责信息流广告投放优化",
                    "source_text": "3年以上信息流投放经验，熟悉巨量引擎",
                },
            ]
            jd_path.write_text(json.dumps(jd, ensure_ascii=False), encoding="utf-8")
            resume = root / "resume.txt"
            resume.write_text(
                "3年信息流投放经验，负责巨量引擎账户优化。", encoding="utf-8"
            )
            keywords = {
                item["term"]: item
                for item in workflow.collect_keywords(
                    jd, resume.read_text(encoding="utf-8").casefold(), 3
                )
            }
            self.assertTrue(keywords["信息流"]["present"])
            self.assertTrue(keywords["投放"]["present"])
            self.assertTrue(keywords["巨量引擎"]["present"])
            self.assertFalse(keywords["广告"]["present"])
            self.assertFalse(keywords["熟悉"]["present"])

    def make_scored_application(self, root: Path, slug: str, strong: bool) -> Path:
        application = self.create_application(root, slug=slug)
        report_path = application / "match-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not strong:
            report["matches"][0]["status"] = "unsupported"
            report["matches"][0]["claim_ids"] = []
            report["matches"][1]["status"] = "unsupported"
            report["matches"][1]["claim_ids"] = []
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return application

    def test_compare_ranks_applications(self) -> None:
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            weak = self.make_scored_application(root, "weak-app", strong=False)
            strong = self.make_scored_application(root, "strong-app", strong=True)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                result = workflow.command_compare(
                    Namespace(
                        application_dirs=[str(weak), str(strong)],
                        format="json",
                        output=None,
                    )
                )
            self.assertEqual(result, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["ranking"], ["strong-app", "weak-app"])
            by_slug = {item["slug"]: item for item in payload["applications"]}
            self.assertEqual(by_slug["strong-app"]["recommendation"], "apply")
            self.assertEqual(by_slug["weak-app"]["recommendation"], "low priority")
            self.assertIn("not an ATS pass probability", payload["disclaimer"])

    def test_compare_rejects_single_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            with self.assertRaisesRegex(RuntimeError, "at least two"):
                workflow.command_compare(
                    Namespace(
                        application_dirs=[str(application)],
                        format="table",
                        output=None,
                    )
                )

    cover_letter_text = (
        "Hi Example Co team,\n\n"
        "I run paid social campaign analysis end to end, from creative testing through "
        "budget decisions, and I use SQL for ad-hoc data queries when dashboards are not "
        "enough. My recent work lifted test velocity while keeping reporting honest about "
        "what the data actually supports.\n\n"
        "I would love to bring the same evidence-first habit to your growth team and keep "
        "every claim traceable to its source.\n\n"
        "Best regards,\nAlex Rivera\n"
    )

    def test_cover_letter_approve_qa_deliver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            letter = application / "cover-letter.md"
            letter.write_text(self.cover_letter_text, encoding="utf-8")
            workflow.command_cover_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            manifest = json.loads((application / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["cover_status"], "approved")
            self.assertIsNotNone(manifest["cover_approval"]["approved_text_sha256"])

            cover_file = application / "cover-letter.txt"
            cover_file.write_text(self.cover_letter_text, encoding="utf-8")
            workflow.command_cover_qa(
                Namespace(
                    application_dir=application,
                    file=[cover_file],
                    text="passed",
                    facts="passed",
                )
            )
            manifest = json.loads((application / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["cover_status"], "cover-qa-passed")

            delivery = root / "delivery"
            workflow.command_cover_qa  # noqa - keep linters calm about ordering
            workflow.command_deliver(
                Namespace(
                    application_dir=application,
                    file=[cover_file],
                    delivery_dir=delivery,
                    force=False,
                )
            )
            self.assertTrue((delivery / "cover-letter.txt").is_file())

    def test_cover_approve_rejects_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            (application / "cover-letter.md").write_text("Hi! Hire me.", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                workflow.command_cover_approve(
                    Namespace(application_dir=application, approved_by="user-confirmed")
                )

    def test_cover_approve_backfills_old_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            manifest_path = application / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for key in ("cover_approval", "cover_qa", "cover_status"):
                manifest.pop(key, None)
            manifest["files"].pop("cover_letter", None)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (application / "cover-letter.md").write_text(
                self.cover_letter_text, encoding="utf-8"
            )
            workflow.command_cover_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["cover_status"], "approved")

    def test_cover_change_invalidates_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            letter = application / "cover-letter.md"
            letter.write_text(self.cover_letter_text, encoding="utf-8")
            workflow.command_cover_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            letter.write_text(letter.read_text(encoding="utf-8") + "\nP.S. Edited.\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                workflow.command_cover_qa(
                    Namespace(
                        application_dir=application,
                        file=[application / "cover-letter.txt"],
                        text="passed",
                        facts="passed",
                    )
                )

    def test_export_import_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            archive = root / "demo.zip"
            result = workflow.command_export(
                Namespace(application_dir=application, output=archive, force=False)
            )
            self.assertEqual(result, 0)
            self.assertTrue(archive.is_file())
            restored_root = root / "restored"
            result = workflow.command_import(
                Namespace(
                    archive=archive,
                    output_root=restored_root,
                    slug="demo2",
                    force=False,
                )
            )
            self.assertEqual(result, 0)
            restored = restored_root / "demo2"
            for name in ("manifest.json", "jd-analysis.json", "evidence-ledger.json",
                         "match-report.json", "text-review.md", "cover-letter.md"):
                self.assertEqual(
                    (application / name).read_bytes(),
                    (restored / name).read_bytes(),
                    f"roundtrip mismatch: {name}",
                )

    def test_import_rejects_non_workspace_archive(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "plain.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("hello.txt", "not a workspace")
            with self.assertRaisesRegex(RuntimeError, "not a ResumeProof workspace"):
                workflow.command_import(
                    Namespace(
                        archive=archive,
                        output_root=root / "out",
                        slug=None,
                        force=False,
                    )
                )

    def test_import_collision_needs_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            archive = root / "demo.zip"
            workflow.command_export(
                Namespace(application_dir=application, output=archive, force=False)
            )
            args = Namespace(
                archive=archive, output_root=root / "out", slug="demo", force=False
            )
            workflow.command_import(args)  # first import ok
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                workflow.command_import(args)  # second needs --force
            args.force = True
            workflow.command_import(args)
            self.assertTrue((root / "out" / "demo" / "manifest.json").is_file())

    def test_interview_generates_prep(self) -> None:
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                result = workflow.command_interview(
                    Namespace(application_dir=application, output=None)
                )
            self.assertEqual(result, 0)
            document = buffer.getvalue()
            self.assertIn("Tell me about a time", document)
            self.assertIn("claim-001", document)
            self.assertIn("needs-confirmation", document)
            self.assertIn("Questions to ask them", document)

    def test_status_reports_full_state(self) -> None:
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                result = workflow.command_status(Namespace(application_dir=application))
            self.assertEqual(result, 0)
            state = json.loads(buffer.getvalue())
            self.assertEqual(state["slug"], "sample")
            self.assertFalse(state["approval"])
            self.assertEqual(state["qa"]["text"], "pending")
            self.assertTrue(state["matching_valid"])
            self.assertEqual(state["scores"]["band"], "Strong")
            self.assertIsNone(state["outcome"])

    def test_extract_writes_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "resume.txt"
            source.write_text("Campaign analysis and testing.", encoding="utf-8")
            output = root / "out.txt"
            result = workflow.command_extract(Namespace(file=source, output=output))
            self.assertEqual(result, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "Campaign analysis and testing.")

    def test_qa_from_inspect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            review = application / "text-review.md"
            review.write_text(
                "# Complete resume\n\n## Experience\n\n"
                + "Growth analyst who uses confirmed campaign evidence to make clear decisions. " * 6,
                encoding="utf-8",
            )
            workflow.command_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            output = application / "resume.txt"
            output.write_text("Growth analyst with campaign evidence.", encoding="utf-8")
            workflow.command_qa(
                Namespace(
                    application_dir=application,
                    file=[output],
                    text=None,
                    facts="passed",
                    pagination=None,
                    visual="passed",
                    from_inspect=True,
                    required=["campaign"],
                    forbid=["placeholder"],
                    max_pages=None,
                    case_sensitive=False,
                )
            )
            manifest = json.loads((application / "manifest.json").read_text(encoding="utf-8"))
            # text comes from inspect; pagination stays pending for txt (no page count)
            self.assertEqual(manifest["qa"]["text"], "passed")
            self.assertEqual(manifest["qa"]["facts"], "passed")
            self.assertEqual(manifest["qa"]["pagination"], "pending")

    def test_qa_from_inspect_fails_on_missing_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = self.create_application(root)
            review = application / "text-review.md"
            review.write_text(
                "# Complete resume\n\n## Experience\n\n"
                + "Growth analyst who uses confirmed campaign evidence to make clear decisions. " * 6,
                encoding="utf-8",
            )
            workflow.command_approve(
                Namespace(application_dir=application, approved_by="user-confirmed")
            )
            output = application / "resume.txt"
            output.write_text("Nothing relevant here.", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "from-inspect failed"):
                workflow.command_qa(
                    Namespace(
                        application_dir=application,
                        file=[output],
                        text=None,
                        facts="passed",
                        pagination=None,
                        visual="passed",
                        from_inspect=True,
                        required=["campaign"],
                        forbid=[],
                        max_pages=None,
                        case_sensitive=False,
                    )
                )

    def test_outcome_records_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            application = self.create_application(Path(temporary))
            workflow.command_outcome(
                Namespace(
                    application_dir=application,
                    status="applied",
                    note="via Greenhouse",
                    date="2026-10-10",
                )
            )
            workflow.command_outcome(
                Namespace(
                    application_dir=application,
                    status="rejected",
                    note="",
                    date="2026-10-11",
                )
            )
            manifest = json.loads((application / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["outcome"]["status"], "rejected")
            self.assertEqual(len(manifest["outcome_history"]), 2)
            self.assertEqual(manifest["outcome_history"][0]["status"], "applied")

    def test_inspect_plain_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "resume.txt"
            path.write_text("Campaign analysis and testing.", encoding="utf-8")
            result = workflow.command_inspect(
                Namespace(
                    file=path,
                    required=["campaign analysis"],
                    forbid=["placeholder"],
                    max_pages=2,
                    case_sensitive=False,
                )
            )
            self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
