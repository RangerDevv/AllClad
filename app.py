"""AllClad – Calibration Tracking System (Flask Application)."""

import os
import uuid
from datetime import date, datetime

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, send_from_directory, abort,
)
from werkzeug.utils import secure_filename

from config import Config
from models import (
    db, Tool, CalibrationRecord, TestReport, FileAttachment,
    SCHEDULE_CHOICES, STATUS_CHOICES, RESULT_CHOICES,
)

# ── App factory ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def save_upload(file):
    """Save an uploaded file and return (stored_filename, original_filename)."""
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[1].lower() if "." in original else "bin"
    stored = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], stored))
    return stored, original


# ── Context processors ──────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    """Make constants and alert counts available in every template."""
    overdue = Tool.query.filter(
        Tool.status == "overdue", Tool.on_backup_list == False
    ).count()
    due_soon = Tool.query.filter(
        Tool.status == "due_soon", Tool.on_backup_list == False
    ).count()
    return dict(
        schedule_choices=SCHEDULE_CHOICES,
        status_choices=STATUS_CHOICES,
        result_choices=RESULT_CHOICES,
        alert_overdue=overdue,
        alert_due_soon=due_soon,
        today=date.today(),
    )


# ── Refresh statuses on every request (lightweight for small DBs) ───────────

@app.before_request
def refresh_tool_statuses():
    """Keep status flags in sync with calendar."""
    if request.endpoint and request.endpoint != "static":
        tools = Tool.query.filter(Tool.on_backup_list == False).all()
        changed = False
        for t in tools:
            old = t.status
            t.refresh_status()
            if t.status != old:
                changed = True
        if changed:
            db.session.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════════════════════

# ── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Main tracking list with filters."""
    # Query params for filtering
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "")
    schedule_filter = request.args.get("schedule", "")
    location_filter = request.args.get("location", "")
    owner_filter = request.args.get("owner", "")
    router_filter = request.args.get("router", "")
    sort = request.args.get("sort", "next_calibration_date")
    order = request.args.get("order", "asc")

    query = Tool.query.filter(Tool.on_backup_list == False)

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Tool.name.ilike(like),
                Tool.serial_number.ilike(like),
                Tool.log_number.ilike(like),
                Tool.sticker_id.ilike(like),
                Tool.owner.ilike(like),
                Tool.location.ilike(like),
                Tool.description.ilike(like),
                Tool.router.ilike(like),
            )
        )
    if status_filter:
        query = query.filter(Tool.status == status_filter)
    if schedule_filter:
        query = query.filter(Tool.schedule == schedule_filter)
    if location_filter:
        query = query.filter(Tool.location == location_filter)
    if owner_filter:
        query = query.filter(Tool.owner == owner_filter)
    if router_filter:
        query = query.filter(Tool.router == router_filter)

    # Sorting
    col = getattr(Tool, sort, Tool.next_calibration_date)
    query = query.order_by(col.asc() if order == "asc" else col.desc())

    tools = query.all()

    # Distinct values for filter dropdowns
    locations = [r[0] for r in db.session.query(Tool.location).distinct() if r[0]]
    owners = [r[0] for r in db.session.query(Tool.owner).distinct() if r[0]]
    routers = [r[0] for r in db.session.query(Tool.router).distinct() if r[0]]

    return render_template(
        "dashboard.html", tools=tools,
        locations=locations, owners=owners, routers=routers,
        q=q, status_filter=status_filter, schedule_filter=schedule_filter,
        location_filter=location_filter, owner_filter=owner_filter,
        router_filter=router_filter, sort=sort, order=order,
    )


# ── Add / Edit Tool ────────────────────────────────────────────────────────

@app.route("/tools/new", methods=["GET", "POST"])
def tool_new():
    if request.method == "POST":
        tool = Tool(
            name=request.form.get("name", "").strip(),
            description=request.form.get("description", "").strip(),
            tool_type=request.form.get("tool_type", "").strip(),
            manufacturer=request.form.get("manufacturer", "").strip(),
            model_number=request.form.get("model_number", "").strip(),
            serial_number=request.form.get("serial_number", "").strip(),
            log_number=request.form.get("log_number", "").strip(),
            location=request.form.get("location", "").strip(),
            owner=request.form.get("owner", "").strip(),
            router=request.form.get("router", "").strip(),
            schedule=request.form.get("schedule", "annual"),
            custom_interval_days=int(request.form["custom_interval_days"]) if request.form.get("custom_interval_days") else None,
            status=request.form.get("status", "active"),
            sticker_id=request.form.get("sticker_id", "").strip(),
            comments=request.form.get("comments", "").strip(),
        )
        # Dates
        lcd = request.form.get("last_calibration_date")
        if lcd:
            tool.last_calibration_date = date.fromisoformat(lcd)
            tool.recalculate_next_date()
        sid = request.form.get("service_in_date")
        if sid:
            tool.service_in_date = date.fromisoformat(sid)
        sod = request.form.get("service_out_date")
        if sod:
            tool.service_out_date = date.fromisoformat(sod)

        db.session.add(tool)
        db.session.commit()
        flash(f"Tool '{tool.name}' added successfully.", "success")
        return redirect(url_for("tool_detail", tool_id=tool.id))

    return render_template("tool_form.html", tool=None, editing=False)


