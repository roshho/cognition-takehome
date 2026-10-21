"""Repository interface + per-app adapter registry.

Apps never touch storage directly: each app registers one or more adapter
factories (``register_adapter(app, "sql", Factory)``) at import time and
its routers call ``get_repository(app)``. The adapter kind is chosen by
config (see ``config.data_adapter_for``).

``Repository`` is the minimum contract every adapter satisfies (list /
get / update, plus a transaction scope and an audit write so each adapter
controls where the audit row lands). Apps may extend it with domain
methods — e.g. the KYC app's case aggregate in apps/kyc/backend.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol

from . import config


class Repository(Protocol):
    def transaction(self):
        """Context manager yielding a tx handle for one atomic unit of work."""
        ...

    def list(self, tx=None, **filters) -> list[dict]: ...
    def get(self, key: Any, tx=None) -> dict | None: ...
    def update(self, tx, key: Any, fields: dict) -> None: ...

    def write_audit(
        self,
        tx,
        *,
        actor: str,
        action: str,
        entity: str,
        entity_id: Any = None,
        before: Any = None,
        after: Any = None,
    ) -> None: ...


_FACTORIES: dict[str, dict[str, Callable[[], Any]]] = {}
_INSTANCES: dict[str, Any] = {}


def register_adapter(app: str, kind: str, factory: Callable[[], Any]) -> None:
    """Register an adapter factory for ``app`` (e.g. kind "sql" or "dataverse")."""
    _FACTORIES.setdefault(app, {})[kind] = factory
    _INSTANCES.pop(app, None)


def available_adapters(app: str) -> list[str]:
    return sorted(_FACTORIES.get(app, {}))


def get_repository(app: str):
    """The configured adapter instance for ``app`` (cached per process)."""
    if app in _INSTANCES:
        return _INSTANCES[app]
    factories = _FACTORIES.get(app)
    if not factories:
        raise LookupError(f"no data adapters registered for app {app!r}")
    kind = config.data_adapter_for(app, available=set(factories))
    if kind not in factories:
        raise RuntimeError(
            f"app {app!r} has no {kind!r} adapter (available: {', '.join(sorted(factories))})"
        )
    _INSTANCES[app] = factories[kind]()
    return _INSTANCES[app]


def _reset_for_tests() -> None:
    _INSTANCES.clear()
