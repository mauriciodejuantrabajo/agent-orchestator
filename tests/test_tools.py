"""Tests de las herramientas: la calculadora segura y el SQL de solo lectura.

No hacen ninguna llamada de red (web_search/read_url se prueban en otros proyectos
y aquí no aportan; lo crítico de seguridad es calc y run_sql)."""

from __future__ import annotations

from src.tools import SQLTool, calc


# ---- calc: parser aritmético seguro ----
def test_calc_operaciones_basicas():
    assert calc("2 + 3 * 4") == "2 + 3 * 4 = 14"
    assert calc("(8.2 - 6.5) / 6.5 * 100").startswith("(8.2 - 6.5) / 6.5 * 100 = ")
    assert calc("2 ** 10") == "2 ** 10 = 1024"


def test_calc_entero_sin_decimal_sobrante():
    assert calc("10 / 2") == "10 / 2 = 5"  # 5.0 -> 5


def test_calc_division_por_cero():
    assert "división por cero" in calc("1 / 0")


def test_calc_rechaza_codigo_arbitrario():
    # Nada de nombres, llamadas ni imports: deben rechazarse, no ejecutarse.
    for malicioso in ["__import__('os')", "open('x')", "x + 1", "abs(-3)", "1; 2"]:
        assert calc(malicioso).startswith("Error")


def test_calc_vacio():
    assert "vacía" in calc("   ")


# ---- run_sql: solo lectura ----
def test_run_sql_select_funciona():
    sql = SQLTool()  # usa data/demo.db
    out = sql.run_sql("SELECT name FROM products ORDER BY name LIMIT 1")
    assert "Auriculares" in out


def test_run_sql_bloquea_escritura():
    sql = SQLTool()
    for peligroso in [
        "DELETE FROM products",
        "DROP TABLE products",
        "UPDATE products SET unit_price = 0",
        "INSERT INTO products VALUES (9,'x','y',1)",
    ]:
        assert sql.run_sql(peligroso).startswith("Error")


def test_run_sql_bloquea_multiples_sentencias():
    sql = SQLTool()
    out = sql.run_sql("SELECT 1; DROP TABLE products")
    assert out.startswith("Error")


def test_schema_lista_tablas():
    sql = SQLTool()
    schema = sql.schema()
    assert "products" in schema and "sales" in schema and "regions" in schema
