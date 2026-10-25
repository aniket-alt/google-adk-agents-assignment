# (e) E-Commerce Shopping Agent: ADK + MCP Toolbox for Databases

"Trail", the assistant for a fictional outdoor store (TrailMart). It finds products, answers order questions
and places or cancels orders, with guardrails so it cannot buy anything the customer did not explicitly confirm.

Based on the Google codelab and [`sports-agent-adk-mcp-alloydb`](https://github.com/mtoscano84/sports-agent-adk-mcp-alloydb),
which pairs an ADK agent with **MCP Toolbox for Databases** over AlloyDB. This version keeps that architecture
(declarative SQL tools served over MCP) but runs on **SQLite**, because the build environment had no Google Cloud
project, and adds a transactional, guarded checkout.

## Architecture

```
customer ──► ADK Agent "trailmart_assistant"
                │
                ├── ToolboxToolset("storefront") ──MCP──► MCP Toolbox server ──► store.db (SQLite)
                │     READ-ONLY tools declared in store/tools.yaml:
                │     search-products · get-product-details · list-categories
                │     get-order-status · list-my-orders
                │
                ├── prepare_order / confirm_order / cancel_order    (ecommerce_agent/checkout.py)
                │     WRITE tools: Python + SQLite transactions + business rules
                │
                └── callbacks: before_tool (quantity guardrail + audit) · after_tool (audit)
```

### Why reads and writes are split
- **Reads are declarative and least-privilege.** `tools.yaml` holds parameterized SQL only (no string building), and
  the agent receives just the `storefront` toolset. Changing a query needs no Python.
- **Writes need real transactions and rules**, so they are plain Python functions with validation.

### Safety and production concerns
| Concern | How it is handled |
|---|---|
| Accidental purchase | Two-step checkout: `prepare_order` shows the exact total; `confirm_order` only works if the order was prepared in an **earlier turn** (compared by ADK `invocation_id`), so the model cannot prepare and place in one go |
| Overselling | `confirm_order` runs `BEGIN IMMEDIATE`, re-checks stock and price, then inserts the order and decrements stock atomically; a lost race returns "sold out" and changes nothing |
| Data leakage | Order tools match **both** order id and email; wrong email returns nothing |
| SQL injection | Every query is parameterized |
| Abuse | Quantity capped at 10 in code (guardrail callback and function) |
| Prompt injection | Prompt tells the model tool output and product text is data, not instructions |
| Auditability | `outputs/audit.log` (JSON lines) records every write attempt and result, **emails masked** |
| Policies in code | Free shipping at $75+, otherwise $6.99; cancel only while status is `placed` |

Limitation: identity is just an email on file, which is fine for a demo. A real store would use sign-in (the
reference uses Google Sign-In) and pass the verified identity to the tools.

## Files

| Path | Purpose |
|---|---|
| `store/tools.yaml` | Toolbox source, 5 read-only SQL tools and the `storefront` toolset |
| `ecommerce_agent/agent.py` | Prompt, agent wiring (starts Toolbox automatically) |
| `ecommerce_agent/checkout.py` | Transactional write tools and guardrail/audit callbacks |
| `ecommerce_agent/store_db.py` | Schema, 24 products, 2 customers, 3 orders |
| `ecommerce_agent/toolbox_server.py` | Starts/stops the Toolbox process |
| `tests/test_offline.py` | Business rules, race condition, guardrails, live Toolbox through ADK (no API key) |
| `run_demo.py` | Scripted 4-turn conversation |

## Run it

1. Download the Toolbox binary (v1.15.0, Windows shown; ~290 MB, not committed to git):
   ```powershell
   mkdir bin
   curl.exe -L -o bin\toolbox.exe https://storage.googleapis.com/mcp-toolbox-for-databases/v1.15.0/windows/amd64/toolbox.exe
   ```
   (Other platforms: replace `windows/amd64/toolbox.exe` with e.g. `linux/amd64/toolbox`, and set `TOOLBOX_BIN`.)
2. ```powershell
   pip install -r requirements.txt
   cd e_ecommerce_agent
   python tests/test_offline.py     # no API key needed
   python run_demo.py               # scripted conversation with Gemini
   adk web                          # chat UI; pick "ecommerce_agent"
   ```
   Demo customers: `alex@example.com` (orders 1 and 2) and `sam@example.com` (order 3).
   Reset the data any time with `python -m ecommerce_agent.store_db --reset`.

## Example conversation

See the run captured in `outputs/sample_conversation.txt`.
