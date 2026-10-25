"""SQLite store database: schema and seed data.

    python -m ecommerce_agent.store_db --reset      # (re)create store/store.db with demo data
"""

import os
import sqlite3
import sys
from contextlib import closing

STORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "store"))
DB_PATH = os.path.join(STORE_DIR, "store.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    brand       TEXT NOT NULL,
    category    TEXT NOT NULL,
    description TEXT NOT NULL,
    price       REAL NOT NULL CHECK (price > 0),
    stock       INTEGER NOT NULL CHECK (stock >= 0)
);
CREATE TABLE IF NOT EXISTS customers (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    status      TEXT NOT NULL DEFAULT 'placed' CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled')),
    subtotal    REAL NOT NULL,
    shipping    REAL NOT NULL,
    total       REAL NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL
);
"""

# (id, name, brand, category, description, price, stock)
PRODUCTS = [
    (1, "Trailblazer 50L Backpack", "Osprey", "Backpacks", "Waterproof 50L hiking backpack with rain cover and ventilated back panel, ideal for weekend treks.", 139.99, 12),
    (2, "DayTripper 22L Pack", "Deuter", "Backpacks", "Lightweight 22L daypack with hydration sleeve and water-resistant fabric.", 64.50, 30),
    (3, "Summit 70L Expedition Pack", "Gregory", "Backpacks", "Heavy-duty 70L pack with adjustable suspension for multi-day backpacking.", 249.00, 5),
    (4, "Glycerin Run 20", "Brooks", "Running Shoes", "Plush cushioned road running shoe with soft landings for long distances.", 159.95, 18),
    (5, "Pegasus Trail 5", "Nike", "Running Shoes", "Rugged trail running shoe with grippy outsole and rock plate, water-resistant upper.", 139.00, 9),
    (6, "Speedster Racer", "Adidas", "Running Shoes", "Lightweight carbon-plated racing shoe for 5K to marathon.", 189.00, 4),
    (7, "Everyday Trainer 3", "ASICS", "Running Shoes", "Durable daily trainer with balanced cushioning, great value.", 89.99, 40),
    (8, "Alpine 3-Season Tent", "MSR", "Camping", "Two-person 3-season tent, waterproof rainfly, 2.1 kg, quick pitch.", 329.00, 6),
    (9, "Cloud Loft Sleeping Bag", "Marmot", "Camping", "Down sleeping bag rated to -5C, compressible, with waterproof shell.", 219.00, 10),
    (10, "Trek Stove Mini", "Jetboil", "Camping", "Compact camp stove that boils water in two minutes.", 109.95, 22),
    (11, "Headlamp 400", "Petzl", "Camping", "Rechargeable 400-lumen waterproof headlamp with red night mode.", 49.95, 50),
    (12, "Carbon Road Helmet", "Giro", "Cycling", "Aerodynamic road cycling helmet with MIPS protection and ventilation.", 129.00, 14),
    (13, "Commuter Lock Pro", "Kryptonite", "Cycling", "Hardened steel U-lock with 2 keys, theft-protection rated.", 79.00, 25),
    (14, "Trail Bike Gloves", "Fox", "Cycling", "Padded full-finger mountain bike gloves, touchscreen compatible.", 34.95, 35),
    (15, "Smart Bike Light Set", "Lezyne", "Cycling", "USB rechargeable front and rear light set, 800 lumens, waterproof.", 59.00, 28),
    (16, "Adjustable Dumbbell Set", "Bowflex", "Fitness", "Adjustable dumbbells from 2 to 24 kg, replaces 15 sets of weights.", 349.00, 7),
    (17, "Pro Yoga Mat 6mm", "Manduka", "Fitness", "Non-slip, eco-friendly 6mm yoga mat, lifetime guarantee.", 89.00, 33),
    (18, "Resistance Band Kit", "TheraBand", "Fitness", "Five-level resistance bands with door anchor and handles.", 29.99, 60),
    (19, "Foam Roller Deep", "TriggerPoint", "Fitness", "High-density foam roller for muscle recovery.", 39.95, 45),
    (20, "GPS Running Watch 5", "Garmin", "Wearables", "GPS watch with heart-rate, training load, and 14-day battery, water-resistant to 50m.", 299.99, 11),
    (21, "Fitness Tracker Band", "Fitbit", "Wearables", "Slim tracker with sleep tracking, 7-day battery, swim-proof.", 99.95, 38),
    (22, "Insulated Bottle 1L", "Hydro Flask", "Accessories", "Vacuum-insulated stainless steel bottle keeps drinks cold 24 hours.", 44.95, 70),
    (23, "Merino Running Socks 3-Pack", "Smartwool", "Accessories", "Moisture-wicking merino socks, blister-resistant seams.", 36.00, 80),
    (24, "Rain Shell Jacket", "Patagonia", "Apparel", "Waterproof breathable shell jacket, packs into its own pocket.", 179.00, 15),
]

CUSTOMERS = [
    (1, "Alex Rivera", "alex@example.com"),
    (2, "Sam Chen", "sam@example.com"),
]

# (customer_id, status, [(product_id, qty, unit_price)])
ORDERS = [
    (1, "delivered", [(7, 1, 89.99), (23, 2, 36.00)]),
    (1, "shipped", [(1, 1, 139.99)]),
    (2, "placed", [(17, 1, 89.00)]),
]


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def shipping_for(subtotal: float) -> float:
    """Shipping policy: free over $75, otherwise a flat $6.99."""
    return 0.0 if subtotal >= 75 else 6.99


def init_db(path: str = DB_PATH, reset: bool = False) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with closing(connect(path)) as conn:
        if reset:  # drop tables instead of deleting the file, which fails on Windows while Toolbox has it open
            conn.executescript("DROP TABLE IF EXISTS order_items; DROP TABLE IF EXISTS orders; "
                               "DROP TABLE IF EXISTS customers; DROP TABLE IF EXISTS products;")
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", PRODUCTS)
            conn.executemany("INSERT INTO customers VALUES (?, ?, ?)", CUSTOMERS)
            for customer_id, status, items in ORDERS:
                subtotal = round(sum(q * p for _, q, p in items), 2)
                ship = shipping_for(subtotal)
                cur = conn.execute(
                    "INSERT INTO orders (customer_id, status, subtotal, shipping, total) VALUES (?, ?, ?, ?, ?)",
                    (customer_id, status, subtotal, ship, round(subtotal + ship, 2)),
                )
                conn.executemany(
                    "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    [(cur.lastrowid, pid, q, p) for pid, q, p in items],
                )
        conn.commit()


if __name__ == "__main__":
    init_db(reset="--reset" in sys.argv)
    print(f"Database ready at {DB_PATH}")
