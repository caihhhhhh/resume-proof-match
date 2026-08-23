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
    def create_application(self, root: Path) -> Path:
        workflow.command_new(
            Namespace(
                company="Example Co",
                role="Growth Analyst",
                language="en",
                output_root=root,
                slug="sample",
            )
        )
        application = root / "sample"
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
                "# Complete resume\n\n"
                + "Growth analyst who uses confirmed campaign evidence to make clear decisions. " * 4,
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
            review.write_text("# Complete resume\n\n" + "Evidence-backed result. " * 8, encoding="utf-8")
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
            review.write_text("# Complete resume\n\n" + "Evidence-backed result. " * 8, encoding="utf-8")
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
