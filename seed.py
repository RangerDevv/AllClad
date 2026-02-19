"""Seed script – populate the database with sample tools for demo/testing.

Includes tools that match the real AllClad calibration PDF filenames so you
can test the bulk-upload auto-linking feature.
"""

from datetime import date, timedelta
from app import app
from models import db, Tool, CalibrationRecord, TestReport

SAMPLE_TOOLS = [
    # ── Tools that match the real calibration PDFs ──────────────────
    # PDF: NA1857-006-031025-CTR_1124667-1ME_Floor Scale_2256_All Clad…
    {
        "name": "Floor Scale 2256",
        "tool_type": "Floor Scale",
        "manufacturer": "Mettler Toledo",
        "model_number": "2256",
        "serial_number": "1124667-1ME",
        "log_number": "CLAD-0001",
        "location": "Clad",
        "owner": "Blanking Cell",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "Asset #1",
        "last_calibration_date": date(2024, 9, 11),
        "comments": "Terminal Model Panther Plus / Term #0068616-6MF. Calibrated 9/11/24.",
    },
    # PDF: NA1857-005-031025-CTR_01240720B1_PEC-PW1-N_All Clad…
    {
        "name": "Floor Scale 2156",
        "tool_type": "Floor Scale",
        "manufacturer": "Mettler Toledo",
        "model_number": "2156",
        "serial_number": "01240720B1",
        "log_number": "CLAD-0002",
        "location": "Clad",
        "owner": "Rowe Line",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "Asset #2",
        "last_calibration_date": date(2024, 9, 11),
        "comments": "Terminal Model Panther Plus. Calibrated 9/11/24.",
    },
    # Another Mettler Toledo floor scale from the CSV
    {
        "name": "Floor Scale 2156 (Forming Wash)",
        "tool_type": "Floor Scale",
        "manufacturer": "Mettler Toledo",
        "model_number": "2156",
        "serial_number": "1039961-1QV",
        "log_number": "FORM-0001",
        "location": "Forming",
        "owner": "Forming Wash",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "Asset #6",
        "last_calibration_date": date(2024, 9, 11),
        "comments": "Terminal Model Panther Plus / Term #0046348-6HF.",
    },
    # ── Pull Testers (yearly) ───────────────────────────────────────
    {
        "name": "Lloyd Pull Tester",
        "tool_type": "Pull Tester",
        "manufacturer": "Lloyd Instrument",
        "model_number": "xlc-5000N",
        "serial_number": "10000504",
        "log_number": "CLAD-0003",
        "location": "Clad",
        "owner": "",
        "router": "",
        "schedule": "annual",
        "sticker_id": "98626",
        "last_calibration_date": date.today() - timedelta(days=300),
        "comments": "",
    },
    {
        "name": "Lloyd Pull Tester #2",
        "tool_type": "Pull Tester",
        "manufacturer": "Lloyd Instrument",
        "model_number": "xlc-5000N",
        "serial_number": "2042000510",
        "log_number": "CLAD-0004",
        "location": "Clad",
        "owner": "",
        "router": "",
        "schedule": "annual",
        "sticker_id": "98627",
        "last_calibration_date": date.today() - timedelta(days=300),
        "comments": "",
    },
    # ── RA Meters ───────────────────────────────────────────────────
    {
        "name": "RA Meter SR160",
        "tool_type": "RA Meter",
        "manufacturer": "Starrett",
        "model_number": "SR160",
        "serial_number": "C07441",
        "log_number": "CLAD-0005",
        "location": "Clad",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "Passed at Jan 2026 calibration.",
    },
    {
        "name": "RA Meter SR160 (Costa)",
        "tool_type": "RA Meter",
        "manufacturer": "Starrett",
        "model_number": "SR160",
        "serial_number": "C07682",
        "log_number": "CLAD-0006",
        "location": "Clad",
        "owner": "Costa",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "Clad Costa area.",
    },
    # ── Micrometers ─────────────────────────────────────────────────
    {
        "name": "Micrometer - Analog Outside",
        "tool_type": "Micrometer - Analog Outside",
        "manufacturer": "Mitutoyo",
        "model_number": "",
        "serial_number": "M-15 (S/N 71436098)",
        "log_number": "CLAD-0007",
        "location": "Clad",
        "owner": "Mike M.",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "M-15",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "",
    },
    {
        "name": "Micrometer - Analog Outside",
        "tool_type": "Micrometer - Analog Outside",
        "manufacturer": "Mitutoyo",
        "model_number": "",
        "serial_number": "M-9 (S/N 72214026)",
        "log_number": "CLAD-0008",
        "location": "Clad",
        "owner": "Brush Line",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "M-9",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "Brush Line.",
    },
    # ── Height Gauges ───────────────────────────────────────────────
    {
        "name": "12\" Height Gauge",
        "tool_type": "Height Gauge",
        "manufacturer": "Mitutoyo",
        "model_number": "HDS-12\"CX",
        "serial_number": "15117347",
        "log_number": "FORM-0002",
        "location": "Forming",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "",
    },
    {
        "name": "12\" Height Gauge",
        "tool_type": "Height Gauge",
        "manufacturer": "Mitutoyo",
        "model_number": "HDS-12\"CX",
        "serial_number": "15126678",
        "log_number": "QA-0001",
        "location": "Quality",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "Can't go above 10\".",
    },
    # ── Calipers ────────────────────────────────────────────────────
    {
        "name": "Caliper - 12\"",
        "tool_type": "Caliper",
        "manufacturer": "Mitutoyo",
        "model_number": "CD-12\"C",
        "serial_number": "QA-SC2 (S/N 01027381)",
        "log_number": "QA-0002",
        "location": "Quality",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "QA-SC2",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "In quality cabinet.",
    },
    {
        "name": "Caliper - 18\"",
        "tool_type": "Caliper",
        "manufacturer": "Mitutoyo",
        "model_number": "CD-18\"C",
        "serial_number": "QA1 (S/N 0008142)",
        "log_number": "QA-0003",
        "location": "Quality",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "QA1",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "In quality cabinet.",
    },
    # ── Concavity Gauges ────────────────────────────────────────────
    {
        "name": "Digital Dial Indicator Concavity Gauge",
        "tool_type": "Concavity Gauge",
        "manufacturer": "Mitutoyo",
        "model_number": "",
        "serial_number": "QA-CG-1 (S/N 16061507)",
        "log_number": "ASSY-0001",
        "location": "Assembly",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "QA-CG-1",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "",
    },
    # ── Thermocouple Reader ─────────────────────────────────────────
    {
        "name": "Thermocouple Reader OM-CP-OCTPRO",
        "tool_type": "Thermocouple Reader",
        "manufacturer": "Omega",
        "model_number": "OM-CP-OCTPRO",
        "serial_number": "S30255",
        "log_number": "CLAD-0009",
        "location": "Clad",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "Solid State - OM-CP-OCTPRO, Calibrated Jan 2026.",
    },
    # ── Depth Gauges ────────────────────────────────────────────────
    {
        "name": "Depth Gauge DG1",
        "tool_type": "Depth Gauge",
        "manufacturer": "Fowler",
        "model_number": "",
        "serial_number": "DG1",
        "log_number": "QA-0004",
        "location": "Quality",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2026, 1, 15),
        "comments": "In quality cabinet.",
    },
    # ── Overdue tool for testing alerts ─────────────────────────────
    {
        "name": "Micrometer - Digital Dial QA 202",
        "tool_type": "Micrometer - Digital Dial",
        "manufacturer": "Mitutoyo",
        "model_number": "",
        "serial_number": "QA-202",
        "log_number": "CLAD-0010",
        "location": "Clad",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2025, 4, 1),
        "comments": "At Blank Deburr machine inspection station. MISSING 10/31/25.",
        "status": "not_in_use",
        "on_backup_list": True,
    },
    # ── Broken tool for backup list ─────────────────────────────────
    {
        "name": "Micrometer - Analog Outside M-12",
        "tool_type": "Micrometer - Analog Outside",
        "manufacturer": "Fowler",
        "model_number": "",
        "serial_number": "M-12",
        "log_number": "CLAD-0011",
        "location": "Clad",
        "owner": "",
        "router": "",
        "schedule": "semiannual",
        "sticker_id": "",
        "last_calibration_date": date(2024, 7, 1),
        "comments": "Broken 12/14/24.",
        "status": "out_of_cal",
        "on_backup_list": True,
    },
]


