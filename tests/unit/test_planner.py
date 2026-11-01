from dataclasses import replace

from nile_lab.model import (
    LABEL_CLIENT,
    LABEL_MANAGED,
    LABEL_RUNTIME_HASH,
    LABEL_USB,
    ActionKind,
    Container,
    DockerNetwork,
    NetInterface,
    UnitFile,
    UsbDevice,
)
from nile_lab.planner import plan, runtime_hash
from tests.conftest import fresh_server

DONGLE_PORT = "1-1.2.4"


def owned(client: str, runtime: str, running: bool = True, **labels: str) -> Container:
    return Container(
        f"nile-{client}",
        running,
        {LABEL_MANAGED: "true", LABEL_CLIENT: client, LABEL_RUNTIME_HASH: runtime_hash(runtime), **labels},
    )


def converged():
    """Everything the sample config asks for, already running."""
    mgmt = DockerNetwork("nile-mgmt", "bridge", ("172.30.0.0/24",), {LABEL_MANAGED: "true"})
    wired = DockerNetwork("nile-wired-port1", "macvlan", (), {LABEL_MANAGED: "true"})
    return replace(
        fresh_server(),
        interfaces=(
            NetInterface("eno1", "74:86:7a:ed:7a:b4", True),
            NetInterface("eno3", "02:00:00:00:10:01", True),
            NetInterface("wlxdongle", "02:00:00:00:00:01", False, DONGLE_PORT),
        ),
        host_routes=("10.1.255.0/24", "172.30.0.0/24"),
        unit_files=tuple(UnitFile(n, True) for n in (
            "nile-lab-boot.service", "nile-lab-monitor.service", "nile-lab-cloudflared.service")),
        docker_available=True,
        networks=(mgmt, wired),
        containers=(owned("win01", f"usb:{DONGLE_PORT}"), owned("mac01", "wired:eno3")),
    )


def kinds(p, phase=None):
    return {(a.resource, a.name): a.kind for ph in p.phases if phase in (None, ph.name) for a in ph.actions}


def test_converged_lab_is_all_noop(sample_cfg):
    p = plan(sample_cfg, converged(), offline=True)
    assert set(kinds(p).values()) == {ActionKind.NOOP}
    assert not p.has_changes and not p.refusals and not p.foreign


def test_fresh_server_creates_everything(sample_cfg):
    p = plan(sample_cfg, fresh_server(), offline=True)
    assert kinds(p, "clients") == {("client", "win01"): ActionKind.CREATE, ("client", "mac01"): ActionKind.CREATE}
    assert p.phases[-1].status == "skipped (offline)"


# covers: AC-4
def test_foreign_resources_get_no_action(sample_cfg):
    state = converged()
    state = replace(
        state,
        containers=(Container("nile-win01", True, {}), state.containers[1], Container("nile-stray", True, {})),
        networks=(*state.networks, DockerNetwork("nile-other", "bridge", (), {})),
        unit_files=(*state.unit_files, UnitFile("nile-lab-handmade.service", False)),
    )
    p = plan(sample_cfg, state, offline=True)
    foreign = {(f.resource, f.name) for f in p.foreign}
    assert foreign == {("container", "nile-win01"), ("container", "nile-stray"), ("network", "nile-other")}
    acted = {a.name for a in p.actions if a.kind != ActionKind.NOOP}
    assert not acted & {"nile-stray", "nile-other", "nile-lab-handmade.service"}
    win = next(a for a in p.actions if a.name == "win01")
    assert win.kind == ActionKind.NOOP and "not owned by nile-lab" in win.problems[0]


# covers: AC-4
def test_foreign_unit_with_our_name_is_not_rewritten(sample_cfg):
    state = replace(converged(), unit_files=(UnitFile("nile-lab-boot.service", False),))
    p = plan(sample_cfg, state, offline=True)
    assert ("unit", "nile-lab-boot.service") not in kinds(p, "host")
    assert ("unit", "nile-lab-boot.service") in {(f.resource, f.name) for f in p.foreign}


def test_owned_container_not_in_config_is_orphan(sample_cfg):
    state = converged()
    state = replace(state, containers=(*state.containers, owned("old01", "usb:9-9")))
    assert kinds(plan(sample_cfg, state, offline=True))[("client", "old01")] == ActionKind.ORPHAN


def test_claimed_dongle_trusted_through_label(sample_cfg):
    state = converged()
    # The VM claimed the dongle, so its host interface is gone.
    state = replace(
        state,
        interfaces=tuple(i for i in state.interfaces if i.name != "wlxdongle"),
        usb_devices=(UsbDevice(DONGLE_PORT, 1, 7, "2357", "012d"),),
        containers=(owned("win01", f"usb:{DONGLE_PORT}", **{LABEL_USB: DONGLE_PORT}), state.containers[1]),
    )
    win = next(a for a in plan(sample_cfg, state, offline=True).actions if a.name == "win01")
    assert win.kind == ActionKind.NOOP and not win.problems
    assert "claimed by VM" in win.detail


def test_claimed_port_with_other_device_is_missing(sample_cfg):
    state = converged()
    state = replace(
        state,
        interfaces=tuple(i for i in state.interfaces if i.name != "wlxdongle"),
        usb_devices=(UsbDevice(DONGLE_PORT, 1, 7, "046d", "c52b"),),
        containers=(owned("win01", f"usb:{DONGLE_PORT}", **{LABEL_USB: DONGLE_PORT}), state.containers[1]),
    )
    win = next(a for a in plan(sample_cfg, state, offline=True).actions if a.name == "win01")
    assert win.problems == ("dongle 02:00:00:00:00:01 not found",)


