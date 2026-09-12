""" Base plugin interface for Red-Fastapi extensions.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from fastapi import APIRouter


class BasePlugin(ABC):
    """ Abstract base class that all Red-Fastapi plugins must inherit from.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """ Unique plugin name / identifier. """
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """ Plugin semantic version string. """
        pass

    def register_nodes(self, registry) -> None:
        """ Hook to register node HTML templates and icons into the node registry.
        """
        pass

    def register_engine_types(self, engine) -> None:
        """ Hook to register executable Node constructor subclasses into FlowEngine.
        """
        pass

    def get_routers(self) -> List[APIRouter]:
        """ Hook returning custom FastAPI APIRouters to mount on the main FastAPI application.
        """
        return []
