"""Synthetic Hyper integration, evidence integrity, and opt-in boundary checks."""

import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
from test_tableau_pack import ROOT, SCRIPTS, XML, enrich_fixture, pack, runtime, save

import value_profiler

try:
    import tableauhyperapi as hyper
except ImportError:
    hyper = None


class OptInTests(unittest.TestCase):
    def test_default_never_imports_hyper_or_reads_extract(self):
        with tempfile.TemporaryDirectory(prefix="dia-profile-off-") as temporary:
            base = Path(temporary)
            source = base / "Synthetic.twbx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("Synthetic.twb", XML)
                archive.writestr("Data/invalid.hyper", b"Deliberately invalid; must never be opened")
            with patch.dict(sys.modules, {"tableauhyperapi": None}), patch.object(value_profiler, "profile", side_effect=AssertionError):
                pack.initialize(source, base / "pack", "synthetic.payments", "Synthetic", "synthetic")
                enrich_fixture(base / "pack")
                pack.finalize(base / "pack")
                self.assertEqual(pack.validate(base / "pack"), [])
            manifest = runtime.load(base / "pack/dataset.yaml")
            self.assertNotIn("value_profile", manifest["source"])
            self.assertEqual(manifest["data_verification"], "not_tested")
            self.assertFalse((base / "pack/evidence/value-profile.yaml").exists())

    def test_missing_dependency_has_actionable_error(self):
        with tempfile.TemporaryDirectory(prefix="dia-profile-missing-") as temporary:
            base = Path(temporary)
            source = base / "Synthetic.twbx"
            source.write_bytes(b"synthetic")
            with patch.dict(sys.modules, {"tableauhyperapi": None}):
                with self.assertRaisesRegex(RuntimeError, "requires tableauhyperapi"):
                    value_profiler.profile(source, base / "pack", runtime.digest(source))
            self.assertFalse((base / "pack/evidence/value-profile.yaml").exists())


