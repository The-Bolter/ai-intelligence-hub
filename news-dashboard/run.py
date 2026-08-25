import os, sys, logging

sys.path.insert(0, os.path.dirname(__file__))
import config
from app import app, start_auto_refresh
from fetcher import refresh_all

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting news-dashboard server...")
    if not os.path.exists(config.AI_DATA_FILE) and not os.path.exists(config.GAMING_DATA_FILE):
        logger.info("No cached data found, fetching initial data...")
        refresh_all()
    start_auto_refresh()
    app.run(host="127.0.0.1", port=5678, debug=False)
