"""MCP server exposing a small SQLite bug tracker.

Runs over stdio so the ADK agent can launch it as a subprocess:
    python bug_tracker_server.py
"""

import os
import sqlite3
from contextlib import closing

from mcp.server.fastmcp import FastMCP

DB_PATH = os.environ.get(
    "BUG_DB_PATH", os.path.join(os.path.dirname(__file__), "bugs.db")
)

SEVERITIES = ("low", "medium", "high", "critical")
STATUSES = ("open", "in_progress", "resolved", "closed")

SEED_TICKETS = [
    ("Login crashes with NullPointerException when email is empty", "AuthService.login() dereferences user.email before validation. Crash on submit with blank email field.", "high", "resolved", "auth", "Added null/blank check before lookup in AuthService.login(); added unit test."),
    ("App freezes on startup after upgrading to v2.4", "UI thread blocked by synchronous config migration on first launch after upgrade. Splash screen never dismisses.", "critical", "resolved", "mobile", "Moved migration to a background worker and show progress indicator."),
    ("Memory leak in image gallery when scrolling quickly", "Bitmaps are not recycled in RecyclerView adapter. Heap grows until OutOfMemoryError after ~200 images.", "high", "in_progress", "mobile", ""),
    ("API returns 500 on /orders when cart is empty", "OrderController.create() assumes at least one line item and throws IndexOutOfRangeException.", "medium", "resolved", "backend", "Return 400 with a clear message when cart is empty."),
    ("Database connection pool exhausted under load", "Connections are not released when an exception occurs inside transaction block. Pool of 20 saturates in minutes at 100 rps.", "critical", "resolved", "backend", "Wrapped transactions in try/finally (context manager) so connections always return to the pool."),
    ("Dark mode text unreadable on settings page", "Hard-coded #333 text colour on dark background in SettingsPage.css.", "low", "open", "frontend", ""),
    ("CORS error when frontend calls the payments API", "Access-Control-Allow-Origin header missing for staging domain. Preflight OPTIONS returns 403.", "medium", "resolved", "backend", "Added staging origin to the CORS allow-list and handled OPTIONS in middleware."),
    ("Timezone off by one day in report exports", "Dates are stored in UTC but exported using server local timezone, causing off-by-one at midnight boundaries.", "medium", "open", "reports", ""),
    ("Password reset email never arrives", "SMTP provider rejects messages from unverified sender domain. Bounces are silently swallowed.", "high", "resolved", "auth", "Verified sender domain (SPF/DKIM) and log bounce events."),
    ("Search is slow on tables with >1M rows", "Query on products.name uses LIKE '%term%' with no index; full table scan takes 8s.", "medium", "in_progress", "backend", ""),
    ("Race condition causes duplicate order confirmation emails", "Two workers pick up the same job because the queue visibility timeout is shorter than processing time.", "high", "open", "backend", ""),
    ("Build fails: module not found 'utils/date'", "Case-sensitive import path breaks on Linux CI; file is named Utils/Date.js.", "low", "resolved", "build", "Renamed directory to lowercase and fixed imports."),
    ("File upload fails for files larger than 10MB", "Nginx client_max_body_size defaults to 1MB/10MB; request rejected with 413 before reaching app.", "medium", "resolved", "infra", "Raised client_max_body_size to 50MB and added matching app-level limit."),
    ("JWT token expires immediately for some users", "Server clock drift of several minutes causes 'nbf' check to fail on freshly issued tokens.", "high", "resolved", "auth", "Enabled NTP sync on app servers and added 60s clock-skew leeway to validation."),
    ("Checkout button unresponsive on Safari", "Event handler uses Array.prototype.at() which is not supported in older Safari versions.", "medium", "resolved", "frontend", "Replaced with index access and added Babel polyfill."),
    ("Unhandled promise rejection crashes Node service", "fetchInventory() rejects when upstream times out; no catch, process exits under Node 20 default behaviour.", "critical", "resolved", "backend", "Added catch handler with retry/backoff and a global unhandledRejection logger."),
    ("Push notifications not delivered on Android 13", "POST_NOTIFICATIONS runtime permission is never requested, so notifications are silently dropped.", "high", "open", "mobile", ""),
    ("Docker image is 2.4GB", "Build includes dev dependencies and cache layers; multi-stage build not used.", "low", "open", "infra", ""),
    ("Pagination returns duplicate items across pages", "ORDER BY created_at is not unique; items with same timestamp shuffle between pages.", "medium", "in_progress", "backend", ""),
    ("Deadlock between inventory update and order creation", "Transactions lock rows in opposite order (inventory then orders vs orders then inventory).", "critical", "open", "backend", ""),
]

