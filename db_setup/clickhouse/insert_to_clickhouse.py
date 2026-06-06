"""
ClickHouse Data Migration Script
Transfers BIRD SQLite databases into ClickHouse (one database per BIRD db).

Usage:
    python insert_to_clickhouse.py --bird-root /path/to/bird/dev_databases

Environment variables (override defaults):
    BIRD_ROOT  - Path to BIRD dev_databases directory
    CH_HOST    - ClickHouse host (default: localhost)
    CH_PORT    - ClickHouse HTTP port (default: 8123)
    CH_USER    - ClickHouse user (default: default)
    CH_PASS    - ClickHouse password (default: empty)

Prerequisites:
    - Docker: docker compose up -d (in this directory)
    - pip install clickhouse-connect pandas sqlalchemy
"""

import os
import sqlite3
import argparse
import pandas as pd
import clickhouse_connect
from sqlalchemy import create_engine, MetaData, types

# ================= Configuration =================
CH_HOST = os.environ.get("CH_HOST", "localhost")
CH_PORT = int(os.environ.get("CH_PORT", "8123"))
CH_USER = os.environ.get("CH_USER", "default")
CH_PASS = os.environ.get("CH_PASS", "")

DATABASES = [
    'california_schools', 'card_games', 'european_football_2',
    'formula_1', 'student_club', 'thrombosis_prediction', 'toxicology',
    'superhero', 'codebase_community', 'debit_card_specializing', 'financial'
]
# =================================================


def get_clickhouse_client():
    return clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASS
    )


def map_sqlalchemy_type_to_ch(sqla_column):
    """
    Type mapping:
    - Integer/Float types keep numeric types
    - Everything else (Date, DateTime, Boolean, String, Text) -> String for safety
    """
    t = sqla_column.type

    if isinstance(t, types.BigInteger):
        return "Int64"
    if isinstance(t, types.Integer):
        return "Int32"
    if isinstance(t, types.SmallInteger):
        return "Int16"
    if isinstance(t, (types.Float, types.Numeric, types.REAL)):
        return "Float64"

    return "String"


def transfer_database(folder_name, sqlite_path):
    print(f"========== Migrating: {folder_name} ==========")

    ch_client = get_clickhouse_client()

    ch_client.command(f"DROP DATABASE IF EXISTS `{folder_name}`")
    ch_client.command(f"CREATE DATABASE `{folder_name}`")

    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}")
    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)

    for table in metadata.sorted_tables:
        table_name = table.name
        print(f"  -> Table: {table_name}")

        columns_gen = []
        pks = []
        for col in table.columns:
            # Special case: european_football_2.Player.height should be Float64
            if folder_name == "european_football_2" and table_name == "Player" and col.name.lower() == "height":
                base_type = "Float64"
            else:
                base_type = map_sqlalchemy_type_to_ch(col)
            ch_type = f"Nullable({base_type})" if not col.primary_key else base_type
            columns_gen.append(f"`{col.name}` {ch_type}")
            if col.primary_key:
                pks.append(f"`{col.name}`")

        order_by = f"({', '.join(pks)})" if pks else "tuple()"
        create_sql = (
            f"CREATE TABLE `{folder_name}`.`{table_name}` "
            f"({', '.join(columns_gen)}) "
            f"ENGINE = MergeTree() ORDER BY {order_by}"
        )
        ch_client.command(create_sql)

        try:
            with sqlite3.connect(sqlite_path) as conn:
                df = pd.read_sql_query(f"SELECT * FROM `{table_name}`", conn)

                if folder_name == "european_football_2" and table_name == "Player" and "height" in df.columns:
                    df["height"] = pd.to_numeric(df["height"], errors="coerce")

                for col_name in df.columns:
                    if df[col_name].dtype == 'object' or 'datetime' in str(df[col_name].dtype):
                        df[col_name] = df[col_name].apply(lambda x: str(x) if pd.notnull(x) else None)

                if not df.empty:
                    ch_client.insert_df(database=folder_name, table=table_name, df=df)
                    print(f"     [OK] {len(df)} rows inserted")
                else:
                    print(f"     [Note] Empty table, schema only")

        except Exception as e:
            print(f"     [ERROR] {e}")


def main():
    parser = argparse.ArgumentParser(description="Migrate BIRD SQLite databases to ClickHouse")
    parser.add_argument("--bird-root", type=str,
                        default=os.environ.get("BIRD_ROOT", "./bird/dev_databases"),
                        help="Path to BIRD dev_databases directory")
    args = parser.parse_args()
    bird_root = args.bird_root

    if not os.path.exists(bird_root):
        print(f"Error: Directory {bird_root} does not exist")
        return

    for db_folder in DATABASES:
        sqlite_file = os.path.join(bird_root, db_folder, f"{db_folder}.sqlite")
        if os.path.exists(sqlite_file):
            transfer_database(db_folder, sqlite_file)
        else:
            print(f"Skip: {sqlite_file} not found")


if __name__ == "__main__":
    main()
