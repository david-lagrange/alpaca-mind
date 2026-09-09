"""The supervisor's alias resolution against the operator's alias table."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "engine"))

from supervisor import Supervisor  # noqa: E402


class _Log:
    def __init__(self):
        self.warns = []

    def warn(self, event, **kv):
        self.warns.append((event, kv))


class _Sup:
    """Just enough of a supervisor for _resolve_alias."""
    EFFORT_CHOICES = Supervisor.EFFORT_CHOICES

    def __init__(self, cfg_path):
        self.cfg_path = cfg_path
        self.log = _Log()


def resolve(table_text, alias="fable", effort="xhigh"):
    with tempfile.TemporaryDirectory() as d:
        cfg_path = os.path.join(d, "mind.yaml")
        if table_text is not None:
            with open(os.path.join(d, "aliases.json"), "w", encoding="utf-8") as f:
                f.write(table_text)
        sup = _Sup(cfg_path)
        out = Supervisor._resolve_alias(sup, alias, effort)
        return out, sup.log.warns


class ResolveAlias(unittest.TestCase):
    def test_absent_table_passes_through(self):
        (model, effort, sub), warns = resolve(None)
        self.assertEqual((model, effort, sub), ("fable", "xhigh", None))
        self.assertEqual(warns, [])

    def test_empty_table_passes_through(self):
        for text in ("{}", '{"aliases": {}}', '{"written_at": "x", "aliases": {}}'):
            (model, effort, sub), warns = resolve(text)
            self.assertEqual((model, effort, sub), ("fable", "xhigh", None), text)
            self.assertEqual(warns, [])

    def test_fallback_entry_resolves_model_effort_and_subagents(self):
        table = json.dumps({"written_at": "x",
                            "aliases": {"fable": {"model": "claude-opus-5", "effort": "max"}},
                            "subagent_model": "claude-opus-5"})
        (model, effort, sub), _ = resolve(table)
        self.assertEqual((model, effort, sub), ("claude-opus-5", "max", "claude-opus-5"))

    def test_other_aliases_untouched_but_subagents_follow(self):
        table = json.dumps({"aliases": {"fable": {"model": "claude-opus-5", "effort": "max"}},
                            "subagent_model": "claude-opus-5"})
        (model, effort, sub), _ = resolve(table, alias="opus", effort="medium")
        self.assertEqual((model, effort, sub), ("opus", "medium", "claude-opus-5"))

    def test_effort_only_overrides_when_named_and_valid(self):
        (model, effort, _), _ = resolve(json.dumps({"aliases": {"fable": {"model": "claude-opus-5"}}}))
        self.assertEqual((model, effort), ("claude-opus-5", "xhigh"))
        (model, effort, _), _ = resolve(json.dumps({"aliases": {"fable": {"model": "m", "effort": "ultra"}}}))
        self.assertEqual((model, effort), ("m", "xhigh"))
        (model, effort, _), _ = resolve(json.dumps({"aliases": {"fable": {"effort": "high"}}}))
        self.assertEqual((model, effort), ("fable", "high"))

    def test_malformed_table_warns_and_passes_through(self):
        for text in ("{not json", "[1, 2]", '{"aliases": "x"}'):
            (model, effort, sub), warns = resolve(text)
            self.assertEqual((model, effort, sub), ("fable", "xhigh", None), text)
        (_, _, _), warns = resolve("{not json")
        self.assertEqual(warns[0][0], "alias_table_unreadable")


if __name__ == "__main__":
    unittest.main()
