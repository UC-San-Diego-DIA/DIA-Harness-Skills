"""Synthetic glossary/reference-integrity and CSV safety tests. No user files."""

import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pack_glossary", ROOT / "skills/dia-tableau-dataset-intelligence/scripts/glossary.py")
glossary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(glossary)
sys.path.insert(0, str(ROOT / "skills/dia-tableau-workbook-intake/scripts"))
import schema_check


def dictionary():
    def field(ident, name, category="business"):
        return {"id": ident, "name": name, "caption": name, "datatype": "real",
                "category": category, "source_columns": [{"table": "payments", "name": name}],
                "definition": {"text": "A proposed payment value.", "basis": "context_inferred",
                               "confirmation_status": "unconfirmed", "evidence_refs": [ident]},
                "enrichment": {"label": None}}
    return {"source": {"workbook_sha256": "a" * 64},
            "context_sources": [{"id": "context-1"}],
            "datasources": [{"id": "source-a", "name": "A", "caption": "A",
                             "fields": [field("a.amount", "Amount"), field("a.internal", "Internal", "tableau_internal")]},
                            {"id": "source-b", "name": "B", "caption": "B",
                             "fields": [field("b.amount", "Amount")]}]}


def authored(data):
    result = glossary.seed(data, "team.synthetic")
    result["reviewed"] = True
    result["terms"] = [{"term_id": "team.synthetic.term.payment", "name": "Payment",
                        "definition": {"text": "Entry settling a transaction, subject to review.",
                                       "basis": "context_inferred", "status": "proposed",
                                       "evidence_refs": ["a.amount", "context-1"], "confirmed_by": None, "confirmed_at": None},
                        "synonyms": [{"text": "Payment entry", "status": "proposed", "evidence_refs": ["a.amount"], "confirmed_by": None, "confirmed_at": None}],
                        "field_refs": ["a.amount"], "approval_status": "proposed",
                        "verification": "not_tested", "open_questions": ["How are reversals recorded?"]}]
    return result


class GlossaryTests(unittest.TestCase):
    def setUp(self):
        self.dictionary = dictionary()
        self.glossary = authored(self.dictionary)
        self.schema = json.loads((ROOT / "skills/dia-tableau-dataset-intelligence/references/business-glossary.schema.json").read_text(encoding="utf-8"))

    def test_seed_has_no_automatic_field_definitions_or_approvals(self):
        seed = glossary.seed(self.dictionary, "team.synthetic")
        self.assertEqual(seed["terms"], [])
        self.assertFalse(seed["reviewed"])
        self.assertEqual(schema_check.validate(seed, self.schema), [])
        self.assertEqual(glossary.validate(seed, self.dictionary), [])
        seed["reviewed"] = True
        self.assertTrue(glossary.validate(seed, self.dictionary))

    def test_authored_concept_schema_and_review_are_separate_from_verification(self):
        self.assertEqual(schema_check.validate(self.glossary, self.schema), [])
        self.assertEqual(glossary.validate(self.glossary, self.dictionary), [])
        self.glossary["terms"][0]["verification"] = "verified"
        self.assertTrue(schema_check.validate(self.glossary, self.schema))
        self.assertTrue(glossary.validate(self.glossary, self.dictionary))

    def test_hash_scoped_ids_and_dangling_refs(self):
        mutations = [lambda g: g.update(source_workbook_sha256="b" * 64),
                     lambda g: g["terms"][0].update(term_id="other.term.payment"),
                     lambda g: g["terms"][0].update(field_refs=["missing"]),
                     lambda g: g["terms"][0].update(field_refs=["a.internal"]),
                     lambda g: g["terms"][0]["definition"].update(evidence_refs=["missing"]),
                     lambda g: g["terms"][0]["synonyms"][0].update(evidence_refs=["missing"])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(self.glossary)
                mutate(changed)
                self.assertTrue(glossary.validate(changed, self.dictionary))

    def test_duplicate_ids_and_names_rejected(self):
        self.glossary["terms"].append(copy.deepcopy(self.glossary["terms"][0]))
        paths = [v["path"] for v in glossary.validate(self.glossary, self.dictionary)]
        self.assertIn("terms[1].term_id", paths)
        self.assertIn("terms[1].name", paths)

    def test_confirmation_requires_explicit_attribution_and_time(self):
        term = self.glossary["terms"][0]
        term["approval_status"] = "confirmed"
        term["definition"].update(status="confirmed", basis="analyst_confirmed")
        self.assertTrue(glossary.validate(self.glossary, self.dictionary))
        term["definition"].update(confirmed_by="Synthetic analyst", confirmed_at="2026-01-01T12:00:00+00:00")
        self.assertEqual(glossary.validate(self.glossary, self.dictionary), [])
        # Confirming a concept never silently confirms synonyms.
        self.assertEqual(term["synonyms"][0]["status"], "proposed")
        term["definition"]["confirmed_at"] = "2026-01-01T12:00:00"
        self.assertTrue(glossary.validate(self.glossary, self.dictionary))

    def test_renderer_is_deterministic_and_escapes_table_content(self):
        self.glossary["terms"][0]["name"] = "Payment|entry\nSecond line"
        first = glossary.render(self.glossary)
        self.assertEqual(first, glossary.render(self.glossary))
        self.assertIn("Payment\\|entry<br>Second line", first)
        self.assertIn("not tested", first)
        self.assertIn("[proposed]", first)

    def test_csv_retains_all_sources_and_internals_without_claiming_nullability(self):
        original = copy.deepcopy(self.dictionary)
        result = glossary.export_dictionary_csv(self.dictionary)
        rows = list(csv.DictReader(io.StringIO(result)))
        self.assertEqual([r["field_id"] for r in rows], ["a.amount", "a.internal", "b.amount"])
        self.assertEqual(rows[0]["technical_name"], rows[2]["technical_name"])
        self.assertNotEqual(rows[0]["source_id"], rows[2]["source_id"])
        self.assertTrue(all(r["source_declared_nullability"] == "unknown" for r in rows))
        self.assertTrue(all(r["verification"] == "not_tested" for r in rows))
        self.assertEqual(json.loads(rows[0]["source_mappings"]), original["datasources"][0]["fields"][0]["source_columns"])
        self.assertEqual(self.dictionary, original)
        self.assertEqual(result, glossary.export_dictionary_csv(self.dictionary))

    def test_csv_formula_injection_is_neutralized_only_in_view(self):
        field = self.dictionary["datasources"][0]["fields"][0]
        field["caption"] = " \t=HYPERLINK(\"example\")"
        field["definition"]["text"] = "@SUM(A1)"
        field["name"] = "+command"
        rows = list(csv.DictReader(io.StringIO(glossary.export_dictionary_csv(self.dictionary))))
        self.assertTrue(rows[0]["display_name"].startswith("'"))
        self.assertEqual(rows[0]["meaning"], "'@SUM(A1)")
        self.assertEqual(rows[0]["technical_name"], "'+command")
        self.assertEqual(field["definition"]["text"], "@SUM(A1)")


if __name__ == "__main__":
    unittest.main()
