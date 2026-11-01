import pytest

from nile_lab.model import LABEL_MANAGED, Action, ActionKind, Container, DockerNetwork, Phase, Plan


@pytest.mark.parametrize("value, owned", [("true", True), ("True", False), ("1", False), (None, False)])
def test_ownership_needs_the_exact_managed_label(value, owned):
    labels = {} if value is None else {LABEL_MANAGED: value}
    assert Container("nile-x", True, labels).owned is owned
    assert DockerNetwork("nile-x", "bridge", (), labels).owned is owned


def plan_of(*kinds: ActionKind) -> Plan:
    return Plan([Phase("host", actions=[Action(k, "unit", f"u{i}") for i, k in enumerate(kinds)])])


# covers: AC-5 (what counts as "changes pending" for --detailed-exitcode)
@pytest.mark.parametrize("kind", [ActionKind.CREATE, ActionKind.UPDATE, ActionKind.RECREATE])
def test_real_changes_are_pending(kind):
    assert plan_of(ActionKind.NOOP, kind).has_changes


def test_noop_and_orphan_are_not_pending_changes():
    assert not plan_of(ActionKind.NOOP, ActionKind.ORPHAN).has_changes
    assert not plan_of().has_changes


def test_actions_flatten_phases_in_order():
    p = Plan([Phase("a", actions=[Action(ActionKind.NOOP, "unit", "1")]),
              Phase("b", actions=[Action(ActionKind.NOOP, "unit", "2")])])
    assert [a.name for a in p.actions] == ["1", "2"]
