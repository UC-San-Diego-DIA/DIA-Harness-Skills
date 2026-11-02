"""Behavior checks for metadata-only Tableau dictionaries and intake reuse."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parent.parent
INTAKE = ROOT / "skills" / "dia-tableau-workbook-intake" / "scripts"
PREPARE = ROOT / "skills" / "dia-tableau-data-dictionary" / "scripts" / "prepare_dictionary.py"
sys.path.insert(0, str(INTAKE))
sys.dont_write_bytecode = True
import extract_workbook_facts as intake
import schema_check
import validate_facts
import yaml_min
sys.path.insert(0, str(PREPARE.parent))
import data_dictionary as dictionary


# Synthetic workbook metadata only. No user workbook or actual source rows.
XML = """<workbook version="18.1"><datasources>
<datasource name="main" caption="Transactions">
 <column name="[Cost]" caption="Expense" datatype="real" role="measure" type="quantitative" hidden="false" aggregation="Sum">
  <desc><formatted-text><run>Recorded expense.</run></formatted-text></desc>
 </column>
 <column name="[Status]" caption="Status" datatype="string" hidden="true">
  <aliases><alias key="A" value="Active"/></aliases>
 </column>
 <column name="[Ratio]" datatype="real"><calculation class="tableau" formula="SUM([Cost]) /&#10;&#9;SUM([Headcount])  &#10;"/></column>
 <column name="[CalcWithoutFormula]"><calculation class="categorical-bin"/></column>
 <column name="[A B]"/><column name="[A-B]"/>
 <connection><metadata-records>
  <metadata-record class="column"><local-name>[Cost]</local-name><local-type>real</local-type><remote-name>COST</remote-name><parent-name>[T]</parent-name><remote-type>5</remote-type></metadata-record>
  <metadata-record class="column"><local-name>[Headcount]</local-name><local-type>integer</local-type><aggregation>Sum</aggregation></metadata-record>
  <metadata-record class="column"><remote-name>UNNAMED</remote-name></metadata-record>
 </metadata-records></connection>
</datasource>
<datasource name="other" caption="Other"><column name="[Cost]" datatype="integer"/></datasource>
<datasource name="Parameters"><column name="[Parameter 1]" caption="Year" param-domain-type="list"><members><member value="2026"/></members></column></datasource>
<datasource name="published" caption="Published reference"/>
</datasources><worksheets><worksheet name="Unused Sheet"><table><view>
<datasource-dependencies datasource="main">
 <column name="[Cost]" caption="Old cost" datatype="real"/>
 <column name="[DependencyOnly]" datatype="date"/>
