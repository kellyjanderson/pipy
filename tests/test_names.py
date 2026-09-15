from types import SimpleNamespace

import pipy.names as names
from pipy.name_data import GIVEN_NAMES, NODE_NAME_DATASET_VERSION, SURNAMES


def test_node_name_dataset_v1_is_frozen_large_corpus() -> None:
    assert NODE_NAME_DATASET_VERSION == 1
    assert len(GIVEN_NAMES) == 412
    assert len(SURNAMES) == 519
    assert len(GIVEN_NAMES) * len(SURNAMES) == 213_828
    assert "Albert" in GIVEN_NAMES
    assert "Turing" in SURNAMES


def test_node_name_golden_vector() -> None:
    assert names.node_name("test-public-key") == "Isadore Newell"
    assert names.node_name("test-public-key") == names.node_name("test-public-key")


def test_public_key_changes_name_material() -> None:
    assert names.node_name("alpha") == "Brian Penrose"
    assert names.node_name("beta") == "Al-Biruni Vadhan"
    assert names.node_name("alpha") != names.node_name("beta")


def test_collision_resolution_is_deterministic_and_order_independent(monkeypatch) -> None:
    monkeypatch.setattr(names, "GIVEN_NAMES", ("Albert",))
    monkeypatch.setattr(names, "SURNAMES", ("Turing",))
    a = SimpleNamespace(node_id="node-a", public_key="public-a")
    b = SimpleNamespace(node_id="node-b", public_key="public-b")

    forward = names.cluster_node_names([a, b])
    reverse = names.cluster_node_names([b, a])

    assert forward == reverse
    assert forward["node-a"].startswith("Albert Turing-")
    assert forward["node-b"].startswith("Albert Turing-")
    assert forward["node-a"] != forward["node-b"]


def test_unique_base_name_has_no_suffix() -> None:
    a = SimpleNamespace(node_id="node-a", public_key="alpha")
    result = names.cluster_node_names([a])
    assert result == {"node-a": "Brian Penrose"}
