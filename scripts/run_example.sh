#!/bin/bash
# =============================================================================
# SQL-IQ Example Run Script
# =============================================================================
# This script demonstrates how to run SQL-IQ evaluation tasks.
# Before running, make sure you have:
#   1. Installed dependencies: pip install -r requirements.txt
#   2. Updated configs/tasks_config.yaml with your actual data paths
#   3. Set your LLM API credentials via environment variables
# =============================================================================

# --- Configuration ---
export OPENAI_API_KEY="<YOUR_API_KEY>"
export OPENAI_BASE_URL="<YOUR_API_BASE_URL>"  # e.g., https://api.openai.com/v1

MODEL_NAME="gpt-4o"
CONFIG_FILE="configs/tasks_config.yaml"
OUTPUT_DIR="outputs"

# --- Run single task ---
echo "[INFO] Running Text2SQL evaluation..."
python -m sql_iq \
    --tasks_config "$CONFIG_FILE" \
    --tasks text2sql \
    --model "$MODEL_NAME" \
    --output_dir "$OUTPUT_DIR" \
    --num_workers 4 \
    --timeout 30

# --- Run multiple tasks ---
# echo "[INFO] Running multiple tasks..."
# python -m sql_iq \
#     --tasks_config "$CONFIG_FILE" \
#     --tasks text2sql,sql_judge,sql_equ_judge \
#     --model "$MODEL_NAME" \
#     --output_dir "$OUTPUT_DIR" \
#     --num_workers 4

# --- Run SQL Translation (specific dialect) ---
# echo "[INFO] Running SQL Translation (oracle)..."
# python -m sql_iq \
#     --tasks_config "$CONFIG_FILE" \
#     --tasks sql_trans \
#     --model "$MODEL_NAME" \
#     --output_dir "$OUTPUT_DIR" \
#     --num_workers 2 \
#     --timeout 60

# --- Run all tasks ---
# echo "[INFO] Running all tasks..."
# python -m sql_iq \
#     --tasks_config "$CONFIG_FILE" \
#     --tasks text2sql,conversational_sql,sql_judge,sql_equ_judge,sql_err_class,sql_trans \
#     --model "$MODEL_NAME" \
#     --output_dir "$OUTPUT_DIR"

echo "[INFO] Done. Results saved to $OUTPUT_DIR/"
