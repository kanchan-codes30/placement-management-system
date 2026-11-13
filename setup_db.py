"""Creates the database, tables, function, procedures, triggers and views.

Usage:  python setup_db.py          (asks before dropping an existing database)
        python setup_db.py --yes    (no question)
"""
import pathlib
import sys

import mysql.connector

from config import DB_CONFIG, DB_NAME

SQL_DIR = pathlib.Path(__file__).parent / "sql"
SQL_FILES = ["01_schema.sql", "02_procedures.sql", "03_triggers.sql", "04_views.sql"]


def split_statements(sql_text):
    """Splits a .sql file into statements, understanding the DELIMITER command."""
    delimiter, statements, buf = ";", [], []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(None, 1)[1].strip()
            continue
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        joined = "\n".join(buf).rstrip()
        if joined.endswith(delimiter):
            statements.append(joined[: -len(delimiter)].strip())
            buf = []
    if "".join(buf).strip():
        statements.append("\n".join(buf).strip())
    return statements


def main():
    if "--yes" not in sys.argv:
        answer = input(f"This will DROP and re-create database '{DB_NAME}'. Continue? (y/n): ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{DB_NAME}`")
    cur.execute(f"CREATE DATABASE `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE `{DB_NAME}`")

    for name in SQL_FILES:
        statements = split_statements((SQL_DIR / name).read_text(encoding="utf-8"))
        for stmt in statements:
            cur.execute(stmt)
        print(f"  ran {name}  ({len(statements)} statements)")

    conn.commit()
    cur.close()
    conn.close()
    print(f"Database '{DB_NAME}' is ready. Next: python seed_data.py")


if __name__ == "__main__":
    main()
