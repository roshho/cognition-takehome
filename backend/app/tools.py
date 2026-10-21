"""Registry of tools surfaced on the portal home page.

Phases 2 and 3 add their tools here; roles control visibility, and each
tool's own endpoints still enforce the same roles server-side.
"""

TOOLS = [
    {
        "id": "kyc-queue",
        "name": "KYC review queue",
        "description": "Work the onboarding review queue: verify documents, screening hits, approve or reject.",
        "path": "/kyc",
        "roles": ["reviewer", "admin"],
    },
    {
        "id": "directory",
        "name": "User directory",
        "description": "Browse portal users and their roles.",
        "path": "/directory",
        "roles": ["admin"],
    },
    {
        "id": "audit-trail",
        "name": "Audit trail",
        "description": "See the audit log — admins see everything, reviewers see their own actions.",
        "path": "/audit",
        "roles": ["reviewer", "admin"],
    },
]
