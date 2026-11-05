# -*- coding: utf-8 -*-
"""Read a markdown file's YAML frontmatter: a small stdlib subset of YAML, enough for
SKILL.md and agent files (plain, quoted, literal | and folded > scalars). No PyYAML."""
import re

_FRONTMATTER = re.compile(r"^---[ \t]*\n(.*?)^---[ \t]*$", re.S | re.M)
_TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*):(?:[ \t]+(.*?))?[ \t]*$")
_BLOCK_HEADER = re.compile(r"^([|>])[0-9+-]*(?:[ \t]+#.*)?$")
_ESCAPES = {"n": "\n", "t": "\t"}


def _block_scalar(style, lines):
    """A YAML literal (|) or folded (>) block: drop the common indent, then keep the
    line breaks (literal) or fold single breaks into spaces (folded)."""
    body = list(lines)
    while body and not body[-1].strip():
        body.pop()
    indent = min((len(l) - len(l.lstrip(" ")) for l in body if l.strip()), default=0)
    body = [l[indent:] for l in body]
    if style == "|":
        return "\n".join(body)
    paras, cur = [], []
    for l in body + [""]:
        if l.strip():
            cur.append(l.strip())
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    return "\n".join(paras)


def _scalar(first, more):
    """One top-level YAML scalar. `first` is the text after `key:`, `more` its indented
    continuation lines. Handles plain, single- and double-quoted, and block (| >) scalars."""
    if _BLOCK_HEADER.match(first):
        return _block_scalar(first[0], more)
    flat = " ".join([first] + [l.strip() for l in more if l.strip()]).strip()
    if flat.startswith('"'):
        m = re.match(r'"((?:[^"\\]|\\.)*)"', flat)
        inner = m.group(1) if m else flat[1:]
        return re.sub(r"\\(.)", lambda e: _ESCAPES.get(e.group(1), e.group(1)), inner)
    if flat.startswith("'"):
        m = re.match(r"'((?:[^']|'')*)'", flat)
        return (m.group(1) if m else flat[1:]).replace("''", "'")
    return flat


def _top_level_scalars(block):
    """Top-level `key: value` pairs of a frontmatter block: a small YAML subset, enough
    for SKILL.md and agent files, with no PyYAML dependency. First occurrence wins."""
    out, lines, i = {}, block.splitlines(), 0
    while i < len(lines):
        m = _TOP_KEY.match(lines[i])
        i += 1
        if not m:
            continue
        more = []
        while i < len(lines) and (not lines[i].strip() or lines[i][:1] in " \t"):
            more.append(lines[i])
            i += 1
        out.setdefault(m.group(1), _scalar(m.group(2) or "", more))
    return out


def frontmatter(path):
    """(name, description) from a markdown file's YAML frontmatter; ("", "") if unreadable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read(16000).lstrip("﻿")
    except OSError:
        return "", ""
    m = _FRONTMATTER.search(txt)
    fields = _top_level_scalars(m.group(1) if m else txt)
    return fields.get("name", "").strip(), fields.get("description", "").strip()
