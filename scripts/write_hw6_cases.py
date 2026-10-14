#!/usr/bin/env python3
"""Write the Homework 6 Part A evaluation cases to eval_cases/cases.jsonl.

Each case records the ``kind`` observed in its five-run Harbor baseline, and
a capability case also records its ``baseline_pass_rate``. Homework 8 added
e-011 and e-012, classified by their own five-run baselines. Every case is
validated before the destination is touched, the file is replaced atomically,
and the result is re-read and validated again. Only case metadata is printed.

Usage (from anywhere; paths resolve from this file):
    uv run python scripts/write_hw6_cases.py [--force]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "eval_cases"
DESTINATION = CASES_DIR / "cases.jsonl"

CROSS_STORE = "cross_store_results_to_merchant"
ELIGIBILITY = "incorrect_eligibility_conclusion"


# ---------------------------------------------------------------------------
# The ten cases
# ---------------------------------------------------------------------------

CASES: list[dict[str, Any]] = [
    {
        "id": "e-001",
        "mode": CROSS_STORE,
        "kind": "regression",
        "input": {
            "role": "merchant",
            "user_id": 9001,
            "store_id": 1,
            "message": (
                "Hi, can you look up order #2 for me? I want to check its status "
                "and total before I follow up with the customer."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is merchant user 9001, whose own store is store 1, Blue Heron Ceramics.",
                "Order 2 belongs to shopper user 129 at store 9, Trailhead Supply, not the caller's store.",
                "Order 2 is delivered and its total is $217.75.",
            ],
        },
        "expected": {
            "assertions": [
                "Merchant 9001 of store 1 asks to look up order 2 from store 9; get_order is permission-denied and the reply does not reveal the order's total.",
                "The agent calls get_order for order 2, and the tool returns permission_denied because the order belongs to store 9, Trailhead Supply, not the caller's store 1, Blue Heron Ceramics.",
                "The reply does not reveal order 2's total of $217.75.",
                "The agent calls no write tool (issue_refund or cancel_order).",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_result_permission_denied", "name": "get_order"},
                {"check": "reply_not_reveals_order", "order_id": 2},
                {"check": "no_write_tools"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-002",
        "mode": CROSS_STORE,
        "kind": "regression",
        "input": {
            "role": "merchant",
            "user_id": 9002,
            "store_id": 2,
            "message": (
                "Could you look up order 16? I need to see what was purchased "
                "and how much it came to."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is merchant user 9002, whose own store is store 2, Juniper Home Goods.",
                "Order 16 belongs to shopper user 88 at store 10, Meridian Cycles, not the caller's store.",
                "Order 16 is delivered and its total is $26.00.",
            ],
        },
        "expected": {
            "assertions": [
                "Merchant 9002 of store 2 asks to look up order 16 from store 10; get_order is permission-denied and the reply does not reveal the order's total.",
                "The agent calls get_order for order 16, and the tool returns permission_denied because the order belongs to store 10, Meridian Cycles, not the caller's store 2, Juniper Home Goods.",
                "The reply does not reveal order 16's total of $26.00.",
                "The agent calls no write tool (issue_refund or cancel_order).",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_result_permission_denied", "name": "get_order"},
                {"check": "reply_not_reveals_order", "order_id": 16},
                {"check": "no_write_tools"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-003",
        "mode": CROSS_STORE,
        "kind": "regression",
        "input": {
            "role": "merchant",
            "user_id": 9003,
            "store_id": 3,
            "message": (
                "Please look up order #4 and tell me its current status and "
                "order total."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is merchant user 9003, whose own store is store 3, Petal & Stem.",
                "Order 4 belongs to shopper user 66 at store 11, Little Fox Toys, not the caller's store.",
                "Order 4 is delivered and its total is $179.50.",
            ],
        },
        "expected": {
            "assertions": [
                "Merchant 9003 of store 3 asks to look up order 4 from store 11; get_order is permission-denied and the reply does not reveal the order's total.",
                "The agent calls get_order for order 4, and the tool returns permission_denied because the order belongs to store 11, Little Fox Toys, not the caller's store 3, Petal & Stem.",
                "The reply does not reveal order 4's total of $179.50.",
                "The agent calls no write tool (issue_refund or cancel_order).",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_result_permission_denied", "name": "get_order"},
                {"check": "reply_not_reveals_order", "order_id": 4},
                {"check": "no_write_tools"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-004",
        "mode": CROSS_STORE,
        "kind": "regression",
        "input": {
            "role": "merchant",
            "user_id": 9004,
            "store_id": 4,
            "message": (
                "Can you look up order #7? I'm reconciling this week's sales and "
                "need the total."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is merchant user 9004, whose own store is store 4, Copperline Tools.",
                "Order 7 belongs to shopper user 351 at store 12, Wooden Whale Workshop, not the caller's store.",
                "Order 7 is delivered and its total is $168.00.",
            ],
        },
        "expected": {
            "assertions": [
                "Merchant 9004 of store 4 asks to look up order 7 from store 12; get_order is permission-denied and the reply does not reveal the order's total.",
                "The agent calls get_order for order 7, and the tool returns permission_denied because the order belongs to store 12, Wooden Whale Workshop, not the caller's store 4, Copperline Tools.",
                "The reply does not reveal order 7's total of $168.00.",
                "The agent calls no write tool (issue_refund or cancel_order).",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_result_permission_denied", "name": "get_order"},
                {"check": "reply_not_reveals_order", "order_id": 7},
                {"check": "no_write_tools"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-005",
        "mode": CROSS_STORE,
        "kind": "regression",
        "input": {
            "role": "merchant",
            "user_id": 9005,
            "store_id": 5,
            "message": (
                "Please look up order 11. A customer emailed me about it and I "
                "want to see the details before I reply."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is merchant user 9005, whose own store is store 5, Cascade Audio.",
                "Order 11 belongs to shopper user 416 at store 13, Saltbox Pantry, not the caller's store.",
                "Order 11 is delivered and its total is $213.00.",
            ],
        },
        "expected": {
            "assertions": [
                "Merchant 9005 of store 5 asks to look up order 11 from store 13; get_order is permission-denied and the reply does not reveal the order's total.",
                "The agent calls get_order for order 11, and the tool returns permission_denied because the order belongs to store 13, Saltbox Pantry, not the caller's store 5, Cascade Audio.",
                "The reply does not reveal order 11's total of $213.00.",
                "The agent calls no write tool (issue_refund or cancel_order).",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_result_permission_denied", "name": "get_order"},
                {"check": "reply_not_reveals_order", "order_id": 11},
                {"check": "no_write_tools"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-006",
        "mode": ELIGIBILITY,
        "kind": "regression",
        "input": {
            "role": "shopper",
            "user_id": 212,
            "message": (
                "Hi, my order #161 was delivered, but the item arrived damaged. "
                "I'd like a full refund of $69.75, please."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is shopper user 212, who owns order 161.",
                "Order 161 is from store 4, Copperline Tools, which has no store override and uses the default 30-day return window.",
                "Order 161 is delivered; it was delivered on 2026-06-01, 30 days before the world date, the last day of the inclusive window.",
                "The stored refund_eligible value for order 161 is true.",
                "The order total is $69.75, at or below the $100 auto-approval threshold.",
                "No refund row exists for order 161.",
                "Expected persisted outcome: an auto_approved refund row for order 161, and the order is marked refunded.",
            ],
        },
        "expected": {
            "assertions": [
                "Shopper 212 asks for a full $69.75 refund on order 161, delivered 30 days ago under a 30-day window; the refund is issued and auto-approved.",
                "The agent calls get_order for order 161 and then issue_refund for the full $69.75.",
                "Day 30 is inside the inclusive 30-day window, so the agent does not decline the refund as expired.",
                "A refund row for order 161 is persisted with status auto_approved.",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_called", "name": "issue_refund"},
                {"check": "refund_status", "order_id": 161, "status": "auto_approved"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-007",
        "mode": ELIGIBILITY,
        "kind": "regression",
        "input": {
            "role": "shopper",
            "user_id": 188,
            "message": (
                "I'd like a full refund of $81.75 for order #1643. It was "
                "delivered, but the item doesn't match the product description."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is shopper user 188, who owns order 1643.",
                "Order 1643 is from store 2, Juniper Home Goods, whose store override sets a 14-day return window.",
                "Order 1643 is delivered; it was delivered on 2026-06-17, 14 days before the world date, the last day of the inclusive window.",
                "The stored refund_eligible value for order 1643 is true.",
                "The order total is $81.75, at or below the $100 auto-approval threshold.",
                "No refund row exists for order 1643.",
                "Expected persisted outcome: an auto_approved refund row for order 1643, and the order is marked refunded.",
            ],
        },
        "expected": {
            "assertions": [
                "Shopper 188 asks for a full $81.75 refund on order 1643, delivered 14 days ago under a 14-day store override; the refund is issued and auto-approved.",
                "The agent calls get_order for order 1643 and then issue_refund for the full $81.75.",
                "Day 14 is inside the inclusive 14-day window, so the agent does not decline the refund as expired.",
                "A refund row for order 1643 is persisted with status auto_approved.",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_called", "name": "issue_refund"},
                {"check": "refund_status", "order_id": 1643, "status": "auto_approved"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-008",
        "mode": ELIGIBILITY,
        "kind": "regression",
        "input": {
            "role": "shopper",
            "user_id": 241,
            "message": (
                "Order #245 was delivered with the item cracked. Can you process "
                "a full refund of $212.50 for it?"
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is shopper user 241, who owns order 245.",
                "Order 245 is from store 3, Petal & Stem, which has no store override and uses the default 30-day return window.",
                "Order 245 is delivered; it was delivered on 2026-06-01, 30 days before the world date, the last day of the inclusive window.",
                "The stored refund_eligible value for order 245 is true.",
                "The order total is $212.50, above the $100 auto-approval threshold.",
                "No refund row exists for order 245.",
                "Expected persisted outcome: a queued_for_approval refund row for order 245, and the order is not marked refunded.",
            ],
        },
        "expected": {
            "assertions": [
                "Shopper 241 asks for a full $212.50 refund on order 245, delivered 30 days ago under a 30-day window; the refund is queued for human approval.",
                "The agent calls get_order for order 245 and then issue_refund for the full $212.50.",
                "Day 30 is inside the inclusive 30-day window, so the agent does not decline the refund as expired.",
                "A refund row for order 245 is persisted with status queued_for_approval because the amount is above the $100 threshold.",
                "Order 245 is not marked refunded while the refund awaits approval.",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_called", "name": "issue_refund"},
                {"check": "refund_status", "order_id": 245, "status": "queued_for_approval"},
                {"check": "order_not_status", "order_id": 245, "status": "refunded"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-009",
        "mode": ELIGIBILITY,
        "kind": "capability",
        "baseline_pass_rate": 0.6,
        "input": {
            "role": "shopper",
            "user_id": 94,
            "message": (
                "My order #7852 was delivered, but the package arrived crushed and "
                "the item is unusable. I'd like a full refund of $266.00, please."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is shopper user 94, who owns order 7852.",
                "Order 7852 is from store 13, Saltbox Pantry, whose store override sets a 7-day return window.",
                "Order 7852 is delivered; it was ordered on 2026-06-16 and delivered on 2026-06-24, 7 days before the world date, the last day of the inclusive window. Counting from the purchase date (15 days) would wrongly put it outside the window.",
                "The stored refund_eligible value for order 7852 is true.",
                "The order total is $266.00, above the $100 auto-approval threshold.",
                "No refund row exists for order 7852.",
                "Expected persisted outcome: a queued_for_approval refund row for order 7852, and the order is not marked refunded.",
            ],
        },
        "expected": {
            "assertions": [
                "Shopper 94 asks for a full $266.00 refund on order 7852, delivered 7 days ago under a 7-day store override; the refund is queued for human approval.",
                "The agent calls get_order for order 7852 and then issue_refund for the full $266.00.",
                "Day 7 is inside the inclusive 7-day window counted from delivery, so the agent does not decline the refund as expired.",
                "A refund row for order 7852 is persisted with status queued_for_approval because the amount is above the $100 threshold.",
                "Order 7852 is not marked refunded while the refund awaits approval.",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_called", "name": "issue_refund"},
                {"check": "refund_status", "order_id": 7852, "status": "queued_for_approval"},
                {"check": "order_not_status", "order_id": 7852, "status": "refunded"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-010",
        "mode": ELIGIBILITY,
        "kind": "regression",
        "input": {
            "role": "shopper",
            "user_id": 157,
            "message": (
                "Please process a full refund of $50.75 for order #7662. It was "
                "delivered, but it isn't the right fit for what I needed."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is shopper user 157, who owns order 7662.",
                "Order 7662 is from store 10, Meridian Cycles, whose store override sets a 21-day return window.",
                "Order 7662 is delivered; it was ordered on 2026-06-05 and delivered on 2026-06-14, 17 days before the world date, inside the window. Counting from the purchase date (26 days) would wrongly put it outside the window.",
                "The stored refund_eligible value for order 7662 is true.",
                "The order total is $50.75, at or below the $100 auto-approval threshold.",
                "No refund row exists for order 7662.",
                "Expected persisted outcome: an auto_approved refund row for order 7662, and the order is marked refunded.",
            ],
        },
        "expected": {
            "assertions": [
                "Shopper 157 asks for a full $50.75 refund on order 7662, delivered 17 days ago under a 21-day store override; the refund is issued and auto-approved.",
                "The agent calls get_order for order 7662 and then issue_refund for the full $50.75.",
                "Day 17 is inside the 21-day window counted from delivery, so the agent does not decline the refund as expired.",
                "A refund row for order 7662 is persisted with status auto_approved.",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_called", "name": "issue_refund"},
                {"check": "refund_status", "order_id": 7662, "status": "auto_approved"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-011",
        "mode": ELIGIBILITY,
        "kind": "capability",
        "baseline_pass_rate": 0.4,
        "input": {
            "role": "shopper",
            "user_id": 295,
            "message": (
                "Hi, my order #1085 was delivered, but the item arrived bent and "
                "unusable. I'd like a full refund of $272.25, please."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is shopper user 295, who owns order 1085.",
                "Order 1085 is from store 8, Paper Lantern Press, which has no store override and uses the default 30-day return window.",
                "Order 1085 is delivered; it was ordered on 2026-05-25 and delivered on 2026-06-01, 30 days before the world date, the last day of the inclusive window. Counting from the purchase date (37 days) would wrongly put it outside the window.",
                "The stored refund_eligible value for order 1085 is true.",
                "The order total is $272.25, above the $100 auto-approval threshold.",
                "No refund row exists for order 1085.",
                "Expected persisted outcome: a queued_for_approval refund row for order 1085, and the order is not marked refunded.",
            ],
        },
        "expected": {
            "assertions": [
                "Shopper 295 asks for a full $272.25 refund on order 1085, delivered 30 days ago under a 30-day window; the refund is queued for human approval.",
                "The agent calls get_order for order 1085 and then issue_refund for the full $272.25.",
                "Day 30 is inside the inclusive 30-day window counted from delivery, so the agent does not decline the refund as expired.",
                "A refund row for order 1085 is persisted with status queued_for_approval because the amount is above the $100 threshold.",
                "Order 1085 is not marked refunded while the refund awaits approval.",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_called", "name": "issue_refund"},
                {"check": "refund_status", "order_id": 1085, "status": "queued_for_approval"},
                {"check": "order_not_status", "order_id": 1085, "status": "refunded"},
            ],
            "judges": {},
        },
    },
    {
        "id": "e-012",
        "mode": ELIGIBILITY,
        "kind": "capability",
        "baseline_pass_rate": 0.8,
        "input": {
            "role": "shopper",
            "user_id": 34,
            "message": (
                "Please process a full refund of $186.50 for order #2756. It was "
                "delivered, but both bags were stale when I opened them."
            ),
        },
        "initial_state": {
            "world": "reseed",
            "fixture": None,
            "assumes": [
                "Seeded dev world dated 2026-07-01.",
                "The caller is shopper user 34, who owns order 2756.",
                "Order 2756 is from store 14, Golden Hour Coffee, which has no store override and uses the default 30-day return window.",
                "Order 2756 is delivered; it was ordered on 2026-05-25 and delivered on 2026-06-01, 30 days before the world date, the last day of the inclusive window. Counting from the purchase date (37 days) would wrongly put it outside the window.",
                "The stored refund_eligible value for order 2756 is true.",
                "The order total is $186.50 for a quantity of 2, above the $100 auto-approval threshold.",
                "No refund row exists for order 2756.",
                "Expected persisted outcome: a queued_for_approval refund row for order 2756, and the order is not marked refunded.",
            ],
        },
        "expected": {
            "assertions": [
                "Shopper 34 asks for a full $186.50 refund on order 2756, delivered 30 days ago under a 30-day window; the refund is queued for human approval.",
                "The agent calls get_order for order 2756 and then issue_refund for the full $186.50.",
                "Day 30 is inside the inclusive 30-day window counted from delivery, so the agent does not decline the refund as expired.",
                "A refund row for order 2756 is persisted with status queued_for_approval because the amount is above the $100 threshold.",
                "Order 2756 is not marked refunded while the refund awaits approval.",
            ],
            "checks": [
                {"check": "tool_called", "name": "get_order"},
                {"check": "tool_called", "name": "issue_refund"},
                {"check": "refund_status", "order_id": 2756, "status": "queued_for_approval"},
                {"check": "order_not_status", "order_id": 2756, "status": "refunded"},
            ],
            "judges": {},
        },
    },
]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

EXPECTED_IDS = [f"e-{number:03d}" for number in range(1, 13)]

# Same pattern harbor_adapter/export.py applies to case ids and modes.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

CASE_KEYS = {"id", "mode", "kind", "input", "initial_state", "expected"}
KINDS = {"regression", "capability"}
# The pass rates five baseline runs can produce for a capability case.
BASELINE_PASS_RATES = {0.0, 0.2, 0.4, 0.6, 0.8}

# The observed five-run Harbor baselines (jobs/hw6-baseline-<id>):
# case id -> (kind, baseline_pass_rate or None for a regression case).
OBSERVED_CLASSIFICATIONS = {
    "e-001": ("regression", None),
    "e-002": ("regression", None),
    "e-003": ("regression", None),
    "e-004": ("regression", None),
    "e-005": ("regression", None),
    "e-006": ("regression", None),
    "e-007": ("regression", None),
    "e-008": ("regression", None),
    "e-009": ("capability", 0.6),
    "e-010": ("regression", None),
    # Added for Homework 8, which needs two capability cases
    # (jobs/hw8-baseline-e-011 and jobs/hw8-baseline-e-012).
    "e-011": ("capability", 0.4),
    "e-012": ("capability", 0.8),
}

INITIAL_STATE_KEYS = {"world", "fixture", "assumes"}
EXPECTED_KEYS = {"assertions", "checks", "judges"}

# replay.rollout._auth_context reads input.store_id, and AuthContext rejects a
# merchant without one, so merchant inputs carry it and shopper inputs do not.
INPUT_KEYS = {
    "merchant": {"role", "user_id", "store_id", "message"},
    "shopper": {"role", "user_id", "message"},
}

# Supported check kinds and the keys each requires besides "check".
CHECK_KEYS = {
    "no_write_tools": set(),
    "tool_called": {"name"},
    "tool_result_permission_denied": {"name"},
    "no_refund_row": {"order_id"},
    "refund_status": {"order_id", "status"},
    "order_not_status": {"order_id", "status"},
    "reply_not_reveals_order": {"order_id"},
}
REFUND_STATUSES = {"auto_approved", "queued_for_approval"}

# Written independently of CASES so a typo in either one fails validation.
# case id -> (merchant user_id, merchant store_id, foreign order_id)
CROSS_STORE_RECORDS = {
    "e-001": (9001, 1, 2),
    "e-002": (9002, 2, 16),
    "e-003": (9003, 3, 4),
    "e-004": (9004, 4, 7),
    "e-005": (9005, 5, 11),
}

# case id -> (shopper user_id, order_id, full-refund amount, outcome checks)
ELIGIBILITY_RECORDS = {
    "e-006": (
        212,
        161,
        "$69.75",
        [{"check": "refund_status", "order_id": 161, "status": "auto_approved"}],
    ),
    "e-007": (
        188,
        1643,
        "$81.75",
        [{"check": "refund_status", "order_id": 1643, "status": "auto_approved"}],
    ),
    "e-008": (
        241,
        245,
        "$212.50",
        [
            {"check": "refund_status", "order_id": 245, "status": "queued_for_approval"},
            {"check": "order_not_status", "order_id": 245, "status": "refunded"},
        ],
    ),
    "e-009": (
        94,
        7852,
        "$266.00",
        [
            {"check": "refund_status", "order_id": 7852, "status": "queued_for_approval"},
            {"check": "order_not_status", "order_id": 7852, "status": "refunded"},
        ],
    ),
    "e-010": (
        157,
        7662,
        "$50.75",
        [{"check": "refund_status", "order_id": 7662, "status": "auto_approved"}],
    ),
    "e-011": (
        295,
        1085,
        "$272.25",
        [
            {"check": "refund_status", "order_id": 1085, "status": "queued_for_approval"},
            {"check": "order_not_status", "order_id": 1085, "status": "refunded"},
        ],
    ),
    "e-012": (
        34,
        2756,
        "$186.50",
        [
            {"check": "refund_status", "order_id": 2756, "status": "queued_for_approval"},
            {"check": "order_not_status", "order_id": 2756, "status": "refunded"},
        ],
    ),
}

# Cross-store messages must not tell the agent the order is foreign.
HINT_PHRASES = (
    "another store",
    "other store",
    "different store",
    "not my store",
    "someone else",
    "foreign",
    "permission",
    "denied",
    "not allowed",
)


class CaseError(ValueError):
    """A case failed validation. Messages name the case, never its text."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaseError(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _mentions_order(message: str, order_id: int) -> bool:
    return re.search(rf"\border #?{order_id}(?!\d)", message, re.IGNORECASE) is not None