@unittest.skipIf(hyper is None, "Install tableauhyperapi to run native Hyper integration tests")
class ValueProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dia-profile-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.extract = self.base / "synthetic.hyper"
        with hyper.HyperProcess(hyper.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                                parameters={"log_config": "", "log_dir": str(self.base), "use_tcp_port": "off"}) as process:
            with hyper.Connection(process.endpoint, self.extract, hyper.CreateMode.CREATE) as connection:
                connection.execute_command('CREATE SCHEMA "Extract"')
                connection.execute_command('CREATE TABLE "Extract"."Payments" '
                                           '("ID" TEXT, "Amount" NUMERIC(18,2), "Date" DATE, '
                                           '"hundred" INTEGER, "many" INTEGER, "all_null" TEXT, "quote\"\"field" BOOLEAN)')
                table = hyper.TableName("Extract", "Payments")
                from datetime import date
                from decimal import Decimal
                with hyper.Inserter(connection, table) as inserter:
                    inserter.add_rows([("A" if i < 60 else ("" if i < 100 else None), Decimal("1.25"),
                                        date(2026, 1, 1), i % 100, i, None, i % 2 == 0) for i in range(101)])
                    inserter.execute()
                connection.execute_command('CREATE SCHEMA "Other"')
                connection.execute_command('CREATE TABLE "Other"."Payments" ("ID" TEXT)')
        self.source = self.base / "Synthetic.twbx"
        self.package()
        self.root = self.base / "pack"

    def package(self, extra=None):
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("Synthetic.twb", XML)
            # Traversal entry is deliberately harmless: no archive path is extracted.
            archive.write(self.extract, "../../Data/synthetic.hyper")
            if extra:
                archive.writestr(extra, b"not a Hyper file")

    def initialize(self):
        with redirect_stdout(io.StringIO()):
            pack.initialize(self.source, self.root, "synthetic.payments", "Synthetic", "synthetic", profile_values=True)
        return runtime.load(self.root / value_profiler.PROFILE_PATH)

    def test_counts_caps_types_and_immutable_local_evidence(self):
        before = runtime.digest(self.source), runtime.digest(self.extract)
        connection_factory = hyper.Connection

        def require_readonly(*args, **kwargs):
            connection = connection_factory(*args, **kwargs)
            try:
                with self.assertRaises(hyper.HyperException):
                    connection.execute_command('DELETE FROM "Extract"."Payments"')
            except BaseException:
                connection.close()
                raise
            return connection

        with patch.object(hyper, "Connection", side_effect=require_readonly):
            profile = self.initialize()
        self.assertEqual(value_profiler.validate(profile, before[0]), [])
        self.assertEqual(profile["provenance"]["extract_sha256"], before[1])
        self.assertEqual(before, (runtime.digest(self.source), runtime.digest(self.extract)))
        table = next(t for t in profile["tables"] if t["schema"] == "Extract")
        self.assertEqual(table["row_count"], 101)
        fields = {f["name"]: f for f in table["fields"]}
        self.assertEqual(fields["ID"]["null_count"], 1)
        self.assertEqual(fields["ID"]["values"], [{"value": "A", "count": 60}, {"value": "", "count": 40}])
        self.assertEqual(fields["hundred"]["distinct_count"], 100)
        self.assertEqual(len(fields["hundred"]["values"]), 50)
        self.assertTrue(fields["hundred"]["values_truncated"])
        self.assertEqual(fields["many"]["distinct_count"], 101)
        self.assertEqual(fields["many"]["values"], [])
        self.assertEqual(fields["all_null"]["null_count"], 101)
        self.assertEqual(fields["all_null"]["distinct_count"], 0)
        self.assertEqual(fields["Amount"]["values"][0]["value"], "1.25")
        self.assertEqual(fields["Date"]["values"][0]["value"], "2026-01-01")
        self.assertEqual(fields['quote"field']["distinct_count"], 2)
        self.assertEqual(next(t for t in profile["tables"] if t["schema"] == "Other")["row_count"], 0)
        self.assertEqual({p.name for p in (self.root / "evidence").iterdir()}, {"workbook-facts.yaml", "value-profile.yaml"})
        with self.assertRaisesRegex(ValueError, "immutable"):
            value_profiler.profile(self.source, self.root, before[0])

    def add_domain(self, profile):
        dictionary = runtime.load(self.root / "data-dictionary.yaml")
        field = next(f for f in dictionary["datasources"][0]["fields"] if f["name"] == "[ID]")
        table = next(t for t in profile["tables"] if t["schema"] == "Extract")
        column = next(c for c in table["fields"] if c["name"] == "ID")
        field["value_domain"] = {key: copy.deepcopy(column[key]) for key in
                                 ("null_count", "distinct_count", "values", "values_truncated")}
        field["value_domain"].update(row_count=table["row_count"], provenance={
            "profile_path": value_profiler.PROFILE_PATH, "profile_sha256": runtime.digest(self.root / value_profiler.PROFILE_PATH),
            "extract_sha256": profile["provenance"]["extract_sha256"], "schema": "Extract", "table": "Payments", "column": "ID"})
        field["enrichment"]["code_meanings"] = [{"code": "A", "meaning": {
            "text": "proposed from observed values: A may represent active records; confirm with the owner.",
            "basis": "observed_values", "confirmation_status": "unconfirmed", "confirmed_at": None, "confirmed_by": None,
            "evidence_refs": [field["id"], value_profiler.PROFILE_PATH]}}]
        save(self.root, "data-dictionary.yaml", dictionary)
        return dictionary, field

    def test_review_finalize_validate_portability_and_no_auto_approval(self):
        profile = self.initialize()
        enrich_fixture(self.root)
        dictionary, field = self.add_domain(profile)
        self.assertEqual(pack.validate(self.root), [])
        self.assertEqual(field["definition"]["confirmation_status"], "unconfirmed")
        self.assertEqual(runtime.load(self.root / "dataset.yaml")["data_verification"], "profiled")
        pack.finalize(self.root)
        self.assertEqual(pack.validate(self.root, require_sealed=True), [])
        moved = self.base / "moved"
        shutil.copytree(self.root, moved)
        self.source.unlink()
        self.extract.unlink()
        self.assertEqual(pack.validate(moved, require_sealed=True), [])
        evidence = moved / value_profiler.PROFILE_PATH
        evidence.write_bytes(evidence.read_bytes() + b"\n# changed\n")
        self.assertTrue(pack.validate(moved))

    def test_domain_observations_provenance_and_proposal_labels_are_checked(self):
        profile = self.initialize()
        enrich_fixture(self.root)
        dictionary, field = self.add_domain(profile)
        good = copy.deepcopy(dictionary)
        for key, value in (("null_count", 99), ("values", [])):
            field["value_domain"][key] = value
            self.assertTrue(runtime.dictionary.validate(dictionary, self.root / "data-dictionary.yaml"))
            dictionary = copy.deepcopy(good)
            field = next(f for f in dictionary["datasources"][0]["fields"] if f["name"] == "[ID]")
        field["value_domain"]["provenance"]["extract_sha256"] = "0" * 64
        self.assertTrue(runtime.dictionary.validate(dictionary, self.root / "data-dictionary.yaml"))
        dictionary = copy.deepcopy(good)
        field = next(f for f in dictionary["datasources"][0]["fields"] if f["name"] == "[ID]")
        meaning = field["enrichment"]["code_meanings"][0]["meaning"]
        meaning["text"] = "A means active."
        self.assertTrue(runtime.dictionary.validate(dictionary, self.root / "data-dictionary.yaml"))
        meaning["text"] = "proposed from observed values: A means active."
        meaning["confirmation_status"] = "confirmed"
        self.assertTrue(runtime.dictionary.validate(dictionary, self.root / "data-dictionary.yaml"))

    def test_bad_inputs_fail_without_profile_evidence(self):
        self.package(extra="Data/second.hyper")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.initialize()
        self.assertFalse((self.root / value_profiler.PROFILE_PATH).exists())
        source = self.base / "only.twb"
        source.write_text(XML)
        with self.assertRaisesRegex(ValueError, "requires a TWBX"):
            value_profiler.profile(source, self.base / "bare", runtime.digest(source))
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("Synthetic.twb", XML)
        with self.assertRaisesRegex(ValueError, "found 0"):
            value_profiler.profile(self.source, self.base / "missing", runtime.digest(self.source))
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("Synthetic.twb", XML)
            archive.writestr("Data/broken.hyper", b"not a Hyper database")
        failed = self.base / "failed"
        with self.assertRaisesRegex(RuntimeError, "Local Hyper profiling failed"):
            value_profiler.profile(self.source, failed, runtime.digest(self.source))
        self.assertFalse((failed / value_profiler.PROFILE_PATH).exists())
        self.assertEqual(list((failed / "evidence").iterdir()), [])

    def test_standalone_installed_cli_profiles_and_validates(self):
        target = self.base / "installed"
        installed = subprocess.run(["pwsh", "-NoProfile", "-File", str(ROOT / "scripts/install-skill.ps1"),
                                    "-Skill", "dia-tableau-dataset-intelligence", "-Destination", str(target), "-Force"],
                                   capture_output=True, text=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        entry = target / "dia-tableau-dataset-intelligence/scripts/pack.py"
        result = subprocess.run([sys.executable, str(entry), "init", "--input", str(self.source), "--output", str(self.root),
                                 "--dataset-id", "synthetic.payments", "--domain", "synthetic", "--profile-values"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "evidence/workbook-facts.yaml").is_file())
        profile = runtime.load(self.root / value_profiler.PROFILE_PATH)
        enrich_fixture(self.root)
        self.add_domain(profile)
        for command in ("finalize", "validate"):
            result = subprocess.run([sys.executable, str(entry), command, "--pack", str(self.root)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
