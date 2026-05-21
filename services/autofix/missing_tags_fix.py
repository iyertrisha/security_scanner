"""Deterministic Terraform tag merge for MISSING_TAGS autofix (no LLM)."""

from __future__ import annotations

import re
from typing import Optional

_RESOURCE_HEAD = re.compile(
    r'^(\s*)resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
    re.MULTILINE,
)

_TAG_HEADER = re.compile(r"^(\s*)tags\s*=\s*\{", re.MULTILINE)

REQUIRED_TAGS = ("environment", "owner", "project")


def canonical_basename(p: str) -> str:
    return p.replace("\\", "/").rstrip("/").split("/")[-1]


def _tag_key_present(text: str, key: str) -> bool:
    return bool(re.search(rf"^\s*{re.escape(key)}\s*=", text, re.MULTILINE | re.IGNORECASE))


def _find_matching_brace(s: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    while i < len(s):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _locate_resource_block(content: str, resource_type: str, resource_name: str) -> tuple[int, int] | None:
    for m in _RESOURCE_HEAD.finditer(content):
        rtype, rname = m.group(2), m.group(3)
        if rtype != resource_type or rname != resource_name:
            continue
        brace_open = content.find("{", m.start())
        if brace_open < 0:
            continue
        close = _find_matching_brace(content, brace_open)
        if close < 0:
            continue
        return m.start(), close + 1
    return None


def _resource_indent(block_text: str) -> str:
    m = re.match(r"^(\s*)", block_text)
    return m.group(1) if m else ""


def apply_missing_tags_terraform(content: str, resource_id: str) -> tuple[str, bool]:
    parts = resource_id.split(".", 1)
    if len(parts) != 2:
        return content, False
    rtype, rname = parts[0], parts[1]
    span = _locate_resource_block(content, rtype, rname)
    if span is None:
        return content, False
    start, end = span
    block = content[start:end]
    brace0 = block.find("{")
    if brace0 < 0:
        return content, False
    outer_close = _find_matching_brace(block, brace0)
    if outer_close < 0:
        return content, False

    ri = _resource_indent(block)
    prop_indent = ri + "  "
    key_indent = ri + "    "

    inner = block[brace0 + 1 : outer_close]

    tm = _TAG_HEADER.search(inner)
    if tm:
        tags_brace = inner.find("{", tm.start())
        if tags_brace < 0:
            return content, False
        tags_close = _find_matching_brace(inner, tags_brace)
        if tags_close < 0:
            return content, False
        tags_body = inner[tags_brace + 1 : tags_close]
        missing = [k for k in REQUIRED_TAGS if not _tag_key_present(tags_body, k)]
        if not missing:
            return content, False
        new_lines = "\n".join(f"{key_indent}{k} = var.{k}" for k in missing)
        last_nl = inner.rfind("\n", 0, tags_close)
        if last_nl < 0:
            insert_at = tags_close
        else:
            insert_at = last_nl + 1
        new_inner = inner[:insert_at] + new_lines + "\n" + inner[insert_at:]
        new_block = block[: brace0 + 1] + new_inner + block[outer_close:]
        return content[:start] + new_block + content[end:], True

    if any(_tag_key_present(inner, k) for k in REQUIRED_TAGS):
        return content, False

    tags_block = (
        f"\n{prop_indent}tags = {{\n"
        f"{key_indent}environment = var.environment\n"
        f"{key_indent}owner       = var.owner\n"
        f"{key_indent}project     = var.project\n"
        f"{prop_indent}}}\n"
    )
    new_block = block[: brace0 + 1] + tags_block + inner + block[outer_close:]
    return content[:start] + new_block + content[end:], True


def try_apply_missing_tags(
    file_map: dict[str, str],
    resource_id: str,
    source_file: Optional[str],
) -> tuple[dict[str, str], bool]:
    if not resource_id or not source_file:
        return file_map, False
    basename = canonical_basename(source_file)
    if source_file in file_map:
        paths = [source_file]
    else:
        cand = [
            k
            for k in file_map
            if k.endswith("/" + basename) or canonical_basename(k) == basename
        ]
        paths = cand if len(cand) == 1 else []

    if len(paths) != 1:
        return file_map, False
    path = paths[0]
    body = file_map[path]
    if not path.endswith(".tf"):
        return file_map, False
    nb, ok = apply_missing_tags_terraform(body, resource_id)
    if not ok:
        return file_map, False
    out = dict(file_map)
    out[path] = nb
    return out, True