def seed():
    with app.app_context():
        # Drop and recreate for a clean slate
        db.drop_all()
        db.create_all()
        print("Database reset.")

        # Create a sample test report
        report = TestReport(
            title="Mettler Toledo Floor Scale Calibration - PA 24713",
            report_number="PA 24713",
            report_date=date(2024, 9, 11),
            source_company="Mettler Toledo",
            notes="Floor scale calibration report for Clad and Forming areas.",
        )
        db.session.add(report)
        db.session.flush()

        for data in SAMPLE_TOOLS:
            on_backup = data.pop("on_backup_list", False)
            status_override = data.pop("status", None)

            tool = Tool(**data)
            tool.on_backup_list = on_backup
            tool.recalculate_next_date()

            if status_override:
                tool.status = status_override
            else:
                tool.refresh_status()

            db.session.add(tool)
            db.session.flush()

            # Add a calibration record for each
            if tool.last_calibration_date:
                cal = CalibrationRecord(
                    tool_id=tool.id,
                    calibration_date=tool.last_calibration_date,
                    performed_by="Cal Tec",
                    calibration_company="Mettler Toledo / Cal Tec",
                    certificate_number=f"CERT-{tool.log_number}",
                    result="pass",
                    notes="Calibrated per manufacturer specs.",
                    test_report_id=report.id if "Scale" in tool.name else None,
                )
                db.session.add(cal)

        db.session.commit()
        print(f"Seeded {len(SAMPLE_TOOLS)} tools + 1 test report.")
        print()
        print("Tools with serials matching real PDF filenames:")
        print("  1124667-1ME  -> Floor Scale 2256 (matches NA1857-006 PDF)")
        print("  01240720B1   -> Floor Scale 2156 (matches NA1857-005 PDF)")
        print()
        print("Upload those PDFs via /bulk-upload to test auto-linking!")


if __name__ == "__main__":
    seed()