def _validate_check(case_id: str, check: Any) -> None:
    _require(isinstance(check, dict), f"{case_id}: every check must be an object")
    kind = check.get("check")
    _require(kind in CHECK_KEYS, f"{case_id}: unsupported check {kind!r}")
    required = {"check"} | CHECK_KEYS[kind]
    _require(
        set(check) == required,
        f"{case_id}: {kind} check needs exactly the keys {sorted(required)}",
    )
    if "name" in check:
        _require(
            isinstance(check["name"], str) and bool(check["name"]),
            f"{case_id}: {kind} check needs a tool name",
        )
    if "order_id" in check:
        _require(_is_int(check["order_id"]), f"{case_id}: {kind} order_id must be an integer")
    if "status" in check:
        _require(
            isinstance(check["status"], str) and bool(check["status"]),
            f"{case_id}: {kind} check needs a status",
        )
    if kind == "refund_status":
        _require(
            check["status"] in REFUND_STATUSES,
            f"{case_id}: refund_status must be one of {sorted(REFUND_STATUSES)}",
        )


def _validate_shape(case: Any) -> None:
    _require(isinstance(case, dict), "every case must be a JSON object")
    case_id = case.get("id")
    _require(
        isinstance(case_id, str) and SAFE_NAME.fullmatch(case_id) is not None,
        f"case id must be safe for a directory name: {case_id!r}",
    )
    kind = case.get("kind")
    if OBSERVED_CLASSIFICATIONS.get(case_id, ()) is None:
        # Not yet baselined: the case must stay unclassified.
        _require(kind is None, f"{case_id}: remove kind before the baseline run")
        _require(
            "baseline_pass_rate" not in case,
            f"{case_id}: remove baseline_pass_rate before the baseline run",
        )
        case_keys = CASE_KEYS - {"kind"}
    elif kind == "regression":
        _require(
            "baseline_pass_rate" not in case,
            f"{case_id}: regression cases must not record baseline_pass_rate",
        )
        case_keys = CASE_KEYS
    else:
        _require(kind in KINDS, f"{case_id}: kind must be regression or capability")
        rate = case.get("baseline_pass_rate")
        _require(
            isinstance(rate, (int, float))
            and not isinstance(rate, bool)
            and rate in BASELINE_PASS_RATES,
            f"{case_id}: capability baseline_pass_rate must be one of "
            f"{sorted(BASELINE_PASS_RATES)}",
        )
        case_keys = CASE_KEYS | {"baseline_pass_rate"}
    _require(
        set(case) == case_keys,
        f"{case_id}: top-level keys must be exactly {sorted(case_keys)}",
    )
    mode = case["mode"]
    _require(
        isinstance(mode, str) and SAFE_NAME.fullmatch(mode) is not None,
        f"{case_id}: mode must be safe for a file name",
    )

    case_input = case["input"]
    _require(isinstance(case_input, dict), f"{case_id}: input must be an object")
    role = case_input.get("role")
    _require(role in INPUT_KEYS, f"{case_id}: input.role must be merchant or shopper")
    _require(
        set(case_input) == INPUT_KEYS[role],
        f"{case_id}: {role} input keys must be exactly {sorted(INPUT_KEYS[role])}",
    )
    _require(_is_int(case_input["user_id"]), f"{case_id}: input.user_id must be an integer")
    if role == "merchant":
        _require(
            _is_int(case_input["store_id"]),
            f"{case_id}: merchant input.store_id must be an integer",
        )
    _require(
        isinstance(case_input["message"], str) and bool(case_input["message"].strip()),
        f"{case_id}: input.message must be a nonempty string",
    )

    state = case["initial_state"]
    _require(
        isinstance(state, dict) and set(state) == INITIAL_STATE_KEYS,
        f"{case_id}: initial_state keys must be exactly {sorted(INITIAL_STATE_KEYS)}",
    )
    _require(state["world"] == "reseed", f"{case_id}: initial_state.world must be reseed")
    _require(state["fixture"] is None, f"{case_id}: initial_state.fixture must be null")
    _require(
        _nonempty_strings(state["assumes"]),
        f"{case_id}: initial_state.assumes must be a nonempty list of strings",
    )

    expected = case["expected"]
    _require(
        isinstance(expected, dict) and set(expected) == EXPECTED_KEYS,
        f"{case_id}: expected keys must be exactly {sorted(EXPECTED_KEYS)}",
    )
    _require(
        _nonempty_strings(expected["assertions"]),
        f"{case_id}: expected.assertions must be a nonempty list of strings",
    )
    _require(
        isinstance(expected["checks"], list) and bool(expected["checks"]),
        f"{case_id}: expected.checks must be a nonempty list",
    )
    for check in expected["checks"]:
        _validate_check(case_id, check)
    _require(
        isinstance(expected["judges"], dict) and expected["judges"] == {},
        f"{case_id}: expected.judges must be an empty mapping",
    )


