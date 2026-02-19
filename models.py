"""Database models for AllClad calibration tracking system."""

from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ── Enums as constants ──────────────────────────────────────────────────────

SCHEDULE_CHOICES = [
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly (3 months)"),
    ("semiannual", "Semi-Annual (6 months)"),
    ("annual", "Annual (12 months)"),
    ("biennial", "Biennial (24 months)"),
    ("custom", "Custom interval"),
]

STATUS_CHOICES = [
    ("active", "Active"),
    ("due_soon", "Due Soon"),
    ("overdue", "Overdue"),
    ("out_of_cal", "Out of Calibration"),
    ("backup", "Backup / Not Tracked"),
    ("not_in_use", "Not In Use"),
    ("repurposed", "Repurposed"),
    ("retired", "Retired"),
]

RESULT_CHOICES = [
    ("pass", "Pass"),
    ("fail", "Fail"),
    ("adjusted", "Adjusted & Pass"),
    ("limited", "Limited / Conditional"),
]


# ── Helper ──────────────────────────────────────────────────────────────────

SCHEDULE_DELTAS = {
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "semiannual": relativedelta(months=6),
    "annual": relativedelta(years=1),
    "biennial": relativedelta(years=2),
}


def _next_cal_date(last_cal_date, schedule, custom_days=None):
    """Calculate the next calibration due date from the last calibration."""
    if not last_cal_date:
        return None
    if schedule == "custom" and custom_days:
        return last_cal_date + relativedelta(days=custom_days)
    delta = SCHEDULE_DELTAS.get(schedule)
    if delta:
        return last_cal_date + delta
    return None


# ── Tool / Instrument ───────────────────────────────────────────────────────

class Tool(db.Model):
    __tablename__ = "tools"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    tool_type = db.Column(db.String(100), default="")          # e.g. Micrometer, Caliper
    manufacturer = db.Column(db.String(200), default="")
    model_number = db.Column(db.String(100), default="")
    serial_number = db.Column(db.String(100), unique=True, nullable=False)
    log_number = db.Column(db.String(100), unique=True, nullable=False)
    location = db.Column(db.String(200), default="")
    owner = db.Column(db.String(200), default="")
    router = db.Column(db.String(200), default="")              # specific to router

    # Calibration schedule
    schedule = db.Column(db.String(20), default="annual")
    custom_interval_days = db.Column(db.Integer, nullable=True) # used when schedule == 'custom'

    # Status
    status = db.Column(db.String(20), default="active")
    on_backup_list = db.Column(db.Boolean, default=False)

    # Dates
    last_calibration_date = db.Column(db.Date, nullable=True)
    next_calibration_date = db.Column(db.Date, nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    service_in_date = db.Column(db.Date, nullable=True)
    service_out_date = db.Column(db.Date, nullable=True)

    # Misc
    comments = db.Column(db.Text, default="")
    sticker_id = db.Column(db.String(100), default="")         # for sticker tracking

    # Relationships
    calibrations = db.relationship(
        "CalibrationRecord", backref="tool", lazy="dynamic",
        cascade="all, delete-orphan", order_by="CalibrationRecord.calibration_date.desc()"
    )
    attachments = db.relationship(
        "FileAttachment", backref="tool", lazy="dynamic",
        cascade="all, delete-orphan",
        foreign_keys="FileAttachment.tool_id",
    )

    def recalculate_next_date(self):
        """Recalculate next calibration date from last calibration."""
        self.next_calibration_date = _next_cal_date(
            self.last_calibration_date, self.schedule, self.custom_interval_days
        )

    def refresh_status(self):
        """Auto-update status based on calibration dates (only for active tools)."""
        if self.status in ("backup", "not_in_use", "repurposed", "retired"):
            return
        if not self.next_calibration_date:
            return
        today = date.today()
        if self.next_calibration_date < today:
            self.status = "overdue"
        elif (self.next_calibration_date - today).days <= 30:
            self.status = "due_soon"
        else:
            self.status = "active"

    @property
    def days_until_due(self):
        if not self.next_calibration_date:
            return None
        return (self.next_calibration_date - date.today()).days

    @property
    def is_on_main_list(self):
        return not self.on_backup_list and self.status not in ("retired",)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "serial_number": self.serial_number,
            "log_number": self.log_number,
            "location": self.location,
            "owner": self.owner,
            "status": self.status,
            "schedule": self.schedule,
            "last_calibration_date": str(self.last_calibration_date) if self.last_calibration_date else None,
            "next_calibration_date": str(self.next_calibration_date) if self.next_calibration_date else None,
            "on_backup_list": self.on_backup_list,
            "days_until_due": self.days_until_due,
        }

    def __repr__(self):
        return f"<Tool {self.log_number} – {self.name}>"


# ── Calibration Record ──────────────────────────────────────────────────────

class CalibrationRecord(db.Model):
    __tablename__ = "calibration_records"

    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey("tools.id"), nullable=False)

    calibration_date = db.Column(db.Date, nullable=False)
    performed_by = db.Column(db.String(200), default="")
    calibration_company = db.Column(db.String(200), default="")
    certificate_number = db.Column(db.String(100), default="")
    result = db.Column(db.String(20), default="pass")           # pass / fail / adjusted / limited
    notes = db.Column(db.Text, default="")

    # If it failed, flag investment need
    requires_replacement = db.Column(db.Boolean, default=False)
    replacement_notes = db.Column(db.Text, default="")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Linked test report
    test_report_id = db.Column(db.Integer, db.ForeignKey("test_reports.id"), nullable=True)

    # Linked certificate files
    certificates = db.relationship(
        "FileAttachment", backref="calibration_record", lazy="dynamic",
        foreign_keys="FileAttachment.calibration_record_id",
    )

    def __repr__(self):
        return f"<CalibrationRecord {self.id} tool={self.tool_id} date={self.calibration_date}>"


# ── Test Report ─────────────────────────────────────────────────────────────

class TestReport(db.Model):
    __tablename__ = "test_reports"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    report_number = db.Column(db.String(100), default="")
    report_date = db.Column(db.Date, nullable=True)
    source_company = db.Column(db.String(200), default="")      # company that issued the report
    notes = db.Column(db.Text, default="")
    file_path = db.Column(db.String(500), default="")           # path to uploaded file
    original_filename = db.Column(db.String(300), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Linked calibration records
    calibrations = db.relationship("CalibrationRecord", backref="test_report", lazy="dynamic")

    def __repr__(self):
        return f"<TestReport {self.report_number} – {self.title}>"


# ── File Attachment (generic – certs, photos, docs) ─────────────────────────

class FileAttachment(db.Model):
    __tablename__ = "file_attachments"

    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey("tools.id"), nullable=True)
    calibration_record_id = db.Column(db.Integer, db.ForeignKey("calibration_records.id"), nullable=True)
    filename = db.Column(db.String(300), nullable=False)
    original_filename = db.Column(db.String(300), nullable=False)
    file_type = db.Column(db.String(50), default="")            # cert, photo, report, misc
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, default="")

    def __repr__(self):
        return f"<FileAttachment {self.original_filename}>"
