# run_scheduler.py
# ─────────────────────────────────────────────
# For local development, run this in a separate terminal:
#   python run_scheduler.py
#
# This keeps running until you close the terminal.
# It's completely separate from Streamlit — closing that tab doesn't affect it.
# ─────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
import signal
from loguru import logger
from backend.database import init_db

# Initialize the DB first
init_db()

from backend.pipeline.scheduler import create_scheduler

scheduler = create_scheduler()
scheduler.start()

logger.info("=" * 50)
logger.info("🚀 Scheduler started — local development mode")
logger.info("=" * 50)

for job in scheduler.get_jobs():
    logger.info(f"  ⏰ {job.id}: next run at {job.next_run_time}")

logger.info("Press Ctrl+C to stop")
logger.info("=" * 50)

# Graceful shutdown on Ctrl+C
def _shutdown(sig, frame):
    logger.info("Shutting down scheduler...")
    scheduler.shutdown(wait=False)
    sys.exit(0)

signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# Keep it alive
while True:
    time.sleep(60)