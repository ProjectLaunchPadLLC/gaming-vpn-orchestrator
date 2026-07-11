"""Core infrastructure for Gaming VPN Orchestrator.

Modular components for AI Workers, VPN management, traffic classification,
and metrics collection. Designed for AIOL-style composition and extensibility.
"""

__version__ = "0.1.0"
__author__ = "ProjectLaunchPadLLC"

from .logger import Logger
from .database import Database, get_database

__all__ = [
    "Logger",
    "Database",
    "get_database",
]