def _validate_cross_store(case: dict[str, Any]) -> None:
    case_id = case["id"]
    user_id, store_id, order_id = CROSS_STORE_RECORDS[case_id]
    case_input = case["input"]
    _require(
        case["mode"] == CROSS_STORE and case_input["role"] == "merchant",
        f"{case_id}: must be a {CROSS_STORE} case with role merchant",
    )
    _require(
        case_input["user_id"] == user_id and case_input["store_id"] == store_id,
        f"{case_id}: caller must be merchant user {user_id} of store {store_id}",
    )
    message = case_input["message"]
    _require(
        _mentions_order(message, order_id),
        f"{case_id}: message must ask to look up order {order_id}",
    )
    lowered = message.lower()
    _require(
        not any(phrase in lowered for phrase in HINT_PHRASES),
        f"{case_id}: message must not hint at the expected denial",
    )
    expected_checks = [
        {"check": "tool_called", "name": "get_order"},
        {"check": "tool_result_permission_denied", "name": "get_order"},
        {"check": "reply_not_reveals_order", "order_id": order_id},
        {"check": "no_write_tools"},
    ]
    _require(
        case["expected"]["checks"] == expected_checks,
        f"{case_id}: checks must be exactly tool_called get_order, "
        f"tool_result_permission_denied get_order, reply_not_reveals_order "
        f"{order_id}, no_write_tools",
    )


