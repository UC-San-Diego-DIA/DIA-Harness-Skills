"""Exercise installed explorer behavior using synthetic files in a temporary folder."""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]


def payload(path):
    html = Path(path).read_text(encoding="utf-8")
    match = re.search(r'<script id="explorer-data" type="application/json">(.*?)</script>', html, re.S)
    assert match, "Dashboard needs an embedded result payload"
    return json.loads(match[1]), html


def main():
    with tempfile.TemporaryDirectory(prefix="dia-explorer-test-") as tmp:
        base = Path(tmp)
        installed = base / "installed"
        subprocess.run(["pwsh", "-NoProfile", "-File", str(REPO / "scripts/install-skill.ps1"),
                        "-Skill", "dia-local-data-explorer", "-Destination", str(installed), "-Force"],
                       check=True, capture_output=True, text=True)
        helper = installed / "dia-local-data-explorer/scripts/local_data_explorer.py"
        assert (helper.parent / "duckdb_analysis.py").is_file()
        project = base / "project with spaces"

        def call(command, *args, bad=False, target=project):
            argv = [sys.executable, str(helper), command]
            if command != "inspect":
                argv += ["--project", str(target)]
            result = subprocess.run(argv + list(map(str, args)), capture_output=True, text=True, encoding="utf-8")
            if bad:
                assert result.returncode != 0, result.stdout
                return result.stderr
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)

        source = base / "activity.csv"
        injected = '</script><img src=x onerror="alert(1)">'
        with source.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows([
                ["team", "amount", "month"], ["A", 10, "2026-01"], ["A", 2, "2026-02"],
                ["B", -2, "2026-01"], [injected, 0, "2026-02"], ["C", "", "2026-02"]])
        original = source.read_bytes()
        state = call("init", "--source", source, "--title", "Synthetic activity")
        assert state["row_count"] == 5
        assert source.read_bytes() == original
        assert (project / state["snapshot"]).read_bytes() == original
        assert state["snapshot_hash"] == hashlib.sha256(original).hexdigest()
        for path in ["AGENTS.md", "README.md", "questions", "visuals", "reports"]:
            assert (project / path).exists()
        assert "new project" in call("init", "--source", source, "--title", "Overwrite", bad=True)
        assert "No saved" in call("build", bad=True)

        sql = base / "question.sql"

        def ask(statement, question="Amount by team?", max_rows=200):
            sql.write_text(statement, encoding="utf-8")
            return call("ask", "--question", question, "--sql-file", sql,
                        "--note", "Sum amount by team. Missing amounts excluded, with an explicit zero for all-missing groups.",
                        "--max-rows", max_rows)

        q = ask("SELECT team, coalesce(sum(amount), 0) AS total FROM dataset GROUP BY team ORDER BY team")
        assert q["rows"] == [["A", "12"], ["B", "-2"], ["C", "0"], [injected, "0"]] or {
            r[0]: str(r[1]) for r in q["rows"]} == {"A": "12", "B": "-2", "C": "0", injected: "0"}
        assert not q["truncated"]
        preview = call("visual", "--question-id", q["id"], "--kind", "bar", "--x", "team", "--y", "total", "--title", injected)
        content, html = payload(preview["preview"])
        assert content["panels"][0]["result"]["rows"] == q["rows"]
        assert injected not in html, "Cell values must never terminate the JSON script"
        assert "\\u003c/script\\u003e" in html
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\']https?://', html)
        call("save", "--visual-id", preview["id"])
        call("save", "--visual-id", preview["id"])
        assert call("status")["saved"] == [preview["id"]]

        draft = call("visual", "--question-id", q["id"], "--kind", "table", "--title", "Unsaved table")
        built = call("build")
        data, _ = payload(built["dashboard"])
        assert [p["id"] for p in data["panels"]] == [preview["id"]], "Only explicit saved choices belong in dashboards"
        assert data["snapshot_hash"] == state["snapshot_hash"]
        assert data["panels"][0]["result"]["sql"] == q["sql"]
        second = call("build")
        assert built["dashboard"] != second["dashboard"]
        call("save", "--visual-id", draft["id"])
        call("unsave", "--visual-id", preview["id"])
        assert call("build")["visual_ids"] == [draft["id"]]
        assert (project / "visuals" / (preview["id"] + ".json")).exists()

        # V1 supported visual shapes, including all-zero and negative data.
        monthly = ask("SELECT month, sum(amount) AS total FROM dataset GROUP BY month ORDER BY month")
        call("visual", "--question-id", monthly["id"], "--kind", "line", "--x", "month", "--y", "total", "--title", "Trend")
        single = ask("SELECT count(*) AS requests FROM dataset")
        call("visual", "--question-id", single["id"], "--kind", "kpi", "--y", "requests", "--title", "Requests")
        zero = ask("SELECT team, 0 AS total FROM dataset GROUP BY team")
        call("visual", "--question-id", zero["id"], "--kind", "bar", "--x", "team", "--y", "total", "--title", "Zero")

        # Incomplete and ambiguous chart data cannot become saved visuals.
        truncated = ask("SELECT * FROM dataset", max_rows=2)
        assert truncated["truncated"]
        call("visual", "--question-id", truncated["id"], "--kind", "table", "--title", "Partial", bad=True)
        duplicates = ask("SELECT team, amount FROM dataset")
        call("visual", "--question-id", duplicates["id"], "--kind", "bar", "--x", "team", "--y", "amount", "--title", "Invalid", bad=True)
        null = ask("SELECT 'A' AS team, NULL AS amount")
        call("visual", "--question-id", null["id"], "--kind", "bar", "--x", "team", "--y", "amount", "--title", "Missing", bad=True)
        large = ask("SELECT 9007199254740993 AS total")
        call("visual", "--question-id", large["id"], "--kind", "kpi", "--y", "total", "--title", "Too large", bad=True)
        call("save", "--visual-id", "../../escape", bad=True)

        # Query controls survive bundling and disallow other local files.
        for statement in ("DELETE FROM dataset", "SELECT 1; SELECT 2"):
            sql.write_text(statement, encoding="utf-8")
            call("ask", "--question", "Blocked", "--sql-file", sql, "--note", "test", bad=True)
        other = base / "other.csv"
        other.write_text("secret\nprivate\n", encoding="utf-8")
        sql.write_text("SELECT * FROM read_csv('" + str(other).replace("'", "''") + "')", encoding="utf-8")
        call("ask", "--question", "Other file", "--sql-file", sql, "--note", "test", bad=True)
        assert source.read_bytes() == original

        # Original file updates do not change the checked snapshot.
        source.write_text("different\n1\n", encoding="utf-8")
        assert call("status")["snapshot_hash"] == state["snapshot_hash"]
        snapshot = project / state["snapshot"]
        snapshot.write_text("changed\n1\n", encoding="utf-8")
        assert "Snapshot changed" in call("status", bad=True)
        call("build", bad=True)

        # XLSX selection is deterministic before any extension is installed.
        workbook = base / "sheets.xlsx"
        with zipfile.ZipFile(workbook, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="First" sheetId="1"/><sheet name="Second" sheetId="2"/></sheets></workbook>')
        sheets = call("inspect", "--source", workbook)
        assert "First" in str(sheets) and "Second" in str(sheets)
        unused = base / "ambiguous sheets"
        call("init", "--source", workbook, "--title", "Sheets", target=unused, bad=True)
        assert not unused.exists(), "Ambiguous sheets should fail before project writes"
        print("PASS: installed explorer lifecycle, selection, provenance, chart limits, escaping, query restrictions, and snapshot integrity")


if __name__ == "__main__":
    main()
