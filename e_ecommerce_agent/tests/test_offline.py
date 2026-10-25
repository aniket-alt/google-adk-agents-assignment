"""Offline tests: business rules, guardrails, and the live MCP Toolbox server (no API key or model quota).

Run from e_ecommerce_agent/:   python tests/test_offline.py
Resets store/store.db first and again at the end.
"""

import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import ecommerce_agent.checkout as checkout
from ecommerce_agent.store_db import connect, init_db
from ecommerce_agent.toolbox_server import ensure_toolbox, stop_toolbox

checkout.AUDIT_LOG = os.path.join(tempfile.mkdtemp(prefix="ecom_test_"), "audit.log")


def ctx(invocation: str, state: dict | None = None):
    """Minimal stand-in for ADK's ToolContext."""
    return SimpleNamespace(state=state if state is not None else {}, invocation_id=invocation)


def stock(product_id: int) -> int:
    conn = connect()
    try:
        return conn.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()["stock"]
    finally:
        conn.close()


def check_business_rules() -> None:
    A = "alex@example.com"
    # --- validation
    assert "error" in checkout.prepare_order("not-an-email", 1, 1, ctx("t1"))
    assert "error" in checkout.prepare_order(A, 1, 0, ctx("t1"))
    assert "error" in checkout.prepare_order(A, 1, 11, ctx("t1"))
    assert "error" in checkout.prepare_order("ghost@example.com", 1, 1, ctx("t1"))
    assert "error" in checkout.prepare_order(A, 999, 1, ctx("t1"))
    assert "Only 4" in checkout.prepare_order(A, 6, 5, ctx("t1"))["error"], "cannot order more than stock"

    # --- confirmation guard
    assert "error" in checkout.confirm_order(ctx("t1")), "confirm without prepare must fail"
    state: dict = {}
    prep = checkout.prepare_order(A, 2, 1, ctx("turn-1", state))  # $64.50 -> shipping 6.99
    assert prep["status"] == "awaiting_customer_confirmation" and "71.49" in prep["summary"], prep
    assert "error" in checkout.confirm_order(ctx("turn-1", state)), "same-turn confirm must be refused"
    assert state["pending_order"] is not None and stock(2) == 30, "refused confirm must not change anything"
    done = checkout.confirm_order(ctx("turn-2", state))
    assert done["status"] == "placed" and done["total"] == 71.49, done
    assert stock(2) == 29 and state["pending_order"] is None
    assert "error" in checkout.confirm_order(ctx("turn-3", state)), "an order can only be confirmed once"

    # --- free shipping at $75+
    s2: dict = {}
    assert "$0.00" in checkout.prepare_order(A, 1, 1, ctx("a", s2))["summary"]  # $139.99

    # --- atomic stock: two customers race for the last units of product 6 (stock 4)
    s_a, s_b = {}, {}
    checkout.prepare_order(A, 6, 3, ctx("x1", s_a))
    checkout.prepare_order("sam@example.com", 6, 3, ctx("y1", s_b))
    assert checkout.confirm_order(ctx("x2", s_a))["status"] == "placed"
    lost = checkout.confirm_order(ctx("y2", s_b))
    assert "sold out" in lost["error"] and stock(6) == 1, (lost, stock(6))
    assert s_b["pending_order"] is None

    # --- cancellation restores stock and enforces ownership/status
    assert "error" in checkout.cancel_order(done["order_id"], "sam@example.com"), "wrong owner"
    assert "error" in checkout.cancel_order(2, A), "shipped orders cannot be cancelled"
    assert checkout.cancel_order(done["order_id"], A)["status"] == "cancelled" and stock(2) == 30
    assert "error" in checkout.cancel_order(done["order_id"], A), "cannot cancel twice"

    # --- guardrail callback
    tool = SimpleNamespace(name="prepare_order")
    assert "error" in checkout.before_tool(tool, {"quantity": 50, "email": A}, ctx("g"))
    assert checkout.before_tool(SimpleNamespace(name="search-products"), {"quantity": 50}, ctx("g")) is None
    prepared = checkout.prepare_order(A, 2, 1, ctx("audit-turn"))
    checkout.after_tool(SimpleNamespace(name="prepare_order"), {}, ctx("audit-turn"), prepared)
    log = open(checkout.AUDIT_LOG, encoding="utf-8").read()
    assert "a***@example.com" in log and A not in log, "emails must be masked in the audit log"
    assert "@ $64.50" in log, "free text containing '@' must not be mangled by the email masker"
    print("business rules + guardrails: OK")


async def check_toolbox() -> None:
    from google.adk.tools.toolbox_toolset import ToolboxToolset

    url = ensure_toolbox()
    toolset = ToolboxToolset(server_url=url, toolset_name="storefront")
    tools = await toolset.get_tools()
    names = sorted(t.name for t in tools)
    assert names == ["get-order-status", "get-product-details", "list-categories", "list-my-orders", "search-products"], names
    search = next(t for t in tools if t.name == "search-products")
    result = await search.run_async(args={"keyword": "waterproof", "category": "", "max_price": 150}, tool_context=None)
    text = json.dumps(result, default=str)
    assert "Trailblazer" in text and "Summit 70L" not in text, text[:300]
    print(f"MCP Toolbox via ADK: OK ({len(tools)} tools; search returned {text.count('Trailblazer')}+ match(es))")
    await toolset.close()


if __name__ == "__main__":
    init_db(reset=True)
    try:
        check_business_rules()
        asyncio.run(check_toolbox())
        print("\nOFFLINE TESTS PASSED")
    finally:
        stop_toolbox()
        init_db(reset=True)  # leave a clean demo database behind