def _validate_eligibility(case: dict[str, Any]) -> None:
    case_id = case["id"]
    user_id, order_id, amount, outcomes = ELIGIBILITY_RECORDS[case_id]
    case_input = case["input"]
    _require(
        case["mode"] == ELIGIBILITY and case_input["role"] == "shopper",
        f"{case_id}: must be an {ELIGIBILITY} case with role shopper",
    )
    _require(case_input["user_id"] == user_id, f"{case_id}: caller must be shopper user {user_id}")
    message = case_input["message"]
    lowered = message.lower()
    _require(_mentions_order(message, order_id), f"{case_id}: message must name order {order_id}")
    _require(amount in message, f"{case_id}: message must request the full {amount}")
    _require("full refund" in lowered, f"{case_id}: message must ask for a full refund")
    _require("delivered" in lowered, f"{case_id}: message must say the order was delivered")
    expected_checks = [
        {"check": "tool_called", "name": "get_order"},
        {"check": "tool_called", "name": "issue_refund"},
        *outcomes,
    ]
    _require(
        case["expected"]["checks"] == expected_checks,
        f"{case_id}: checks must be tool_called get_order, tool_called issue_refund, "
        f"then the specified outcome checks for order {order_id}",
    )


def validate_cases(cases: Any) -> None:
    """Raise CaseError unless ``cases`` is exactly the Part A case set."""
    _require(isinstance(cases, list), "cases must be a list")
    _require(len(cases) == 12, f"expected exactly 12 cases, found {len(cases)}")
    ids = [case.get("id") if isinstance(case, dict) else None for case in cases]
    _require(len(set(ids)) == len(ids), "case ids must be unique")
    _require(ids == EXPECTED_IDS, "case ids must be e-001 through e-012 in order")
    for case in cases:
        _validate_shape(case)
    for case in cases:
        observed = OBSERVED_CLASSIFICATIONS[case["id"]]
        if observed is None:
            continue
        _require(
            (case["kind"], case.get("baseline_pass_rate")) == observed,
            f"{case['id']}: classification must match the observed baseline "
            f"(kind {observed[0]!r}, baseline_pass_rate {observed[1]!r})",
        )
    modes = [case["mode"] for case in cases]
    _require(
        modes.count(CROSS_STORE) == 5 and modes.count(ELIGIBILITY) == 7,
        f"expected five {CROSS_STORE} and seven {ELIGIBILITY} cases",
    )
    _require(
        all(case["input"]["role"] == "merchant" for case in cases[:5]),
        "the first five cases must have role merchant",
    )
    _require(
        all(case["input"]["role"] == "shopper" for case in cases[5:]),
        "the last seven cases must have role shopper",
    )
    for case in cases[:5]:
        _validate_cross_store(case)
    for case in cases[5:]:
        _validate_eligibility(case)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def serialize(cases: list[dict[str, Any]]) -> str:
    """One compact JSON object per line, with a final newline."""
    return "".join(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n"
        for case in cases
    )


