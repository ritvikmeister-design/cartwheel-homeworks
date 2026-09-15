"""Homework 2 authentication tests.

Everything here runs offline: no Langfuse, no Docker, and no model provider
key. The tests call the endpoint functions directly instead of over HTTP, so
no server has to be running.

Both cases check the same property from different angles: the authenticated
identity comes from the server, never from the caller.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_create_session_rejects_claimed_role_mismatch(world: dict) -> None:
    """User 1 is a shopper in the seeded world, so claiming merchant fails."""
    from server import app as server_app

    server_app._SESSIONS.clear()

    with pytest.raises(HTTPException) as excinfo:
        server_app.create_session(
            server_app.SessionCreate(user_id=1, role="merchant")
        )

    assert excinfo.value.status_code == 403

    # Fail closed: a rejected request must not leave a usable session behind.
    assert server_app._SESSIONS == {}


def test_token_cannot_authorize_a_different_session(world: dict) -> None:
    """A signed token is scoped to the one session it was issued for."""
    from server import app as server_app

    server_app._SESSIONS.clear()

    shopper = server_app.create_session(
        server_app.SessionCreate(user_id=1, role="shopper")
    )
    merchant = server_app.create_session(
        server_app.SessionCreate(user_id=9002, role="merchant")
    )
    assert shopper["session_id"] != merchant["session_id"]

    shopper_header = "Bearer " + shopper["token"]

    # Positive control: the token authorizes its own session.
    ctx = server_app._authorize(shopper["session_id"], shopper_header)
    assert ctx.user_id == 1
    assert ctx.role == "shopper"

    # The same token must not authorize a different session.
    with pytest.raises(HTTPException) as excinfo:
        server_app._authorize(merchant["session_id"], shopper_header)

    assert excinfo.value.status_code == 403
