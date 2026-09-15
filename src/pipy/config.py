from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from platformdirs import user_data_dir


@dataclass(slots=True)
class Paths:
    root: Path

    @property
    def state_db(self) -> Path:
        return self.root / "state.sqlite3"

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    @property
    def node_private(self) -> Path:
        return self.root / "node.key"

    @property
    def cluster_private(self) -> Path:
        return self.root / "imapipy.key"


def default_paths() -> Paths:
    override = os.environ.get("PIPY_HOME")
    root = Path(override).expanduser() if override else Path(user_data_dir("pipy", "pipy"))
    root.mkdir(parents=True, exist_ok=True)
    return Paths(root)


@dataclass(slots=True)
class LocalConfig:
    node_public: str
    node_private: str
    node_id: str
    cluster_id: str | None = None
    cluster_public: str | None = None
    cluster_private: str | None = None
    unity_key: str | None = None
    bootstrap_bundle: str | None = None
    wifi_ssid: str | None = None
    wifi_password: str | None = None
    port: int = 31415

    @property
    def enrolled(self) -> bool:
        return bool(self.cluster_id and self.cluster_public and self.unity_key)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    @classmethod
    def load(cls, path: Path) -> "LocalConfig":
        return cls(**json.loads(path.read_text(encoding="utf-8")))
