"""nile-lab: declarative reconciler for the Nile client VM lab (spec 0001)."""


def main() -> None:
    from nile_lab.cli import app

    app()
