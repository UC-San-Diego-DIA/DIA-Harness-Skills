"""Minimal YAML reader for the block-style YAML emitted by
dia-data-model-intake. Standard library only.

Supports the deterministic subset used by model-facts.yaml: nested mappings
(keys may contain colons, as in catalog metadata), lists of scalars and
mappings, quoted strings with escapes, literal block scalars (|-), inline
empty collections, and common scalar types.
"""

from __future__ import annotations

import re


INT_RE = re.compile(r"[-+]?\d+")
FLOAT_RE = re.compile(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?")
UNICODE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


class YamlError(Exception):
    """Raised when the input is not in the supported YAML subset."""


def _column(line):
    return len(line) - len(line.lstrip(" "))


def _content_line(lines, index):
    """Return (index, line) of the next non-blank, non-comment line."""
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            index += 1
            continue
        return index, line
    return index, None


def _split_key(text):
    """Split 'key: value' where the key itself may contain a colon."""
    for index, char in enumerate(text):
        if char == ":" and (index + 1 == len(text) or text[index + 1] in " \t"):
            return text[:index], text[index + 1:].strip()
    return None


def _parse_block_scalar(lines, index, parent_indent):
    """Read a literal block; the content indent comes from the first line."""
    collected = []
    content_indent = None
    while index < len(lines):
        line = lines[index]
        if line.strip() == "":
            collected.append("")
            index += 1
            continue
        column = _column(line)
        if content_indent is None:
            if column <= parent_indent:
                break
            content_indent = column
        if column < content_indent:
            break
        collected.append(line[content_indent:].rstrip())
        index += 1
    while collected and collected[-1] == "":
        collected.pop()
    return "\n".join(collected), index


def _parse_quoted(text):
    if not text.startswith('"') or not text.endswith('"'):
        raise YamlError(f"malformed quoted scalar: {text!r}")
    body = text[1:-1]
    out = []
    i = 0
    while i < len(body):
        char = body[i]
        if char != "\\":
            out.append(char)
            i += 1
            continue
        if i + 1 >= len(body):
            raise YamlError(f"dangling escape in scalar: {text!r}")
        nxt = body[i + 1]
        if nxt == "u":
            match = UNICODE_RE.match(body, i)
            if match is None:
                raise YamlError(f"malformed unicode escape in scalar: {text!r}")
            out.append(chr(int(match.group(1), 16)))
            i = match.end()
            continue
        mapped = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt)
        if mapped is None:
            raise YamlError(f"unsupported escape \\{nxt} in scalar: {text!r}")
        out.append(mapped)
        i += 2
    return "".join(out)


def _parse_scalar(text):
    text = text.strip()
    if text in ("", "null", "~"):
        return None
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith('"'):
        return _parse_quoted(text)
    if INT_RE.fullmatch(text):
        return int(text)
    if FLOAT_RE.fullmatch(text):
        return float(text)
    if " #" in text:
        raise YamlError(f"unquoted scalar contains a comment marker: {text!r}")
    return text


def _parse_value_after_key(lines, index, value_text, key_indent):
    if value_text is None or value_text == "":
        child_index, child_line = _content_line(lines, index)
        if child_line is None or _column(child_line) <= key_indent:
            return {}, child_index
        return _parse_block(lines, child_index, _column(child_line))
    if value_text in ("|", "|-", "|+"):
        return _parse_block_scalar(lines, index, key_indent)
    return _parse_scalar(value_text), index


def _parse_block(lines, index, indent):
    index, line = _content_line(lines, index)
    if line is None:
        return None, index
    if _column(line) < indent:
        indent = _column(line)
    if line.lstrip().startswith("- ") or line.lstrip() == "-":
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent, None)


def _parse_list(lines, index, indent):
    result = []
    while index < len(lines):
        index, line = _content_line(lines, index)
        if line is None or _column(line) != indent:
            break
        stripped = line.lstrip()
        if not (stripped == "-" or stripped.startswith("- ")):
            break
        rest = stripped[1:].strip()
        if rest == "":
            child_index, child_line = _content_line(lines, index + 1)
            if child_line is None or _column(child_line) <= indent:
                result.append(None)
                index = child_index
            else:
                item, index = _parse_block(lines, index + 1, _column(child_line))
                result.append(item)
        elif rest in ("|", "|-", "|+"):
            item, index = _parse_block_scalar(lines, index + 1, indent)
            result.append(item)
        else:
            key_match = _split_key(rest)
            if key_match is not None:
                key, value_text = key_match
                item = {}
                item[key], index = _parse_value_after_key(
                    lines, index + 1, value_text, indent + 2
                )
                item, index = _parse_mapping(lines, index, indent + 2, item)
                result.append(item)
            else:
                result.append(_parse_scalar(rest))
                index += 1
    return result, index


def _parse_mapping(lines, index, indent, seed):
    result = seed if seed is not None else {}
    while index < len(lines):
        index, line = _content_line(lines, index)
        if line is None or _column(line) != indent:
            break
        stripped = line.lstrip()
        if stripped == "-" or stripped.startswith("- "):
            break
        key_match = _split_key(stripped)
        if key_match is None:
            raise YamlError(f"cannot parse line as a mapping entry: {line!r}")
        key, value_text = key_match
        result[key], index = _parse_value_after_key(lines, index + 1, value_text, indent)
    return result, index


def load(text):
    lines = [line.rstrip("\r") for line in text.split("\n")]
    value, index = _parse_block(lines, 0, 0)
    _, remaining = _content_line(lines, index)
    if remaining is not None:
        raise YamlError(f"trailing content after line {index}: {remaining!r}")
    return value
