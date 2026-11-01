"""PURE planner: (LabConfig, ActualState) -> Plan. No I/O, no clock, no randomness."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from ipaddress import ip_network

from nile_lab.config.models import Client, LabConfig
from nile_lab.model import (
    LABEL_CLIENT,
    LABEL_RUNTIME_HASH,
    LABEL_USB,
    MGMT_NETWORK,
    Action,
    ActionKind,
    ActualState,
    Container,
    Foreign,
    NetInterface,
    Phase,
    Plan,
    project_name,
    wired_network_name,
)

# All 11 dongles are TP-Link Archer T3U; the IDs only confirm a claimed port, never pick a device.
T3U_IDS = {("2357", "012d")}

UNITS = ("nile-lab-boot.service", "nile-lab-monitor.service", "nile-lab-cloudflared.service")


@dataclass(frozen=True)
class Resolved:
    """Where a client's client side link is right now."""

    runtime: str | None  # "usb:<port>" or "wired:<iface>"; None when missing
    detail: str
    problem: str | None = None


def plan(cfg: LabConfig, actual: ActualState, *, offline: bool) -> Plan:
    foreign: list[Foreign] = []
    refusals: list[str] = []
    phases = [
        _host(cfg, actual, foreign),
        _docker(cfg, actual, foreign, refusals),
        _clients(cfg, actual, foreign),
        Phase("cloudflare", status="skipped (offline)" if offline else "skipped (not built yet, feature 6)"),
    ]
    return Plan(phases, foreign, refusals)


# ---- host ----


def _host(cfg: LabConfig, actual: ActualState, foreign: list[Foreign]) -> Phase:
    phase = Phase("host")
    units = {u.name: u for u in actual.unit_files}
    for name in UNITS:
        unit = units.get(name)
        if unit is None:
            phase.actions.append(Action(ActionKind.CREATE, "unit", name))
        elif not unit.managed:
            foreign.append(Foreign("unit", name))
        else:
            phase.actions.append(Action(ActionKind.NOOP, "unit", name))

    for w in cfg.wired_networks:
        iface = _iface_by_mac(actual, w.parent_mac)
        if iface is None:
            phase.actions.append(
                Action(ActionKind.UPDATE, "link", w.name, "set parent link up (no IP)",
                       (f"no interface has MAC {w.parent_mac}",))
            )
        elif iface.up:
            phase.actions.append(Action(ActionKind.NOOP, "link", w.name, f"{iface.name} is up"))
        else:
            phase.actions.append(Action(ActionKind.UPDATE, "link", w.name, f"set {iface.name} up (no IP)"))

    if not actual.docker_available:
        phase.notes.append("docker is not installed yet (host bootstrap, feature 4)")
    return phase


# ---- docker ----


def _docker(cfg: LabConfig, actual: ActualState, foreign: list[Foreign], refusals: list[str]) -> Phase:
    phase = Phase("docker")
    nets = {n.name: n for n in actual.networks}
    mgmt = cfg.mgmt_network
    subnet = str(mgmt.subnet)

    existing = nets.get(MGMT_NETWORK)
    own_subnet = existing is not None and existing.owned and subnet in existing.subnets
    for route in actual.host_routes:
        if own_subnet and route == subnet:
            continue  # the route of our own bridge
        if ip_network(route, strict=False).overlaps(mgmt.subnet):
            refusals.append(f"mgmt_network.subnet {subnet} overlaps host route {route}")

    detail = f"bridge {subnet} gw {mgmt.effective_gateway}"
    if existing is None:
        phase.actions.append(Action(ActionKind.CREATE, "network", MGMT_NETWORK, detail))
    elif not existing.owned:
        foreign.append(Foreign("network", MGMT_NETWORK))
    elif subnet not in existing.subnets:
        phase.actions.append(
            Action(ActionKind.NOOP, "network", MGMT_NETWORK, detail,
                   (f"running with {', '.join(existing.subnets)}; changing the subnet is not supported yet",))
        )
    else:
        phase.actions.append(Action(ActionKind.NOOP, "network", MGMT_NETWORK, detail))

    for w in cfg.wired_networks:
        name = wired_network_name(w.name)
        iface = _iface_by_mac(actual, w.parent_mac)
        mode = "dhcp" if w.dhcp else f"static {w.subnet}"
        detail = f"macvlan on {iface.name if iface else '?'} ({mode})"
        problems = () if iface else (f"no interface has MAC {w.parent_mac}",)
        net = nets.get(name)
        if net is None:
            phase.actions.append(Action(ActionKind.CREATE, "network", name, detail, problems))
        elif not net.owned:
            foreign.append(Foreign("network", name))
        else:
            phase.actions.append(Action(ActionKind.NOOP, "network", name, detail, problems))

    wanted = {MGMT_NETWORK, *(wired_network_name(w.name) for w in cfg.wired_networks)}
    for n in actual.networks:
        if n.name in wanted:
            continue  # handled above
        if n.owned:
            phase.actions.append(Action(ActionKind.ORPHAN, "network", n.name, "not in config, left alone"))
        else:
            foreign.append(Foreign("network", n.name))

    if not actual.docker_available:
        phase.notes.append("docker is not installed, so nothing could be observed here")
    return phase


