"""AllClad – Calibration Tracking System (Flask Application)."""

import csv
import io
import os
import re
import uuid
from datetime import date, datetime

import fitz  # PyMuPDF – PDF text extraction

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
        db.session.flush()  # get record.id for cert linking

        # Update tool dates
        tool.last_calibration_date = cal_date
        tool.recalculate_next_date()
        if result == "fail":
            tool.status = "out_of_cal"
        else:
            tool.refresh_status()

        # Handle certificate file upload
        cert_file = request.files.get("certificate_file")
        if cert_file and cert_file.filename and allowed_file(cert_file.filename):
            stored, original = save_upload(cert_file)
            attachment = FileAttachment(
                tool_id=tool.id,
                calibration_record_id=record.id,
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
    user_type = request.form.get("file_type", "auto")

    # Auto-detect PDF type if set to auto
    detected_type = user_type
    pdf_text = ""
    if original.lower().endswith(".pdf") and user_type in ("auto", "misc"):
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored)
        pdf_text = extract_pdf_text(filepath)
        if pdf_text:
            detected_type = classify_pdf(pdf_text, original)

    if detected_type == "report" and original.lower().endswith(".pdf"):
        # Auto-create a TestReport entry
        if not pdf_text:
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored)
            pdf_text = extract_pdf_text(filepath)
        meta = extract_report_metadata(pdf_text, original)
        report = TestReport(
            title=meta["title"],
            report_number=meta["report_number"],
            report_date=meta["report_date"],
            source_company=meta["source_company"],
            file_path=stored,
            original_filename=original,
            notes=request.form.get("notes", "") or "Auto-detected as test report",
        )
        db.session.add(report)
        db.session.flush()
        # Link to most recent calibration record
        latest_cal = CalibrationRecord.query.filter_by(tool_id=tool.id)\
            .order_by(CalibrationRecord.calibration_date.desc()).first()
        if latest_cal and not latest_cal.test_report_id:
            latest_cal.test_report_id = report.id

    attachment = FileAttachment(
        tool_id=tool.id,
        filename=stored,
        original_filename=original,
        file_type=detected_type,
        notes=request.form.get("notes", ""),
    )
    db.session.add(attachment)
    db.session.commit()
    type_label = "Test Report" if detected_type == "report" else "Certificate" if detected_type == "cert" else detected_type.title()
    flash(f"File '{original}' uploaded as {type_label}.", "success")
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


# ── PDF Text Extraction & Matching Helpers ──────────────────────────────────

def extract_pdf_text(filepath):
    """Extract all text from a PDF using PyMuPDF."""
    try:
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text
    except Exception:
        return ""


def classify_pdf(text, filename=""):
    """Determine whether a PDF is a calibration certificate or a test report.
    Returns 'report' or 'cert'."""
    text_lower = text.lower()
    fn_lower = filename.lower()

    report_keywords = [
        "test report", "comprehensive test report", "measurement results",
        "eccentricity", "error of indication", "custom tolerance",
        "repeatability", "report id", "report version",
        "attachment to test report",
    ]
    cert_keywords = [
        "certificate of calibration", "calibration certificate",
        "calibration result", "cert #", "cert#", "cal date",
        "cal. due date", "cal. interval",
        "service technician", "serviced by", "serviced for",
        "standards used", "procedures used", "test points",
    ]

    report_score = sum(1 for kw in report_keywords if kw in text_lower)
    cert_score = sum(1 for kw in cert_keywords if kw in text_lower)

    # Filename hints
    if "ctr" in fn_lower or "report" in fn_lower:
        report_score += 2
    if "cert" in fn_lower or "cal" in fn_lower:
        cert_score += 1

    return "report" if report_score > cert_score else "cert"


