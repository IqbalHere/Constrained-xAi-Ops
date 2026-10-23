"""Central Configuration Loader for Constrained-xAIOps.

Loads and parses configs/default.yaml dynamically to ensure zero hard-coded magic numbers.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


@lru_cache(maxsize=4)
def load_default_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Loads and caches the default YAML configuration."""
    if config_path:
        path = Path(config_path).resolve()
    else:
        path = (CONFIGS_DIR / "default.yaml").resolve()
        if not path.exists():
            path = Path("configs/default.yaml").resolve()

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_hyperparameter(key: str, default: Any = None) -> Any:
    """Retrieves a named hyperparameter from default.yaml."""
    cfg = load_default_config()
    return cfg.get("hyperparameters", {}).get(key, default)


def get_paper_metadata() -> Dict[str, Any]:
    """Retrieves paper title, authors, affiliations, and keywords from default.yaml."""
    cfg = load_default_config()
    return cfg.get("paper", {})
