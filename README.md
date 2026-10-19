# Timekpr Screen Time Sync

> ## ⚠️ Disclaimer: AI-generated project
>
> **This entire project was generated with AI assistance, using mostly open-weight models.**
> It exists because I needed the functionality and wanted to see if I could get it working with
> open weight models. It is not a polished or even at the state of frontier models such as 
> Opus would achieve.
> The code, tests, installer and documentation have not been reviewed by a human in great 
> detail beyond getting it to work. Treat it as an experimental prototype.
>
> - It changes screen-time settings on a child's computer and can lock the desktop. Test it on a spare
>   machine first, and keep a way to unlock it (Timekpr admin tools, root login) before you rely on it.
> - Review every file before running `install.sh` as root, and check the agent's logs after install.
> - Use it at your own risk. No warranty is given. The authors accept no responsibility for lockouts,
>   data loss, or any other effect of running this software.

A Home Assistant integration plus a small Linux client (`timekpr_agent.py`) that together enforce a
**shared 300-minute-per-week screen-time budget** between a child's Linux PC (enforced locally by
[Timekpr-nExT](https://github.com/polesapart/timekpr-next)) and a TV (tracked manually in Home
Assistant). Home Assistant is the **single source of truth** for the weekly balance; the PC client is
a pure **actuator + reporter** over MQTT.

## Status

- Implemented: HA config-flow integration, PC agent, systemd installer, unit tests.
- Client unit tests pass (`client/test_timekpr_agent.py`).
- HA integration tests pass (`tests/`), with known gaps:
  - The Monday 00:00 reset test is skipped. The reset logic is not verified by a test.
  - Every HA test reports a teardown error from HA's MQTT mock (`EnsureJobAfterCooldown` lingering
    timer). This is a test-harness issue, not a verified integration bug.
- Not yet verified: a real MQTT broker, a real Timekpr-nExT PC, the systemd unit, and HACS install.

## How it works

