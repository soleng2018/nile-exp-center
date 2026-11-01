"""Pure data types shared by observe, planner, apply and the CLI. No I/O here."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# Ownership contract (spec 0001): labels every owned Docker object carries.
LABEL_MANAGED = "lab.nile.managed"
LABEL_CLIENT = "lab.nile.client"
LABEL_SPEC_HASH = "lab.nile.spec-hash"
LABEL_RUNTIME_HASH = "lab.nile.runtime-hash"
LABEL_USB = "lab.nile.usb"

MANAGED_HEADER = "# managed by nile-lab"
MGMT_NETWORK = "nile-mgmt"

PHASES = ("host", "docker", "clients", "cloudflare")


def project_name(client: str) -> str:
    return f"nile-{client}"


def wired_network_name(name: str) -> str:
    return f"nile-wired-{name}"


class ActionKind(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    RECREATE = "recreate"
    NOOP = "noop"
    ORPHAN = "orphan"


class Health(StrEnum):
    """Shared health model (spec 0001). observe_health arrives with feature 5."""

    ABSENT = "absent"
    STOPPED = "stopped"
    INSTALLING = "installing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


# ---- actual state (what observe found) ----


@dataclass(frozen=True)
class NetInterface:
    name: str
    mac: str
    up: bool
    usb_port: str | None = None  # sysfs USB port path, e.g. "1-1.2.4"


@dataclass(frozen=True)
class UsbDevice:
    port: str  # sysfs port path, e.g. "1-1.2.4"
    busnum: int
    devnum: int
    vendor: str
    product: str


@dataclass(frozen=True)
class Container:
    name: str
    running: bool
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def owned(self) -> bool:
        return self.labels.get(LABEL_MANAGED) == "true"


@dataclass(frozen=True)
class DockerNetwork:
    name: str
    driver: str
    subnets: tuple[str, ...]
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def owned(self) -> bool:
        return self.labels.get(LABEL_MANAGED) == "true"


@dataclass(frozen=True)
class UnitFile:
    name: str
    managed: bool  # carries MANAGED_HEADER


@dataclass(frozen=True)
class ActualState:
    interfaces: tuple[NetInterface, ...] = ()
    usb_devices: tuple[UsbDevice, ...] = ()
    host_routes: tuple[str, ...] = ()  # destination CIDRs, e.g. "10.1.255.0/24"
    host_routes_read: bool = True  # False when `ip route` failed, so overlap can't be checked
    unit_files: tuple[UnitFile, ...] = ()
    docker_available: bool = False
    containers: tuple[Container, ...] = ()
    networks: tuple[DockerNetwork, ...] = ()


# ---- plan ----


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    resource: str  # e.g. "unit", "link", "network", "client"
    name: str
    detail: str = ""
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class Foreign:
    resource: str
    name: str


@dataclass
class Phase:
    name: str
    status: str = "planned"  # planned | skipped (<reason>)
    actions: list[Action] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Plan:
    phases: list[Phase]
    foreign: list[Foreign] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    @property
    def actions(self) -> list[Action]:
        return [a for p in self.phases for a in p.actions]

    @property
    def has_changes(self) -> bool:
        return any(a.kind not in (ActionKind.NOOP, ActionKind.ORPHAN) for a in self.actions)
