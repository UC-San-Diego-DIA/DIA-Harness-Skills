"""Synthetic-only contract and cross-reference tests for dataset proposals."""

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "skills" / "dia-tableau-dataset-intelligence"
sys.path.insert(0, str(PACK / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "dia-tableau-workbook-intake" / "scripts"))
import proposals
import schema_check


class ProposalsTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = {"source": {"workbook_sha256": "a" * 64}, "datasources": [{"fields": [
            {"id": "field.amount", "datatype": "real"},
            {"id": "field.date", "datatype": "date"},
            {"id": "field.location", "datatype": "string"},
            {"id": "field.internal", "datatype": "table", "category": "tableau_internal"},
        ]}]}
        self.model = {"dataset_id": "synthetic.dataset", "source_workbook_sha256": "a" * 64,
                      "grains": [{"id": "synthetic.dataset.grain.1", "status": "proposed"}]}
        self.glossary = {"dataset_id": "synthetic.dataset", "source_workbook_sha256": "a" * 64,
                         "terms": [{"term_id": "synthetic.dataset.term.payment"}]}
        self.metrics = proposals.seed_metrics(self.dictionary, self.model, self.glossary, "synthetic.dataset")
        self.metric = {"id": "synthetic.dataset.metric.payment-amount", "name": "Payment amount candidate",
                       "description": "Sum payment records after confirming grain.",
                       "origin": "schema_proposed", "status": "proposed", "support": "conditional",
                       "support_rationale": "Fields exist; additive grain is untested.",
                       "data_verification": "not_tested", "approval": None,
                       "approval_gates": [{"id": "grain", "requirement": "Confirm additive grain.", "resolved": False, "evidence": None}],
                       "assumptions": ["No join fanout."], "field_refs": ["field.amount", "field.date", "field.location"],
                       "glossary_refs": ["synthetic.dataset.term.payment"],
                       "formula": {"expression": "SUM({amount})", "bindings": [{"symbol": "amount", "field_id": "field.amount"}],
                                   "aggregation": "sum", "grain_ref": "synthetic.dataset.grain.1", "grain_statement": "One payment record, proposed."},
                       "date": {"field_ref": "field.date", "basis": "Recorded payment date", "period": "day", "timezone": "Unconfirmed"},
                       "dimension_refs": ["field.location"], "filters": [],
                       "unit": {"label": "Currency unconfirmed", "basis": "Numeric amount field."}}
        self.metrics["metrics"] = [self.metric]
        self.questions = proposals.seed_questions(self.dictionary, self.model, self.glossary, self.metrics, "synthetic.dataset")
        self.question = {k: copy.deepcopy(v) for k, v in self.metric.items() if k in {
            "origin", "status", "support", "support_rationale", "data_verification", "approval", "approval_gates", "assumptions", "field_refs", "glossary_refs", "dimension_refs"}}
        self.question.update({"id": "synthetic.dataset.question.payment-trend", "question": "How do payment amounts vary by date and location?",
                              "rationale": "Describe payment mix after validation.", "metric_refs": [self.metric["id"]], "date_field_ref": "field.date"})
        self.questions["questions"] = [self.question]

    def validate_metric(self):
        return proposals.validate_metrics(self.metrics, self.dictionary, self.model, self.glossary)

    def validate_question(self):
        return proposals.validate_questions(self.questions, self.dictionary, self.model, self.glossary, self.metrics)

    def test_seed_and_complete_fixture_match_schemas(self):
        for data, filename in ((self.metrics, "metrics.schema.json"), (self.questions, "questions.schema.json")):
            schema = json.loads((PACK / "references" / filename).read_text(encoding="utf-8"))
            self.assertEqual([], schema_check.validate(data, schema))
            empty = copy.deepcopy(data)
            empty["metrics" if filename.startswith("metrics") else "questions"] = []
            self.assertEqual([], schema_check.validate(empty, schema))
        self.assertEqual([], self.validate_metric())
        self.assertEqual([], self.validate_question())

    def test_snapshot_and_dataset_mismatches_fail(self):
        self.model["source_workbook_sha256"] = "b" * 64
        self.glossary["dataset_id"] = "another.dataset"
        self.assertEqual(2, len(self.validate_metric()))

    def test_missing_formula_binding_and_invented_fields_fail(self):
        self.metric["formula"]["expression"] = "SUM({invented})"
        self.assertTrue(self.validate_metric())
        self.metric["formula"]["expression"] = "SUM([ImaginaryAmount])"
        self.assertTrue(self.validate_metric())
        self.metric["formula"]["expression"] = "SUM({amount})"
        self.metric["formula"]["bindings"][0]["field_id"] = "missing"
        self.assertTrue(self.validate_metric())

    def test_internal_fields_are_not_business_metric_inputs(self):
        self.metric["formula"]["bindings"][0]["field_id"] = "field.internal"
        self.metric["field_refs"][0] = "field.internal"
        self.assertTrue(self.validate_metric())

    def test_duplicate_ids_symbols_and_unknown_grain_fail(self):
        self.metrics["metrics"].append(copy.deepcopy(self.metric))
        self.metric["formula"]["bindings"].append(copy.deepcopy(self.metric["formula"]["bindings"][0]))
        self.metric["formula"]["grain_ref"] = "unknown.grain"
        self.assertGreaterEqual(len(self.validate_metric()), 3)

    def test_unsupported_approval_and_verification_claims_fail(self):
        self.metric["status"] = "approved"
        self.metric["data_verification"] = "verified"
        self.assertGreaterEqual(len(self.validate_metric()), 3)
        self.metric["status"] = "proposed"
        self.metric["approval"] = {"by": "Reviewer", "at": "2026-01-01T00:00:00+00:00", "evidence": "Explicit review"}
        self.assertTrue(self.validate_metric())

    def test_supported_requires_confirmed_grain_and_resolved_gates(self):
        self.metric["support"] = "supported"
        self.assertTrue(self.validate_metric())
        self.metric["approval_gates"][0].update({"resolved": True, "evidence": "Analyst confirmed grain and additivity in supplied review."})
        self.assertTrue(self.validate_metric())
        self.model["grains"][0]["status"] = "confirmed"
        self.assertEqual([], self.validate_metric())
        self.assertEqual("not_tested", self.metric["data_verification"])

    def test_resolved_gate_and_approval_need_evidence_and_timestamp(self):
        self.metric["approval_gates"][0]["resolved"] = True
        self.metric["status"] = "approved"
        self.metric["support"] = "supported"
        self.metric["approval"] = {"by": "Reviewer", "at": "2026-01-01", "evidence": "Explicit review"}
        self.assertTrue(any(issue["path"].endswith("approval.at") for issue in self.validate_metric()))

    def test_question_missing_metric_and_field_refs_fail(self):
        self.question["metric_refs"] = ["missing.metric"]
        self.assertTrue(self.validate_question())
        self.question["metric_refs"] = []
        self.assertTrue(self.validate_question())
        self.question["metric_refs"] = [self.metric["id"]]
        self.question["field_refs"] = ["field.amount"]
        self.assertTrue(self.validate_question())

    def test_questions_cannot_invent_dimensions_or_override_metric_support(self):
        self.question["dimension_refs"] = ["supplier_name"]
        self.assertTrue(self.validate_question())
        self.question["dimension_refs"] = ["field.location"]
        self.question["support"] = "supported"
        self.question["approval_gates"] = []
        self.assertTrue(any("referenced metric" in issue["message"] for issue in self.validate_question()))

    def test_question_metric_snapshot_must_match(self):
        self.metrics["source_workbook_sha256"] = "b" * 64
        self.assertTrue(self.validate_question())

    def test_render_is_deterministic_and_exposes_limits(self):
        metric_view = proposals.render_metrics(self.metrics)
        question_view = proposals.render_questions(self.questions)
        self.assertEqual(metric_view, proposals.render_metrics(copy.deepcopy(self.metrics)))
        self.assertIn("SUM(\\{amount\\})", metric_view)
        self.assertIn("\\[unresolved\\]", metric_view)
        self.assertIn("field.location", question_view)
        self.assertIn("No values were calculated", question_view)

    def test_renderer_escapes_user_markup_and_app_directives(self):
        self.metric["description"] = '<script>alert(1)</script>\n::code-comment{title="test"}'
        view = proposals.render_metrics(self.metrics)
        self.assertNotIn("<script>", view)
        self.assertNotIn("::code-comment", view)
        self.assertIn("&lt;script&gt;", view)


if __name__ == "__main__":
    unittest.main()
