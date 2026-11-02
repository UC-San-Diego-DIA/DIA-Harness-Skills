"""Metadata-only structural extraction and model interpretation checks."""
import copy
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "skills/dia-tableau-workbook-intake/scripts"))
sys.path.insert(0, str(ROOT / "skills/dia-tableau-dataset-intelligence/scripts"))
import extract_workbook_facts as intake
import model_structure
import model_spec
import schema_check


XML = '''<workbook version="18.1"><datasources><datasource name="main">
<column name="[ID]"/><column name="[Amount]"/>
<connection><relation type="collection"><relation type="table" name="Proxy" table="[Proxy]"/></relation>
<metadata-records><metadata-record class="column"><local-name>[ID]</local-name><object-id>[a]</object-id><nullable>false</nullable><contains-null>true</contains-null></metadata-record></metadata-records></connection>
<object-graph><objects>
<object id="a" caption="Header"><properties context=""><relation type="join" join="left">
<clause type="join"><expression op="="><expression op="[A].[ID]"/><expression op="[B].[ID]"/></expression></clause>
<relation type="table" name="A" table="[db].[A]"/><relation type="table" name="B" table="[db].[B]"/></relation></properties>
<properties context="extract"><relation type="table" table="[Extract].[A]"/></properties></object>
<object id="b" caption="Payments"><properties><relation type="union"><relation type="table" table="[Current]"/><relation type="table" table="[Archive]"/></relation></properties></object>
</objects><relationships><relationship cardinality="one-to-many"><expression op="="><expression op="[ID]"/><expression op="[HeaderID]"/></expression>
<first-end-point object-id="a" unique-key="true" referential-integrity="some-records-match"/><second-end-point object-id="b"/></relationship></relationships></object-graph>
</datasource><datasource name="published"/></datasources></workbook>'''


def extract(xml=XML):
    root = ET.fromstring(xml)
    facts = intake.parse_workbook(root, [], [], {})
    facts["workbook"]["name"] = "Example"
    intake.assign_ids(facts, intake.IdAssigner())
    facts["model_metadata_version"] = 1
    facts["provenance"] = {"input_sha256": "a" * 64}
    model_structure.extract_model_structure(root, facts["datasources"])
    return facts


