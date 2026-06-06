"""
PostgreSQL Data Migration Script
Transfers BIRD SQLite databases into PostgreSQL (one database per BIRD db).

Usage:
    python insert_to_postgres.py --bird-root /path/to/bird/dev_databases

Environment variables (override defaults):
    BIRD_ROOT  - Path to BIRD dev_databases directory
    PG_HOST    - PostgreSQL host (default: localhost)
    PG_PORT    - PostgreSQL port (default: 5433)
    PG_USER    - PostgreSQL user (default: postgres)
    PG_PASS    - PostgreSQL password (default: 123456)

Prerequisites:
    - Docker: docker compose up -d (in this directory)
    - pip install psycopg2-binary
"""

import sqlite3
import psycopg2
from psycopg2 import sql
import os
import argparse

# ================= Configuration =================
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5433")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASS", "123456")

DATABASES = [
    'california_schools', 'card_games', 'european_football_2',
    'formula_1', 'student_club', 'thrombosis_prediction', 'toxicology',
    'superhero', 'codebase_community', 'debit_card_specializing', 'financial'
]
# =================================================


def get_pg_connection(dbname=None, autocommit=False):
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASS,
        dbname=dbname if dbname else "postgres"
    )
    if autocommit:
        conn.autocommit = True
    return conn


def map_sqlite_type_to_pg(sqlite_type):
    """Type mapping: SQLite -> PostgreSQL"""
    st = sqlite_type.upper()
    if 'INT' in st:
        return 'BIGINT'
    if 'REAL' in st or 'FLOA' in st or 'DOUB' in st:
        return 'DOUBLE PRECISION'
    if 'BOOL' in st:
        return 'BOOLEAN'
    if 'BLOB' in st:
        return 'BYTEA'
    if 'DATE' in st or 'TIME' in st:
        return 'TIMESTAMP'
    return 'TEXT'


def clean_data_for_pg(val):
    """Clean data for PG's strict requirements."""
    if val is None:
        return None
    if isinstance(val, str):
        if '\x00' in val:
            val = val.replace('\x00', '')
        return val
    return val


def main():
    parser = argparse.ArgumentParser(description="Migrate BIRD SQLite databases to PostgreSQL")
    parser.add_argument("--bird-root", type=str,
                        default=os.environ.get("BIRD_ROOT", "./bird/dev_databases"),
                        help="Path to BIRD dev_databases directory")
    args = parser.parse_args()
    bird_root = args.bird_root

    try:
        admin_conn = get_pg_connection(autocommit=True)
        admin_cursor = admin_conn.cursor()
    except Exception as e:
        print(f"Cannot connect to PostgreSQL: {e}")
        return

    for db_name in DATABASES:
        sqlite_file = os.path.join(bird_root, db_name, f'{db_name}.sqlite')
        if not os.path.exists(sqlite_file):
            print(f"Skip: {sqlite_file} not found")
            continue

        print(f"\n========== Migrating: {db_name} ==========")

        try:
            admin_cursor.execute(
                sql.SQL("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s"),
                [db_name]
            )
            admin_cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))
            admin_cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"  -> Database {db_name} created")
        except Exception as e:
            print(f"  [Error] Create database failed: {e}")
            continue

        pg_conn = get_pg_connection(dbname=db_name)
        pg_cursor = pg_conn.cursor()

        sqlite_conn = sqlite3.connect(sqlite_file)
        sqlite_cursor = sqlite_conn.cursor()

        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in sqlite_cursor.fetchall()]

        for table_name in tables:
            if table_name.startswith('sqlite_'):
                continue

            print(f"  -> Table: {table_name}")

            sqlite_cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns_info = sqlite_cursor.fetchall()

            cols_def = []
            col_names = []
            for col in columns_info:
                raw_name = col[1]
                raw_type = col[2]
                pg_type = map_sqlite_type_to_pg(raw_type)
                safe_col_name = f'"{raw_name.lower()}"'
                cols_def.append(f'{safe_col_name} {pg_type}')
                col_names.append(safe_col_name)

            safe_table_name = f'"{table_name.lower()}"'
            create_sql = f'CREATE TABLE {safe_table_name} ({", ".join(cols_def)})'

            try:
                pg_cursor.execute(create_sql)
            except Exception as e:
                print(f"     [Create Failed] {e}")
                pg_conn.rollback()
                continue

            sqlite_cursor.execute(f'SELECT * FROM "{table_name}"')
            rows = sqlite_cursor.fetchall()

            if rows:
                placeholders = ["%s"] * len(col_names)
                insert_sql = f'INSERT INTO {safe_table_name} VALUES ({", ".join(placeholders)})'

                batch_data = []
                for row in rows:
                    batch_data.append(tuple(clean_data_for_pg(val) for val in row))

                try:
                    pg_cursor.executemany(insert_sql, batch_data)
                    pg_conn.commit()
                except Exception as e:
                    print(f"     [Insert Failed] {e}")
                    pg_conn.rollback()

        sqlite_conn.close()
        pg_conn.close()
        print(f"  [Success] {db_name}")

    admin_conn.close()


if __name__ == "__main__":
    main()
