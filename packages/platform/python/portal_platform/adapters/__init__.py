"""Adapter building blocks: ``SqlRepository`` (real, over the portal's
SQLite DB) and ``DataverseClient`` (OData Web API plumbing). App-specific
adapters subclass these and register via ``portal_platform.repository``."""
from ..repository import get_repository, register_adapter, _reset_for_tests  # noqa: F401

__all__ = ["get_repository", "register_adapter", "_reset_for_tests"]
