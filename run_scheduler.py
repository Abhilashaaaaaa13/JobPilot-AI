# run_scheduler.py
# ─────────────────────────────────────────────
# Local development ke liye alag terminal mein chalao:
#   python run_scheduler.py
#
# Yeh tab tak chalta rahega jab tak terminal band na karo.
# Streamlit se bilkul alag hai — tab band karne se affect nahi hota.
# ─────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import time
import signal
from loguru import logger
from backend.database import init_db

# DB initialize karo pehle
init_db()

from backend.pipeline.scheduler import create_scheduler

scheduler = create_scheduler()
scheduler.start()

logger.info("=" * 50)
logger.info("🚀 Scheduler started — local development mode")
logger.info("=" * 50)

for job in scheduler.get_jobs():
    logger.info(f"  ⏰ {job.id}: next run at {job.next_run_time}")

logger.info("Ctrl+C se band karo")
logger.info("=" * 50)

# Graceful shutdown on Ctrl+C
def _shutdown(sig, frame):
    logger.info("Shutting down scheduler...")
    scheduler.shutdown(wait=False)
    sys.exit(0)

signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# Alive rakho
while True:
    time.sleep(60)