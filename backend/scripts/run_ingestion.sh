#!/bin/bash
#
# Cron entry point for the job-posting ingestion run.
#
# Invoked once a day at 09:00 America/Los_Angeles (Pacific -- PST/PDT,
# DST handled by the OS timezone) by the crontab line:
#
#   0 9 * * * /Users/nguyennguyen/Desktop/JobPrep/backend/scripts/run_ingestion.sh
#
# It runs `python -m app.ingestion.runner`, whose __main__ calls
# run_ingestion() -- discover every current SimplifyJobs README posting,
# upsert companies/job_postings, and mark unseen postings inactive.
#
# cron runs with a bare environment and `/` as cwd, so everything below
# is spelled out absolutely: the repo path, the venv interpreter, and an
# explicit TZ for the log timestamps.

set -euo pipefail

BACKEND_DIR="/Users/nguyennguyen/Desktop/JobPrep/backend"
PYTHON="${BACKEND_DIR}/.venv/bin/python"
LOG_DIR="${BACKEND_DIR}/logs"
LOG_FILE="${LOG_DIR}/ingestion.log"

export TZ="America/Los_Angeles"

mkdir -p "${LOG_DIR}"
cd "${BACKEND_DIR}"

echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') : starting run_ingestion ===" >> "${LOG_FILE}"
if "${PYTHON}" -m app.ingestion.runner >> "${LOG_FILE}" 2>&1; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') : run_ingestion OK ===" >> "${LOG_FILE}"
else
    status=$?
    echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') : run_ingestion FAILED (exit ${status}) ===" >> "${LOG_FILE}"
    exit "${status}"
fi
