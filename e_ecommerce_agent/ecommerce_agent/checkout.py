"""Write-side tools (checkout, cancellation) and guardrail callbacks.

Reads go through MCP Toolbox (see store/tools.yaml). Anything that changes data lives here because it needs
real transactions and business rules enforced in code, not in a prompt.

Checkout is a two-step flow:
  prepare_order  validates everything, shows the exact charge and stores a pending order in session state
  confirm_order  places it, but ONLY if the pending order was prepared in an EARLIER user turn,
                 so the model can never prepare and place an order in the same turn.
"""

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from google.adk.tools.tool_context import ToolContext

from .store_db import DB_PATH, connect, shipping_for

MAX_QTY_PER_ORDER = 10
AUDIT_LOG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "outputs", "audit.log"))
WRITE_TOOLS = {"prepare_order", "confirm_order", "cancel_order"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _customer(conn: sqlite3.Connection, email: str):
    return conn.execute("SELECT id, name, email FROM customers WHERE lower(email) = lower(?)", (email.strip(),)).fetchone()


def prepare_order(email: str, product_id: int, quantity: int, tool_context: ToolContext) -> dict:
    """Validate an order and show the customer exactly what they would be charged. Does NOT place it.

    After this, present the summary to the customer and wait for them to explicitly confirm in their next
    message. Only then call confirm_order.

    Args:
        email: The customer's email address (must belong to an existing customer).
        product_id: Product id from search results.
        quantity: Number of units (1 to 10).
    """
    if not _EMAIL.match(email or ""):
        return {"error": "Please provide a valid email address."}
    if not isinstance(quantity, int) or not 1 <= quantity <= MAX_QTY_PER_ORDER:
        return {"error": f"Quantity must be a whole number from 1 to {MAX_QTY_PER_ORDER}."}
    with closing(connect()) as conn:
        customer = _customer(conn, email)
        if customer is None:
            return {"error": "No customer account found for that email."}
        product = conn.execute("SELECT id, name, price, stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        return {"error": f"Product {product_id} does not exist."}
    if product["stock"] < quantity:
        return {"error": f"Only {product['stock']} of '{product['name']}' in stock."}

    subtotal = round(product["price"] * quantity, 2)
    shipping = shipping_for(subtotal)
    pending = {
        "customer_id": customer["id"], "email": customer["email"], "product_id": product["id"],
        "product_name": product["name"], "quantity": quantity, "unit_price": product["price"],
        "subtotal": subtotal, "shipping": shipping, "total": round(subtotal + shipping, 2),
        "prepared_in_invocation": tool_context.invocation_id,
    }
    tool_context.state["pending_order"] = pending
    return {
        "status": "awaiting_customer_confirmation",
        "summary": f"{quantity} x {product['name']} @ ${product['price']:.2f} = ${subtotal:.2f}; "
                   f"shipping ${shipping:.2f}; TOTAL ${pending['total']:.2f}; for {customer['name']}.",
        "instruction": "Show this to the customer and ask them to confirm. Do not call confirm_order until they reply.",
    }


def confirm_order(tool_context: ToolContext) -> dict:
    """Place the order that prepare_order set up, after the customer has confirmed it in a later message."""
    pending = tool_context.state.get("pending_order")
    if not pending:
        return {"error": "There is no pending order. Call prepare_order first."}
    if pending["prepared_in_invocation"] == tool_context.invocation_id:
        return {"error": "The customer has not confirmed yet. Present the summary and wait for their reply."}

    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")  # take the write lock so the stock check and update are atomic
        row = conn.execute("SELECT stock, price FROM products WHERE id = ?", (pending["product_id"],)).fetchone()
        if row is None or row["stock"] < pending["quantity"]:
            conn.rollback()
            tool_context.state["pending_order"] = None
            return {"error": "Sorry, the item sold out while you were deciding. Nothing was charged."}
        if abs(row["price"] - pending["unit_price"]) > 1e-9:
            conn.rollback()
            tool_context.state["pending_order"] = None
            return {"error": "The price changed since the summary. Please start the order again."}
        cur = conn.execute(
            "INSERT INTO orders (customer_id, status, subtotal, shipping, total) VALUES (?, 'placed', ?, ?, ?)",
            (pending["customer_id"], pending["subtotal"], pending["shipping"], pending["total"]),
        )
        conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (cur.lastrowid, pending["product_id"], pending["quantity"], pending["unit_price"]),
        )
        conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (pending["quantity"], pending["product_id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    tool_context.state["pending_order"] = None
    return {"status": "placed", "order_id": cur.lastrowid, "total": pending["total"], "item": pending["product_name"]}


def cancel_order(order_id: int, email: str) -> dict:
    """Cancel an order that has not shipped yet and return its items to stock.

    Args:
        order_id: Order number.
        email: The email on the order (must match).
    """
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        order = conn.execute(
            "SELECT o.id, o.status FROM orders o JOIN customers c ON c.id = o.customer_id "
            "WHERE o.id = ? AND lower(c.email) = lower(?)", (order_id, email.strip()),
        ).fetchone()
        if order is None:
            conn.rollback()
            return {"error": "No order with that number exists for that email."}
        if order["status"] != "placed":
            conn.rollback()
            return {"error": f"Only orders in 'placed' status can be cancelled; this one is '{order['status']}'."}
        for item in conn.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall():
            conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item["quantity"], item["product_id"]))
        conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"status": "cancelled", "order_id": order_id}


# ---------------------------------------------------------------- callbacks

def _mask_email(value):
    if isinstance(value, str) and _EMAIL.match(value):  # only real addresses, not text that happens to contain "@"
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain}"
    return value


def _audit(event: str, tool_name: str, payload: dict) -> None:
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, "tool": tool_name,
                  "data": {k: _mask_email(v) for k, v in payload.items()}}
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass  # auditing must never break a customer's request


def before_tool(tool, args, tool_context):
    """Guardrail + audit trail. Returning a dict skips the tool and uses that dict as its result."""
    if tool.name in WRITE_TOOLS:
        _audit("call", tool.name, dict(args))
        qty = args.get("quantity")
        if isinstance(qty, (int, float)) and qty > MAX_QTY_PER_ORDER:
            return {"error": f"Orders are limited to {MAX_QTY_PER_ORDER} units. For bulk orders please contact sales."}
    return None


def after_tool(tool, args, tool_context, tool_response):
    if tool.name in WRITE_TOOLS and isinstance(tool_response, dict):
        _audit("result", tool.name, {k: v for k, v in tool_response.items() if k != "instruction"})
    return None
