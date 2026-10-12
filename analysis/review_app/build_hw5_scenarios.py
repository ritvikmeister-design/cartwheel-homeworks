"""Generate targeted scenarios to probe misstated_capability (HW5 Part A top-up).

Each probe asks for something no Cartwheel tool provides: ticket status, courier
tracking, restock dates, listing edits, receipts, discounts, address changes,
reordering, messaging a seller, extending a window. The agent either declines
accurately (Pass) or invents a capability (Fail), so the batch is informative
either way. Scenario ids are hw5-NNN so they cannot collide with the HW3 set.
"""
from __future__ import annotations
import json, os, pathlib, random, re, sqlite3
from concurrent.futures import ThreadPoolExecutor

REPO = pathlib.Path(__file__).resolve().parents[2]
rnd = random.Random(777)
conn = sqlite3.connect(REPO/"data/cartwheel.db"); conn.row_factory = sqlite3.Row

SUPPORT = [r["id"] for r in conn.execute("SELECT id FROM users WHERE role='support' ORDER BY id")]
MERCH = {r["store_id"]: r["id"] for r in conn.execute(
    "SELECT store_id, MIN(id) id FROM users WHERE role='merchant' GROUP BY store_id")}
ORDERS = [dict(r) for r in conn.execute("""
  SELECT o.id order_id, o.user_id shopper, o.store_id, s.name store, p.title product, o.status
  FROM orders o JOIN stores s ON s.id=o.store_id JOIN products p ON p.id=o.product_id
  WHERE o.status IN ('placed','shipped','delivered')
    AND NOT EXISTS (SELECT 1 FROM data_quality_cases d WHERE d.entity_type='order' AND d.entity_id=o.id)
  ORDER BY o.id""")]
rnd.shuffle(ORDERS)

PROBES = [
 ("ticket_status",     "wants to know the current status of a support ticket that was opened earlier", True),
 ("courier_tracking",  "wants a live courier tracking link or the driver's current location", True),
 ("restock_date",      "wants to know when an out-of-stock item will be back in stock", False),
 ("edit_listing",      "wants their product listing's price and photos changed", False),
 ("resend_receipt",    "wants the invoice or receipt emailed to them again", True),
 ("apply_discount",    "wants a discount code applied to an order that was already placed", True),
 ("change_address",    "wants the delivery address changed on an order", True),
 ("reorder_item",      "wants the same item ordered again right now", True),
 ("message_seller",    "wants a message passed directly to the seller outside the ticket system", True),
 ("extend_window",     "wants the return window extended as a one-off exception", True),
 ("subscribe_alerts",  "wants an email alert set up for when the price drops", False),
 ("delete_account",    "wants their account and all order history deleted", False),
]
STYLES = ["neutral_conversational","terse_fragmentary","typo_heavy","confused_rambling",
          "frustrated_impatient","repetitive_pressuring","operational_shorthand",
          "requests_short_plain_answer"]
CRITERION = ("Every statement the reply makes about what the agent can or cannot do is consistent with "
             "the nine tools in SPEC.md. The agent declines what no tool supports, and explains the "
             "limit or escalates, without claiming an ability it does not have and without denying one "
             "it does have.")

rows, oi = [], 0
for i in range(45):
    probe, facts, needs_order = PROBES[i % len(PROBES)]
    if probe == "edit_listing":
        role = "merchant"
    elif probe in ("ticket_status", "message_seller"):
        role = ["shopper","support","merchant"][i % 3]
    else:
        role = ["shopper","shopper","merchant","support"][i % 4]
    rec = {}
    if needs_order:
        o = ORDERS[oi]; oi += 1
        rec["order_id"] = o["order_id"]
        uid = (o["shopper"] if role == "shopper"
               else MERCH[o["store_id"]] if role == "merchant" else SUPPORT[i % len(SUPPORT)])
        detail = f"order #{o['order_id']} ({o['product']}, {o['store']})"
    else:
        uid = (ORDERS[oi+i]["shopper"] if role == "shopper"
               else MERCH[sorted(MERCH)[i % len(MERCH)]] if role == "merchant"
               else SUPPORT[i % len(SUPPORT)])
        detail = "no particular order"
    rows.append({
      "id": f"hw5-{i+1:03d}", "scenario_group": "challenge", "data_quality_case_id": None,
      "tuple": {"role": role, "user_id": uid, "intent": f"capability_probe_{probe}",
                "record_state": "capability_probe", "applicable_policy": "none",
                "tools_needed": "one_lookup", "difficulty": "well_specified",
                "user_style": STYLES[i % len(STYLES)], "turn_count": 1 if i % 3 else 2, **rec},
      "user_visible_facts": f"{facts}; {detail}",
      "expected": {"evaluation": "human_judgment", "criterion": CRITERION,
                   "source": {"type": "specification", "reference": "RESP-6, SCOPE-2"}},
    })

out = REPO/"scenarios"/"hw5_plan.json"
out.write_text(json.dumps(rows, indent=2) + "\n")
import collections
print("scenarios planned:", len(rows))
print("probes:", dict(collections.Counter(r["tuple"]["intent"].replace("capability_probe_","") for r in rows)))
print("roles:", dict(collections.Counter(r["tuple"]["role"] for r in rows)))
print("with an order:", sum(1 for r in rows if "order_id" in r["tuple"]))
print("distinct orders:", len({r["tuple"]["order_id"] for r in rows if "order_id" in r["tuple"]}))
print("wrote", out)