@app.route("/tools/<int:tool_id>/edit", methods=["GET", "POST"])
def tool_edit(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    if request.method == "POST":
        tool.name = request.form.get("name", "").strip()
        tool.description = request.form.get("description", "").strip()
        tool.tool_type = request.form.get("tool_type", "").strip()
        tool.manufacturer = request.form.get("manufacturer", "").strip()
        tool.model_number = request.form.get("model_number", "").strip()
        tool.serial_number = request.form.get("serial_number", "").strip()
        tool.log_number = request.form.get("log_number", "").strip()
        tool.location = request.form.get("location", "").strip()
        tool.owner = request.form.get("owner", "").strip()
        tool.router = request.form.get("router", "").strip()
        tool.schedule = request.form.get("schedule", "annual")
        cid = request.form.get("custom_interval_days")
        tool.custom_interval_days = int(cid) if cid else None
        tool.status = request.form.get("status", "active")
        tool.sticker_id = request.form.get("sticker_id", "").strip()
        tool.comments = request.form.get("comments", "").strip()

        lcd = request.form.get("last_calibration_date")
        tool.last_calibration_date = date.fromisoformat(lcd) if lcd else None
        tool.recalculate_next_date()

        sid = request.form.get("service_in_date")
        tool.service_in_date = date.fromisoformat(sid) if sid else None
        sod = request.form.get("service_out_date")
        tool.service_out_date = date.fromisoformat(sod) if sod else None

        db.session.commit()
        flash(f"Tool '{tool.name}' updated.", "success")
        return redirect(url_for("tool_detail", tool_id=tool.id))

    return render_template("tool_form.html", tool=tool, editing=True)


# ── Tool Detail ─────────────────────────────────────────────────────────────

@app.route("/tools/<int:tool_id>")
def tool_detail(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    calibrations = tool.calibrations.order_by(CalibrationRecord.calibration_date.desc()).all()
    attachments = tool.attachments.order_by(FileAttachment.uploaded_at.desc()).all()
    test_reports = TestReport.query.all()  # for linking dropdown
    return render_template(
        "tool_detail.html", tool=tool,
        calibrations=calibrations, attachments=attachments,
        test_reports=test_reports,
    )


# ── Delete Tool ─────────────────────────────────────────────────────────────

@app.route("/tools/<int:tool_id>/delete", methods=["POST"])
def tool_delete(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    db.session.delete(tool)
    db.session.commit()
    flash(f"Tool '{tool.name}' deleted.", "warning")
    return redirect(url_for("dashboard"))


# ── Move to Backup / Restore ───────────────────────────────────────────────

@app.route("/tools/<int:tool_id>/to-backup", methods=["POST"])
def tool_to_backup(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    tool.on_backup_list = True
    tool.status = request.form.get("reason", "backup")
    db.session.commit()
    flash(f"'{tool.name}' moved to backup list.", "info")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/tools/<int:tool_id>/restore", methods=["POST"])
def tool_restore(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    tool.on_backup_list = False
    tool.status = "active"
    tool.refresh_status()
    db.session.commit()
    flash(f"'{tool.name}' restored to main list.", "success")
    return redirect(request.referrer or url_for("backup_list"))


# ── Backup List Page ────────────────────────────────────────────────────────

@app.route("/backup")
def backup_list():
    tools = Tool.query.filter(Tool.on_backup_list == True).all()
    return render_template("backup_list.html", tools=tools)


# ── Log Calibration ────────────────────────────────────────────────────────

@app.route("/tools/<int:tool_id>/calibrate", methods=["GET", "POST"])
def calibrate(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    if request.method == "POST":
        cal_date = date.fromisoformat(request.form["calibration_date"])
        result = request.form.get("result", "pass")

        record = CalibrationRecord(
            tool_id=tool.id,
            calibration_date=cal_date,
            performed_by=request.form.get("performed_by", "").strip(),
            calibration_company=request.form.get("calibration_company", "").strip(),
            certificate_number=request.form.get("certificate_number", "").strip(),
            result=result,
            notes=request.form.get("notes", "").strip(),
            requires_replacement=result == "fail",
            replacement_notes=request.form.get("replacement_notes", "").strip() if result == "fail" else "",
        )

        # Link to test report
        tr_id = request.form.get("test_report_id")
        if tr_id:
            record.test_report_id = int(tr_id)

        db.session.add(record)

        # Update tool dates
        tool.last_calibration_date = cal_date
        tool.recalculate_next_date()
        if result == "fail":
            tool.status = "out_of_cal"
        else:
            tool.refresh_status()

        db.session.commit()

        # Handle certificate file upload
        cert_file = request.files.get("certificate_file")
        if cert_file and cert_file.filename and allowed_file(cert_file.filename):
            stored, original = save_upload(cert_file)
            attachment = FileAttachment(
                tool_id=tool.id,
                filename=stored,
                original_filename=original,
                file_type="cert",
                notes=f"Calibration certificate - {cal_date}",
            )
            db.session.add(attachment)
            db.session.commit()

        flash(f"Calibration logged for '{tool.name}' - {result.upper()}.", "success")
        return redirect(url_for("tool_detail", tool_id=tool.id))

    test_reports = TestReport.query.order_by(TestReport.report_date.desc()).all()
    return render_template("calibration_form.html", tool=tool, test_reports=test_reports)


# ── Test Reports ────────────────────────────────────────────────────────────

@app.route("/reports")
def test_reports():
    reports = TestReport.query.order_by(TestReport.report_date.desc()).all()
    return render_template("test_reports.html", reports=reports)


@app.route("/reports/new", methods=["GET", "POST"])
def report_new():
    if request.method == "POST":
        report = TestReport(
            title=request.form.get("title", "").strip(),
            report_number=request.form.get("report_number", "").strip(),
            report_date=date.fromisoformat(request.form["report_date"]) if request.form.get("report_date") else None,
            source_company=request.form.get("source_company", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )
        rfile = request.files.get("report_file")
        if rfile and rfile.filename and allowed_file(rfile.filename):
            stored, original = save_upload(rfile)
            report.file_path = stored
            report.original_filename = original

        db.session.add(report)
        db.session.commit()
        flash(f"Test report '{report.title}' saved.", "success")
        return redirect(url_for("test_reports"))

    return render_template("report_form.html", report=None, editing=False)


@app.route("/reports/<int:report_id>")
def report_detail(report_id):
    report = TestReport.query.get_or_404(report_id)
    linked_cals = report.calibrations.all()
    return render_template("report_detail.html", report=report, linked_cals=linked_cals)


@app.route("/reports/<int:report_id>/delete", methods=["POST"])
def report_delete(report_id):
    report = TestReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    flash("Test report deleted.", "warning")
    return redirect(url_for("test_reports"))


# ── File Uploads / Downloads ───────────────────────────────────────────────

@app.route("/tools/<int:tool_id>/upload", methods=["POST"])
def upload_file(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("tool_detail", tool_id=tool.id))
    if not allowed_file(f.filename):
        flash("File type not allowed.", "danger")
        return redirect(url_for("tool_detail", tool_id=tool.id))
    stored, original = save_upload(f)
    attachment = FileAttachment(
        tool_id=tool.id,
        filename=stored,
        original_filename=original,
        file_type=request.form.get("file_type", "misc"),
        notes=request.form.get("notes", ""),
    )
    db.session.add(attachment)
    db.session.commit()
    flash(f"File '{original}' uploaded.", "success")
    return redirect(url_for("tool_detail", tool_id=tool.id))


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/attachments/<int:att_id>/delete", methods=["POST"])
def delete_attachment(att_id):
    att = FileAttachment.query.get_or_404(att_id)
    tool_id = att.tool_id
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], att.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(att)
    db.session.commit()
    flash("Attachment deleted.", "warning")
    return redirect(url_for("tool_detail", tool_id=tool_id))


# ── Lookup / Scan ──────────────────────────────────────────────────────────

@app.route("/lookup")
def lookup():
    return render_template("lookup.html")


@app.route("/api/lookup", methods=["POST"])
def api_lookup():
    """Accept one or more serial/log/sticker numbers and return matching tools."""
    data = request.get_json(silent=True) or {}
    queries = data.get("queries", [])
    if isinstance(queries, str):
        queries = [q.strip() for q in queries.split(",") if q.strip()]
    results = []
    for q in queries:
        like = f"%{q}%"
        matches = Tool.query.filter(
            db.or_(
                Tool.serial_number.ilike(like),
                Tool.log_number.ilike(like),
                Tool.sticker_id.ilike(like),
                Tool.name.ilike(like),
            )
        ).all()
        results.append({"query": q, "matches": [t.to_dict() for t in matches]})
    return jsonify(results)


# ── API: Alerts ─────────────────────────────────────────────────────────────

@app.route("/api/alerts")
def api_alerts():
    """Return tools that are overdue or due soon."""
    overdue = Tool.query.filter(
        Tool.status == "overdue", Tool.on_backup_list == False
    ).all()
    due_soon = Tool.query.filter(
        Tool.status == "due_soon", Tool.on_backup_list == False
    ).all()
    return jsonify({
        "overdue": [t.to_dict() for t in overdue],
        "due_soon": [t.to_dict() for t in due_soon],
    })


# ── API: Quick status change ───────────────────────────────────────────────

@app.route("/api/tools/<int:tool_id>/status", methods=["PATCH"])
def api_change_status(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status and new_status in dict(STATUS_CHOICES):
        tool.status = new_status
        if new_status in ("backup", "not_in_use", "repurposed", "retired"):
            tool.on_backup_list = True
        db.session.commit()
        return jsonify(tool.to_dict())
    return jsonify({"error": "Invalid status"}), 400


# ── Init DB ─────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()


# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1111, debug=True)
