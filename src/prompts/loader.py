import os
from functools import lru_cache
from typing import Any, Dict

import yaml

PROMPTS_DIR = os.path.dirname(__file__)


@lru_cache(maxsize=None)
def load_prompt(agent_name: str, version: str = "v1") -> Dict[str, Any]:
    """Loads a versioned YAML prompt template for the given agent."""
    path = os.path.join(PROMPTS_DIR, agent_name, f"{version}.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No prompt found for agent={agent_name} version={version} at {path}")
    with open(path, "r") as f:
        return yaml.safe_load(f)


def render_prompt(agent_name: str, version: str = "v1", **kwargs) -> str:
    """Loads a prompt and formats its `template` with the given variables."""
    prompt = load_prompt(agent_name, version)
    return prompt["template"].format(**kwargs)
