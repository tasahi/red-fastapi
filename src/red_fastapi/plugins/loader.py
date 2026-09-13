""" Plugin discovery and initialization loader for Red-Fastapi.
"""

import logging
from importlib.metadata import entry_points
from typing import List
from fastapi import FastAPI
from red_fastapi.plugins.base import BasePlugin
from red_fastapi.runtime import registry as runtime_registry
from red_fastapi.runtime.engine import engine as flow_engine

logger = logging.getLogger("red_fastapi.plugins")

# In-memory registry of loaded plugins
loaded_plugins: List[BasePlugin] = []


def load_plugins(app: FastAPI) -> None:
    """ Discovers and registers all installed plugins via standard Python entry points.
    Checks both 'red_fastapi.plugins' and legacy 'fastapi_red.plugins' entry point groups.
    """
    logger.info("Scanning for installed Red-Fastapi plugins...")

    discovered = []
    for group_name in ("red_fastapi.plugins", "fastapi_red.plugins"):
        try:
            discovered.extend(entry_points(group=group_name))
        except Exception as e:
            logger.warning(f"Error accessing entry_points for {group_name}: {e}")

    seen_names = {p.name for p in loaded_plugins}

    for ep in discovered:
        try:
            plugin_cls = ep.load()
            if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, BasePlugin)):
                logger.warning(f"Entry point {ep.name} does not subclass BasePlugin. Skipping.")
                continue

            plugin: BasePlugin = plugin_cls()
            if plugin.name in seen_names:
                continue
            seen_names.add(plugin.name)

            logger.info(f"Loading plugin '{plugin.name}' (v{plugin.version})...")

            # 1. Register node templates and icons
            plugin.register_nodes(runtime_registry)

            # 2. Register executable Node constructor types
            plugin.register_engine_types(flow_engine)

            # 3. Mount custom API routers
            routers = plugin.get_routers()
            for r in routers:
                app.include_router(r)

            loaded_plugins.append(plugin)
            logger.info(f"Plugin '{plugin.name}' successfully loaded.")

        except Exception as err:
            logger.error(f"Failed to load plugin '{ep.name}': {err}", exc_info=True)
