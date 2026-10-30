"""Shared constants and helpers for the workbook-facts v2 pipeline."""

from __future__ import annotations

import hashlib


SCHEMA_VERSION = 2
TOOL_VERSION = "2.0.0"
SCHEMA_URL = (
    "https://github.com/UC-San-Diego-DIA/DIA-Harness-Skills/blob/main/"
    "docs/shared/workbook-facts.schema.json"
)

ROLE_VOCABULARY = [
    "kpi_card",
    "trend_chart",
    "breakdown_chart",
    "distribution_chart",
    "table",
    "text_annotation",
    "data_date_stamp",
    "map",
    "filter_panel",
    "other",
]

ANOMALY_CODES = [
    "EMPTY_ZONE",
    "DUPLICATE_SHEET_NAME",
    "ORPHAN_SHEET",
    "ID_COLLISION",
    "UNRECOGNIZED_ZONE",
    "MULTIPLE_TWB_ENTRIES",
    "STORY_NOT_INVENTORIED",
    "UNCLASSIFIED_WARNING",
]


def slugify(text):
    """Contract slug rule: lowercase, spaces and / ( ) to hyphens, collapse
    repeated hyphens, strip trailing hyphens."""
    lowered = str(text).lower()
    for char in (" ", "/", "(", ")"):
        lowered = lowered.replace(char, "-")
    while "--" in lowered:
        lowered = lowered.replace("--", "-")
    return lowered.rstrip("-")


class IdAssigner:
    """Assigns unique IDs with the contract's _2/_3 collision suffixes."""

    def __init__(self):
        self.used = {}
        self.collisions = []

    def assign(self, proposed, evidence):
        if proposed not in self.used:
            self.used[proposed] = 1
            return proposed
        suffix = self.used[proposed] + 1
        self.used[proposed] = suffix
        final = f"{proposed}_{suffix}"
        self.collisions.append(
            {"proposed": proposed, "final": final, "evidence": evidence}
        )
        return final


def build_provenance(
    input_sha256, extracted_at, container, entry, input_file, reason=None
):
    digest_text = input_sha256 if input_sha256 else "null"
    run_id = hashlib.sha256(
        f"{digest_text}:{extracted_at}".encode("utf-8")
    ).hexdigest()[:12]
    provenance = {
        "run_id": run_id,
        "tool_version": TOOL_VERSION,
        "input_file": input_file,
        "input_sha256": input_sha256,
        "container": container,
        "entry": entry,
        "extracted_at": extracted_at,
        "schema_url": SCHEMA_URL,
    }
    if reason is not None:
        provenance["input_sha256_reason"] = reason
    return provenance