class TableauModelTests(unittest.TestCase):
    def test_logical_physical_join_union_and_context_stay_separate(self):
        facts = extract()
        model = facts["datasources"][0]["model_structure"]
        self.assertEqual([table["caption"] for table in model["logical_tables"]], ["Header", "Payments"])
        self.assertEqual(len(model["relations"]), 9)
        join = next(item for item in model["relations"] if item["type"] == "join")
        self.assertEqual(join["join_type"], "left")
        self.assertEqual(len([item for item in model["relations"] if item["parent_relation_id"] == join["id"]]), 2)
        self.assertEqual(join["clauses"][0]["children"][0]["attributes"]["op"], "=")
        union = next(item for item in model["relations"] if item["type"] == "union")
        self.assertEqual(len([item for item in model["relations"] if item["parent_relation_id"] == union["id"]]), 2)
        self.assertEqual(len([item for item in model["relations"] if item["context"] == "extract"]), 1)
        self.assertIsNone(model["relations"][0]["logical_table_id"])
        self.assertFalse(model_structure.validate_model_structure(facts))

    def test_settings_and_cached_flags_do_not_become_constraints(self):
        model = extract()["datasources"][0]["model_structure"]
        endpoint = model["relationships"][0]["endpoints"][0]
        self.assertEqual(endpoint["configured_settings"]["unique-key"], "true")
        self.assertEqual(endpoint["configured_settings"]["referential-integrity"], "some-records-match")
        self.assertNotIn("cardinality", model["relationships"][0]["endpoints"][1]["configured_settings"])
        column = model["column_metadata"][0]
        self.assertEqual(column["source_declared_nullable"], "false")
        self.assertEqual(column["cached_contains_null"], "true")
        self.assertNotIn("verified", str(model))

    def test_namespaces_preserve_extraction_and_existing_ids(self):
        plain = extract()
        namespaced = extract(XML.replace('<workbook version=', '<workbook xmlns="urn:test" version='))
        self.assertEqual(plain, namespaced)
        root = ET.fromstring(XML)
        old = intake.parse_workbook(root, [], [], {})
        old["workbook"]["name"] = "Example"
        intake.assign_ids(old, intake.IdAssigner())
        self.assertEqual(old["datasources"][0]["fields"], plain["datasources"][0]["fields"])
        prefixed = '<t:workbook xmlns:t="urn:test"><t:datasources><t:datasource name="x"/></t:datasources></t:workbook>'
        decoded, container, entry = intake.load_workbook_document(prefixed.encode(), [], [])
        self.assertEqual(container, "twb")
        self.assertEqual(extract(decoded)["datasources"][0]["name"], "x")

    def test_missing_and_unsupported_structure_is_explicit(self):
        facts = extract(XML.replace('type="union"', 'type="unknown"').replace('object-id="b"', 'object-id="missing"'))
        codes = {item["code"] for source in facts["datasources"] for item in source["model_structure"]["gaps"]}
        self.assertTrue({"UNSUPPORTED_RELATION_TYPE", "UNRESOLVED_RELATIONSHIP_ENDPOINT", "NO_LOGICAL_OBJECT_GRAPH", "NO_RELATIONS_RECORDED"} <= codes)
        missing = facts["datasources"][0]["model_structure"]["relationships"][0]["endpoints"][1]
        self.assertIsNone(missing["logical_table_id"])

    def test_optional_extension_schema_and_reference_validation(self):
        facts = extract()
        schema = json.loads((ROOT / "docs/shared/workbook-facts.schema.json").read_text())
        for source in facts["datasources"]:
            self.assertFalse(schema_check.validate(source["model_structure"], {**schema, "$ref": "#/$defs/model_structure"}))
        facts["datasources"][0]["model_structure"]["relations"][0]["parent_relation_id"] = "missing"
        self.assertIn("MODEL_UNKNOWN_REFERENCE", {item["code"] for item in model_structure.validate_model_structure(facts)})
        del facts["model_metadata_version"]
        self.assertIn("MODEL_VERSION_REQUIRED", {item["code"] for item in model_structure.validate_model_structure(facts)})

    def test_model_schema_seed_snapshot_and_no_universal_grain(self):
        facts = extract()
        model = model_spec.seed(facts, "example.dataset")
        schema = json.loads((ROOT / "skills/dia-tableau-dataset-intelligence/references/data-model.schema.json").read_text())
        self.assertFalse(schema_check.validate(model, schema))
        self.assertFalse(model_spec.validate(model, facts))
        self.assertEqual(len(model["grains"]), 2)
        self.assertTrue(all(item["verification"] == "not_tested" for item in model["grains"]))
        damaged = copy.deepcopy(model)
        damaged["structural_snapshot"][0]["model_structure"]["logical_tables"][0]["caption"] = "Changed"
        self.assertIn("MODEL_SNAPSHOT_MISMATCH", {item["code"] for item in model_spec.validate(damaged, facts)})
        damaged = copy.deepcopy(model)
        damaged["grains"][0]["verification"] = "passed"
        damaged["grains"][0]["status"] = "confirmed"
        self.assertTrue({"UNSUPPORTED_VERIFICATION", "CONFIRMATION_ATTRIBUTION"} <= {item["code"] for item in model_spec.validate(damaged, facts)})
        rendered = model_spec.render(model)
        self.assertIn("Grain by table", rendered)
        self.assertIn("Recorded settings", rendered)
        self.assertIn("no data tests were run", rendered)

    def test_physical_only_model_uses_distinct_leaf_grains(self):
        facts = extract('<workbook><datasources><datasource name="x"><connection><relation type="join" join="inner"><relation type="table" table="[A]"/><relation type="table" table="[B]"/></relation></connection></datasource></datasources></workbook>')
        model = model_spec.seed(facts, "example")
        self.assertEqual(len(model["grains"]), 2)
        self.assertFalse(model_spec.validate(model, facts))
        self.assertEqual(len(model["structural_snapshot"][0]["model_structure"]["gaps"]), 1)

    def test_known_field_binding_cannot_silently_move_between_grains(self):
        facts = extract()
        model = model_spec.seed(facts, "example.dataset")
        fields = {item["name"]: item["id"] for item in facts["datasources"][0]["fields"]}
        model["grains"][1]["field_ids"] = [fields["[ID]"]]
        self.assertIn("FIELD_TABLE_MISMATCH", {item["code"] for item in model_spec.validate(model, facts)})
        # No recorded physical binding for Amount. A proposed interpretation
        # remains possible without inventing evidence or claiming a data test.
        model["grains"][1]["field_ids"] = [fields["[Amount]"]]
        self.assertFalse(model_spec.validate(model, facts))

    def test_missing_model_stays_an_explicit_gap_after_review(self):
        facts = extract('<workbook><datasources><datasource name="published"/></datasources></workbook>')
        model = model_spec.seed(facts, "example.dataset")
        model["reviewed"] = True
        gaps = model["structural_snapshot"][0]["model_structure"]["gaps"]
        model["open_questions"] = [{"id": "example.dataset.model-question.1",
            "question": "Can the owner supply the published source model and table grains?",
            "evidence": [item["id"] for item in gaps]}]
        self.assertFalse(model_spec.validate(model, facts))
        self.assertFalse(model["grains"])
        self.assertEqual({item["code"] for item in gaps}, {"NO_LOGICAL_OBJECT_GRAPH", "NO_RELATIONS_RECORDED"})
        self.assertIn("No physical relation tree is recorded", model_spec.render(model))


if __name__ == "__main__":
    unittest.main()
