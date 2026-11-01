import json
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from nile_lab.cli import app
from tests.conftest import FIXTURES, SAMPLE

runner = CliRunner()


def run(*args: str):
    return runner.invoke(app, list(args))


# covers: AC-2
def test_non_root_exits_before_reading_config(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    res = run("plan", "--offline", "--config", "/nonexistent/lab.yaml")
    assert res.exit_code == 2
    assert "must run as root" in res.output
    assert "nonexistent" not in res.output


@pytest.mark.usefixtures("as_root", "fake_observe")
class TestPlan:
    # covers: AC-1
    def test_matches_golden_text(self):
        res = run("plan", "--offline", "--config", str(SAMPLE))
        assert res.exit_code == 0, res.output
        assert res.output == (FIXTURES / "plan.sample.txt").read_text()

    # covers: AC-1
    def test_matches_golden_json(self):
        res = run("plan", "--offline", "--json", "--config", str(SAMPLE))
        assert res.exit_code == 0, res.output
        assert json.loads(res.output) == json.loads((FIXTURES / "plan.sample.json").read_text())

    # covers: AC-5
    def test_detailed_exitcode_when_changes_pending(self):
        assert run("plan", "--offline", "--detailed-exitcode", "-c", str(SAMPLE)).exit_code == 3

    def test_subnet_overlap_is_refused(self, fake_observe):
        fake_observe.state = replace(fake_observe.state, host_routes=("172.30.0.0/16",))
        res = run("plan", "--offline", "-c", str(SAMPLE))
        assert res.exit_code == 2
        assert "overlaps host route 172.30.0.0/16" in res.output

    def test_config_from_env(self, monkeypatch):
        monkeypatch.setenv("NILE_LAB_CONFIG", str(SAMPLE))
        assert run("plan", "--offline").exit_code == 0


@pytest.mark.usefixtures("as_root")
class TestValidate:
    # covers: AC-5
    def test_invalid_config_names_each_field_without_values(self):
        res = run("validate", "-c", str(FIXTURES / "lab.invalid.yaml"))
        assert res.exit_code == 2
        for field in ("server_name", "clients.0.image", "clients.0.wifi_dongle_mac", "clients.1.os"):
            assert f"  - {field}:" in res.output
        assert "super-secret-token-value" not in res.output
        assert "not-a-mac" not in res.output

    def test_cross_field_problems_one_per_line(self, tmp_path):
        bad = SAMPLE.read_text().replace("172.30.0.11", "10.0.0.5").replace("wired_network: port1", "wired_network: nope")
        path = tmp_path / "lab.yaml"
        path.write_text(bad)
        res = run("validate", "-c", str(path))
        assert res.exit_code == 2
        assert "(root): client win01: mgmt_ip 10.0.0.5 is outside 172.30.0.0/24" in res.output
        assert "(root): client mac01: wired_network 'nope' is not defined" in res.output

    def test_missing_file(self):
        res = run("validate", "-c", "/nonexistent/lab.yaml")
        assert res.exit_code == 2
        assert "cannot read file" in res.output

    def test_sample_is_valid(self):
        res = run("validate", "-c", str(SAMPLE))
        assert res.exit_code == 0
        assert "config ok: lab01, 2 client(s)" in res.output


def test_non_root_validate_is_refused(monkeypatch):
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    res = run("validate", "-c", str(SAMPLE))
    assert res.exit_code == 2 and "must run as root" in res.output


def test_no_args_shows_help():
    res = run()
    assert "plan" in res.output and "validate" in res.output


@pytest.mark.usefixtures("as_root", "fake_observe")
class TestPlanOutput:
    def converged(self, fake_observe):
        from tests.unit.test_planner import converged

        fake_observe.state = converged()

    # covers: AC-5
    def test_detailed_exitcode_is_zero_when_converged(self, fake_observe):
        self.converged(fake_observe)
        res = run("plan", "--offline", "--detailed-exitcode", "-c", str(SAMPLE))
        assert res.exit_code == 0, res.output
        assert "Plan: 0 to create, 0 to update, 0 to recreate, 0 orphaned." in res.output

    # covers: AC-5 (a refusal outranks pending changes)
    def test_refusal_exits_2_even_with_detailed_exitcode(self, fake_observe):
        fake_observe.state = replace(fake_observe.state, host_routes=("172.30.0.0/16",))
        assert run("plan", "--offline", "--detailed-exitcode", "-c", str(SAMPLE)).exit_code == 2

    # covers: AC-4
    def test_foreign_resources_are_listed_as_ignored(self, fake_observe):
        from nile_lab.model import Container

        fake_observe.state = replace(fake_observe.state, containers=(Container("nile-stray", True, {}),))
        res = run("plan", "--offline", "-c", str(SAMPLE))
        assert "foreign, ignored:\n  container nile-stray\n" in res.output
        doc = json.loads(run("plan", "--offline", "--json", "-c", str(SAMPLE)).output)
        assert doc["foreign"] == [{"resource": "container", "name": "nile-stray", "status": "foreign, ignored"}]

    def test_refusals_are_listed_in_text_and_json(self, fake_observe):
        fake_observe.state = replace(fake_observe.state, host_routes=("172.30.0.0/16",))
        doc = json.loads(run("plan", "--offline", "--json", "-c", str(SAMPLE)).output)
        assert doc["refusals"] == ["mgmt_network.subnet 172.30.0.0/24 overlaps host route 172.30.0.0/16"]

    def test_json_reports_changes_pending(self, fake_observe):
        assert json.loads(run("plan", "--offline", "--json", "-c", str(SAMPLE)).output)["changes_pending"] is True
        self.converged(fake_observe)
        assert json.loads(run("plan", "--offline", "--json", "-c", str(SAMPLE)).output)["changes_pending"] is False

    def test_plan_output_never_contains_the_token(self):
        for extra in ((), ("--json",)):
            assert "sample-not-a-real-token" not in run("plan", "--offline", *extra, "-c", str(SAMPLE)).output

    def test_invalid_config_stops_plan_before_observing(self, monkeypatch):
        monkeypatch.setattr("nile_lab.observe.observe", lambda: pytest.fail("observed an invalid config"))
        assert run("plan", "--offline", "-c", str(FIXTURES / "lab.invalid.yaml")).exit_code == 2


@pytest.mark.usefixtures("as_root")
class TestValidateEdges:
    def test_flag_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("NILE_LAB_CONFIG", str(FIXTURES / "lab.invalid.yaml"))
        assert run("validate", "-c", str(SAMPLE)).exit_code == 0

    def test_config_that_is_not_utf8_is_invalid_not_a_crash(self, tmp_path):
        path = tmp_path / "lab.yaml"
        path.write_bytes(SAMPLE.read_bytes().replace(b"lab01", b"lab\xe9"))
        res = run("validate", "-c", str(path))
        assert res.exit_code == 2, res.exception
        assert "invalid config" in res.output
