"""
Genera la base de ejemplo `data/demo.db` para el DataAgent.

Una pequeña base de ventas (regiones, productos, ventas) con datos inventados pero
coherentes, suficiente para demostrar consultas SQL no triviales (JOINs, GROUP BY).

Uso:
    python -m scripts.seed_db
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "demo.db"

REGIONS = [
    (1, "Norte"),
    (2, "Centro"),
    (3, "Sur"),
]

PRODUCTS = [
    (1, "Teclado", "Periféricos", 25.0),
    (2, "Mouse", "Periféricos", 15.0),
    (3, "Monitor", "Pantallas", 180.0),
    (4, "Notebook", "Computadoras", 950.0),
    (5, "Auriculares", "Audio", 60.0),
]

# (id, product_id, region_id, units, month)
SALES = [
    (1, 4, 1, 12, "2026-01"),
    (2, 3, 1, 30, "2026-01"),
    (3, 1, 2, 80, "2026-01"),
    (4, 2, 2, 95, "2026-01"),
    (5, 5, 3, 40, "2026-01"),
    (6, 4, 2, 8, "2026-02"),
    (7, 3, 3, 22, "2026-02"),
    (8, 1, 1, 60, "2026-02"),
    (9, 5, 1, 18, "2026-02"),
    (10, 2, 3, 70, "2026-02"),
    (11, 4, 3, 15, "2026-03"),
    (12, 3, 2, 25, "2026-03"),
    (13, 5, 2, 33, "2026-03"),
    (14, 1, 3, 50, "2026-03"),
    (15, 2, 1, 88, "2026-03"),
]


def build() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE regions (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit_price REAL NOT NULL
        );
        CREATE TABLE sales (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            region_id INTEGER NOT NULL REFERENCES regions(id),
            units INTEGER NOT NULL,
            month TEXT NOT NULL
        );
        """
    )
    cur.executemany("INSERT INTO regions VALUES (?, ?)", REGIONS)
    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", PRODUCTS)
    cur.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?)", SALES)
    con.commit()
    con.close()
    return DB_PATH


if __name__ == "__main__":
    path = build()
    print(f"Base de ejemplo creada en: {path}")
