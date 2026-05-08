"""Load and validate YAML configuration files."""

from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = {"name", "manifest", "selectors", "output"}
REQUIRED_SELECTOR_KEYS = {"row"}
REQUIRED_OUTPUT_KEYS = {"csv", "json"}


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load a YAML config file and validate required keys.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Parsed configuration as a dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required keys are missing from the config.
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError(f"Config file must be a YAML mapping: {path}")

    missing_top = REQUIRED_KEYS - set(config.keys())
    if missing_top:
        raise ValueError(f"Config is missing required keys: {missing_top}")

    selectors = config.get("selectors", {})
    missing_selectors = REQUIRED_SELECTOR_KEYS - set(selectors.keys())
    if missing_selectors:
        raise ValueError(
            f"Config 'selectors' is missing required keys: {missing_selectors}"
        )

    output = config.get("output", {})
    missing_output = REQUIRED_OUTPUT_KEYS - set(output.keys())
    if missing_output:
        raise ValueError(
            f"Config 'output' is missing required keys: {missing_output}"
        )

    return config
