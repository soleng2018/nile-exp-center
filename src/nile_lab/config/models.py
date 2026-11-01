"""Config models for lab.yaml.

PROVISIONAL: this is the smallest schema the scaffold needs to plan. Feature 3
(config & secrets file) owns the real schema and will extend or replace it.
"""

from __future__ import annotations

import re
from ipaddress import IPv4Address, IPv4Network
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    model_validator,
)

NAME_RE = r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$"
_MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


def _mac(value: object) -> object:
    if isinstance(value, str):
        value = value.strip().lower().replace("-", ":")
        if not _MAC_RE.match(value):
            raise ValueError("must be a MAC address like 48:22:54:30:5d:28")
    return value


def _pinned_image(value: str) -> str:
    repo, sep, tag = value.rpartition(":")
    if not sep or not tag or "/" in tag or not repo:
        raise ValueError("must name a pinned tag, e.g. dockurr/windows:6.06")
    if tag == "latest":
        raise ValueError("must be pinned to a version tag, not latest")
    return value


Name = Annotated[str, Field(pattern=NAME_RE)]
Mac = Annotated[str, BeforeValidator(_mac)]
Image = Annotated[str, AfterValidator(_pinned_image)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MgmtNetwork(_Strict):
    subnet: IPv4Network
    gateway: IPv4Address | None = None

    @property
    def effective_gateway(self) -> IPv4Address:
        return self.gateway or next(self.subnet.hosts())

    @model_validator(mode="after")
    def _gateway_in_subnet(self) -> MgmtNetwork:
        if self.gateway is not None and self.gateway not in self.subnet:
            raise ValueError(f"gateway {self.gateway} is outside subnet {self.subnet}")
        return self


class WiredNetwork(_Strict):
    name: Name
    parent_mac: Mac
    dhcp: bool = True
    subnet: IPv4Network | None = None
    gateway: IPv4Address | None = None

    @model_validator(mode="after")
    def _static_needs_subnet(self) -> WiredNetwork:
        if not self.dhcp and self.subnet is None:
            raise ValueError("subnet is required when dhcp is false")
        return self


class Client(_Strict):
    name: Name
    os: Literal["windows", "macos"]
    image: Image
    mgmt_ip: IPv4Address
    wifi_dongle_mac: Mac | None = None
    wired_network: Name | None = None

    @model_validator(mode="after")
    def _one_link(self) -> Client:
        if (self.wifi_dongle_mac is None) == (self.wired_network is None):
            raise ValueError("set exactly one of wifi_dongle_mac or wired_network")
        return self


class Cloudflare(_Strict):
    account_id: Annotated[str, Field(min_length=1)]
    zone_name: Annotated[str, Field(min_length=1)]
    api_token: SecretStr


class LabConfig(_Strict):
    server_name: Name
    mgmt_network: MgmtNetwork
    wired_networks: list[WiredNetwork] = []
    clients: list[Client] = []
    cloudflare: Cloudflare

    @model_validator(mode="after")
    def _cross_checks(self) -> LabConfig:
        errors: list[str] = []
        _dupes(errors, "client name", [c.name for c in self.clients])
        _dupes(errors, "mgmt_ip", [str(c.mgmt_ip) for c in self.clients])
        _dupes(errors, "wifi_dongle_mac", [c.wifi_dongle_mac for c in self.clients if c.wifi_dongle_mac])
        _dupes(errors, "wired network name", [w.name for w in self.wired_networks])
        _dupes(errors, "parent_mac", [w.parent_mac for w in self.wired_networks])

        net = self.mgmt_network
        reserved = {net.subnet.network_address, net.subnet.broadcast_address, net.effective_gateway}
        wired = {w.name for w in self.wired_networks}
        for c in self.clients:
            if c.mgmt_ip not in net.subnet:
                errors.append(f"client {c.name}: mgmt_ip {c.mgmt_ip} is outside {net.subnet}")
            elif c.mgmt_ip in reserved:
                errors.append(f"client {c.name}: mgmt_ip {c.mgmt_ip} is reserved (network, broadcast or gateway)")
            if c.wired_network is not None and c.wired_network not in wired:
                errors.append(f"client {c.name}: wired_network {c.wired_network!r} is not defined")
        if errors:
            raise ValueError("\n".join(errors))  # the loader prints one line each
        return self


def _dupes(errors: list[str], what: str, values: list[str]) -> None:
    seen: set[str] = set()
    for v in values:
        if v in seen:
            errors.append(f"duplicate {what} {v}")
        seen.add(v)
