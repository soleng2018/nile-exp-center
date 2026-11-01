# nile-lab

One command line tool that turns this server into a lab of Windows and macOS client VMs, reachable in the browser through Cloudflare. It reads one config file (the desired state), looks at what is running, and applies only the difference. The design lives in [docs/specs/0001-stack-architecture](docs/specs/0001-stack-architecture/index.md).

> **Status:** early scaffold. Today you can run `validate` and `plan` (both read only). `apply`, `status`, and `monitor` come with later features. Items marked *(later)* below are not needed yet, but you will need them once those features land.

## Prerequisites

You need these on the lab server before you start.

| What | Why | Check it |
|---|---|---|
| Ubuntu server (26.04, the target in spec 0001) | The tool uses systemd, udev, and sysfs | `lsb_release -a` |
| Root access (`sudo`) | Every `nile-lab` command refuses to run without root | `sudo -v` |
| `git` | To clone this repo | `git --version` |
| [uv](https://docs.astral.sh/uv/) | Installs the pinned Python 3.13 and the locked dependencies. It never touches system Python | `uv --version` |
| Docker Engine with the `docker compose` plugin | `plan` reads Docker networks and containers | `sudo docker compose version` |
| `iproute2` (the `ip` command) | `plan` reads routes to catch subnet overlaps | `ip -V` |
| KVM support *(later)* | The Windows and macOS VMs run on KVM | `ls /dev/kvm` |
| USB WiFi dongles and wired ports *(later)* | Each client gets its own dongle or wired port, matched by MAC address | `ip -br link` |

You do not need to install `cloudflared` yourself. The tool will set it up as a systemd service in a later feature.

## Secrets and values you need

Everything goes into **one file**, `/srv/nile-lab/lab.yaml`. Keep it `0600`, owned by root, and back it up: it is the only file you need to rebuild the lab. Never commit it (`.gitignore` already blocks `lab.yaml`, `*.token`, and `.env`). Start from [examples/lab.sample.yaml](examples/lab.sample.yaml).

| Value | Secret? | Where to get it | Config key |
|---|---|---|---|
| Cloudflare API token | **Yes** | Cloudflare dashboard, My Profile, API Tokens. Create a token used only by this tool. The exact least privilege permissions are still to be decided in feature 6 | `cloudflare.api_token` |
| Cloudflare account ID | No | Cloudflare dashboard, account home page, right side panel | `cloudflare.account_id` |
| Zone name | No | Your domain in Cloudflare, `nileglobalinc.com` | `cloudflare.zone_name` |
| MAC addresses of your dongles and wired ports | No | `ip -br link` on the server | `clients[].wifi_dongle_mac`, `wired_networks[].parent_mac` |
| Guest passwords and WiFi keys *(later)* | **Yes** | You choose them | schema comes in feature 3 |
| Authentik identity provider name *(later)* | No | Your Cloudflare Zero Trust login methods | schema comes in feature 6 |

The Cloudflare tunnel token is **not** something you provide. The tool fetches it from the API and writes it to `/etc/nile-lab/tunnel.token` (`0600`).

## Get started

1. Clone the repo and install the locked dependencies.
   ```sh
   git clone git@github.com:soleng2018/nile-exp-center.git
   cd nile-exp-center
   uv sync --locked
   ```
2. Try the plan against the sample config. `--offline` skips Cloudflare, so no token is needed.
   ```sh
   sudo .venv/bin/nile-lab plan --offline --config examples/lab.sample.yaml
   ```
3. Create your real config from the sample, then lock it down.
   ```sh
   sudo mkdir -p /srv/nile-lab
   sudo cp examples/lab.sample.yaml /srv/nile-lab/lab.yaml
   sudo chmod 600 /srv/nile-lab/lab.yaml
   sudoedit /srv/nile-lab/lab.yaml
   ```
4. Validate it. Every bad field is listed, and secret values are never printed.
   ```sh
   sudo .venv/bin/nile-lab validate
   ```
5. See what the tool would change. It only reads, it never changes the host, Docker, or Cloudflare.
   ```sh
   sudo .venv/bin/nile-lab plan
   sudo .venv/bin/nile-lab plan --json                # machine readable
   sudo .venv/bin/nile-lab plan --detailed-exitcode   # exit 3 when changes are pending
   ```

With no `--config`, every command reads `/srv/nile-lab/lab.yaml`.

## Run the tests

The unit tests need no root, no KVM, and no network.

```sh
uv run pytest
```

## Exit codes

`0` ok · `1` runtime error (for example Docker not responding) · `2` invalid config or refused precondition (not root, subnet overlap, host routes could not be read) · `3` changes pending (only with `plan --detailed-exitcode`).

## More

- What changed: [CHANGELOG.md](CHANGELOG.md)
- What is planned: [docs/scope/scope.md](docs/scope/scope.md)
