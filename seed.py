"""Seed script – populate the database with sample tools for demo/testing."""

from datetime import date, timedelta
from app import app
from models import db, Tool, CalibrationRecord, TestReport

SAMPLE_TOOLS = [
    {
        "name": "Micrometer 0-1\"",
        "tool_type": "Micrometer",
        "manufacturer": "Mitutoyo",
        "model_number": "103-135",
        "serial_number": "MIT-001234",
        "log_number": "LOG-0001",
        "location": "Machine Shop – Station A",
        "owner": "John Martinez",
        "router": "Router 1",
        "schedule": "annual",
        "sticker_id": "STK-0001",
        "last_calibration_date": date.today() - timedelta(days=330),
        "comments": "Primary micrometer for QC station",
    },
    {
        "name": "Digital Caliper 6\"",
        "tool_type": "Caliper",
        "manufacturer": "Mitutoyo",
        "model_number": "500-196-30",
        "serial_number": "MIT-005678",
        "log_number": "LOG-0002",
        "location": "Inspection Lab",
        "owner": "Sarah Chen",
        "router": "Router 2",
        "schedule": "semiannual",
        "sticker_id": "STK-0002",
        "last_calibration_date": date.today() - timedelta(days=200),
        "comments": "",
    },
    {
        "name": "Torque Wrench 10-150 ft-lb",
        "tool_type": "Torque Wrench",
        "manufacturer": "Snap-on",
        "model_number": "QD3R250A",
        "serial_number": "SN-TW-0099",
        "log_number": "LOG-0003",
        "location": "Assembly Floor",
        "owner": "Mike Thompson",
        "router": "Router 1",
        "schedule": "annual",
        "sticker_id": "STK-0003",
        "last_calibration_date": date.today() - timedelta(days=400),
        "comments": "Overdue – needs immediate attention",
    },
    {
        "name": "Pressure Gauge 0-100 PSI",
        "tool_type": "Pressure Gauge",
        "manufacturer": "Ashcroft",
        "model_number": "1009",
        "serial_number": "ASH-PG-0042",
        "log_number": "LOG-0004",
        "location": "Test Cell 3",
        "owner": "Sarah Chen",
        "router": "Router 3",
        "schedule": "semiannual",
        "sticker_id": "STK-0004",
        "last_calibration_date": date.today() - timedelta(days=160),
        "comments": "",
    },
    {
        "name": "Height Gauge 12\"",
        "tool_type": "Height Gauge",
        "manufacturer": "Starrett",
        "model_number": "254EMZ",
        "serial_number": "STR-HG-0777",
        "log_number": "LOG-0005",
        "location": "Inspection Lab",
        "owner": "John Martinez",
        "router": "Router 2",
        "schedule": "annual",
        "sticker_id": "STK-0005",
        "last_calibration_date": date.today() - timedelta(days=90),
        "comments": "",
    },
    {
        "name": "Dial Indicator 0-1\"",
        "tool_type": "Dial Indicator",
        "manufacturer": "Starrett",
        "model_number": "25-131J",
        "serial_number": "STR-DI-1234",
        "log_number": "LOG-0006",
        "location": "Machine Shop – Station B",
        "owner": "Mike Thompson",
        "router": "Router 1",
        "schedule": "annual",
        "sticker_id": "STK-0006",
        "last_calibration_date": date.today() - timedelta(days=50),
        "comments": "Recently calibrated",
    },
    {
        "name": "Pin Gauge Set M2",
        "tool_type": "Pin Gauge",
        "manufacturer": "Vermont Gage",
        "model_number": "101100500",
        "serial_number": "VG-PG-SET-088",
        "log_number": "LOG-0007",
        "location": "Tool Crib",
        "owner": "Sarah Chen",
        "router": "Router 2",
        "schedule": "biennial",
        "sticker_id": "STK-0007",
        "last_calibration_date": date.today() - timedelta(days=700),
        "comments": "Due soon for biennial check",
        "on_backup_list": True,
        "status": "not_in_use",
    },
]


def seed():
    with app.app_context():
        if Tool.query.count() > 0:
            print("Database already has tools. Skipping seed.")
            return

        # Create a sample test report
        report = TestReport(
            title="Annual Calibration Report – Acme Labs",
            report_number="RPT-2025-001",
            report_date=date.today() - timedelta(days=30),
            source_company="Acme Calibration Labs",
            notes="Full batch calibration report for Q4 instruments.",
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
                    performed_by="Acme Labs Tech",
                    calibration_company="Acme Calibration Labs",
                    certificate_number=f"CERT-{tool.log_number}",
                    result="pass",
                    notes="Calibrated per manufacturer specs.",
                    test_report_id=report.id,
                )
                db.session.add(cal)

        db.session.commit()
        print(f"✓ Seeded {len(SAMPLE_TOOLS)} tools + 1 test report.")


if __name__ == "__main__":
    seed()
