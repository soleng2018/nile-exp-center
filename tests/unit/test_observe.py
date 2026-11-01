import json
import subprocess

import pytest

from nile_lab import observe
from nile_lab.adapters import host

READ_COMMANDS = {("ip", "-j", "route"), ("docker", "ps", "-a"), ("docker", "network", "ls"),
                 ("docker", "network", "inspect")}


@pytest.fixture
def empty_host(monkeypatch):
    """Empty sysfs/systemd reads (file reads only), and record every command run."""
    for fn in ("read_interfaces", "read_usb_devices", "read_unit_files"):
        monkeypatch.setattr(host, fn, lambda: ())
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["docker", "network"] and cmd[2] == "ls":
            out = json.dumps({"Name": "nile-mgmt"}) + "\n"
        elif cmd[:3] == ["docker", "network", "inspect"]:
            out = json.dumps([{"Name": "nile-mgmt", "Driver": "bridge", "Labels": {}, "IPAM": {}}])
        elif cmd[0] == "ip":
            out = "[]"
        else:
            out = ""
        return subprocess.CompletedProcess(cmd, 0, out, "")

    monkeypatch.setattr("subprocess.run", fake_run)
    return calls


def test_without_docker_never_calls_docker(empty_host, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    state = observe.observe()
    assert not state.docker_available
    assert state.containers == () and state.networks == ()
    assert all(cmd[0] != "docker" for cmd in empty_host)


def test_with_docker_reads_containers_and_networks(empty_host, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    state = observe.observe()
    assert state.docker_available
    assert [n.name for n in state.networks] == ["nile-mgmt"]


# covers: AC-1 (plan changes nothing: observe only ever runs read commands)
def test_observe_only_runs_read_commands(empty_host, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    observe.observe()
    assert {tuple(cmd[:3]) for cmd in empty_host} <= READ_COMMANDS


def test_failed_route_read_is_flagged(empty_host, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(host, "read_routes", lambda: None)
    state = observe.observe()
    assert state.host_routes == () and not state.host_routes_read
