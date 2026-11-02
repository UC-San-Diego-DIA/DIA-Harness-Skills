"""Synthetic end-to-end pack, portability, validation, and installed-runtime checks."""

from contextlib import redirect_stdout
import copy
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "dia-tableau-dataset-intelligence" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import pack
import pack_runtime as runtime

XML = '''<workbook version="18.1"><datasources><datasource name="main" caption="Synthetic payments">
<column name="[ID]" datatype="string" role="dimension"/>
<column name="[Amount]" datatype="real" role="measure"/>
<column name="[Date]" datatype="date" role="dimension"/>
<connection><relation type="table" name="Payments" table="[Payments]"/>
<metadata-records><metadata-record class="column"><local-name>[ID]</local-name><object-id>[p]</object-id><nullable>false</nullable><contains-null>true</contains-null></metadata-record></metadata-records></connection>
<object-graph><objects><object id="p" caption="Payments"><properties context=""><relation type="table" name="Payments" table="[Payments]" custom.flag="retained"/></properties></object></objects><relationships/></object-graph>
</datasource></datasources></workbook>'''


def save(root, name, data):
    (root / name).write_text(runtime.yaml_text(data), encoding="utf-8", newline="\n")


def enrich_fixture(root):
    """A synthetic authored proposal set, not automatic production inference."""
    data = pack.assets(root)
    dictionary = data["dictionary"]
    source = dictionary["datasources"][0]
    fields = {field["name"]: field for field in source["fields"]}
    amount, date, identifier = (fields[name]["id"] for name in ("[Amount]", "[Date]", "[ID]"))

    def annotation(text, reference):
        return {"text": text, "basis": "context_inferred", "confirmation_status": "unconfirmed",
                "confirmed_at": None, "confirmed_by": None, "evidence_refs": [reference]}

    dictionary["dataset_context"].update(reviewed=True, summary=annotation("Synthetic payment records for behavior tests.", source["id"]))
    for field in source["fields"]:
        field["definition"] = annotation("A synthetic payment attribute requiring business review.", field["id"])
        field["enrichment"]["reviewed"] = True
    model = data["model"]
    for table in model["table_meanings"]:
        table["statement"] = "Payment records in the synthetic model."
    for grain in model["grains"]:
        grain["statement"] = "One payment record, proposed and untested."
        grain["field_ids"] = [identifier]
    model["reviewed"] = True
    terms = data["glossary"]
    terms["reviewed"] = True
    term_id = "synthetic.payments.term.payment"
    terms["terms"] = [{"term_id": term_id, "name": "Payment", "definition": {
        "text": "A proposed payment event.", "basis": "context_inferred", "status": "proposed",
        "evidence_refs": [amount], "confirmed_at": None, "confirmed_by": None},
        "synonyms": [], "field_refs": [amount], "approval_status": "proposed", "verification": "not_tested", "open_questions": []}]
    metric_id = "synthetic.payments.metric.amount"
    gate = {"id": "grain", "requirement": "Confirm payment grain and additivity.", "resolved": False, "evidence": None}
    metric = {"id": metric_id, "name": "Proposed payment amount", "description": "Sum payment amounts only after review.",
              "origin": "schema_proposed", "status": "proposed", "support": "conditional", "support_rationale": "Grain is untested.",
              "data_verification": "not_tested", "approval": None, "approval_gates": [gate], "assumptions": [],
              "field_refs": [amount, date], "glossary_refs": [term_id],
              "formula": {"expression": "SUM({amount})", "bindings": [{"symbol": "amount", "field_id": amount}],
                          "aggregation": "sum", "grain_ref": model["grains"][0]["id"], "grain_statement": "One payment, proposed."},
              "date": {"field_ref": date, "basis": "Recorded date field", "period": "month", "timezone": "Unknown"},
              "dimension_refs": [], "filters": [], "unit": {"label": "Unconfirmed", "basis": "No unit documented."}}
    data["metrics"].update(reviewed=True, metrics=[metric])
    question = {"id": "synthetic.payments.question.trend", "question": "How does payment amount trend?",
                "rationale": "A proposed time comparison.", "origin": "schema_proposed", "status": "proposed", "support": "conditional",
                "support_rationale": "Depends on the conditional metric.", "data_verification": "not_tested", "approval": None,
                "approval_gates": [copy.deepcopy(gate)], "assumptions": [], "field_refs": [amount, date], "glossary_refs": [term_id],
                "metric_refs": [metric_id], "dimension_refs": [], "date_field_ref": date}
    data["questions"].update(reviewed=True, questions=[question])
    for key, value in data.items():
        save(root, pack.ASSETS[key][0], value)
    manifest = runtime.load(root / "dataset.yaml")
    manifest.update(reviewed=True, description="Synthetic Dataset Intelligence Pack for integration tests.")
    save(root, "dataset.yaml", manifest)


class PackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dia-pack-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.source = self.base / "Synthetic.twb"
        self.source.write_text(XML, encoding="utf-8")
        self.root = self.base / "pack"
        with redirect_stdout(io.StringIO()):
            pack.initialize(self.source, self.root, "synthetic.payments", "Synthetic Payments", "synthetic")

    def test_seed_blocks_finalization_until_llm_review(self):
        self.assertTrue(pack.validate(self.root))
        with self.assertRaises(ValueError):
            pack.finalize(self.root)
        self.assertFalse((self.root / "README.md").exists())
        self.assertEqual(self.source.read_text(), XML)

    def test_complete_pack_moves_and_regenerates_exact_views(self):
        enrich_fixture(self.root)
        self.assertEqual(pack.validate(self.root), [])
        pack.finalize(self.root)
        self.assertEqual(pack.validate(self.root, require_sealed=True), [])
        content = pack.assets(self.root)
        csv_rows = list(csv.DictReader(io.StringIO((self.root / "data-dictionary.csv").read_text())))
        self.assertEqual(next(item for item in csv_rows if item["technical_name"] == "[ID]")["source_declared_nullability"], "false")
        self.assertTrue(all(row["verification"] == "not_tested" for row in csv_rows))
        moved = self.base / "moved-pack"
        shutil.copytree(self.root, moved)
        self.source.unlink()
        self.assertEqual(pack.validate(moved, require_sealed=True), [])
        before = (moved / "dataset.yaml").read_bytes()
        with self.assertRaises(ValueError):
            pack.finalize(moved)
        self.assertEqual((moved / "dataset.yaml").read_bytes(), before)
        self.assertEqual(len(content["dictionary"]["datasources"][0]["fields"]), 3)

    def test_stale_asset_and_reader_edits_are_detected(self):
        enrich_fixture(self.root)
        pack.finalize(self.root)
        reader = self.root / "data-dictionary.md"
        original = reader.read_bytes()
        reader.write_bytes(original + b"\nDirect reader edit\n")
        self.assertTrue(pack.validate(self.root, require_sealed=True))
        reader.write_bytes(original)
        source = self.root / "metrics.yaml"
        source.write_bytes(source.read_bytes() + b"\n# changed upstream asset\n")
        self.assertTrue(pack.validate(self.root, require_sealed=True))

    def test_identity_bad_dictionary_and_external_evidence_are_rejected(self):
        enrich_fixture(self.root)
        metric = runtime.load(self.root / "metrics.yaml")
        metric["dataset_id"] = "other.dataset"
        save(self.root, "metrics.yaml", metric)
        self.assertTrue(pack.validate(self.root))
        metric["dataset_id"] = "synthetic.payments"
        save(self.root, "metrics.yaml", metric)
        dictionary = runtime.load(self.root / "data-dictionary.yaml")
        invalid = copy.deepcopy(dictionary)
        invalid.pop("source")
        save(self.root, "data-dictionary.yaml", invalid)
        self.assertTrue(pack.validate(self.root))
        external = self.base / "external-facts.yaml"
        shutil.copyfile(self.root / "evidence/workbook-facts.yaml", external)
        dictionary["source"]["facts_path"] = "../external-facts.yaml"
        save(self.root, "data-dictionary.yaml", dictionary)
        self.assertTrue(pack.validate(self.root))

    def test_quoted_xml_keys_roundtrip_and_duplicate_keys_fail(self):
        sample = {"attributes": {"custom.flag": "true", "{urn:test}qualified": "kept", 'a"b': "escaped", "7": "text"},
                  "text": "SELECT\t[ID]  \nFROM [Payments]\n"}
        self.assertEqual(runtime.dictionary.yaml_min.load(runtime.yaml_text(sample)), sample)
        self.assertEqual(runtime.dictionary.yaml_min.load(runtime.dictionary.intake.render_yaml(sample)), sample)
        with self.assertRaises(runtime.dictionary.yaml_min.YamlError):
            runtime.dictionary.yaml_min.load('key: first\nkey: second\n')
        # New raw facts contain arbitrary XML keys and still seed the dictionary.
        self.assertIn('"custom.flag"', (self.root / "evidence/workbook-facts.yaml").read_text())

    def test_standalone_install_has_no_sibling_skill_requirement(self):
        target = self.base / "installed"
        installed = subprocess.run(["pwsh", "-NoProfile", "-File", str(ROOT / "scripts/install-skill.ps1"),
                                    "-Skill", "dia-tableau-dataset-intelligence", "-Destination", str(target), "-Force"],
                                   capture_output=True, text=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertFalse((target / "dia-tableau-data-dictionary").exists())
        entry = target / "dia-tableau-dataset-intelligence/scripts/pack.py"
        fresh = self.base / "installed-output"
        result = subprocess.run([sys.executable, str(entry), "init", "--input", str(self.source), "--output", str(fresh),
                                 "--dataset-id", "synthetic.payments", "--name", "Synthetic Payments", "--domain", "synthetic"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        enrich_fixture(fresh)
        for command in ("finalize", "validate"):
            result = subprocess.run([sys.executable, str(entry), command, "--pack", str(fresh)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