def extract_report_metadata(text, filename=""):
    """Extract test report metadata (report number, date, company, title) from PDF text."""
    meta = {"title": "", "report_number": "", "report_date": None, "source_company": ""}

    # Report ID / Number
    for pat in [
        r"Report\s*ID\s*[:=]?\s*([A-Za-z0-9\-]+)",
        r"Report\s*(?:No\.?|Number|#)\s*[:=]?\s*([A-Za-z0-9\-]+)",
        r"Certificate\s*Number\s*[:=]?\s*([A-Za-z0-9\-]+)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            meta["report_number"] = m.group(1).strip()
            break

    # Source company
    for pat in [
        r"(Mettler\s*Toledo)",
        r"Serviced\s*By\s*[:=]?\s*(.+?)\n",
        r"(Cal\s*Tec\s*Labs)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            meta["source_company"] = m.group(1).strip()
            break

    # Date
    for pat in [
        r"(?:Issue|Testing|As Found Testing)\s*Date\s*[:=]?\s*([\d]{1,2}[\-/][A-Za-z]{3}[\-/][\d]{4})",
        r"(?:Issue|Testing|As Found Testing)\s*Date\s*[:=]?\s*([\d]{1,2}[\-/][\d]{1,2}[\-/][\d]{4})",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            for fmt in ("%d-%b-%Y", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y"):
                try:
                    meta["report_date"] = datetime.strptime(raw, fmt).date()
                    break
                except ValueError:
                    continue
            if meta["report_date"]:
                break

    # Title — build from model/manufacturer/type if available
    model_m = re.search(r"Model\s*[:=]?\s*([^\n]+)", text)
    mfg_m = re.search(r"Manufacturer\s*[:=]?\s*([^\n]+)", text)
    serial_m = re.search(r"Serial\s*No\.?\s*[:=]?\s*([^\n]+)", text)
    parts = []
    if mfg_m:
        parts.append(mfg_m.group(1).strip())
    if model_m:
        parts.append(model_m.group(1).strip())
    if serial_m:
        parts.append(f"SN {serial_m.group(1).strip()}")
    if parts:
        meta["title"] = "Comprehensive Test Report - " + " ".join(parts)
    elif meta["report_number"]:
        meta["title"] = f"Test Report {meta['report_number']}"
    else:
        fn_base = os.path.splitext(filename)[0] if filename else "Unknown"
        meta["title"] = f"Test Report - {fn_base}"

    return meta


def extract_identifiers(text, filename=""):
    """Pull serial numbers, certificate numbers, and other IDs from text + filename."""
    combined = text + "\n" + filename
    identifiers = set()

    # Split filename by underscores and hyphens for token matching
    fn_base = os.path.splitext(filename)[0] if filename else ""
    for token in re.split(r"[_\s]+", fn_base):
        token = token.strip()
        if len(token) >= 3 and not token.lower().startswith("all clad"):
            identifiers.add(token)

    # Look for common certificate / serial patterns in PDF text
    # Serial No: XXXX  or  S/N: XXXX  or  Serial Number: XXXX
    for pattern in [
        r"(?:Serial\s*(?:No\.?|Number|#)\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:S/N\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:Asset\s*(?:No\.?|Number|#|ID)\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:Certificate\s*(?:No\.?|Number|#)\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:Cert\.?\s*(?:No\.?|#)\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:Order\s*(?:No\.?|Number)\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:Model\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:ID\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:I\.D\.?\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
        r"(?:Sticker\s*(?:ID|#|No\.?)\s*[:=]?\s*)([A-Za-z0-9\-/]+)",
    ]:
        for m in re.finditer(pattern, combined, re.IGNORECASE):
            val = m.group(1).strip().rstrip(".,;:")
            if len(val) >= 3:
                identifiers.add(val)

    return identifiers


def match_pdf_to_tools(identifiers):
    """Try to match extracted identifiers against tools in the database.
    Returns list of (tool, match_field, match_value) sorted by confidence."""
    matches = []
    seen_ids = set()
    tools = Tool.query.all()

    for tool in tools:
        for ident in identifiers:
            ident_lower = ident.lower().strip()
            if len(ident_lower) < 3:
                continue

            # Check serial number (most reliable)
            if tool.serial_number and ident_lower in tool.serial_number.lower():
                if tool.id not in seen_ids:
                    matches.append((tool, "serial_number", ident))
                    seen_ids.add(tool.id)
                    break

            # Check log number
            if tool.log_number and ident_lower == tool.log_number.lower():
                if tool.id not in seen_ids:
                    matches.append((tool, "log_number", ident))
                    seen_ids.add(tool.id)
                    break

            # Check sticker ID
            if tool.sticker_id and ident_lower in tool.sticker_id.lower():
                if tool.id not in seen_ids:
                    matches.append((tool, "sticker_id", ident))
                    seen_ids.add(tool.id)
                    break

            # Check model number
            if tool.model_number and len(ident_lower) >= 4 and ident_lower in tool.model_number.lower():
                if tool.id not in seen_ids:
                    matches.append((tool, "model_number", ident))
                    seen_ids.add(tool.id)
                    break

    return matches


# ── Bulk PDF Upload ─────────────────────────────────────────────────────────

@app.route("/bulk-upload", methods=["GET", "POST"])
def bulk_upload():
    if request.method == "POST":
        files = request.files.getlist("files")
        if not files or all(f.filename == "" for f in files):
            flash("No files selected.", "danger")
            return redirect(url_for("bulk_upload"))

        results = []
        for f in files:
            if not f.filename:
                continue
            if not allowed_file(f.filename):
                results.append({
                    "filename": f.filename,
                    "status": "skipped",
                    "reason": "File type not allowed",
                    "matches": [],
                })
                continue

            # Save the file
            stored, original = save_upload(f)

            # Extract text if PDF
            pdf_text = ""
            if original.lower().endswith(".pdf"):
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored)
                pdf_text = extract_pdf_text(filepath)

            # Extract identifiers from text + filename
            identifiers = extract_identifiers(pdf_text, original)

            # Try matching
            tool_matches = match_pdf_to_tools(identifiers)

            # Classify the document
            doc_type = classify_pdf(pdf_text, original) if pdf_text else "cert"

            file_result = {
                "filename": original,
                "stored": stored,
                "status": "matched" if tool_matches else "unmatched",
                "doc_type": doc_type,
                "matches": [],
                "identifiers": list(identifiers)[:20],  # cap for display
            }

            if tool_matches:
                # Auto-link to best match (first = highest confidence)
                for tool, field, value in tool_matches:
                    # Find most recent calibration record for this tool
                    latest_cal = CalibrationRecord.query.filter_by(tool_id=tool.id)\
                        .order_by(CalibrationRecord.calibration_date.desc()).first()

                    if doc_type == "report":
                        # Create a TestReport entry and link to the calibration record
                        meta = extract_report_metadata(pdf_text, original)
                        report = TestReport(
                            title=meta["title"],
                            report_number=meta["report_number"],
                            report_date=meta["report_date"],
                            source_company=meta["source_company"],
                            file_path=stored,
                            original_filename=original,
                            notes=f"Auto-imported via {field}: {value}",
                        )
                        db.session.add(report)
                        db.session.flush()
                        # Link calibration record to this report
                        if latest_cal and not latest_cal.test_report_id:
                            latest_cal.test_report_id = report.id
                        attachment = FileAttachment(
                            tool_id=tool.id,
                            calibration_record_id=latest_cal.id if latest_cal else None,
                            filename=stored,
                            original_filename=original,
                            file_type="report",
                            notes=f"Test report - auto-linked via {field}: {value}",
                        )
                    else:
                        attachment = FileAttachment(
                            tool_id=tool.id,
                            calibration_record_id=latest_cal.id if latest_cal else None,
                            filename=stored,
                            original_filename=original,
                            file_type="cert",
                            notes=f"Certificate - auto-linked via {field}: {value}",
                        )
                    db.session.add(attachment)
                    file_result["matches"].append({
                        "tool_id": tool.id,
                        "tool_name": tool.name,
                        "serial_number": tool.serial_number,
                        "log_number": tool.log_number,
                        "match_field": field,
                        "match_value": value,
                    })

            results.append(file_result)

        db.session.commit()

        matched = sum(1 for r in results if r["status"] == "matched")
        unmatched = sum(1 for r in results if r["status"] == "unmatched")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        flash(
            f"Processed {len(results)} files: {matched} matched, {unmatched} unmatched, {skipped} skipped.",
            "success" if matched > 0 else "warning",
        )

        return render_template("bulk_upload.html", results=results, processed=True,
                               all_tools=Tool.query.order_by(Tool.log_number).all())

    return render_template("bulk_upload.html", results=[], processed=False)


@app.route("/bulk-upload/link", methods=["POST"])
def bulk_upload_link():
    """Manually link an unmatched file to a tool."""
    stored = request.form.get("stored_filename")
    original = request.form.get("original_filename")
    tool_id = request.form.get("tool_id")

    if not stored or not tool_id:
        flash("Missing file or tool selection.", "danger")
        return redirect(url_for("bulk_upload"))

    tool = Tool.query.get_or_404(int(tool_id))
    latest_cal = CalibrationRecord.query.filter_by(tool_id=tool.id)\
        .order_by(CalibrationRecord.calibration_date.desc()).first()

    attachment = FileAttachment(
        tool_id=tool.id,
        calibration_record_id=latest_cal.id if latest_cal else None,
        filename=stored,
        original_filename=original or stored,
        file_type="cert",
        notes="Manually linked via bulk upload",
    )
    db.session.add(attachment)
    db.session.commit()
    flash(f"File linked to '{tool.name}'.", "success")
    return redirect(url_for("bulk_upload"))


# ── Certificates ────────────────────────────────────────────────────────────

@app.route("/certificates")
def certificates():
    """Browse all calibration certificate files."""
    certs = (
        FileAttachment.query
        .filter(FileAttachment.file_type == "cert")
        .order_by(FileAttachment.uploaded_at.desc())
        .all()
    )
    return render_template("certificates.html", certs=certs)


# ── CSV Import ──────────────────────────────────────────────────────────────

SCHEDULE_MAP = {
    "monthly": "monthly",
    "quarterly": "quarterly",
    "6 months": "semiannual",
    "6 month": "semiannual",
    "semiannual": "semiannual",
    "semi-annual": "semiannual",
    "yearly": "annual",
    "annual": "annual",
    "12 months": "annual",
    "biennial": "biennial",
    "24 months": "biennial",
    "2 years": "biennial",
}


def parse_schedule(raw):
    """Convert a raw schedule string from the CSV to a model schedule value."""
    if not raw:
        return "annual"
    cleaned = raw.strip().lower()
    for key, val in SCHEDULE_MAP.items():
        if key in cleaned:
            return val
    # Check for year patterns like "5/years/2026"
    if "year" in cleaned:
        return "annual"
    return "annual"


@app.route("/csv-import", methods=["GET", "POST"])
def csv_import():
    if request.method == "POST":
        f = request.files.get("csv_file")
        if not f or not f.filename:
            flash("No file selected.", "danger")
            return redirect(url_for("csv_import"))

        if not f.filename.lower().endswith(".csv"):
            flash("Please upload a CSV file.", "danger")
            return redirect(url_for("csv_import"))

        try:
            stream = io.StringIO(f.stream.read().decode("utf-8", errors="replace"))
            reader = csv.DictReader(stream)

            imported = 0
            skipped = 0
            updated = 0
            errors = []

            for i, row in enumerate(reader, start=2):
                # Skip empty rows or header-like rows
                dept = (row.get("DEPT") or "").strip()
                if not dept or dept.lower() == "dept":
                    continue

                manufacturer = (row.get("Manufacturer") or "").strip()
                type_model = (row.get("Type/Model") or "").strip()
                asset_serial = (row.get("Asset / Serial No.") or row.get("Asset / Serial No") or "").strip()
                interval = (row.get("Calibration Interval") or "").strip()
                cal_company = (row.get("Calibration Company") or "").strip()
                in_service = (row.get("In-Service Date") or "").strip()
                out_service = (row.get("Out-of-Service date") or row.get("Out-of-Service Date") or "").strip()
                status_raw = (row.get("Status (Active/Inactive)") or "").strip()
                person = (row.get("Person Responsible (if applicable)") or "").strip()
                notes = (row.get("Notes") or "").strip()
                cal_date_raw = (row.get("Calibration Date") or "").strip()
                cert = (row.get("Calibration/Certificate") or "").strip()

                if not asset_serial and not type_model:
                    skipped += 1
                    continue

                # Generate a serial number from asset/serial field or manufacture a unique one
                serial = asset_serial if asset_serial else f"IMPORT-{uuid.uuid4().hex[:8]}"

                # Check if tool with this serial already exists
                existing = Tool.query.filter(Tool.serial_number == serial).first()
                if existing:
                    # Update notes if new info
                    if notes and notes not in (existing.comments or ""):
                        existing.comments = (existing.comments or "") + ("\n" if existing.comments else "") + notes
                    updated += 1
                    continue

                # Build tool name from type/model or manufacturer
                name = type_model if type_model else f"{manufacturer} instrument"

                schedule = parse_schedule(interval)

                # Determine status
                tool_status = "active"
                if status_raw.lower() in ("inactive", "retired"):
                    tool_status = "retired"
                if "missing" in notes.lower():
                    tool_status = "not_in_use"
                if "broken" in notes.lower() or "damaged" in notes.lower():
                    tool_status = "out_of_cal"

                on_backup = tool_status in ("retired", "not_in_use")

                # Generate log number
                log_number = f"CSV-{dept[:3].upper()}-{i:04d}"

                tool = Tool(
                    name=name,
                    tool_type=type_model,
                    manufacturer=manufacturer,
                    serial_number=serial,
                    log_number=log_number,
                    location=dept,
                    owner=person,
                    schedule=schedule,
                    status=tool_status,
                    on_backup_list=on_backup,
                    comments=notes,
                    sticker_id=cert if cert and cert.lower() not in ("x", "missing", "not checked") else "",
                )

                # Try to parse calibration date
                if cal_date_raw and cal_date_raw.lower() != "x":
                    try:
                        tool.last_calibration_date = date.fromisoformat(cal_date_raw)
                        tool.recalculate_next_date()
                    except ValueError:
                        pass  # non-standard date, skip

                db.session.add(tool)
                imported += 1

            db.session.commit()
            flash(
                f"CSV imported: {imported} new tools, {updated} existing updated, {skipped} rows skipped.",
                "success",
            )
        except Exception as e:
            flash(f"Error reading CSV: {str(e)}", "danger")

        return redirect(url_for("csv_import"))

    return render_template("csv_import.html")


# ── Init DB ─────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()


# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1111, debug=True)
