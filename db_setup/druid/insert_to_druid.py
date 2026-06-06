"""
Druid Data Migration Script
Transfers BIRD SQLite databases into Apache Druid (one datasource per table).

Usage:
    python insert_to_druid.py --bird-root /path/to/bird/dev_databases

Environment variables (override defaults):
    BIRD_ROOT              - Path to BIRD dev_databases directory
    DRUID_OVERLORD_URL     - Druid Overlord URL (default: http://localhost:8181/druid/indexer/v1/task)
    HOST_TEMP_DIR          - Host temp dir for data files (default: ./temp_data)
    CONTAINER_TEMP_DIR     - Container mount path (default: /opt/data/temp_data)

Prerequisites:
    - Docker: docker compose up -d (in this directory)
    - pip install requests
    - Wait for Druid to be fully started (~1-2 minutes)
"""

import sqlite3
import requests
import json
import os
import time
import argparse

# ================= Configuration =================
DRUID_OVERLORD_URL = os.environ.get(
    "DRUID_OVERLORD_URL",
    "http://localhost:8181/druid/indexer/v1/task"
)
DRUID_COORDINATOR_URL = os.environ.get(
    "DRUID_COORDINATOR_URL",
    "http://localhost:8181/druid/indexer/v1/task/{task_id}/status"
)

HOST_TEMP_DIR = os.environ.get("HOST_TEMP_DIR", "./temp_data")
CONTAINER_TEMP_DIR = os.environ.get("CONTAINER_TEMP_DIR", "/opt/data/temp_data")

DATABASES = [
    'california_schools', 'card_games', 'european_football_2',
    'formula_1', 'student_club', 'thrombosis_prediction', 'toxicology',
    'superhero', 'codebase_community', 'debit_card_specializing', 'financial'
]
# =================================================

os.makedirs(HOST_TEMP_DIR, exist_ok=True)


def map_sqlite_type_to_druid(sqlite_type):
    """Type mapping: SQLite -> Druid"""
    st = sqlite_type.upper()
    if 'INT' in st:
        return 'long'
    if 'REAL' in st or 'FLOA' in st or 'DOUB' in st:
        return 'double'
    return 'string'


def wait_for_task(task_id):
    """Wait for a Druid ingestion task to complete."""
    print(f"    Waiting for task: {task_id}...", end="", flush=True)
    while True:
        try:
            url = DRUID_COORDINATOR_URL.format(task_id=task_id)
            resp = requests.get(url)
            status_info = resp.json().get('status', {})
            status = status_info.get('status')
            if status == 'SUCCESS':
                print(" [OK]")
                return True
            elif status == 'FAILED':
                print(f" [FAILED] {status_info.get('errorMsg', 'unknown')}")
                return False
            time.sleep(2)
        except Exception as e:
            print(f" [Error: {e}]")
            return False


def ingest_to_druid(datasource, columns_info, rows):
    """Submit data to Druid via LocalInputSource."""

    dimensions = []
    col_names = [col[1].lower() for col in columns_info]
    for col in columns_info:
        col_name = col[1].lower()
        col_type = map_sqlite_type_to_druid(col[2])
        dimensions.append({"name": col_name, "type": col_type})

    temp_filename = f"{datasource}.json"
    host_file_path = os.path.join(HOST_TEMP_DIR, temp_filename)

    default_timestamp = "2024-01-01T00:00:00Z"
    with open(host_file_path, 'w') as f:
        for row in rows:
            record = {"__time": default_timestamp}
            for i, val in enumerate(row):
                record[col_names[i]] = val
            f.write(json.dumps(record) + '\n')

    spec = {
        "type": "index_parallel",
        "spec": {
            "dataSchema": {
                "dataSource": datasource,
                "dimensionsSpec": {"dimensions": dimensions},
                "timestampSpec": {"column": "__time", "format": "iso"},
                "granularitySpec": {
                    "type": "uniform",
                    "segmentGranularity": "ALL",
                    "queryGranularity": "NONE",
                    "rollup": False
                }
            },
            "ioConfig": {
                "type": "index_parallel",
                "inputSource": {
                    "type": "local",
                    "baseDir": CONTAINER_TEMP_DIR,
                    "filter": temp_filename
                },
                "inputFormat": {"type": "json"},
                "appendToExisting": False
            },
            "tuningConfig": {
                "type": "index_parallel",
                "maxRowsInMemory": 100000,
                "forceGuaranteedRollup": True
            }
        }
    }

    try:
        response = requests.post(DRUID_OVERLORD_URL, json=spec)
        if response.status_code == 200:
            task_id = response.json().get('task')
            success = wait_for_task(task_id)
            if os.path.exists(host_file_path):
                os.remove(host_file_path)
            return success
        else:
            print(f"    [Submit Failed] HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"    [Submit Error] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate BIRD SQLite databases to Druid")
    parser.add_argument("--bird-root", type=str,
                        default=os.environ.get("BIRD_ROOT", "./bird/dev_databases"),
                        help="Path to BIRD dev_databases directory")
    args = parser.parse_args()
    bird_root = args.bird_root

    for db_name in DATABASES:
        sqlite_file = os.path.join(bird_root, db_name, f'{db_name}.sqlite')
        if not os.path.exists(sqlite_file):
            print(f"Skip: {sqlite_file} not found")
            continue

        print(f"\n========== Migrating to Druid: {db_name} ==========")

        sqlite_conn = sqlite3.connect(sqlite_file)
        sqlite_cursor = sqlite_conn.cursor()

        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in sqlite_cursor.fetchall()]

        for table_name in tables:
            if table_name.startswith('sqlite_'):
                continue

            datasource_name = f"bird_{db_name}_{table_name}".lower()
            print(f"  -> Table: {table_name} => DataSource: {datasource_name}")

            sqlite_cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns_info = sqlite_cursor.fetchall()

            sqlite_cursor.execute(f'SELECT * FROM "{table_name}"')
            rows = sqlite_cursor.fetchall()

            if not rows:
                print(f"    [Skip] Empty table")
                continue

            success = ingest_to_druid(datasource_name, columns_info, rows)
            if success:
                print(f"    [OK] {table_name} migrated")
            else:
                print(f"    [FAILED] {table_name}")

        sqlite_conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
