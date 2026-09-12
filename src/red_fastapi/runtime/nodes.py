""" Runtime nodes API layer.

Mirrors @node-red/runtime/lib/nodes/index.js:
- getNodeList
- getNodeConfigs
- getNodeConfig
- getIconList
- getNodeIconPath
- getModuleCatalog
- getModuleCatalogs
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from red_fastapi.config import settings
from red_fastapi.runtime import registry


def init():
    """ Initialises the runtime nodes subsystem and loads core nodes.
    """
    registry.load_core_nodes()


def get_node_list() -> List[dict]:
    """ Gets the list of available node sets.
    """
    return registry.get_node_list()


def get_node_configs(lang: str = "en-US") -> str:
    """ Gets all node HTML templates concatenated.
    """
    return registry.get_all_node_configs(lang=lang)


def get_node_config(set_id: str, lang: str = "en-US") -> Optional[str]:
    """ Gets the HTML template for a single node set.
    """
    return registry.get_node_config(set_id, lang=lang)


def get_icon_list() -> Dict[str, List[str]]:
    """ Gets the list of icon names grouped by module.
    """
    return registry.get_node_icons()


def get_node_icon_path(module_name: str, icon_name: str) -> Optional[Path]:
    """ Resolves the filesystem path to a node icon.
    """
    return registry.get_node_icon_path(module_name, icon_name)


def get_module_catalogs(lang: str = "en-US") -> dict:
    """ Returns node i18n catalogs grouped by namespace,
    matching runtimeAPI.nodes.getModuleCatalogs().
    """
    catalogs = {}
    catalog_file = settings.locales_dir / lang / "node-red-messages.json"
    if not catalog_file.is_file():
        catalog_file = settings.locales_dir / "en-US" / "node-red-messages.json"

    if catalog_file.is_file():
        try:
            with open(catalog_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    catalogs["node-red"] = data
        except Exception:
            pass

    return catalogs


def get_module_catalog(module: str, lang: str = "en-US") -> dict:
    """ Returns the node i18n catalog for a specific module,
    matching runtimeAPI.nodes.getModuleCatalog().
    """
    all_catalogs = get_module_catalogs(lang=lang)
    return all_catalogs.get(module, {})

