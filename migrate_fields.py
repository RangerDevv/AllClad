"""Database migration: rename/add/remove columns for field updates.

Changes:
  tools table:
    - Rename 'location' → 'department'
    - Add new 'location' column (precise location within department)
    - Rename 'owner' → 'retained_by'
    - Remove 'router' column
    - Add 'calibration_performed_by' column

  calibration_records table:
    - Add 'test_report_link' column

Run once:  python migrate_fields.py
"""

import sqlite3
import os
import shutil

DB_PATH = os.path.join(os.path.dirname(__file__), "allclad.db")


def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH} — nothing to migrate.")
        print("The new schema will be created automatically when the app starts.")
        return

    # Back up first
    backup = DB_PATH + ".pre_migration.bak"
    shutil.copy2(DB_PATH, backup)
    print(f"Backed up database to {backup}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── Check existing columns in tools ──
    cur.execute("PRAGMA table_info(tools)")
    tool_cols = {row[1] for row in cur.fetchall()}

    # 1. Rename 'location' → 'department' (if not already done)
    if "location" in tool_cols and "department" not in tool_cols:
        cur.execute("ALTER TABLE tools RENAME COLUMN location TO department")
        print("✓ Renamed tools.location → tools.department")
    elif "department" in tool_cols:
        print("· tools.department already exists, skipping rename")

    # 2. Add new 'location' column (precise location within department)
    cur.execute("PRAGMA table_info(tools)")
    tool_cols = {row[1] for row in cur.fetchall()}
    if "location" not in tool_cols:
        cur.execute("ALTER TABLE tools ADD COLUMN location TEXT DEFAULT ''")
        print("✓ Added tools.location (precise location within department)")
    else:
        print("· tools.location already exists, skipping add")

    # 3. Rename 'owner' → 'retained_by'
    if "owner" in tool_cols and "retained_by" not in tool_cols:
        cur.execute("ALTER TABLE tools RENAME COLUMN owner TO retained_by")
        print("✓ Renamed tools.owner → tools.retained_by")
    elif "retained_by" in tool_cols:
        print("· tools.retained_by already exists, skipping rename")

    # 4. Add 'calibration_performed_by'
    cur.execute("PRAGMA table_info(tools)")
    tool_cols = {row[1] for row in cur.fetchall()}
    if "calibration_performed_by" not in tool_cols:
        cur.execute("ALTER TABLE tools ADD COLUMN calibration_performed_by TEXT DEFAULT ''")
        print("✓ Added tools.calibration_performed_by")
    else:
        print("· tools.calibration_performed_by already exists, skipping")

    # 5. We don't drop 'router' (SQLite doesn't support DROP COLUMN in older versions).
    #    It will simply be ignored by the app. Harmless leftover.
    if "router" in tool_cols:
        print("· tools.router column left in place (ignored by app; SQLite compat)")

    # ── Check existing columns in calibration_records ──
    cur.execute("PRAGMA table_info(calibration_records)")
    cal_cols = {row[1] for row in cur.fetchall()}

    # 6. Add 'test_report_link'
    if "test_report_link" not in cal_cols:
        cur.execute("ALTER TABLE calibration_records ADD COLUMN test_report_link TEXT DEFAULT ''")
        print("✓ Added calibration_records.test_report_link")
    else:
        print("· calibration_records.test_report_link already exists, skipping")

    conn.commit()
    conn.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    migrate()
