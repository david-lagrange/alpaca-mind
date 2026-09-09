"""seat_governor.py — the state machine under injected meters and a clock.

Every observation and action goes through a fake io object, so these
run anywhere: no box, no network, no credential.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import seat_governor as sg  # noqa: E402

T0 = 1_000_000_000.0
HOUR = 3600.0


def meters(five=10.0, weekly=50.0, fable=20.0, opus=None, five_reset=T0 + HOUR,
           weekly_reset=T0 + 3 * 24 * HOUR, fable_reset=T0 + 3 * 24 * HOUR):
    return {
        "five_hour": five, "five_hour_resets_at": sg.iso(five_reset),
        "weekly_all": weekly, "weekly_resets_at": sg.iso(weekly_reset),
        "weekly_fable": fable, "fable_resets_at": sg.iso(fable_reset),
        "weekly_opus": opus, "opus_resets_at": None, "read_at": T0,
    }


class FakeIO:
    def __init__(self, *, now=T0, meters=None, error=None, gauge=True,
                 halts=None, hold=None, table=None, state=None, pending=False):
        self.t = now
        self.meters = meters
        self.error = error
        self.gauge = gauge
        self.halts = halts or {"mind": "absent", "ui": "absent"}
        self.hold = hold
        self.table = table if table is not None else {}
        self.state = state or {}
        self.pending = pending
        self.actions = []
        self.logs = []
        self.rows = []
        self.alerts = []

    # observations
    def now(self):
        return self.t

    def gauge_present(self):
        return self.gauge

    def read_meters(self):
        return (None, self.error or "boom") if self.meters is None else (self.meters, None)

    def halt_state(self):
        return dict(self.halts)

    def read_hold(self):
        return dict(self.hold) if self.hold else None

    def read_table(self):
        return dict(self.table)

    def read_state(self):
        return dict(self.state)

    def wake_request_pending(self):
        return self.pending

    # actions
    def write_table(self, table):
        self.actions.append(("write_table", table))
        self.table = table

    def place_halts(self):
        self.actions.append(("place_halts",))
        for k in self.halts:
            if self.halts[k] == "absent":
                self.halts[k] = "marker"

    def remove_halts(self):
        self.actions.append(("remove_halts",))
        for k in self.halts:
            if self.halts[k] == "marker":
                self.halts[k] = "absent"

    def write_hold(self, hold):
        self.actions.append(("write_hold", hold))
        self.hold = hold

    def remove_hold(self):
        self.actions.append(("remove_hold",))
        self.hold = None

    def file_resume_wake(self, placed_at, lifted_at):
        self.actions.append(("file_resume_wake", placed_at, lifted_at))
        self.pending = True

    def manager_run_now(self):
        self.actions.append(("manager_run_now",))

    def write_state(self, st):
        self.actions.append(("write_state", st))
        self.state = st

    def alert(self, text):
        self.alerts.append(text)

    def telemetry(self, row):
        self.rows.append(row)

    def log(self, event, **kv):
        self.logs.append((event, kv))

    # helpers
    def names(self):
        return [a[0] for a in self.actions]

    def events(self):
        return [e for e, _ in self.logs]


CFG = sg.load_config({"OPS_DIR": "/nonexistent/ops",
                      "ENGINE_CONFIG_DIR": "/nonexistent/config"})


class ManualHalt(unittest.TestCase):
    def test_owner_halt_places_nothing(self):
        io = FakeIO(meters=meters(weekly=99.0), halts={"mind": "manual", "ui": "absent"})
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "manual_hold")
        self.assertNotIn("place_halts", io.names())
        self.assertNotIn("write_hold", io.names())
        self.assertIsNone(io.hold)

    def test_owner_halt_never_lifted_even_past_time(self):
        hold = {"kind": "weekly", "placed_at": T0 - HOUR, "until": T0 - 1, "placed_by": "governor"}
        io = FakeIO(meters=meters(weekly=10.0), hold=hold,
                    halts={"mind": "manual", "ui": "marker"})
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "manual_hold")
        self.assertNotIn("remove_halts", io.names())
        self.assertNotIn("remove_hold", io.names())
        self.assertIsNotNone(io.hold)

    def test_owner_halt_with_dead_gauge_still_stands_aside(self):
        hold = {"kind": "five_hour", "placed_at": T0 - HOUR, "until": T0 - 1, "placed_by": "governor"}
        io = FakeIO(meters=None, hold=hold, halts={"mind": "manual", "ui": "marker"})
        sg.tick(io, CFG)
        self.assertNotIn("remove_halts", io.names())

    def test_marker_without_sidecar_is_the_owners(self):
        io = FakeIO(meters=meters(weekly=99.0), halts={"mind": "marker", "ui": "marker"})
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "manual_hold")
        self.assertNotIn("write_hold", io.names())

    def test_table_still_follows_the_meter_under_an_owner_halt(self):
        io = FakeIO(meters=meters(fable=100.0), halts={"mind": "manual", "ui": "absent"})
        sg.tick(io, CFG)
        self.assertIn("write_table", io.names())
        self.assertEqual(io.table["aliases"]["fable"]["model"], "claude-opus-5")


class Holds(unittest.TestCase):
    def test_weekly_hold_placed_sidecar_before_files(self):
        io = FakeIO(meters=meters(weekly=97.0, weekly_reset=T0 + 2 * HOUR))
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "hold_weekly")
        self.assertEqual(io.names()[:2], ["write_hold", "place_halts"])
        self.assertEqual(io.hold["kind"], "weekly")
        self.assertEqual(io.hold["until"], T0 + 2 * HOUR + 120)
        self.assertEqual(io.halts, {"mind": "marker", "ui": "marker"})
        self.assertIn("hold_placed", row["events"])

    def test_below_threshold_places_nothing(self):
        io = FakeIO(meters=meters(weekly=96.9, five=87.9))
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "normal")
        self.assertIsNone(io.hold)

    def test_five_hour_hold(self):
        io = FakeIO(meters=meters(five=88.0, five_reset=T0 + 40 * 60))
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "hold_five_hour")
        self.assertEqual(io.hold["until"], T0 + 40 * 60 + 120)

    def test_weekly_outranks_five_hour(self):
        io = FakeIO(meters=meters(five=95.0, weekly=98.0, weekly_reset=T0 + 5 * HOUR))
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "hold_weekly")
        # ...and an existing five-hour hold is raised, not duplicated
        io2 = FakeIO(meters=meters(five=95.0, weekly=98.0, weekly_reset=T0 + 5 * HOUR),
                     hold={"kind": "five_hour", "placed_at": T0 - 600, "until": T0 + 600,
                           "placed_by": "governor"},
                     halts={"mind": "marker", "ui": "marker"})
        row2 = sg.tick(io2, CFG)
        self.assertEqual(row2["state"], "hold_weekly")
        self.assertEqual(io2.hold["kind"], "weekly")
        self.assertEqual(io2.hold["placed_at"], T0 - 600)
        self.assertNotIn("place_halts", io2.names())
        self.assertIn("hold_raised", row2["events"])

    def test_no_hold_without_a_reset_time(self):
        m = meters(weekly=99.0)
        m["weekly_resets_at"] = None
        io = FakeIO(meters=m)
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "normal")
        self.assertIn("hold_skipped", io.events())

    def test_no_hold_on_a_stale_read_whose_reset_has_passed(self):
        io = FakeIO(meters=meters(weekly=100.0, weekly_reset=T0 - 300))
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "normal")
        self.assertIsNone(io.hold)

    def test_reset_moving_moves_the_hold(self):
        hold = {"kind": "five_hour", "placed_at": T0 - 600, "until": T0 + 600, "placed_by": "governor"}
        io = FakeIO(meters=meters(five=90.0, five_reset=T0 + 1800), hold=hold,
                    halts={"mind": "marker", "ui": "marker"})
        sg.tick(io, CFG)
        self.assertEqual(io.hold["until"], T0 + 1800 + 120)
        self.assertIn("hold_moved", io.events())


class Lifts(unittest.TestCase):
    def _hold(self, kind="weekly", until=T0 - 1):
        return {"kind": kind, "placed_at": T0 - 4 * HOUR, "until": until, "placed_by": "governor"}

    def test_lift_by_time_with_a_dead_gauge(self):
        io = FakeIO(meters=None, hold=self._hold(), halts={"mind": "marker", "ui": "marker"})
        row = sg.tick(io, CFG)
        self.assertEqual(io.names()[:4],
                         ["remove_halts", "remove_hold", "file_resume_wake", "manager_run_now"])
        self.assertEqual(io.halts, {"mind": "absent", "ui": "absent"})
        self.assertIsNone(io.hold)
        self.assertIn("hold_lifted", row["events"])
        self.assertEqual(row["state"], "normal")

    def test_lift_by_time_with_a_live_gauge_still_high(self):
        # The meter lags the real reset: a stale 100% must not pin the hold.
        io = FakeIO(meters=meters(weekly=100.0, weekly_reset=T0 - 300), hold=self._hold(),
                    halts={"mind": "marker", "ui": "marker"})
        row = sg.tick(io, CFG)
        self.assertIn("hold_lifted", row["events"])
        self.assertIsNone(io.hold)
        self.assertEqual(row["state"], "normal")

    def test_no_lift_before_time_while_meter_high(self):
        io = FakeIO(meters=meters(weekly=98.0), hold=self._hold(until=T0 + 600),
                    halts={"mind": "marker", "ui": "marker"})
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "hold_weekly")
        self.assertNotIn("remove_halts", io.names())

    def test_lift_by_meter_uses_hysteresis(self):
        hold = self._hold(kind="five_hour", until=T0 + 600)
        io = FakeIO(meters=meters(five=80.0), hold=hold, halts={"mind": "marker", "ui": "marker"})
        sg.tick(io, CFG)
        self.assertNotIn("remove_halts", io.names())   # 80 is not below 88 - 10
        io = FakeIO(meters=meters(five=77.0), hold=hold, halts={"mind": "marker", "ui": "marker"})
        row = sg.tick(io, CFG)
        self.assertIn("hold_lifted", row["events"])

    def test_resume_wake_only_when_no_sensor_request_pending(self):
        io = FakeIO(meters=meters(), hold=self._hold(), halts={"mind": "marker", "ui": "marker"},
                    pending=True)
        sg.tick(io, CFG)
        self.assertNotIn("file_resume_wake", io.names())
        self.assertIn("manager_run_now", io.names())
        self.assertIn("resume_wake_deferred", io.events())

    def test_lift_removes_only_marker_files(self):
        # The owner's file on one agent appeared after the hold: stand aside.
        io = FakeIO(meters=meters(), hold=self._hold(), halts={"mind": "manual", "ui": "marker"})
        sg.tick(io, CFG)
        self.assertNotIn("remove_halts", io.names())


class AliasTable(unittest.TestCase):
    def test_fallback_at_threshold(self):
        io = FakeIO(meters=meters(fable=90.0))
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "fallback")
        self.assertEqual(io.table, {"aliases": {"fable": {"model": "claude-opus-5",
                                                          "effort": "max"}},
                                    "subagent_model": "claude-opus-5"})

    def test_hysteresis_band_keeps_the_table(self):
        fb = sg.fallback_table(CFG)
        io = FakeIO(meters=meters(fable=87.0), table=fb)
        row = sg.tick(io, CFG)
        self.assertNotIn("write_table", io.names())
        self.assertEqual(row["table"], "fallback")
        io = FakeIO(meters=meters(fable=87.0))
        row = sg.tick(io, CFG)
        self.assertNotIn("write_table", io.names())
        self.assertEqual(row["table"], "pass-through")

    def test_release_below_the_band(self):
        io = FakeIO(meters=meters(fable=84.9), table=sg.fallback_table(CFG))
        row = sg.tick(io, CFG)
        self.assertEqual(io.table, {"aliases": {}})
        self.assertEqual(row["table"], "pass-through")
        self.assertIn("table_pass_through", row["events"])

    def test_no_rewrite_when_unchanged(self):
        io = FakeIO(meters=meters(fable=100.0), table=sg.fallback_table(CFG))
        sg.tick(io, CFG)
        self.assertNotIn("write_table", io.names())

    def test_missing_fable_meter_keeps_the_table(self):
        m = meters()
        m["weekly_fable"] = None
        io = FakeIO(meters=m, table=sg.fallback_table(CFG))
        row = sg.tick(io, CFG)
        self.assertNotIn("write_table", io.names())
        self.assertEqual(row["table"], "fallback")

    def test_table_sticky_when_unreadable(self):
        io = FakeIO(meters=None, table=sg.fallback_table(CFG))
        row = sg.tick(io, CFG)
        self.assertNotIn("write_table", io.names())
        self.assertEqual(row["table"], "fallback")
        self.assertEqual(row["state"], "fallback")


class GaugeOutage(unittest.TestCase):
    def test_no_alert_inside_the_grace_period(self):
        io = FakeIO(meters=None, state={"unreadable_since": T0 - 600})
        row = sg.tick(io, CFG)
        self.assertEqual(io.alerts, [])
        self.assertEqual(row["state"], "normal")
        self.assertEqual(io.state["unreadable_since"], T0 - 600)

    def test_alert_after_the_grace_period(self):
        io = FakeIO(meters=None, error="usage endpoint HTTP 503",
                    state={"unreadable_since": T0 - 1801})
        row = sg.tick(io, CFG)
        self.assertEqual(row["state"], "gauge_stale")
        self.assertEqual(len(io.alerts), 1)
        self.assertIn("HTTP 503", io.alerts[0])
        self.assertTrue(row["gauge"].startswith("unreadable"))

    def test_first_failure_starts_the_clock(self):
        io = FakeIO(meters=None)
        sg.tick(io, CFG)
        self.assertEqual(io.state["unreadable_since"], T0)

    def test_recovery_clears_the_alert_and_the_clock(self):
        io = FakeIO(meters=meters(), state={"unreadable_since": T0 - 4000})
        sg.tick(io, CFG)
        self.assertEqual(io.alerts, [None])
        self.assertIsNone(io.state["unreadable_since"])
        self.assertEqual(io.state["last_ok_at"], T0)

    def test_no_new_holds_while_unreadable(self):
        io = FakeIO(meters=None)
        sg.tick(io, CFG)
        self.assertNotIn("write_hold", io.names())


class NoGauge(unittest.TestCase):
    def test_nothing_happens_without_a_credential(self):
        io = FakeIO(gauge=False, meters=meters(weekly=100.0, fable=100.0))
        row = sg.tick(io, CFG)
        self.assertIsNone(row)
        self.assertEqual(io.rows, [])
        self.assertNotIn("write_table", io.names())
        self.assertIn("no_gauge", io.events())

    def test_a_hold_still_lifts_on_time(self):
        hold = {"kind": "five_hour", "placed_at": T0 - HOUR, "until": T0 - 1, "placed_by": "governor"}
        io = FakeIO(gauge=False, hold=hold, halts={"mind": "marker", "ui": "marker"})
        sg.tick(io, CFG)
        self.assertIn("remove_halts", io.names())
        self.assertIsNone(io.hold)


class Telemetry(unittest.TestCase):
    def test_row_shape(self):
        io = FakeIO(meters=meters(five=12.5, weekly=61.0, fable=100.0, opus=40.0))
        row = sg.tick(io, CFG)
        self.assertEqual(io.rows, [row])
        for k in ("ts", "gauge", "five_hour", "weekly_all", "weekly_fable", "weekly_opus",
                  "five_hour_resets_at", "weekly_resets_at", "fable_resets_at",
                  "state", "table", "hold", "events"):
            self.assertIn(k, row)
        self.assertEqual(row["weekly_opus"], 40.0)
        self.assertEqual(row["gauge"], "ok")
        self.assertIsNone(row["hold"])

    def test_resume_reason_names_the_window_and_nothing_else(self):
        reason = sg.RESUME_REASON.format(a=sg.when(T0), b=sg.when(T0 + HOUR))
        self.assertIn("2001-09-09 01:46 UTC to 2001-09-09 02:46 UTC", reason)
        for word in ("usage", "limit", "cost", "seat", "plan", "%", "$"):
            self.assertNotIn(word, reason.lower())


class Config(unittest.TestCase):
    def test_defaults(self):
        c = sg.load_config({})
        self.assertEqual(c["fable_fallback_pct"], 90)
        self.assertEqual(c["five_hour_hold_pct"], 88)
        self.assertEqual(c["weekly_hold_pct"], 97)
        self.assertEqual(c["hold_buffer_s"], 120)
        self.assertEqual(c["gauge_stale_s"], 1800)
        self.assertEqual(c["ssm_prefix"], "/alpaca-mind")

    def test_env_overrides_and_bad_values(self):
        c = sg.load_config({"WEEKLY_HOLD_PCT": "100", "FIVE_HOUR_HOLD_PCT": "nope",
                            "SAVED_SSM_PREFIX": "/x", "FALLBACK_MODEL": "claude-sonnet-5"})
        self.assertEqual(c["weekly_hold_pct"], 100)
        self.assertEqual(c["five_hour_hold_pct"], 88)
        self.assertEqual(c["ssm_prefix"], "/x")
        self.assertEqual(sg.fallback_table(c)["subagent_model"], "claude-sonnet-5")


if __name__ == "__main__":
    unittest.main()
