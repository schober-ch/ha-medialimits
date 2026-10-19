"""Unit tests for the Timekpr sync client's pure logic (no real MQTT/timekpr)."""

import datetime
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Load the agent module (it guards main() under `__main__`, so importing is safe).
_AGENT_PATH = Path(__file__).resolve().parent.parent / "client" / "timekpr_agent.py"

_spec = importlib.util.spec_from_file_location("timekpr_agent_test_mod", _AGENT_PATH)
agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent)


@pytest.fixture
def patch_caps():
    """Set deterministic weekday/weekend caps for the module under test."""
    with mock.patch.object(agent, "_WEEKDAY_CAP", 30), mock.patch.object(
        agent, "_WEEKEND_CAP", 90
    ):
        yield


@pytest.mark.parametrize(
    "weekday,expected_seconds",
    [
        (0, 1800),  # Monday
        (1, 1800),  # Tuesday
        (4, 1800),  # Friday
        (5, 5400),  # Saturday
        (6, 5400),  # Sunday
    ],
)
def test_get_daily_cap_seconds(weekday, expected_seconds, patch_caps):
    # Base is a Monday (weekday() == 0); offset by `weekday` days.
    day = datetime.datetime(2026, 10, 19) + datetime.timedelta(days=weekday)
    assert agent.get_daily_cap_seconds(now=day) == expected_seconds


def test_allowance_clamp_weekly_limit(patch_caps):
    """min(daily_cap, weekly_budget*60) clamps down to the weekly bank."""
    monday = datetime.datetime(2026, 10, 19)
    daily = agent.get_daily_cap_seconds(now=monday)  # weekday -> 1800
    weekly_minutes = 5
    weekly_secs = weekly_minutes * 60
    assert min(daily, weekly_secs) == 300


def test_allowance_clamp_zero_budget(patch_caps):
    """A weekly budget of 0 clamps allowance to 0 on a weekday."""
    monday = datetime.datetime(2026, 10, 19)
    daily = agent.get_daily_cap_seconds(now=monday)
    weekly_minutes = 0
    weekly_secs = weekly_minutes * 60
    assert min(daily, weekly_secs) == 0


def test_parse_time_left_day_namespace():
    sample = (
        "TIME_LEFT_DAY: 7200\n"
        "PLAYTIME_LEFT_DAY: 300\n"
        "LIMITS_PER_WEEKDAYS: 5\n"
    )
    assert agent._parse_time_left_day(sample) == 7200


def test_parse_time_left_day_missing():
    assert agent._parse_time_left_day("ALLOWED_DAYS: 1;2;3") is None
    assert agent._parse_time_left_day("") is None


def test_get_timekpr_time_left_uses_live_then_stored():
    live_out = "TIME_LEFT_DAY: 1234\n"
    with mock.patch.object(
        agent, "_timekpr_bin", return_value="timekpra"
    ), mock.patch.object(agent, "_TARGET_USER", "child"):
        with mock.patch(
            "subprocess.check_output", return_value=live_out
        ) as check:
            assert agent.get_timekpr_time_left() == 1234
            # First call uses the live flag.
            args = check.call_args.args[0]
            assert "--userinfort" in args


def test_get_timekpr_time_left_falls_back():
    stored_out = "TIME_LEFT_DAY: 99\n"
    with mock.patch.object(
        agent, "_timekpr_bin", return_value="timekpra"
    ), mock.patch.object(agent, "_TARGET_USER", "child"):
        with mock.patch(
            "subprocess.check_output",
            side_effect=[subprocess.CalledProcessError(1, "timekpra"), stored_out],
        ) as check:
            assert agent.get_timekpr_time_left() == 99
            # Both flags tried: live first, then stored.
            flags = [c.args[0][1] for c in check.call_args_list]
            assert flags == ["--userinfort", "--userinfo"]


def test_get_timekpr_time_left_returns_none_on_failure():
    def raiser(*args, **kwargs):
        raise FileNotFoundError("timekpra")

    with mock.patch.object(agent, "_timekpr_bin", return_value="timekpra"), mock.patch.object(
        agent, "_TARGET_USER", "child"
    ), mock.patch("subprocess.check_output", side_effect=raiser):
        assert agent.get_timekpr_time_left() is None


def test_set_timekpr_seconds_never_negative():
    with mock.patch.object(agent, "_timekpr_bin", return_value="timekpra"), mock.patch.object(
        agent, "_TARGET_USER", "child"
    ):
        with mock.patch("subprocess.run") as run:
            assert agent.set_timekpr_seconds(-50) is True
            cmd = run.call_args.args[0]
            # Never passes a negative value to timekpra.
            assert cmd[-1] == "0"
            assert all(int(part) >= 0 for part in cmd[-1:])


def test_set_timekpr_seconds_passes_value():
    with mock.patch.object(agent, "_timekpr_bin", return_value="timekpra"), mock.patch.object(
        agent, "_TARGET_USER", "child"
    ):
        with mock.patch("subprocess.run") as run:
            agent.set_timekpr_seconds(1800)
            cmd = run.call_args.args[0]
            assert cmd[-1] == "1800"


def test_agent_set_marks_reference(monkeypatch):
    """Agent-initiated sets must update the usage reference so they are not reported."""
    monkeypatch.setattr(agent, "set_timekpr_seconds", lambda secs: True)
    agent._agent_set(120)
    assert agent._last_pc_seconds == 120
    agent._agent_set(-5)
    assert agent._last_pc_seconds == 0


def test_apply_caps_updates_values(monkeypatch):
    monkeypatch.setattr(agent, "_WEEKDAY_CAP", 30)
    monkeypatch.setattr(agent, "_WEEKEND_CAP", 90)
    agent._apply_caps('{"weekday_cap_minutes": 20, "weekend_cap_minutes": 60}')
    assert agent._WEEKDAY_CAP == 20
    assert agent._WEEKEND_CAP == 60


@pytest.mark.parametrize("payload", ["not json", '{"weekday_cap_minutes": 20}', '{"weekday_cap_minutes": -1, "weekend_cap_minutes": 60}'])
def test_apply_caps_ignores_invalid(monkeypatch, payload):
    monkeypatch.setattr(agent, "_WEEKDAY_CAP", 30)
    monkeypatch.setattr(agent, "_WEEKEND_CAP", 90)
    agent._apply_caps(payload)
    assert agent._WEEKDAY_CAP == 30
    assert agent._WEEKEND_CAP == 90


def test_clamp_applies_lower_cap_immediately(monkeypatch):
    """A lowered cap must re-clamp today's remaining time right away."""
    monkeypatch.setattr(agent, "_WEEKDAY_CAP", 30)
    monkeypatch.setattr(agent, "_WEEKEND_CAP", 90)
    monkeypatch.setattr(agent, "_weekly_budget_remaining", 300)
    monkeypatch.setattr(agent, "get_daily_cap_seconds", lambda now=None: 20 * 60)
    monkeypatch.setattr(agent, "get_timekpr_time_left", lambda: 1800)
    calls = []
    monkeypatch.setattr(agent, "set_timekpr_seconds", lambda secs: calls.append(secs) or True)
    agent._clamp_to_allowance()
    assert calls == [1200]
    assert agent._last_pc_seconds == 1200
