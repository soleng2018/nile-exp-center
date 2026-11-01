# Scope: Nile client VM lab

A set of scripts that turns this server into a lab of Windows and macOS client VMs, each one reachable in the browser (RDP for Windows, VNC for macOS) through Cloudflare, behind the Authentik login you already use. Internal employees use the VMs for demos. One config and secrets file drives everything, the server comes back on its own after a reboot, and adding a client only touches what is new.

**Build approach:** Tracer Bullet (prove one real path works end to end first, config to VM to browser login, then thicken it one strand at a time).
**Workflow:** GA (after develop: check verify, then test, then a fresh model check review, then document). The project default level of rigor. `/architect` is the recommended first stop for a feature with a real decision, but skippable when you already know the build. Any feature can carry its own tag (e.g. `· Beta`) to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use `/develop` and skip `/architect`. You decide when a feature is `done`._

What we know about the server today: Ubuntu 26.04, 64 cores, 121 GB RAM, KVM available, Docker and `cloudflared` not installed yet, 11 identical USB WiFi dongles (TP-Link Archer T3U, so each must be told apart by MAC or USB port), `eno1` connected and 7 spare wired ports for macvlan.

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Stack & architecture | Foundation | in-progress |
| 2 | Coding standards & tooling | Foundation | planned |
| 3 | Config & secrets file | Foundation | planned |
| 4 | Host bootstrap | Foundation | planned |
| 5 | Windows wireless client VM | Slice 1 | planned |
| 6 | Cloudflare browser access | Slice 1 | planned |
| 7 | Reboot recovery | Slice 2 | planned |
| 8 | Add clients by delta | Slice 3 | planned |
| 9 | macOS wired client VM | Slice 4 | planned |
| 10 | Monitoring & auto recovery | Slice 5 | planned |

## Foundations

### 1. Stack & architecture · in-progress
Decide what the scripts are written in, how the pieces fit (setup, reconcile, startup scripts, monitor), and how the run applies only the difference between the config and what is running. Then scaffold a runnable project.
**Done when:** the choices are recorded in a spec, and a scaffolded entry script runs on this server and prints what it would do from a sample config.
spec [0001](../specs/0001-stack-architecture/index.md) · code in [src/nile_lab/](../../src/nile_lab/)
- [x] Decide the stack (spec): `/architect stack & architecture`
- [x] Scaffold from the decision: `/develop stack & architecture`
- [x] Verify it: `/check verify stack & architecture`
- [x] Test it: `/test stack & architecture`
- [x] Review it (fresh model): `/check review stack & architecture`
- [ ] Document it: `/document stack & architecture`

### 2. Coding standards & tooling
Capture conventions and checks (for example shell and script linting) from the real scaffolded project, then install them.
**Done when:** root `AGENTS.md` reflects the real stack, and lint and format checks run clean.
- [ ] Capture conventions + tooling choices: `/audit`

### 3. Config & secrets file · needs a decision
The single file you back up: server settings, Cloudflare account and tunnel, Authentik app settings, and every client (type, dongle or wired port, network, startup software). It can live outside this folder.
**Done when:** one file describes a whole lab, the scripts refuse a file with missing or wrong fields and say why, secrets never print to logs or the terminal, and the file is readable only by its owner.
- [ ] Design it (spec): `/architect config & secrets file`

### 4. Host bootstrap · needs a decision
Get this server ready to run VMs: Docker, KVM access, `cloudflared`, and anything the dongles and macvlan need. Safe to run again on a server that is already set up.
**Done when:** on a fresh Ubuntu install, one run leaves the host ready, and a second run changes nothing.
- [ ] Design it (spec): `/architect host bootstrap`

## Slice 1: One Windows VM, reachable in the browser

### 5. Windows wireless client VM · needs a decision
One Windows VM (based on `dockur/windows`, following `docker-clients` without Traefik labels) with a management interface for RDP and one USB WiFi dongle passed through as its client network. A startup script installs the needed software on first boot and makes the WiFi interface the preferred route.
**Done when:** a client listed in the config boots with its assigned dongle (picked by MAC or port, not by model), joins the WiFi network, prefers WiFi over the management interface, and has its software running after the first boot.
- [ ] Design it (spec): `/architect windows wireless client VM`

