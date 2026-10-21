"""Tool registry — what the portal home page lists and summarises.

Each app calls ``register_tool(...)`` at import. ``roles`` controls card
visibility (the app's endpoints still enforce RBAC themselves);
``summary(user)`` returns dashboard stats as ``[{label, value, tone?}]``
and should read through the app's repository.
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Tool:
    id: str
    name: str
    description: str
    path: str
    roles: list[str]
    order: int = 100
    summary: Callable[[dict], list[dict]] | None = field(default=None, repr=False)

    def public(self) -> dict:
        return {k: getattr(self, k) for k in ("id", "name", "description", "path", "roles")}


_TOOLS: dict[str, Tool] = {}


def register_tool(
    id: str,
    *,
    name: str,
    description: str,
    path: str,
    roles: list[str],
    order: int = 100,
    summary: Callable[[dict], list[dict]] | None = None,
) -> None:
    _TOOLS[id] = Tool(id, name, description, path, list(roles), order, summary)


def registered_tools() -> list[Tool]:
    return sorted(_TOOLS.values(), key=lambda t: (t.order, t.name))
