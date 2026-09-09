"""gauge.py — parsing the seat's usage payload without touching the network."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gauge  # noqa: E402

PAYLOAD = {
    "five_hour": {"utilization": 29, "resets_at": "2000-01-01T17:30:00Z"},
    "seven_day": {"utilization": 92, "resets_at": "2000-01-04T15:00:00Z"},
    "seven_day_opus": {"utilization": 61, "resets_at": "2000-01-04T15:00:00Z"},
    "seven_day_sonnet": None,
    "limits": [
        {"kind": "session", "percent": 29, "resets_at": "2000-01-01T17:30:00Z"},
        {"kind": "weekly_all", "percent": 92, "resets_at": "2000-01-04T15:00:00Z"},
        {"kind": "weekly_scoped", "percent": 100, "resets_at": "2000-01-04T15:00:00Z"},
    ],
}


class ParseMeters(unittest.TestCase):
    def test_full_payload(self):
        m = gauge.parse_meters(PAYLOAD)
        self.assertEqual(m["five_hour"], 29.0)
        self.assertEqual(m["weekly_all"], 92.0)
        self.assertEqual(m["weekly_fable"], 100.0)
        self.assertEqual(m["weekly_opus"], 61.0)
        self.assertEqual(m["five_hour_resets_at"], "2000-01-01T17:30:00Z")
        self.assertEqual(m["weekly_resets_at"], "2000-01-04T15:00:00Z")
        self.assertEqual(m["fable_resets_at"], "2000-01-04T15:00:00Z")
        self.assertIsInstance(m["read_at"], float)

    def test_missing_fields_are_none_never_zero(self):
        m = gauge.parse_meters({})
        for k in ("five_hour", "weekly_all", "weekly_fable", "weekly_opus",
                  "five_hour_resets_at", "weekly_resets_at", "fable_resets_at"):
            self.assertIsNone(m[k], k)

    def test_limit_rows_fill_missing_top_level_fields(self):
        p = {"limits": PAYLOAD["limits"]}
        m = gauge.parse_meters(p)
        self.assertEqual(m["five_hour"], 29.0)
        self.assertEqual(m["weekly_all"], 92.0)
        self.assertEqual(m["weekly_fable"], 100.0)

    def test_garbage_is_tolerated(self):
        m = gauge.parse_meters({"five_hour": "x", "seven_day": {"utilization": "n/a"},
                                "seven_day_opus": 5, "limits": ["bad", {"kind": 1}]})
        self.assertIsNone(m["five_hour"])
        self.assertIsNone(m["weekly_all"])
        self.assertIsNone(m["weekly_opus"])
        self.assertIsNone(m["weekly_fable"])


class ToEpoch(unittest.TestCase):
    def test_zulu_and_offset_agree(self):
        z = gauge.to_epoch("2000-01-01T12:00:00Z")
        o = gauge.to_epoch("2000-01-01T07:00:00-05:00")
        self.assertEqual(z, o)
        self.assertEqual(z, 946728000.0)

    def test_naive_is_utc(self):
        self.assertEqual(gauge.to_epoch("2000-01-01T12:00:00"), 946728000.0)

    def test_unparseable_is_none(self):
        for bad in (None, "", "soon", 12, "2000-13-45T99:00:00Z"):
            self.assertIsNone(gauge.to_epoch(bad))


class Credential(unittest.TestCase):
    def test_load_rejects_non_login_shapes(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"token": "not-a-login"}, f)
            with self.assertRaises(gauge.GaugeError):
                gauge.load(p)

    def test_save_is_owner_only_and_round_trips(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            gauge.save({"claudeAiOauth": {"accessToken": "a", "refreshToken": "r",
                                          "expiresAt": 1}}, p)
            with open(p, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["claudeAiOauth"]["accessToken"], "a")
            if os.name == "posix":
                self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
