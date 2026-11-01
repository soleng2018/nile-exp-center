import json
import subprocess

import pytest

from nile_lab.adapters import docker
from nile_lab.model import LABEL_MANAGED


class FakeDocker:
    """Stands in for the docker CLI: maps the first args to canned stdout and records every call."""

    def __init__(self, outputs: dict[str, str]):
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        key = " ".join(cmd[1:3])
        if key not in self.outputs:
            raise subprocess.CalledProcessError(1, cmd, "", "Error: no such thing\n")
        return subprocess.CompletedProcess(cmd, 0, self.outputs[key], "")


@pytest.fixture
def fake_cli(monkeypatch):
    def install(outputs: dict[str, str] | None = None) -> FakeDocker:
        fake = FakeDocker(outputs or {})
        monkeypatch.setattr("nile_lab.adapters.docker.subprocess.run", fake)
        return fake

    return install


def json_lines(*rows: dict) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


def test_available_follows_the_docker_binary_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert not docker.available()
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    assert docker.available()


def test_lists_containers_with_state_and_parsed_labels(fake_cli):
    fake_cli({"ps -a": json_lines(
        {"Names": "nile-win01", "State": "running", "Labels": f"{LABEL_MANAGED}=true,lab.nile.client=win01"},
        {"Names": "nile-mac01", "State": "exited", "Labels": ""},
    )})
    win, mac = docker.list_containers()
    assert (win.name, win.running, win.owned) == ("nile-win01", True, True)
    assert win.labels["lab.nile.client"] == "win01"
    assert (mac.name, mac.running, mac.owned, mac.labels) == ("nile-mac01", False, False, {})


def test_label_values_may_contain_equals_signs(fake_cli):
    fake_cli({"ps -a": json_lines({"Names": "nile-x", "State": "running", "Labels": "a=b=c,junk,d="})})
    (c,) = docker.list_containers()
    assert c.labels == {"a": "b=c,junk", "d": ""}


def test_only_lists_nile_containers(fake_cli):
    fake = fake_cli({"ps -a": ""})
    assert docker.list_containers() == ()
    assert "name=^nile-" in fake.calls[0]


def test_networks_are_filtered_to_nile_and_inspected_for_subnets(fake_cli):
    fake = fake_cli({
        "network ls": json_lines({"Name": "bridge"}, {"Name": "nile-mgmt"}, {"Name": "nile-wired-port1"}),
        "network inspect": json.dumps([
            {"Name": "nile-mgmt", "Driver": "bridge", "Labels": {LABEL_MANAGED: "true"},
             "IPAM": {"Config": [{"Subnet": "172.30.0.0/24", "Gateway": "172.30.0.1"}]}},
            {"Name": "nile-wired-port1", "Driver": "macvlan", "Labels": None, "IPAM": {"Config": None}},
        ]),
    })
    mgmt, wired = docker.list_networks()
    assert (mgmt.name, mgmt.driver, mgmt.subnets, mgmt.owned) == ("nile-mgmt", "bridge", ("172.30.0.0/24",), True)
    assert (wired.name, wired.driver, wired.subnets, wired.owned) == ("nile-wired-port1", "macvlan", (), False)
    assert fake.calls[1][-2:] == ["nile-mgmt", "nile-wired-port1"]


def test_no_nile_networks_skips_inspect(fake_cli):
    fake = fake_cli({"network ls": json_lines({"Name": "bridge"}, {"Name": "host"})})
    assert docker.list_networks() == ()
    assert len(fake.calls) == 1


def test_cli_failure_raises_docker_error_with_stderr(fake_cli):
    fake_cli()
    with pytest.raises(docker.DockerError, match=r"^docker ps failed: Error: no such thing$"):
        docker.list_containers()


def test_label_values_may_contain_commas(fake_cli):
    row = {"Names": "nile-win01", "State": "running", "Labels": "a=1,2,b=x=y,c=3"}
    fake_cli({"ps -a": json_lines(row)})
    assert docker.list_containers()[0].labels == {"a": "1,2", "b": "x=y", "c": "3"}


@pytest.mark.parametrize("exc, msg", [
    (subprocess.TimeoutExpired(["docker"], 30), r"^docker ps timed out after 30s"),
    (FileNotFoundError(2, "No such file or directory"), r"^docker ps could not run: No such file or directory$"),
])
def test_timeouts_and_missing_binary_raise_docker_error(monkeypatch, exc, msg):
    def run(cmd, **kwargs):
        raise exc

    monkeypatch.setattr("nile_lab.adapters.docker.subprocess.run", run)
    with pytest.raises(docker.DockerError, match=msg):
        docker.list_containers()
