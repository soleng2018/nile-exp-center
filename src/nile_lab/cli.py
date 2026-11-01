"""Typer app. Exit codes (spec 0001 CLI contract):
0 ok · 1 runtime error or failed client · 2 invalid config or refused precondition · 3 changes pending.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer

from nile_lab import config as cfgmod
from nile_lab import observe as obs
from nile_lab import planner
from nile_lab.model import ActionKind, Plan

EXIT_OK, EXIT_ERROR, EXIT_INVALID, EXIT_PENDING = 0, 1, 2, 3

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Reconcile the Nile client VM lab.")

ConfigOpt = Annotated[
    Path | None,
    typer.Option("--config", "-c", help=f"Config file (default ${cfgmod.loader.ENV_VAR} or {cfgmod.loader.DEFAULT_PATH})."),
]
JsonOpt = Annotated[bool, typer.Option("--json", help="Machine readable output.")]

SYMBOLS = {
    ActionKind.CREATE: "+",
    ActionKind.UPDATE: "~",
    ActionKind.RECREATE: "±",
    ActionKind.NOOP: "=",
    ActionKind.ORPHAN: "?",
}


def _require_root() -> None:
    if os.geteuid() != 0:
        typer.echo("nile-lab must run as root (try: sudo nile-lab ...).", err=True)
        raise typer.Exit(EXIT_INVALID)


def _load(path: Path | None) -> cfgmod.LabConfig:
    resolved = cfgmod.resolve_path(path)
    try:
        return cfgmod.load(resolved)
    except cfgmod.ConfigError as e:
        typer.echo(f"invalid config {e.path}:", err=True)
        for p in e.problems:
            typer.echo(f"  - {p}", err=True)
        raise typer.Exit(EXIT_INVALID) from None


@app.command()
def validate(config: ConfigOpt = None) -> None:
    """Check the config file and report every bad field."""
    _require_root()
    cfg = _load(config)
    typer.echo(f"config ok: {cfg.server_name}, {len(cfg.clients)} client(s)")


@app.command()
def plan(
    config: ConfigOpt = None,
    offline: Annotated[bool, typer.Option("--offline", help="Skip every Cloudflare read and write.")] = False,
    as_json: JsonOpt = False,
    detailed_exitcode: Annotated[
        bool, typer.Option("--detailed-exitcode", help="Exit 3 when changes are pending.")
    ] = False,
) -> None:
    """Show what apply would change. Reads only; changes nothing."""
    _require_root()
    cfg = _load(config)
    result = planner.plan(cfg, obs.observe(), offline=offline)
    typer.echo(plan_json(result) if as_json else plan_text(cfg, result), nl=not as_json)
    if result.refusals:
        raise typer.Exit(EXIT_INVALID)
    if detailed_exitcode and result.has_changes:
        raise typer.Exit(EXIT_PENDING)


# ---- output ----


def plan_text(cfg: cfgmod.LabConfig, p: Plan) -> str:
    lines = [f"nile-lab plan · {cfg.server_name} · {len(cfg.clients)} client(s)", ""]
    for phase in p.phases:
        if phase.status != "planned":
            lines += [f"{phase.name}: {phase.status}", ""]
            continue
        lines.append(f"{phase.name}:")
        if not phase.actions:
            lines.append("  (nothing)")
        for a in phase.actions:
            row = f"  {SYMBOLS[a.kind]} {a.kind:<8} {a.resource:<7} {a.name}"
            lines.append(f"{row}  {a.detail}" if a.detail else row)
            lines += [f"      ! {prob}" for prob in a.problems]
        lines += [f"  note: {n}" for n in phase.notes]
        lines.append("")
    if p.foreign:
        lines.append("foreign, ignored:")
        lines += [f"  {f.resource} {f.name}" for f in p.foreign]
        lines.append("")
    if p.refusals:
        lines.append("refused:")
        lines += [f"  {r}" for r in p.refusals]
        lines.append("")
    counts = {k: sum(a.kind == k for a in p.actions) for k in ActionKind}
    lines.append(
        f"Plan: {counts[ActionKind.CREATE]} to create, {counts[ActionKind.UPDATE]} to update, "
        f"{counts[ActionKind.RECREATE]} to recreate, {counts[ActionKind.ORPHAN]} orphaned."
    )
    return "\n".join(lines)


def plan_json(p: Plan) -> str:
    doc = {
        "phases": [
            {
                "name": ph.name,
                "status": ph.status,
                "actions": [
                    {"kind": str(a.kind), "resource": a.resource, "name": a.name,
                     "detail": a.detail, "problems": list(a.problems)}
                    for a in ph.actions
                ],
                "notes": ph.notes,
            }
            for ph in p.phases
        ],
        "foreign": [{"resource": f.resource, "name": f.name, "status": "foreign, ignored"} for f in p.foreign],
        "refusals": p.refusals,
        "changes_pending": p.has_changes,
    }
    return json.dumps(doc, indent=2) + "\n"
