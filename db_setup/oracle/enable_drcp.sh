#!/bin/bash
# ============================================================
# enable_drcp.sh - Enable DRCP connection pooling in Oracle Free container
# ============================================================
# Usage:
#   bash enable_drcp.sh
#
# This script:
#   1. Increases processes/sessions parameters
#   2. Enables DRCP (Database Resident Connection Pooling)
#   3. Configures pool parameters (MIN_SIZE=10, MAX_SIZE=60)
#   4. Restarts the database to apply changes
# ============================================================

set -e

CONTAINER_NAME="sql-iq-oracle"

echo "=========================================="
echo "Oracle DRCP Connection Pool Setup"
echo "=========================================="

# Check container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "ERROR: Container ${CONTAINER_NAME} is not running. Start it first."
    exit 1
fi

echo ""
echo "Step 1: Increase processes and sessions parameters..."
docker exec -i ${CONTAINER_NAME} bash -c '
sqlplus -s / as sysdba <<EOF
ALTER SYSTEM SET processes=200 SCOPE=SPFILE;
ALTER SYSTEM SET sessions=220 SCOPE=SPFILE;
ALTER SYSTEM SET open_cursors=500 SCOPE=SPFILE;
SELECT '"'"'[OK] Parameters set (restart required)'"'"' AS status FROM dual;
EOF
'

echo ""
echo "Step 2: Start DRCP connection pool..."
docker exec -i ${CONTAINER_NAME} bash -c '
sqlplus -s / as sysdba <<EOF
BEGIN
    DBMS_CONNECTION_POOL.START_POOL();
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -56521 THEN
            NULL;
        ELSE
            RAISE;
        END IF;
END;
/
SELECT '"'"'[OK] DRCP pool started'"'"' AS status FROM dual;
EOF
'

echo ""
echo "Step 3: Configure DRCP pool parameters..."
docker exec -i ${CONTAINER_NAME} bash -c '
sqlplus -s / as sysdba <<EOF
BEGIN
    DBMS_CONNECTION_POOL.ALTER_PARAM('"'"'SYS_DEFAULT_CONNECTION_POOL'"'"', '"'"'MAX_SIZE'"'"', '"'"'60'"'"');
    DBMS_CONNECTION_POOL.ALTER_PARAM('"'"'SYS_DEFAULT_CONNECTION_POOL'"'"', '"'"'MIN_SIZE'"'"', '"'"'10'"'"');
    DBMS_CONNECTION_POOL.ALTER_PARAM('"'"'SYS_DEFAULT_CONNECTION_POOL'"'"', '"'"'INACTIVITY_TIMEOUT'"'"', '"'"'300'"'"');
    DBMS_CONNECTION_POOL.ALTER_PARAM('"'"'SYS_DEFAULT_CONNECTION_POOL'"'"', '"'"'MAX_THINK_TIME'"'"', '"'"'120'"'"');
END;
/
SELECT '"'"'[OK] DRCP configured'"'"' AS status FROM dual;
EOF
'

echo ""
echo "Step 4: Restart database to apply parameter changes..."
docker exec -i ${CONTAINER_NAME} bash -c '
sqlplus -s / as sysdba <<EOF
SHUTDOWN IMMEDIATE;
STARTUP;
BEGIN
    DBMS_CONNECTION_POOL.START_POOL();
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -56521 THEN NULL; ELSE RAISE; END IF;
END;
/
SELECT '"'"'[OK] Oracle restarted, DRCP ready'"'"' AS status FROM dual;
EOF
'

echo ""
echo "=========================================="
echo "DRCP Setup Complete!"
echo "=========================================="
echo "  Pool: MIN=10, MAX=60, TIMEOUT=300s"
echo "  Oracle: processes=200, sessions=220"
echo ""
