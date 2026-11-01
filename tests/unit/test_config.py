import pytest

from nile_lab import config
from tests.conftest import SAMPLE


def load_text(tmp_path, text):
    path = tmp_path / "lab.yaml"
    path.write_text(text)
    return config.load(path)


def test_sample_loads_and_hides_the_token(sample_cfg):
    assert sample_cfg.mgmt_network.effective_gateway.exploded == "172.30.0.1"
    assert "sample-not-a-real-token" not in repr(sample_cfg)


def test_mac_is_normalized(tmp_path):
    cfg = load_text(tmp_path, SAMPLE.read_text().replace("02:00:00:00:00:01", "02-00-00-00-00-AB"))
    assert cfg.clients[0].wifi_dongle_mac == "02:00:00:00:00:ab"


@pytest.mark.parametrize("image", ["dockurr/windows", "dockurr/windows:latest", "localhost:5000/windows"])
def test_image_must_be_pinned(tmp_path, image):
    with pytest.raises(config.ConfigError) as e:
        load_text(tmp_path, SAMPLE.read_text().replace("dockurr/windows:6.06", image))
    assert e.value.problems[0].startswith("clients.0.image:")


def test_client_needs_exactly_one_link(tmp_path):
    text = SAMPLE.read_text().replace("    wired_network: port1\n", "    wired_network: port1\n    wifi_dongle_mac: 02:00:00:00:00:02\n")
    with pytest.raises(config.ConfigError) as e:
        load_text(tmp_path, text)
    assert "set exactly one of wifi_dongle_mac or wired_network" in e.value.problems[0]


def test_duplicates_and_reserved_ips(tmp_path):
    text = SAMPLE.read_text().replace("172.30.0.21", "172.30.0.1").replace("name: mac01", "name: win01")
    with pytest.raises(config.ConfigError) as e:
        load_text(tmp_path, text)
    assert "(root): duplicate client name win01" in e.value.problems
    assert "(root): client win01: mgmt_ip 172.30.0.1 is reserved (network, broadcast or gateway)" in e.value.problems


def test_unknown_field_is_rejected(tmp_path):
    with pytest.raises(config.ConfigError) as e:
        load_text(tmp_path, SAMPLE.read_text() + "extra: 1\n")
    assert e.value.problems == ["extra: Extra inputs are not permitted"]


def test_bad_yaml_reports_line_only(tmp_path):
    with pytest.raises(config.ConfigError) as e:
        load_text(tmp_path, "server_name: [unclosed\n")
    assert e.value.problems[0].startswith("not valid YAML at line")


def problems_for(tmp_path, text):
    with pytest.raises(config.ConfigError) as e:
        load_text(tmp_path, text)
    return e.value.problems


def test_empty_image_tag_is_rejected(tmp_path):
    problems = problems_for(tmp_path, SAMPLE.read_text().replace("dockurr/windows:6.06", "'dockurr/windows:'"))
    assert problems[0].startswith("clients.0.image:")


def test_bad_mac_message_never_echoes_the_value(tmp_path):
    problems = problems_for(tmp_path, SAMPLE.read_text().replace("02:00:00:00:00:01", "zz:zz:zz"))
    assert problems == ["clients.0.wifi_dongle_mac: must be a MAC address like 48:22:54:30:5d:28"]


@pytest.mark.parametrize("name", ["Lab01", "-lab", "lab-", "a" * 33, "lab_01"])
def test_names_must_be_short_lowercase_dns_labels(tmp_path, name):
    problems = problems_for(tmp_path, SAMPLE.read_text().replace("server_name: lab01", f"server_name: '{name}'"))
    assert problems[0].startswith("server_name:")


def test_gateway_must_sit_inside_the_subnet(tmp_path):
    text = SAMPLE.read_text().replace("subnet: 172.30.0.0/24 ", "subnet: 172.30.0.0/24\n  gateway: 172.31.0.1 ")
    assert problems_for(tmp_path, text) == ["mgmt_network: gateway 172.31.0.1 is outside subnet 172.30.0.0/24"]


def test_explicit_gateway_is_reserved_for_clients(tmp_path):
    text = SAMPLE.read_text().replace("subnet: 172.30.0.0/24 ", "subnet: 172.30.0.0/24\n  gateway: 172.30.0.11 ")
    assert problems_for(tmp_path, text) == [
        "(root): client win01: mgmt_ip 172.30.0.11 is reserved (network, broadcast or gateway)"]


def test_static_wired_network_needs_a_subnet(tmp_path):
    text = SAMPLE.read_text().replace("dhcp: true", "dhcp: false")
    assert problems_for(tmp_path, text) == ["wired_networks.0: subnet is required when dhcp is false"]


def test_duplicate_mgmt_ips_and_dongles_are_each_named(tmp_path):
    text = SAMPLE.read_text().replace("172.30.0.21", "172.30.0.11").replace(
        "    wired_network: port1\n", "    wifi_dongle_mac: 02:00:00:00:00:01\n")
    problems = problems_for(tmp_path, text)
    assert "(root): duplicate mgmt_ip 172.30.0.11" in problems
    assert "(root): duplicate wifi_dongle_mac 02:00:00:00:00:01" in problems


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just a string\n"])
def test_top_level_must_be_a_mapping(tmp_path, text):
    assert problems_for(tmp_path, text) == ["top level must be a mapping"]


def test_token_is_still_readable_on_purpose(sample_cfg):
    assert sample_cfg.cloudflare.api_token.get_secret_value() == "sample-not-a-real-token"


class TestResolvePath:
    def test_flag_wins_over_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NILE_LAB_CONFIG", "/from/env.yaml")
        assert config.resolve_path(tmp_path / "flag.yaml") == tmp_path / "flag.yaml"

    def test_env_wins_over_default(self, monkeypatch):
        monkeypatch.setenv("NILE_LAB_CONFIG", "/from/env.yaml")
        assert str(config.resolve_path(None)) == "/from/env.yaml"

    def test_default_is_srv(self, monkeypatch):
        monkeypatch.delenv("NILE_LAB_CONFIG", raising=False)
        assert str(config.resolve_path(None)) == "/srv/nile-lab/lab.yaml"

    def test_empty_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("NILE_LAB_CONFIG", "")
        assert str(config.resolve_path(None)) == "/srv/nile-lab/lab.yaml"
