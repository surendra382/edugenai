"""Wipe all local dev data (SQLite DB + knowledge base files) and recreate
an empty schema, so the app starts fresh with no orphaned state.

Usage:
    python scripts/reset_data.py          # asks for confirmation
    python scripts/reset_data.py --yes    # skips confirmation

Stop the backend server before running this — it deletes data/app.db and
knowledge_base/ while they may be open.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import models  # noqa: E402,F401  registers models with Base.metadata
from backend.app.core.config import settings  # noqa: E402
from backend.app.db.session import create_tables  # noqa: E402


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url.removeprefix("sqlite:///"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    args = parser.parse_args()

    db_path = _sqlite_path(settings.database_url)
    kb_dir = Path(settings.knowledge_base_dir)

    print("This will permanently delete:")
    if db_path is not None:
        print(f"  - {db_path} (all subjects/chapters/question bank items/question sets)")
    print(f"  - {kb_dir}/ (uploaded question-paper images)")

    if not args.yes:
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

    if db_path is not None and db_path.exists():
        db_path.unlink()
        print(f"Deleted {db_path}")

    if kb_dir.exists():
        shutil.rmtree(kb_dir)
        print(f"Deleted {kb_dir}")
    kb_dir.mkdir(parents=True, exist_ok=True)

    create_tables()
    print("Recreated empty schema. Ready for a fresh start.")


if __name__ == "__main__":
    main()