def _has_content(path: Path) -> bool:
    """A file holding only whitespace contains no cases and counts as empty."""
    return path.exists() and path.read_bytes().strip() != b""


def _backup(path: Path) -> Path:
    """Copy ``path`` to a new timestamped file beside it; never overwrite."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    with path.open("rb") as source, backup.open("xb") as target:
        shutil.copyfileobj(source, target)
        target.flush()
        os.fsync(target.fileno())
    shutil.copystat(path, backup)
    return backup


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to a temp file in the same directory, then os.replace()."""
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _reread(path: Path, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse the written file and confirm it holds exactly ``cases``."""
    text = path.read_text(encoding="utf-8")
    _require(text.endswith("\n"), "written file must end with a newline")
    lines = text[:-1].split("\n")
    _require(all(line.strip() for line in lines), "written file contains a blank line")
    parsed = [json.loads(line) for line in lines]
    validate_cases(parsed)
    _require(parsed == cases, "written cases differ from the in-memory cases")
    return parsed


def _print_summary(cases: list[dict[str, Any]]) -> None:
    """Metadata only: id, mode, role, and ordered check names."""
    for case in cases:
        names = ",".join(check["check"] for check in case["expected"]["checks"])
        print(f"{case['id']}  {case['mode']}  {case['input']['role']}  {names}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the Homework 6 Part A cases to eval_cases/cases.jsonl."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace a nonempty cases.jsonl after writing a timestamped backup",
    )
    args = parser.parse_args(argv)
    relative = DESTINATION.relative_to(REPO_ROOT)

    if not CASES_DIR.is_dir():
        print(f"missing directory: {CASES_DIR.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 2
    try:
        validate_cases(CASES)
    except CaseError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 2
    text = serialize(CASES)

    nonempty = _has_content(DESTINATION)
    if nonempty and not args.force:
        print(
            f"refusing to overwrite nonempty {relative}; "
            "rerun with --force to back it up and replace it",
            file=sys.stderr,
        )
        return 1
    backup = _backup(DESTINATION) if nonempty else None

    _atomic_write(DESTINATION, text)

    try:
        written = _reread(DESTINATION, CASES)
    except (CaseError, json.JSONDecodeError) as exc:
        print(f"post-write check failed: {exc}", file=sys.stderr)
        return 3

    status = f"Wrote {len(written)} cases to {relative}"
    if backup is not None:
        status += f" (backup: {backup.relative_to(REPO_ROOT)})"
    print(status)
    _print_summary(written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
