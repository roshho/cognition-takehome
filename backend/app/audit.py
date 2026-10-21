"""Backwards-compat shim — the audit helper lives in portal_platform so
other apps can reuse it; existing app code keeps importing it from here."""
from portal_platform.audit import (  # noqa: F401
    RequestIdMiddleware,
    audit_append_only_guard,
    current_request_id,
    set_request_id,
    write_audit,
)
