""" Plugin discovery and initialization loader for FastAPI-Red.
"""

import logging
from importlib.metadata import entry_points
from typing import List
from fastapi import FastAPI
from fastapi_red.plugins.base import BasePlugin
from fastapi_red.runtime import registry as runtime_registry
from fastapi_red.runtime.engine import engine as flow_engine

logger = logging.getLogger("fastapi_red.plugins")

# In-memory registry of loaded plugins
loaded_plugins: List[BasePlugin] = []


def load_plugins(app: FastAPI) -> None:
    """ Discovers and registers all installed plugins via standard Python entry points.
    Entry point group: 'fastapi_red.plugins'
    """
    logger.info("Scanning for installed FastAPI-Red plugins...")

    try:
        discovered = entry_points(group="fastapi_red.plugins")
    except Exception as e:
        logger.warning(f"Error accessing entry_points: {e}")
        return

    for ep in discovered:
        try:
            plugin_cls = ep.load()
            if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, BasePlugin)):
                logger.warning(f"Entry point {ep.name} does not subclass BasePlugin. Skipping.")
                continue

            plugin: BasePlugin = plugin_cls()
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