mcp = FastMCP("bug-tracker")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with closing(_conn()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL,
                component TEXT NOT NULL,
                resolution TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        if conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO tickets (title, description, severity, status, component, resolution)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                SEED_TICKETS,
            )
        conn.commit()


@mcp.tool()
def search_tickets(query: str, limit: int = 5) -> list[dict]:
    """Search bug tickets by keywords in title, description or resolution.

    Every word in the query is matched independently; tickets matching more
    words rank higher. Use this first to find duplicates or similar past bugs.

    Args:
        query: Keywords describing the problem, e.g. "null pointer login".
        limit: Maximum number of tickets to return.
    """
    words = [w for w in query.lower().split() if len(w) > 2]
    if not words:
        return []
    score = " + ".join(
        "(lower(title || ' ' || description || ' ' || resolution) LIKE ?)" for _ in words
    )
    params = [f"%{w}%" for w in words]
    with closing(_conn()) as conn:
        rows = conn.execute(
            f"SELECT id, title, severity, status, component, resolution, ({score}) AS score"
            " FROM tickets WHERE score > 0 ORDER BY score DESC, id LIMIT ?",
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]


@mcp.tool()
def get_ticket(ticket_id: int) -> dict:
    """Get the full details of one ticket, including its comments.

    Args:
        ticket_id: The numeric ticket id.
    """
    with closing(_conn()) as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"error": f"Ticket {ticket_id} not found"}
        comments = conn.execute(
            "SELECT body, created_at FROM comments WHERE ticket_id = ? ORDER BY id",
            (ticket_id,),
        ).fetchall()
    return {**dict(t), "comments": [dict(c) for c in comments]}


@mcp.tool()
def list_tickets(status: str = "", severity: str = "", component: str = "") -> list[dict]:
    """List tickets, optionally filtered. Leave a filter empty to ignore it.

    Args:
        status: One of open, in_progress, resolved, closed.
        severity: One of low, medium, high, critical.
        component: Component name such as auth, backend, mobile, frontend, infra.
    """
    clauses, params = [], []
    for col, val in (("status", status), ("severity", severity), ("component", component)):
        if val:
            clauses.append(f"{col} = ?")
            params.append(val.lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with closing(_conn()) as conn:
        rows = conn.execute(
            f"SELECT id, title, severity, status, component FROM tickets {where} ORDER BY id",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@mcp.tool()
def create_ticket(title: str, description: str, severity: str, component: str) -> dict:
    """File a new bug ticket. Only call this after searching for duplicates.

    Args:
        title: Short summary of the bug.
        description: Symptoms, error messages and steps to reproduce.
        severity: One of low, medium, high, critical.
        component: Affected component, e.g. auth, backend, mobile, frontend, infra.
    """
    severity = severity.lower()
    if severity not in SEVERITIES:
        return {"error": f"severity must be one of {SEVERITIES}"}
    with closing(_conn()) as conn:
        cur = conn.execute(
            "INSERT INTO tickets (title, description, severity, status, component)"
            " VALUES (?, ?, ?, 'open', ?)",
            (title, description, severity, component.lower()),
        )
        conn.commit()
    return {"id": cur.lastrowid, "status": "open", "title": title}


@mcp.tool()
def add_comment(ticket_id: int, comment: str) -> dict:
    """Add a comment to an existing ticket, e.g. a new occurrence or a finding.

    Args:
        ticket_id: The numeric ticket id.
        comment: Comment text.
    """
    with closing(_conn()) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"error": f"Ticket {ticket_id} not found"}
        conn.execute("INSERT INTO comments (ticket_id, body) VALUES (?, ?)", (ticket_id, comment))
        conn.commit()
    return {"ticket_id": ticket_id, "status": "comment added"}


@mcp.tool()
def update_ticket_status(ticket_id: int, status: str) -> dict:
    """Change a ticket's status.

    Args:
        ticket_id: The numeric ticket id.
        status: One of open, in_progress, resolved, closed.
    """
    status = status.lower()
    if status not in STATUSES:
        return {"error": f"status must be one of {STATUSES}"}
    with closing(_conn()) as conn:
        cur = conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.commit()
    if cur.rowcount == 0:
        return {"error": f"Ticket {ticket_id} not found"}
    return {"ticket_id": ticket_id, "status": status}


if __name__ == "__main__":
    _init_db()
    mcp.run(transport="stdio")
