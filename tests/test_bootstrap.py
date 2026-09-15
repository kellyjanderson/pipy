from pathlib import Path

from pipy.bootstrap import create_enrollment_bundle, decode_bundle, ensure_identity, genesis, make_script
from pipy.config import Paths
from pipy.store import StateStore


def test_genesis_and_make_me_a_pipy(tmp_path: Path) -> None:
    paths = Paths(tmp_path / "node")
    cfg = ensure_identity(paths, 31415)
    store = StateStore(paths.state_db)
    cfg = genesis(paths, store, cfg)
    bundle, token_id = create_enrollment_bundle(store, cfg, seed_host="10.0.0.2")
    decoded = decode_bundle(bundle)
    assert decoded["cluster_id"] == cfg.cluster_id
    assert decoded["cluster_public"] == cfg.cluster_public
    assert decoded["token_id"] == token_id
    script = make_script(bundle)
    assert "pip install" in script
    assert "pipy enroll --bundle" in script
    assert "exec pipy begin" in script
    assert cfg.cluster_private not in script
    store.close()