- **Home Assistant** owns the master entities (`<node>` is the PC node ID, default `child_pc`):
  - `number.weekly_screen_time_left_<node>` — the weekly balance (restored after restarts, reset to the
    budget every Monday 00:00).
  - `switch.block_pc_access_<node>` — emergency lockout (sets the PC's time left to 0 immediately).
  - `binary_sensor.pc_agent_online_<node>` — whether the PC agent is connected.
  - `sensor.pc_time_left_<node>` — live PC time remaining in minutes.
- **PC client** (`client/timekpr_agent.py`, a systemd service) enforces caps locally via `timekpra`:
  - Reports spent minutes to HA so the weekly balance is decremented.
  - Clamps today's remaining time to `min(daily_cap, weekly_budget)` whenever the budget or caps change.
  - Locks and unlocks the desktop when the HA block switch changes.
  - Applies cap changes from HA immediately.
- **TV time** is deducted manually through HA services (dashboard buttons).

## MQTT topic contract

All topics are rooted at `timekpr/<node>/`. Home Assistant and the client must use the same topics.
The node ID is set in the HA config flow and in the client's `/etc/timekpr-agent.conf`.

| Topic | Direction | Payload | Retained | Meaning |
|-------|-----------|---------|:--------:|---------|
| `timekpr/<node>/weekly_budget` | HA → PC | integer minutes | yes | Current weekly balance. PC clamps today's time against it. |
| `timekpr/<node>/caps` | HA → PC | JSON `{"weekday_cap_minutes": n, "weekend_cap_minutes": n}` | yes | Daily caps. PC re-clamps today's time when they change. |
| `timekpr/<node>/blocked/set` | HA → PC | `ON` / `OFF` | no | Emergency lock / unlock command. |
| `timekpr/<node>/deduct` | PC → HA | integer minutes | no | Minutes spent on the PC. HA decrements the balance. |
| `timekpr/<node>/blocked/state` | PC → HA | `ON` / `OFF` | yes | Confirmed block state. |
| `timekpr/<node>/available` | PC → HA | `online` / `offline` | yes (also LWT) | PC agent connectivity. |
| `timekpr/<node>/pc_time_left` | PC → HA | integer seconds | yes | Live PC time remaining. |

## Data flow

1. On setup, HA publishes the retained weekly budget and caps to the PC.
2. The PC agent subscribes to `weekly_budget`, `caps` and `blocked/set`. Every 30 seconds it:
   - publishes `available=online` and `pc_time_left`,
   - reports consumed minutes on `deduct`, carrying partial minutes forward to the next report.
3. HA subscribes to `deduct`, decrements the balance, and re-publishes the new budget.
4. Turning on `switch.block_pc_access_<node>` publishes `blocked/set=ON`. The PC sets time left to 0
   and confirms on `blocked/state`. Turning it off restores the allowance.
5. Changing the weekly budget or caps in the integration's options reloads the entry, which republishes
   the retained values.

## Directory layout

```
custom_components/timekpr_sync/   Home Assistant integration (HACS-ready)
client/                           PC agent, install.sh systemd installer, client unit tests
tests/                            HA integration tests (pytest-homeassistant-custom-component)
plans/                            Implementation plan and builder adaptations
```

## Installation

### Home Assistant (server)

Requires the MQTT integration to be set up and connected.

**HACS** (the repository must be on GitHub; a GitLab repo can be mirrored to GitHub):
1. Add the repository as a custom repository in HACS (category: Integration).
2. Install **Timekpr Screen Time Sync** and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Timekpr Screen Time Sync** and enter the
   node ID, weekly budget and caps.

**Manual:** copy `custom_components/timekpr_sync/` into `<config>/custom_components/`, restart, then add
the integration as above.

Weekly budget and caps can be changed later under the integration's **Configure** (options) menu.

### Linux PC (client)

Install Timekpr-nExT first and create the child's user in it. Then, on the PC:

```bash
sudo ./client/install.sh
```

The installer asks for the child's username, MQTT broker host, port, credentials, node ID and daily
caps. It then:

- checks that `timekpra` is installed,
- requires `paho-mqtt` 2.0 or newer for python3 and exits with an error if it is missing (it does not
  install packages itself, so it works on any distro),
- installs `timekpr_agent.py` to `/usr/local/bin/timekpr_agent.py`,
- writes `/etc/timekpr-agent.conf` (mode 600),
- enables and starts the `timekpr-agent` systemd service.

Check it:

```bash
journalctl -u timekpr-agent -f
sudo timekpra --userinfort <child> | grep TIME_LEFT_DAY
```

The agent runs as root, which `timekpra` requires. It handles SIGTERM, so the `offline` status is
published on stop.

## Dashboard buttons (TV time)

Add buttons or a script that call:

```yaml
service: timekpr_sync.deduct_tv_minutes
data:
  minutes: 15
```

```yaml
service: timekpr_sync.add_tv_minutes
data:
  minutes: 15
```

If more than one PC is configured, add `node_id: <node>` to pick the PC. With a single PC it can be
omitted.

## Development / tests

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
python3 -m pytest client/test_timekpr_agent.py -v     # client unit tests (no HA needed)
python3 -m pytest tests/ -v                           # HA integration tests
python3 -m py_compile client/timekpr_agent.py custom_components/timekpr_sync/*.py
bash -n client/install.sh
```

`pytest.ini` sets `asyncio_mode = auto`. Pin `pytest==8.3.4`: `pytest-homeassistant-custom-component`
requires it, and newer pytest versions break the test harness.

## Known limitations

- Only one PC per config entry. For a second PC, add a second entry with its own node ID.
- TV time is deducted manually with buttons. There is no automatic TV detection.
- The Monday reset test is skipped (see Status).
- HACS needs the repository on GitHub.
- The client's `WEEKDAY_CAP`/`WEEKEND_CAP` in `/etc/timekpr-agent.conf` are only a startup fallback.
  Once HA publishes `caps`, that value is used.
- Not hardware-tested: see the Status section.
