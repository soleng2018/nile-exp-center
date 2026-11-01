"""Build ActualState by calling each adapter's read side. Never writes."""

from __future__ import annotations

from nile_lab.adapters import docker, host
from nile_lab.model import ActualState


def observe() -> ActualState:
    have_docker = docker.available()
    return ActualState(
        interfaces=host.read_interfaces(),
        usb_devices=host.read_usb_devices(),
        host_routes=host.read_routes(),
        unit_files=host.read_unit_files(),
        docker_available=have_docker,
        containers=docker.list_containers() if have_docker else (),
        networks=docker.list_networks() if have_docker else (),
    )