def test_dongle_on_new_port_recreates(sample_cfg):
    state = converged()
    state = replace(state, interfaces=(*state.interfaces[:2], NetInterface("wlxdongle", "02:00:00:00:00:01", False, "1-1.3")))
    assert kinds(plan(sample_cfg, state, offline=True))[("client", "win01")] == ActionKind.RECREATE


def test_stopped_container_is_started(sample_cfg):
    state = converged()
    state = replace(state, containers=(owned("win01", f"usb:{DONGLE_PORT}", running=False), state.containers[1]))
    win = next(a for a in plan(sample_cfg, state, offline=True).actions if a.name == "win01")
    assert win.kind == ActionKind.UPDATE and win.detail.startswith("start")


def test_down_parent_link_is_brought_up(sample_cfg):
    state = converged()
    state = replace(state, interfaces=(state.interfaces[0], NetInterface("eno3", "02:00:00:00:10:01", False), state.interfaces[2]))
    assert kinds(plan(sample_cfg, state, offline=True), "host")[("link", "port1")] == ActionKind.UPDATE


def test_own_bridge_route_is_not_an_overlap(sample_cfg):
    assert not plan(sample_cfg, converged(), offline=True).refusals


# covers: AC-4 (a foreign mgmt bridge is reported and never touched)
def test_foreign_mgmt_bridge_is_refused_not_adopted(sample_cfg):
    state = replace(converged(), networks=(DockerNetwork("nile-mgmt", "bridge", ("172.30.0.0/24",), {}),
                                           converged().networks[1]))
    p = plan(sample_cfg, state, offline=True)
    assert ("network", "nile-mgmt") in {(f.resource, f.name) for f in p.foreign}
    assert ("network", "nile-mgmt") not in kinds(p, "docker")
    assert p.refusals == ["mgmt_network.subnet 172.30.0.0/24 overlaps host route 172.30.0.0/24"]


def test_mgmt_subnet_change_is_flagged_not_applied(sample_cfg):
    state = replace(converged(), networks=(DockerNetwork("nile-mgmt", "bridge", ("172.31.0.0/24",), {LABEL_MANAGED: "true"}),
                                           converged().networks[1]))
    mgmt = next(a for a in plan(sample_cfg, state, offline=True).actions if a.name == "nile-mgmt")
    assert mgmt.kind == ActionKind.NOOP
    assert "changing the subnet is not supported yet" in mgmt.problems[0]


def test_owned_network_not_in_config_is_orphan(sample_cfg):
    state = replace(converged(), networks=(*converged().networks,
                                           DockerNetwork("nile-wired-old", "macvlan", (), {LABEL_MANAGED: "true"})))
    assert kinds(plan(sample_cfg, state, offline=True), "docker")[("network", "nile-wired-old")] == ActionKind.ORPHAN


# covers: AC-4 (a foreign macvlan with our name gets no action)
def test_foreign_wired_network_with_our_name_gets_no_action(sample_cfg):
    state = replace(converged(), networks=(converged().networks[0], DockerNetwork("nile-wired-port1", "macvlan", (), {})))
    p = plan(sample_cfg, state, offline=True)
    assert ("network", "nile-wired-port1") not in kinds(p, "docker")
    assert ("network", "nile-wired-port1") in {(f.resource, f.name) for f in p.foreign}


def test_wired_client_moved_to_another_parent_recreates(sample_cfg):
    state = converged()
    state = replace(state, interfaces=(state.interfaces[0], NetInterface("eno4", "02:00:00:00:10:01", True),
                                       state.interfaces[2]))
    mac = next(a for a in plan(sample_cfg, state, offline=True).actions if a.name == "mac01")
    assert mac.kind == ActionKind.RECREATE and mac.detail.endswith("(link moved, disk kept)")


def test_dongle_is_matched_by_mac_not_by_model(sample_cfg):
    state = converged()
    # Two identical T3U dongles; only the configured MAC counts.
    state = replace(state, interfaces=(*state.interfaces[:2],
                                       NetInterface("wlxother", "02:00:00:00:00:99", False, "1-1.9"),
                                       state.interfaces[2]))
    win = next(a for a in plan(sample_cfg, state, offline=True).actions if a.name == "win01")
    assert win.kind == ActionKind.NOOP and f"on usb {DONGLE_PORT}" in win.detail


def test_container_without_runtime_hash_is_recreated_once_link_is_known(sample_cfg):
    state = converged()
    bare = Container("nile-win01", True, {LABEL_MANAGED: "true", LABEL_CLIENT: "win01"})
    state = replace(state, containers=(bare, state.containers[1]))
    assert kinds(plan(sample_cfg, state, offline=True))[("client", "win01")] == ActionKind.RECREATE


def test_missing_dongle_never_recreates_a_running_vm(sample_cfg):
    state = converged()
    state = replace(state, interfaces=state.interfaces[:2], usb_devices=())
    win = next(a for a in plan(sample_cfg, state, offline=True).actions if a.name == "win01")
    assert win.kind == ActionKind.NOOP and win.problems == ("dongle 02:00:00:00:00:01 not found",)


def test_cloudflare_is_skipped_either_way(sample_cfg):
    assert plan(sample_cfg, converged(), offline=True).phases[-1].status == "skipped (offline)"
    online = plan(sample_cfg, converged(), offline=False).phases[-1]
    assert online.name == "cloudflare" and online.status.startswith("skipped") and not online.actions


def test_phases_come_in_contract_order(sample_cfg):
    assert [ph.name for ph in plan(sample_cfg, fresh_server(), offline=True).phases] == [
        "host", "docker", "clients", "cloudflare"]


def test_plan_is_deterministic(sample_cfg):
    assert plan(sample_cfg, converged(), offline=True) == plan(sample_cfg, converged(), offline=True)
