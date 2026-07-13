# -*- coding: utf-8 -*-
import matching


def test_slug_basic():
    assert matching.slug("Hello World") == "hello-world"
    assert matching.slug("Foo:Bar (baz)") == "foo-bar-baz"
    assert matching.slug("  --Trim--  ") == "trim"
    assert matching.slug("") == ""
    assert matching.slug(None) == ""
    assert matching.slug("already-a-slug") == "already-a-slug"


def test_nkey_strips_parens():
    # parenthetical suffix collapses to the same key as the bare name
    assert matching.nkey("Foo (plugin)") == matching.nkey("Foo") == "foo"
    assert matching.nkey("bar (v2) (beta)") == "bar"
    assert matching.nkey(None) == ""


def test_contains_model_fuzzy():
    keys = ["qwen3-embedding", "some-other-model"]
    # both sides >= 8 chars and one contains the other
    assert matching.contains("qwen3-embedding-0-6b", keys) is True
    assert matching.contains("qwen3-embedding", ["qwen3-embedding-0-6b"]) is True
    # short strings never match (guard against accidental collisions)
    assert matching.contains("short", ["shortish-but-long-enough"]) is False
    assert matching.contains("abc", ["abcdefghij"]) is False
    # no overlap
    assert matching.contains("qwen3-embedding", ["nomic-embed-text"]) is False


def test_dedup_key_casefold():
    assert matching.dedup_key("Foo") == "foo"
    assert matching.dedup_key("BAR-BAZ") == "bar-baz"
