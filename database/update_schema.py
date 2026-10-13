"""Schema-only target migration; no production data operations."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database.migrate_production import migrate
if __name__ == "__main__":
    migrate(apply=True)