### 6. Cloudflare browser access · needs a decision
A new tunnel for this server, with each VM published as a browser RDP or VNC app behind Cloudflare Access, using the existing Authentik login and the same policy style as the apps on the `nova` tunnel. Configured through the Cloudflare API; `nova` itself is never changed.
**Done when:** an employee opens the app URL, signs in through Authentik, and lands in the Windows VM over RDP in the browser; someone outside the policy is refused; the run leaves `nova` and its apps untouched.
- [ ] Design it (spec): `/architect cloudflare browser access`

## Slice 2: Survive a reboot

### 7. Reboot recovery · needs a decision
After a reboot or power cut, the server brings back every VM, its dongle or wired link, and the tunnel without anyone stepping in.
**Done when:** after a reboot, every configured VM is running on its own dongle (even if USB numbering changed), and every app is reachable in the browser again.
- [ ] Design it (spec): `/architect reboot recovery`

## Slice 3: Grow the lab safely

### 8. Add clients by delta · needs a decision
Add a client to the config, run the script again, and only the new client is created and published. Running VMs and their Cloudflare apps stay as they are.
**Done when:** adding a client creates only that VM and its app; a run with no config change does nothing; a dry run shows the planned changes before applying them.
- [ ] Design it (spec): `/architect add clients by delta`

## Slice 4: macOS wired clients

### 9. macOS wired client VM · needs a decision
macOS VMs (based on `dockur/macos`) on a macvlan link from a spare wired port, plus a management interface for VNC, a first boot startup script, and the wired link as the preferred route. Published in the browser over VNC like the Windows VMs.
**Done when:** a macOS client in the config boots on its macvlan link, prefers it over the management interface, has its software running after the first boot, and opens over VNC in the browser after the Authentik login.
- [ ] Design it (spec): `/architect macOS wired client VM`

## Slice 5: Keep it healthy

### 10. Monitoring & auto recovery · needs a decision
A monitor that watches every VM and USB dongle, recovers what fails (restart the VM, reset and reattach the dongle), and logs what it did.
**Done when:** a stopped VM or a pulled and reinserted dongle is detected and recovered without help, each event and its outcome is logged, and a client that keeps failing is logged as failed instead of restarted forever.
- [ ] Design it (spec): `/architect monitoring & auto recovery`

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Alerts**: notify someone when recovery happens or fails · needs a decision
- **Remove or change a client**: take a client out of the config and clean up its VM and app · needs a decision
- **Windows wired clients**: Windows VMs on macvlan · needs a decision
- **macOS wireless clients**: limited driver support for these dongles on macOS · needs a decision

## Legend

**The decision box.** Every feature carries exactly one, the sub task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack & architecture), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | **`/architect` at spec capture** | `Design it` ticked; spec linked; `Build it: /develop <feature>` + **2 to 5 milestones**; the tier's closing boxes (`Verify it` Alpha+, `Test it` Beta+, `Review it` + `Document it` GA); any surfaced follow up enrolled |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | **you, when you decide it is** (any skill sets it when you say so); `/sync` reconciles | boxes you ran ticked, skipped ones marked skipped; the tier's last stage (`Prototype` → after `/develop`; `Alpha` → after `/check verify`; `Beta`/`GA` → after `/test`) is the suggested point to call it done; `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop` (or `/audit` for standards & tooling). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (from before this workflow) and `dropped` (taken out of scope, kept for history).
- **Approach tag** beside a heading (e.g. `· Facade`) overrides the project default for that feature; no tag = inherits it.
- **Workflow tier tag** beside a heading (e.g. `· Beta`, `· Prototype`) sets that one feature's rigor above or below the project default; no tag inherits the default. It decides the feature's check boxes and each skill's next suggestion.
- **Workflow** (header line) is the project default, what runs after `/develop`: **Prototype** = nothing (trust develop's own build time self check); **Alpha** = `/check verify`; **Beta** = `/check verify` then `/test`; **GA** = adds a fresh model `/check review` then `/document`. A feature built on an unratified decision (an `Assumed` spec) stays flagged, but that never blocks `done`.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
