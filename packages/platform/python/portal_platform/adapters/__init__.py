"""Repository selection via DATA_ADAPTER env ("sql" | "dataverse")."""
from .. import config

_repo = None


def get_repository():
    global _repo
    if _repo is not None:
        return _repo
    if config.DATA_ADAPTER == "dataverse":
        from .dataverse_repo import DataverseKycRepository

        _repo = DataverseKycRepository()
    else:
        from .sqlite_repo import SqlKycRepository

        _repo = SqlKycRepository()
    return _repo


def _reset_for_tests() -> None:
    global _repo
    _repo = None