# ---- clients ----


def _clients(cfg: LabConfig, actual: ActualState, foreign: list[Foreign]) -> Phase:
    phase = Phase("clients")
    by_name = {c.name: c for c in actual.containers}
    configured = {project_name(c.name) for c in cfg.clients}

    for client in cfg.clients:
        name = project_name(client.name)
        container = by_name.get(name)
        if container is not None and not container.owned:
            foreign.append(Foreign("container", name))
            phase.actions.append(
                Action(ActionKind.NOOP, "client", client.name, "",
                       (f"container {name} exists but is not owned by nile-lab",))
            )
            continue

        res = _resolve(cfg, client, actual, container)
        detail = f"{client.os} {client.image}, mgmt {client.mgmt_ip}, {res.detail}"
        problems = (res.problem,) if res.problem else ()
        phase.actions.append(_client_action(client.name, container, res, detail, problems))

    for c in actual.containers:
        if c.name in configured:
            continue
        if c.owned:
            phase.actions.append(Action(ActionKind.ORPHAN, "client", c.labels.get(LABEL_CLIENT, c.name),
                                        "not in config, left alone"))
        else:
            foreign.append(Foreign("container", c.name))
    return phase


def _client_action(name: str, container: Container | None, res: Resolved, detail: str,
                   problems: tuple[str, ...]) -> Action:
    if container is None:
        return Action(ActionKind.CREATE, "client", name, detail, problems)
    old = container.labels.get(LABEL_RUNTIME_HASH)
    if res.runtime is not None and old != runtime_hash(res.runtime):
        return Action(ActionKind.RECREATE, "client", name, f"{detail} (link moved, disk kept)", problems)
    if not container.running:
        return Action(ActionKind.UPDATE, "client", name, f"start; {detail}", problems)
    return Action(ActionKind.NOOP, "client", name, detail, problems)


def _resolve(cfg: LabConfig, client: Client, actual: ActualState, container: Container | None) -> Resolved:
    if client.wifi_dongle_mac:
        mac = client.wifi_dongle_mac
        iface = _iface_by_mac(actual, mac)
        if iface is not None and iface.usb_port:
            return Resolved(f"usb:{iface.usb_port}", f"dongle {mac} on usb {iface.usb_port}")
        # A running VM has claimed the dongle: trust our label if the port still holds a T3U.
        port = container.labels.get(LABEL_USB) if container else None
        dev = next((d for d in actual.usb_devices if d.port == port), None)
        if dev is not None and (dev.vendor, dev.product) in T3U_IDS:
            return Resolved(f"usb:{port}", f"dongle {mac} on usb {port} (claimed by VM)")
        return Resolved(None, f"dongle {mac}", f"dongle {mac} not found")

    wired = next(w for w in cfg.wired_networks if w.name == client.wired_network)
    iface = _iface_by_mac(actual, wired.parent_mac)
    if iface is None:
        return Resolved(None, f"wired {wired.name}", f"wired port {wired.parent_mac} not found")
    return Resolved(f"wired:{iface.name}", f"wired {wired.name} on {iface.name}")


def runtime_hash(runtime: str) -> str:
    return hashlib.sha256(runtime.encode()).hexdigest()


def _iface_by_mac(actual: ActualState, mac: str) -> NetInterface | None:
    return next((i for i in actual.interfaces if i.mac == mac), None)
