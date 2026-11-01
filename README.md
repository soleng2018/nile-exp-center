# nile-lab

One command line tool that turns this server into a lab of Windows and macOS client VMs, reachable in the browser through Cloudflare. It reads one config file (the desired state), looks at what is running, and applies only the difference. The design lives in [docs/specs/0001-stack-architecture](docs/specs/0001-stack-architecture/index.md).

## Try it

You need [uv](https://docs.astral.sh/uv/). It installs the pinned Python 3.13 by itself.

```sh
uv sync --locked
sudo .venv/bin/nile-lab plan --offline --config examples/lab.sample.yaml
sudo .venv/bin/nile-lab validate --config /srv/nile-lab/lab.yaml
uv run pytest
```

`plan` only reads. It never changes the host, Docker, or Cloudflare. So far the scaffold has `validate` and `plan`. `apply`, `status`, and `monitor` come with later features.

## Exit codes

`0` ok · `1` runtime error · `2` invalid config or refused precondition (not root, subnet overlap) · `3` changes pending (only with `plan --detailed-exitcode`).
