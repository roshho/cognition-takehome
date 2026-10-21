"""__APP_TITLE__ repository — the router talks to this, never to the DB.

``SqlRepository`` (platform) gives list / get / update / insert /
write_audit over one table; add a second adapter class (e.g. a Dataverse
one built on ``portal_platform.adapters.dataverse.DataverseClient``) and
register it in router.py to make the data source swappable via config.
"""
from portal_platform.adapters.sql import SqlRepository

TABLE = "__APP_TABLE__"


class Sql__APP_CLASS__Repository(SqlRepository):
    table = TABLE
    columns = frozenset({"name", "status", "owner", "updated_at"})