</datasource-dependencies>
<datasource-dependencies datasource="cache-only"><column name="[Cached]" datatype="string"/></datasource-dependencies>
</view></table></worksheet></worksheets></workbook>"""


class FieldMetadataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="dia-tableau-metadata-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def extract(self, xml=XML):
        facts = intake.parse_workbook(ET.fromstring(xml), [], [], {})
        facts["workbook"]["name"] = "Example"
        intake.assign_ids(facts, intake.IdAssigner())
        return facts

    def run_prepare(self, source, output, helper=PREPARE):
        return subprocess.run([sys.executable, str(helper), "--input", str(source), "--output", str(output)],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def test_full_inventory_identity_and_evidence(self):
        facts = self.extract()
        sources = {source["name"]: source for source in facts["datasources"]}
        fields = {field["name"]: field for field in sources["main"]["fields"]}
        self.assertEqual(len(fields), 8)
        self.assertEqual(fields["[Cost]"]["caption"], "Expense")
        self.assertEqual(fields["[Cost]"]["description"], "Recorded expense.")
        self.assertEqual(fields["[Cost]"]["source_columns"][0]["name"], "COST")
        self.assertFalse(fields["[Cost]"]["hidden"])
        self.assertTrue(fields["[Status]"]["hidden"])
        self.assertIsNone(fields["[DependencyOnly]"]["hidden"])
        self.assertEqual(fields["[Headcount]"]["datatype"], "integer")
        self.assertEqual(fields["[Status]"]["aliases"], [{"key": "A", "value": "Active"}])
        self.assertEqual(fields["[CalcWithoutFormula]"]["calculation"]["formula"], None)
        self.assertTrue(fields["[Cost]"]["conflicts"])
        self.assertEqual(sources["main"]["field_inventory"]["skipped_records"], 1)
        self.assertEqual(sources["main"]["field_inventory"]["conflicting_fields"], 1)
        self.assertNotEqual(fields["[Cost]"]["id"], sources["other"]["fields"][0]["id"])
        self.assertNotEqual(fields["[A B]"]["id"], fields["[A-B]"]["id"])
        self.assertEqual(sources["Parameters"]["fields"], [])
        self.assertEqual(len(facts["parameters"]), 1)
        self.assertTrue(sources["published"]["field_inventory"]["warnings"])
        self.assertEqual(sources["cache-only"]["field_inventory"]["scope"], "worksheet_dependencies_only")
        self.assertEqual(validate_facts.check_ids(facts), [])

    def test_package_opens_only_workbook_entry_and_preserves_formula(self):
        workbook = self.path / "Example.twbx"
        facts_path = self.path / "facts.yaml"
        with zipfile.ZipFile(workbook, "w") as package:
            package.writestr("workbook.twb", XML)
            package.writestr("Data/secret.hyper", b"not an extract")
            package.writestr("Data/secret.csv", "must not be read")
        original_hash = hashlib.sha256(workbook.read_bytes()).hexdigest()
        read_entry = zipfile.ZipFile.read
        opened = []

        def guarded_read(package, entry, *args, **kwargs):
            name = entry.filename if isinstance(entry, zipfile.ZipInfo) else entry
            opened.append(name)
            self.assertTrue(name.endswith(".twb"), name)
            return read_entry(package, entry, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "read", guarded_read), redirect_stdout(io.StringIO()):
            self.assertEqual(intake.main(["--input", str(workbook), "--output", str(facts_path)]), 0)
        self.assertEqual(opened, ["workbook.twb"])
        self.assertEqual(original_hash, hashlib.sha256(workbook.read_bytes()).hexdigest())
        facts = yaml_min.load(facts_path.read_text(encoding="utf-8"))
        ratio = next(field for field in facts["datasources"][0]["fields"] if field["name"] == "[Ratio]")
        self.assertEqual(ratio["calculation"]["formula"], "SUM([Cost]) /\n\tSUM([Headcount])  \n")
        schema = json.loads((ROOT / "docs/shared/workbook-facts.schema.json").read_text())
        self.assertEqual(schema_check.validate(facts, schema), [])
        self.assertEqual(validate_facts.check_field_metadata(facts), [])
        # Consumers can still validate older v2 facts without the additive capability.
        legacy = copy.deepcopy(facts)
        legacy.pop("field_metadata_version")
        for source in legacy["datasources"]:
            source.pop("fields")
            source.pop("field_inventory")
        self.assertEqual(schema_check.validate(legacy, schema), [])
        facts["datasources"][0]["field_inventory"]["field_count"] += 1
        self.assertTrue(validate_facts.check_field_metadata(facts))

    def test_source_workflow_and_refusal_to_overwrite(self):
        workbook = self.path / "Book with spaces.twb"
        output = self.path / "scratch" / "facts.yaml"
        workbook.write_text(XML, encoding="utf-8")
        result = self.run_prepare(workbook, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["validated"])
        prior = output.read_bytes()
        self.assertNotEqual(self.run_prepare(workbook, output).returncode, 0)
        self.assertEqual(output.read_bytes(), prior)
        original = workbook.read_bytes()
        self.assertNotEqual(self.run_prepare(workbook, workbook).returncode, 0)
        self.assertEqual(workbook.read_bytes(), original)

    def test_standalone_install_reuses_source_helpers(self):
        destination = self.path / "installed"
        install = subprocess.run(["pwsh", "-NoProfile", "-File", str(ROOT / "scripts/install-skill.ps1"),
                                  "-Skill", "dia-tableau-data-dictionary", "-Destination", str(destination), "-Force"],
                                 capture_output=True, text=True)
        self.assertEqual(install.returncode, 0, install.stderr)
        self.assertFalse((destination / "dia-tableau-workbook-intake").exists())
        helper = destination / "dia-tableau-data-dictionary/scripts/prepare_dictionary.py"
        bundle = helper.parent / "workbook_intake"
        for name in ("extract_workbook_facts.py", "field_metadata.py", "facts_common.py", "validate_facts.py", "schema_check.py", "yaml_min.py"):
            self.assertEqual((bundle / name).read_bytes(), (INTAKE / name).read_bytes())
        workbook = self.path / "Installed.twb"
        workbook.write_text(XML, encoding="utf-8")
        result = self.run_prepare(workbook, self.path / "installed-facts.yaml", helper)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["validated"])
        structured = self.path / "installed-dictionary.yaml"
        rendered = self.path / "installed-dictionary.md"
        dictionary_helper = helper.parent / "data_dictionary.py"
        for arguments in (
            ["create", "--facts", str(self.path / "installed-facts.yaml"), "--output", str(structured)],
            ["render", "--dictionary", str(structured), "--output", str(rendered)],
        ):
            result = subprocess.run([sys.executable, str(dictionary_helper), *arguments],
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            if arguments[0] == "create":
                self.complete_fixture(dictionary.load(structured), structured)
        self.assertIn("Recorded expense.", rendered.read_text(encoding="utf-8"))

    def test_namespace_and_empty_workbook(self):
        facts = self.extract(XML.replace('<workbook version=', '<workbook xmlns="urn:tableau:test" version='))
        self.assertEqual(len(facts["datasources"][0]["fields"]), 8)
        self.assertEqual(self.extract("<workbook/>")["datasources"], [])

    def test_alias_conflicts_do_not_replace_source_definition(self):
        xml = XML.replace('<column name="[DependencyOnly]" datatype="date"/>',
                          '<column name="[DependencyOnly]" datatype="date"/>'
                          '<column name="[Status]"><aliases><alias key="A" value="Archived"/></aliases></column>')
        source = self.extract(xml)["datasources"][0]
        status = next(field for field in source["fields"] if field["name"] == "[Status]")
        self.assertEqual(status["aliases"], [{"key": "A", "value": "Active"}])
        self.assertEqual(status["conflicts"][0]["attribute"], "aliases")

    def test_invalid_workbook_does_not_create_facts(self):
        workbook = self.path / "broken.twb"
        workbook.write_text("<workbook>", encoding="utf-8")
        output = self.path / "bad-facts.yaml"
        self.assertNotEqual(self.run_prepare(workbook, output).returncode, 0)
        self.assertFalse(output.exists())

    def complete_fixture(self, data, structured):
        """Synthetic annotations model the LLM stage; helpers must not invent them."""
        reference = data["workbook"]["id"]
        data["dataset_context"]["reviewed"] = True
        data["dataset_context"]["summary"] = self.annotation("Synthetic transaction metadata for behavioral tests.", reference)
        for source in data["datasources"]:
            for field in source["fields"]:
                field["enrichment"]["reviewed"] = True
                if field["category"] == "business" and field["definition"]["text"] is None:
                    field["open_questions"] = ["Which business concept does this field represent?"]
        structured.write_text(dictionary.yaml_text(data), encoding="utf-8")
        return data

    def annotation(self, text, *references, basis="context_inferred"):
        return {"text": text, "basis": basis, "confirmation_status": "unconfirmed",
                "confirmed_at": None, "confirmed_by": None, "evidence_refs": list(references)}

    def create_structured_dictionary(self, xml=XML, enrich=True):
        workbook = self.path / "Dictionary.twb"
        workbook.write_text(xml, encoding="utf-8")
        facts = self.path / "scratch" / "facts.yaml"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(intake.main(["--input", str(workbook), "--output", str(facts)]), 0)
        structured = self.path / "data-dictionary.yaml"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(dictionary.main(["create", "--facts", str(facts), "--output", str(structured)]), 0)
        data = dictionary.load(structured)
        if enrich:
            self.complete_fixture(data, structured)
        return data, structured, facts, workbook

    def test_structured_source_drives_deterministic_markdown_without_workbook(self):
        data, structured, facts, workbook = self.create_structured_dictionary()
        original = dictionary.load(facts)
        field = data["datasources"][0]["fields"][0]
        field["definition"] = {
            "text": "Confirmed expense in the selected reporting scope.", "basis": "analyst_confirmed",
            "confirmation_status": "confirmed", "confirmed_by": "Synthetic test analyst",
            "confirmed_at": "2026-11-01T12:00:00-08:00",
            "evidence_refs": [field["id"]],
        }
        field["open_questions"] = ["Which currency applies?"]
        # Adversarial Markdown characters must remain data in generated text.
        data["datasources"][1]["fields"][0]["definition"] = {
            "text": "Proposed **meaning** | <script>.", "basis": "name_based",
            "confirmation_status": "unconfirmed", "confirmed_at": None, "confirmed_by": None,
            "evidence_refs": [data["datasources"][1]["fields"][0]["id"]],
        }
        structured.write_text(dictionary.yaml_text(data), encoding="utf-8")
        self.assertEqual(dictionary.load(structured), data)
        self.assertEqual(dictionary.validate(data, structured), [])
        workbook.unlink()
        first, second = self.path / "first.md", self.path / "second.md"
        for output in (first, second):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(dictionary.main(["render", "--dictionary", str(structured), "--output", str(output)]), 0)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        text = first.read_text(encoding="utf-8")
        self.assertIn("Confirmed expense in the selected reporting scope.", text)
        self.assertEqual(dictionary.load(structured)["datasources"][0]["fields"][0]["description"], "Recorded expense.")
        self.assertIn("Which currency applies?", text)
        self.assertIn("Confirmed", text)
        self.assertEqual(dictionary.load(structured)["datasources"][0]["fields"][0]["definition"]["confirmed_by"], "Synthetic test analyst")
        self.assertIn("\\<script\\>", text)
        self.assertIn(dictionary.sha256(structured), text)
        self.assertEqual(dictionary.load(facts), original)

    def test_dictionary_rejects_changed_metadata_coverage_and_false_confirmation_records(self):
        data, structured, facts, _ = self.create_structured_dictionary()
        for mutate in (
            lambda value: value.update(schema_version=99),
            lambda value: value["datasources"][0]["fields"].pop(),
            lambda value: value["datasources"][0]["fields"].append(copy.deepcopy(value["datasources"][0]["fields"][0])),
            lambda value: value["datasources"][0]["fields"][0].update(datatype="string"),
            lambda value: value["datasources"][0]["fields"][0]["definition"].update(basis="analyst_confirmed", confirmation_status="confirmed"),
            lambda value: value["datasources"][0]["fields"][0]["definition"].update(basis="formula_derived"),
            lambda value: value["datasources"][0]["fields"][0]["definition"].update(basis="unsupported_label"),
        ):
            changed = copy.deepcopy(data)
            mutate(changed)
            self.assertTrue(dictionary.validate(changed, structured))
        facts.write_text(facts.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        self.assertTrue(dictionary.validate(data, structured))

    def test_revision_parent_and_regeneration_preserve_previous_source(self):
        data, structured, _, _ = self.create_structured_dictionary()
        prior = structured.read_bytes()
        revision = self.path / "revisions" / "data-dictionary-r2.yaml"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(dictionary.main(["revise", "--dictionary", str(structured), "--output", str(revision)]), 0)
        revised = dictionary.load(revision)
        self.assertEqual(revised["revision"], 2)
        self.assertEqual(revised["schema_version"], 2)
        self.assertEqual(revised["created_at"], data["created_at"])
        self.assertEqual(revised["previous_revision_sha256"], hashlib.sha256(prior).hexdigest())
        self.assertEqual((revision.parent / revised["previous_revision_path"]).resolve(), structured)
        self.assertEqual(dictionary.validate(revised, revision), [])
        self.assertEqual(structured.read_bytes(), prior)
        invalid_parent = copy.deepcopy(revised)
        invalid_parent["revision"] = 3
        self.assertTrue(dictionary.validate(invalid_parent, revision))
        structured.write_bytes(prior + b"\n# edited parent\n")
        self.assertTrue(dictionary.validate(revised, revision))

    def test_invalid_dictionary_cannot_render_or_overwrite_existing_output(self):
        data, structured, _, _ = self.create_structured_dictionary()
        output = self.path / "dictionary.md"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(dictionary.main(["render", "--dictionary", str(structured), "--output", str(output)]), 0)
        prior = output.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertNotEqual(dictionary.main(["render", "--dictionary", str(structured), "--output", str(output)]), 0)
        self.assertEqual(output.read_bytes(), prior)
        data["schema_version"] = 99
        structured.write_text(dictionary.yaml_text(data), encoding="utf-8")
        bad_output = self.path / "invalid.md"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertNotEqual(dictionary.main(["render", "--dictionary", str(structured), "--output", str(bad_output)]), 0)
        self.assertFalse(bad_output.exists())

    def test_contextual_enrichment_is_required_and_references_are_validated(self):
        data, structured, _, _ = self.create_structured_dictionary(enrich=False)
        self.assertEqual(dictionary.validate(data, structured), [])
        self.assertTrue(dictionary.validate(data, structured, require_ready=True))
        unreviewed_output = self.path / "unreviewed.md"
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertNotEqual(dictionary.main(["render", "--dictionary", str(structured), "--output", str(unreviewed_output)]), 0)
        self.assertFalse(unreviewed_output.exists())
        field = data["datasources"][0]["fields"][0]
        related = data["datasources"][0]["fields"][1]
        self.complete_fixture(data, structured)
        field["definition"] = self.annotation("Expense associated with a transaction record.", field["id"], related["id"])
        data["context_sources"] = [{"id": "provided-note", "kind": "user_statement", "locator": "Test conversation",
                                    "sha256": None, "excerpt": "The synthetic amounts are in test credits."}]
        field["enrichment"]["units"] = self.annotation("Test credits", "provided-note", basis="supplied_context")
        field["enrichment"]["label"] = self.annotation("Expense amount", field["id"])
        field["enrichment"]["usage_notes"] = [self.annotation("Interpret alongside the status category.", related["id"], field["id"])]
        related["enrichment"]["code_meanings"] = [{"code": "A", "meaning": self.annotation("Active", related["id"], basis="recorded_metadata")}]
        self.assertEqual(dictionary.validate(data, structured, require_ready=True), [])
        rendered = dictionary.render(data, structured)
        self.assertIn("Expense amount [draft]", rendered)
        self.assertIn("Test credits [draft]", rendered)
        self.assertIn("Code A: Active [draft]", rendered)
        empty_label = copy.deepcopy(field["definition"])
        empty_label.update(text=None, basis="undocumented", evidence_refs=[])
        prior_label = field["enrichment"]["label"]
        field["enrichment"]["label"] = empty_label
        self.assertTrue(dictionary.validate(data, structured))
        field["enrichment"]["label"] = prior_label
        field["enrichment"]["units"]["evidence_refs"] = ["missing-context"]
        self.assertTrue(dictionary.validate(data, structured, require_ready=True))
        field["enrichment"]["units"]["evidence_refs"] = ["provided-note"]
        field["enrichment"]["reviewed"] = False
        self.assertTrue(dictionary.validate(data, structured, require_ready=True))

    def test_internal_records_are_separate_and_technical_metadata_stays_in_yaml(self):
        xml = XML.replace('<column name="[A B]"/>', '<column name="[__tableau_internal_object_id__].[Table]" datatype="table" caption="Internal Table"/>'
                          '<column name="[A B]"/>')
        data, structured, _, _ = self.create_structured_dictionary(xml)
        internal = next(field for field in data["datasources"][0]["fields"] if field["category"] == "tableau_internal")
        text = dictionary.render(data, structured)
        business_text, internal_text = text.split("## Tableau internal metadata")
        self.assertNotIn("Internal Table", business_text)
        self.assertIn("Internal Table", internal_text)
        self.assertNotIn("metadata-record[", text)
        self.assertNotIn("| Default aggregation |", text)
        self.assertIn("metadata-record[", dictionary.yaml_text(data))
        self.assertEqual(dictionary.validate(data, structured, require_ready=True), [])
        internal["category"] = "business"
        self.assertTrue(dictionary.validate(data, structured))

    def test_v1_migration_keeps_original_and_requires_new_context_review(self):
        data, structured, _, _ = self.create_structured_dictionary()
        legacy = copy.deepcopy(data)
        legacy["schema_version"] = 1
        for key in ("migrated_from_schema_version", "context_sources", "dataset_context"):
            legacy.pop(key)
        for source in legacy["datasources"]:
            for field in source["fields"]:
                field.pop("category")
                field.pop("enrichment")
                field["definition"].pop("evidence_refs")
        structured.write_text(dictionary.yaml_text(legacy), encoding="utf-8")
        prior = structured.read_bytes()
        self.assertEqual(dictionary.validate(legacy, structured), [])
        self.assertIn("Original workbook description", dictionary.render(legacy, structured))
        output = self.path / "dictionary-v2.yaml"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(dictionary.main(["migrate", "--dictionary", str(structured), "--output", str(output)]), 0)
        migrated = dictionary.load(output)
        self.assertEqual(structured.read_bytes(), prior)
        self.assertEqual(migrated["revision"], 2)
        self.assertEqual(migrated["migrated_from_schema_version"], 1)
        self.assertEqual(dictionary.validate(migrated, output), [])
        self.assertTrue(dictionary.validate(migrated, output, require_ready=True))
        self.complete_fixture(migrated, output)
        self.assertEqual(dictionary.validate(migrated, output, require_ready=True), [])


if __name__ == "__main__":
    unittest.main()
