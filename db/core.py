import sqlite3
from pathlib import Path
from settings.settings import settings

DB_PATH = str(settings.BASE_PATH) + r"/data/pywf.db"

