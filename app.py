"""AllClad – Calibration Tracking System (Flask Application)."""

import csv
import io
import json
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
    db, Tool, CalibrationRecord, FileAttachment,
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


def save_bytes(data, original_name):
    """Save raw bytes to the upload folder and return (stored_filename, original_filename)."""
    ext = original_name.rsplit(".", 1)[1].lower() if "." in original_name else "pdf"
    stored = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(app.config["UPLOAD_FOLDER"], stored), "wb") as f:
        f.write(data)
    return stored, original_name


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
                Tool.tool_id_number.ilike(like),
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

    col = getattr(Tool, sort, Tool.next_calibration_date)
    query = query.order_by(col.asc() if order == "asc" else col.desc())
    tools = query.all()

    overdue_tools = Tool.query.filter(
        Tool.status == "overdue", Tool.on_backup_list == False
    ).order_by(Tool.next_calibration_date.asc()).all()
    due_soon_tools = Tool.query.filter(
        Tool.status == "due_soon", Tool.on_backup_list == False
    ).order_by(Tool.next_calibration_date.asc()).all()

    locations = [r[0] for r in db.session.query(Tool.location).distinct() if r[0]]
    owners = [r[0] for r in db.session.query(Tool.owner).distinct() if r[0]]
    routers = [r[0] for r in db.session.query(Tool.router).distinct() if r[0]]

    return render_template(
        "dashboard.html", tools=tools,
        locations=locations, owners=owners, routers=routers,
        overdue_tools=overdue_tools, due_soon_tools=due_soon_tools,
        q=q, status_filter=status_filter, schedule_filter=schedule_filter,
        location_filter=location_filter, owner_filter=owner_filter,
        router_filter=router_filter, sort=sort, order=order,
    )


# ── Add / Edit Tool ────────────────────────────────────────────────────────

@app.route("/tools/new", methods=["GET", "POST"])
def tool_new():
    if request.method == "POST":
        serial = request.form.get("serial_number", "").strip()
        tool_id_num = request.form.get("tool_id_number", "").strip()
        tool = Tool(
            name=request.form.get("name", "").strip(),
            description=request.form.get("description", "").strip(),
            tool_type=request.form.get("tool_type", "").strip(),
            manufacturer=request.form.get("manufacturer", "").strip(),
            model_number=request.form.get("model_number", "").strip(),
            serial_number=serial,
            tool_id_number=tool_id_num,
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
        tool.tool_id_number = request.form.get("tool_id_number", "").strip()
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
    return render_template(
        "tool_detail.html", tool=tool,
        calibrations=calibrations, attachments=attachments,
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

        db.session.add(record)
        db.session.flush()

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

    return render_template("calibration_form.html", tool=tool)


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
    user_type = request.form.get("file_type", "cert")

    attachment = FileAttachment(
        tool_id=tool.id,
        filename=stored,
        original_filename=original,
        file_type=user_type,
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
                Tool.tool_id_number.ilike(like),
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


# ══════════════════════════════════════════════════════════════════════════════
# ── Cal Tec Labs PDF Parser ─────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

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


def extract_page_text(doc, page_num):
    """Extract text from a single page."""
    try:
        return doc[page_num].get_text()
    except Exception:
        return ""


def is_cert_start_page(text):
    """Detect if a page is the start of a Cal Tec Labs Certificate of Calibration."""
    lower = text.lower()
    indicators = [
        "certificate of calibration",
        "cert #",
        "cert#",
        "serviced by",
        "serviced for",
        "equipment information",
    ]
    score = sum(1 for kw in indicators if kw in lower)
    return score >= 2


def split_pdf_into_certificates(filepath):
    """Split a multi-certificate PDF into individual certificate page groups.
    
    Each certificate is typically 2 pages. We detect boundaries by looking for
    'Certificate of Calibration' at the top of pages.
    
    Returns list of (start_page, end_page) tuples (0-indexed, inclusive).
    """
    doc = fitz.open(filepath)
    total_pages = len(doc)
    
    if total_pages == 0:
        doc.close()
        return []
    
    # Find all pages that start a new certificate
    cert_starts = []
    for i in range(total_pages):
        text = extract_page_text(doc, i)
        if is_cert_start_page(text):
            cert_starts.append(i)
    
    doc.close()
    
    if not cert_starts:
        # If we can't detect boundaries, treat entire PDF as one certificate
        return [(0, total_pages - 1)]
    
    # Build page ranges: each cert starts at cert_starts[i] and ends just before cert_starts[i+1]
    ranges = []
    for i, start in enumerate(cert_starts):
        if i + 1 < len(cert_starts):
            end = cert_starts[i + 1] - 1
        else:
            end = total_pages - 1
        ranges.append((start, end))
    
    return ranges


def extract_cert_pages_as_pdf(filepath, start_page, end_page):
    """Extract specific pages from a PDF and return as bytes."""
    doc = fitz.open(filepath)
    new_doc = fitz.open()
    for i in range(start_page, end_page + 1):
        new_doc.insert_pdf(doc, from_page=i, to_page=i)
    pdf_bytes = new_doc.tobytes()
    new_doc.close()
    doc.close()
    return pdf_bytes


def parse_cal_tec_cert(text):
    """Parse a Cal Tec Labs Certificate of Calibration from extracted text.
    
    Returns a dict with all extracted fields.
    """
    data = {
        "cert_number": "",
        "generated_date": "",
        "work_order": "",
        "tool_id": "",           # I.D. field
        "serial_number": "",
        "manufacturer": "",
        "model_number": "",
        "tool_type": "",         # Type field
        "description": "",
        "cal_result": "",        # Calibration Result: PASS / FAIL / LTD.
        "cal_due_date": None,
        "cal_date": None,
        "as_found": "",
        "as_left": "",
        "crib_bin": "",
        "service_technician": "",
        "temperature": "",
        "cal_interval": "",
        "test_points": [],
        "standards_used": [],
        "procedures_used": [],
        "building": "",
        "floor": "",
        "room": "",
    }
    
    if not text:
        return data
    
    lines = text.split("\n")
    
    # ── Cert # ──
    for pat in [
        r"Cert\s*#\s*[:=]?\s*(\S+)",
        r"Cert\s*No\.?\s*[:=]?\s*(\S+)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            data["cert_number"] = m.group(1).strip()
            break
    
    # ── Generated date ──
    m = re.search(r"Generated\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    if m:
        data["generated_date"] = m.group(1).strip()
    
    # ── Work Order ──
    m = re.search(r"WO\s+(\S+)", text, re.IGNORECASE)
    if m:
        data["work_order"] = m.group(1).strip()
    
    # ── I.D. ──
    for pat in [
        r"I\.?D\.?\s*[:=]?\s*(\d+)",
        r"I\.D\.\s*[:=]?\s*(\S+)",
    ]:
        m = re.search(pat, text)
        if m:
            data["tool_id"] = m.group(1).strip()
            break
    
    # ── Serial Number ──
    m = re.search(r"Serial\s*Number\s*[:=]?\s*(\S+)", text, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        if val.lower() not in ("calibration", "cal", "cal.", "n/a", "none", ""):
            data["serial_number"] = val
    
    # ── Manufacturer ──
    m = re.search(r"Manufacturer\s+(\S+(?:\s+\S+)*?)(?:\s{2,}|\n|$)", text, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        # Stop at known next fields
        for stop in ["As Found", "As Left", "Cal Date", "Calibration"]:
            idx = val.find(stop)
            if idx > 0:
                val = val[:idx].strip()
        data["manufacturer"] = val
    
    # ── Model Number ──
    m = re.search(r"Model\s*Number\s*[:=]?\s*(\S+(?:\s+\S+)*?)(?:\s{2,}|\n|$)", text, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        for stop in ["Cal Date", "As Found", "Crib"]:
            idx = val.find(stop)
            if idx > 0:
                val = val[:idx].strip()
        data["model_number"] = val
    
    # ── Type ──
    m = re.search(r"Type\s+([A-Z][A-Z\s\d\'\"]+?)(?:\s{2,}|\n|$)", text)
    if m:
        val = m.group(1).strip()
        for stop in ["Crib", "Service", "Temp"]:
            idx = val.find(stop)
            if idx > 0:
                val = val[:idx].strip()
        data["tool_type"] = val
    
    # ── Description ──
    m = re.search(r"Description\s+(.+?)(?:\s{2,}|\n|$)", text, re.IGNORECASE)
    if m:
        data["description"] = m.group(1).strip()
    
    # ── Calibration Result ──
    m = re.search(r"Calibration\s*Result\s*[:=]?\s*(PASS|FAIL|LTD\.?|LIMITED)", text, re.IGNORECASE)
    if m:
        data["cal_result"] = m.group(1).strip().upper()
    
    # ── Cal. Due Date ──
    m = re.search(r"Cal\.?\s*Due\s*Date\s*[:=]?\s*(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    if m:
        try:
            data["cal_due_date"] = datetime.strptime(m.group(1).strip(), "%m/%d/%Y").date()
        except ValueError:
            pass
    
    # ── Cal Date ──
    m = re.search(r"Cal\s*Date\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    if m:
        try:
            data["cal_date"] = datetime.strptime(m.group(1).strip(), "%m/%d/%Y").date()
        except ValueError:
            pass
    
    # ── As Found / As Left ──
    m = re.search(r"As\s*Found\s+(PASS|FAIL|LTD\.?|LIMITED)", text, re.IGNORECASE)
    if m:
        data["as_found"] = m.group(1).strip().upper()
    
    m = re.search(r"As\s*Left\s+(PASS|FAIL|LTD\.?|LIMITED)", text, re.IGNORECASE)
    if m:
        data["as_left"] = m.group(1).strip().upper()
    
    # ── Service Technician ──
    m = re.search(r"Service\s*Technician\s+(.+?)(?:\s{2,}|\n|$)", text, re.IGNORECASE)
    if m:
        data["service_technician"] = m.group(1).strip()
    
    # ── Temp./RH ──
    m = re.search(r"Temp\.?\s*/?\s*RH\s+(.+?)(?:\n|$)", text, re.IGNORECASE)
    if m:
        data["temperature"] = m.group(1).strip()
    
    # ── Cal. Interval ──
    m = re.search(r"Cal\.?\s*Interval\s+(\d+\s+\w+)", text, re.IGNORECASE)
    if m:
        data["cal_interval"] = m.group(1).strip()
    
    # ── Building / Floor / Room ──
    m = re.search(r"Building\s*[:=]?\s*(\S+)", text, re.IGNORECASE)
    if m:
        data["building"] = m.group(1).strip()
    m = re.search(r"Floor\s*[:=]?\s*(\S+)", text, re.IGNORECASE)
    if m:
        data["floor"] = m.group(1).strip()
    m = re.search(r"Room\s*[:=]?\s*(\S+)", text, re.IGNORECASE)
    if m:
        data["room"] = m.group(1).strip()
    
    # ── Test Points ──
    # Look for the test points table section
    tp_section = re.search(
        r"Test\s*Points\s*\n(.*?)(?:Standards?\s*Used|Procedures?\s*Used|This\s*report|Page\s*\d|$)",
        text, re.DOTALL | re.IGNORECASE
    )
    if tp_section:
        tp_text = tp_section.group(1)
        # Parse rows - look for lines with numeric data
        tp_lines = tp_text.strip().split("\n")
        header_found = False
        for line in tp_lines:
            line = line.strip()
            if not line:
                continue
            # Detect header row
            if "description" in line.lower() and "standard" in line.lower():
                header_found = True
                continue
            if re.match(r"^(Seq|#|\d)", line):
                header_found = True
            if header_found:
                # Try to parse a data row
                # Format: Seq Description Standard Tolerance- Tolerance+ Units AsFound AsLeft [V]
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        # Check if first part is a number (sequence)
                        seq_match = re.match(r"^(\d+)", parts[0])
                        if seq_match:
                            tp_row = {
                                "seq": int(seq_match.group(1)),
                                "description": "",
                                "raw": line,
                            }
                            # Try to find the description (text before numbers)
                            desc_match = re.match(r"^\d+\s+([A-Za-z\s]+?)\s+([\d.]+)", line)
                            if desc_match:
                                tp_row["description"] = desc_match.group(1).strip()
                            data["test_points"].append(tp_row)
                    except (ValueError, IndexError):
                        pass
    
    # ── Standards Used ──
    std_section = re.search(
        r"Standards?\s*Used\s*\n(.*?)(?:Procedures?\s*Used|This\s*report|Page\s*\d|$)",
        text, re.DOTALL | re.IGNORECASE
    )
    if std_section:
        std_text = std_section.group(1)
        std_lines = std_text.strip().split("\n")
        for line in std_lines:
            line = line.strip()
            if not line or "company" in line.lower():
                continue
            if "CAL TEC" in line.upper() or "INC" in line.upper() or re.search(r"\d{2,}", line):
                parts = re.split(r"\s{2,}", line)
                if len(parts) >= 2:
                    data["standards_used"].append({
                        "company": parts[0].strip(),
                        "raw": line,
                    })
                elif line.strip():
                    data["standards_used"].append({"raw": line.strip()})
    
    return data


def parse_mettler_toledo_report(text):
    """Parse Mettler-Toledo Comprehensive Test Report (CTR) from extracted text.
    
    Returns same dict structure as parse_cal_tec_cert for uniformity.
    """
    data = {
        "cert_number": "",
        "generated_date": "",
        "work_order": "",
        "tool_id": "",
        "serial_number": "",
        "manufacturer": "Mettler Toledo",
        "model_number": "",
        "tool_type": "",
        "description": "",
        "cal_result": "",
        "cal_due_date": None,
        "cal_date": None,
        "as_found": "",
        "as_left": "",
        "crib_bin": "",
        "service_technician": "",
        "temperature": "",
        "cal_interval": "",
        "test_points": [],
        "standards_used": [],
        "procedures_used": [],
        "building": "",
        "floor": "",
        "room": "",
    }
    
    if not text:
        return data
    
    # Report ID
    m = re.search(r"Report\s*ID\s*[:=]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m:
        data["cert_number"] = m.group(1).strip()
    
    # Serial No
    m = re.search(r"Serial\s*No\.?\s*[:=]?\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        data["serial_number"] = m.group(1).strip()
    
    # Model
    m = re.search(r"Model\s*[:=]?\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        data["model_number"] = m.group(1).strip()
    
    # Instrument Type
    m = re.search(r"Instrument\s*Type\s*[:=]?\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        data["tool_type"] = m.group(1).strip()
    
    return data


def determine_cert_result(cal_result_str):
    """Convert certificate result string to our standard result code."""
    if not cal_result_str:
        return "pass"
    upper = cal_result_str.upper().strip()
    if upper in ("PASS", "PASSED"):
        return "pass"
    elif upper in ("FAIL", "FAILED"):
        return "fail"
    elif upper.startswith("LTD") or upper.startswith("LIMITED"):
        return "limited"
    elif "ADJUST" in upper:
        return "adjusted"
    return "pass"


def determine_schedule_from_interval(interval_str):
    """Convert Cal Tec Labs interval string like '6 MONTHS' to schedule code."""
    if not interval_str:
        return "annual"
    lower = interval_str.strip().lower()
    if "month" in lower:
        m = re.search(r"(\d+)", lower)
        if m:
            months = int(m.group(1))
            if months <= 1:
                return "monthly"
            elif months <= 3:
                return "quarterly"
            elif months <= 6:
                return "semiannual"
            elif months <= 12:
                return "annual"
            elif months <= 24:
                return "biennial"
    if "year" in lower:
        m = re.search(r"(\d+)", lower)
        if m:
            years = int(m.group(1))
            if years <= 1:
                return "annual"
            elif years <= 2:
                return "biennial"
    return "semiannual"  # Default for Cal Tec Labs (6 months is common)


def match_cert_to_tool(cert_data):
    """Try to match parsed certificate data to an existing tool.
    
    Matching priority (Equipment I.D. first — it's the primary identifier):
    1. Equipment I.D. (exact match against tool_id_number)
    2. Equipment I.D. (exact match against sticker_id)
    3. Equipment I.D. (exact match against log_number)
    4. Serial number (exact match) — serial is a separate field
    5. Equipment I.D. (partial/contains match)
    6. Serial number (partial/contains match)
    
    Returns (tool, match_method) or (None, None).
    """
    cert_serial = (cert_data.get("serial_number") or "").strip()
    cert_tool_id = (cert_data.get("tool_id") or "").strip()
    cert_model = (cert_data.get("model_number") or "").strip()
    cert_manufacturer = (cert_data.get("manufacturer") or "").strip()
    cert_description = (cert_data.get("description") or "").strip()
    
    # 1. Exact Equipment I.D. → tool_id_number
    if cert_tool_id:
        tool = Tool.query.filter(
            db.func.lower(Tool.tool_id_number) == cert_tool_id.lower()
        ).first()
        if tool:
            return tool, f"equipment_id={cert_tool_id}"
    
    # 2. Equipment I.D. → sticker_id
    if cert_tool_id:
        tool = Tool.query.filter(
            db.func.lower(Tool.sticker_id) == cert_tool_id.lower()
        ).first()
        if tool:
            return tool, f"sticker_id={cert_tool_id}"
    
    # 3. Equipment I.D. → log_number
    if cert_tool_id:
        tool = Tool.query.filter(
            db.func.lower(Tool.log_number) == cert_tool_id.lower()
        ).first()
        if tool:
            return tool, f"log_number={cert_tool_id}"
    
    # 4. Exact serial number match (serial is a separate identifier)
    if cert_serial:
        tool = Tool.query.filter(
            db.func.lower(Tool.serial_number) == cert_serial.lower()
        ).first()
        if tool:
            return tool, f"serial_number={cert_serial}"
    
    # 5. Partial Equipment I.D. match
    if cert_tool_id and len(cert_tool_id) >= 3:
        tool = Tool.query.filter(
            Tool.tool_id_number.ilike(f"%{cert_tool_id}%")
        ).first()
        if tool:
            return tool, f"equipment_id_contains={cert_tool_id}"
    
    # 6. Partial serial match
    if cert_serial and len(cert_serial) >= 4:
        tool = Tool.query.filter(
            Tool.serial_number.ilike(f"%{cert_serial}%")
        ).first()
        if tool:
            return tool, f"serial_contains={cert_serial}"
    
    return None, None


# ── Bulk PDF Upload (single PDF with multiple certificates) ─────────────────

@app.route("/bulk-upload", methods=["GET", "POST"])
def bulk_upload():
    if request.method == "POST":
        files = request.files.getlist("files")
        if not files or all(f.filename == "" for f in files):
            flash("No files selected.", "danger")
            return redirect(url_for("bulk_upload"))

        all_results = []

        for f in files:
            if not f.filename:
                continue
            if not allowed_file(f.filename):
                all_results.append({
                    "filename": f.filename,
                    "status": "skipped",
                    "reason": "File type not allowed",
                    "certs": [],
                })
                continue

            stored, original = save_upload(f)
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored)

            if not original.lower().endswith(".pdf"):
                all_results.append({
                    "filename": original,
                    "stored": stored,
                    "status": "skipped",
                    "reason": "Not a PDF file",
                    "certs": [],
                })
                continue

            # Split the PDF into individual certificates
            cert_ranges = split_pdf_into_certificates(filepath)

            if not cert_ranges:
                all_results.append({
                    "filename": original,
                    "stored": stored,
                    "status": "skipped",
                    "reason": "No certificates detected in PDF",
                    "certs": [],
                })
                continue

            file_result = {
                "filename": original,
                "stored": stored,
                "status": "processed",
                "total_certs": len(cert_ranges),
                "certs": [],
            }

            doc = fitz.open(filepath)

            for cert_idx, (start_page, end_page) in enumerate(cert_ranges):
                # Extract text from this certificate's pages
                cert_text = ""
                for pg in range(start_page, end_page + 1):
                    cert_text += extract_page_text(doc, pg) + "\n"

                # Determine document type and parse accordingly
                lower_text = cert_text.lower()
                is_mettler = "mettler" in lower_text and "comprehensive test report" in lower_text
                
                if is_mettler:
                    cert_data = parse_mettler_toledo_report(cert_text)
                else:
                    cert_data = parse_cal_tec_cert(cert_text)

                # Try to match to an existing tool
                tool, match_method = match_cert_to_tool(cert_data)

                # Extract this certificate's pages as a separate PDF
                cert_pdf_bytes = extract_cert_pages_as_pdf(filepath, start_page, end_page)
                cert_filename = f"cert_{cert_idx+1}_{original}"
                cert_stored, cert_original = save_bytes(cert_pdf_bytes, cert_filename)

                cert_result = {
                    "index": cert_idx + 1,
                    "pages": f"{start_page+1}-{end_page+1}",
                    "cert_number": cert_data.get("cert_number", ""),
                    "tool_id": cert_data.get("tool_id", ""),
                    "serial": cert_data.get("serial_number", ""),
                    "description": cert_data.get("description", ""),
                    "manufacturer": cert_data.get("manufacturer", ""),
                    "model": cert_data.get("model_number", ""),
                    "cal_result": cert_data.get("cal_result", ""),
                    "cal_date": str(cert_data.get("cal_date", "")) if cert_data.get("cal_date") else "",
                    "due_date": str(cert_data.get("cal_due_date", "")) if cert_data.get("cal_due_date") else "",
                    "technician": cert_data.get("service_technician", ""),
                    "stored": cert_stored,
                    "original": cert_original,
                    "match_method": match_method or "",
                    "matched": tool is not None,
                    "tool_name": "",
                    "tool_log": "",
                    "tool_db_id": None,
                    "action": "",
                }

                if tool:
                    cert_result["tool_name"] = tool.name
                    cert_result["tool_log"] = tool.log_number
                    cert_result["tool_db_id"] = tool.id
                    cert_result["action"] = "linked"

                    # Create calibration record
                    cal_date = cert_data.get("cal_date") or date.today()
                    result_code = determine_cert_result(cert_data.get("cal_result", ""))
                    
                    record = CalibrationRecord(
                        tool_id=tool.id,
                        calibration_date=cal_date,
                        due_date=cert_data.get("cal_due_date"),
                        performed_by=cert_data.get("service_technician", ""),
                        calibration_company=cert_data.get("manufacturer", "Cal Tec Labs") if is_mettler else "Cal Tec Labs",
                        certificate_number=cert_data.get("cert_number", ""),
                        result=result_code,
                        as_found=cert_data.get("as_found", ""),
                        as_left=cert_data.get("as_left", ""),
                        source_company="Cal Tec Labs",
                        temperature=cert_data.get("temperature", ""),
                        cal_interval=cert_data.get("cal_interval", ""),
                        cert_tool_id=cert_data.get("tool_id", ""),
                        cert_serial=cert_data.get("serial_number", ""),
                        cert_model=cert_data.get("model_number", ""),
                        cert_description=cert_data.get("description", ""),
                        test_points=json.dumps(cert_data.get("test_points", [])),
                        standards_used=json.dumps(cert_data.get("standards_used", [])),
                        notes=f"Auto-imported from bulk PDF. Matched via {match_method}.",
                    )
                    if is_mettler:
                        record.report_number = cert_data.get("cert_number", "")
                        record.calibration_company = "Mettler Toledo"
                        record.source_company = "Mettler Toledo"

                    db.session.add(record)
                    db.session.flush()

                    # Attach the cert PDF
                    attachment = FileAttachment(
                        tool_id=tool.id,
                        calibration_record_id=record.id,
                        filename=cert_stored,
                        original_filename=cert_original,
                        file_type="cert",
                        notes=f"Certificate {cert_data.get('cert_number', '')} - auto-imported",
                    )
                    db.session.add(attachment)

                    # Update tool calibration dates
                    if not tool.last_calibration_date or cal_date > tool.last_calibration_date:
                        tool.last_calibration_date = cal_date
                        if cert_data.get("cal_due_date"):
                            tool.next_calibration_date = cert_data["cal_due_date"]
                        else:
                            tool.recalculate_next_date()
                    
                    # Update tool info if missing
                    if cert_data.get("tool_id") and not tool.tool_id_number:
                        tool.tool_id_number = cert_data["tool_id"]
                    if cert_data.get("serial_number") and not tool.serial_number:
                        tool.serial_number = cert_data["serial_number"]
                    if cert_data.get("manufacturer") and not tool.manufacturer:
                        tool.manufacturer = cert_data["manufacturer"]
                    if cert_data.get("model_number") and not tool.model_number:
                        tool.model_number = cert_data["model_number"]
                    if cert_data.get("description") and not tool.description:
                        tool.description = cert_data["description"]
                    
                    # Update schedule from cert interval
                    if cert_data.get("cal_interval"):
                        new_schedule = determine_schedule_from_interval(cert_data["cal_interval"])
                        tool.schedule = new_schedule
                    
                    if result_code == "fail":
                        tool.status = "out_of_cal"
                    else:
                        tool.refresh_status()
                else:
                    cert_result["action"] = "unmatched"

                file_result["certs"].append(cert_result)

            doc.close()
            all_results.append(file_result)

        db.session.commit()

        # Count stats
        total_certs = sum(len(r.get("certs", [])) for r in all_results)
        matched = sum(1 for r in all_results for c in r.get("certs", []) if c.get("matched"))
        unmatched = sum(1 for r in all_results for c in r.get("certs", []) if not c.get("matched"))
        
        flash(
            f"Processed {len(all_results)} PDF(s) containing {total_certs} certificate(s): "
            f"{matched} matched & imported, {unmatched} unmatched.",
            "success" if matched > 0 else "warning",
        )

        return render_template("bulk_upload.html", results=all_results, processed=True,
                               all_tools=Tool.query.order_by(Tool.log_number).all())

    return render_template("bulk_upload.html", results=[], processed=False)


@app.route("/bulk-upload/link", methods=["POST"])
def bulk_upload_link():
    """Manually link an unmatched certificate to a tool and create calibration record."""
    stored = request.form.get("stored_filename")
    original = request.form.get("original_filename")
    tool_id = request.form.get("tool_id")
    create_new = request.form.get("create_new_tool")

    if not stored:
        flash("Missing file information.", "danger")
        return redirect(url_for("bulk_upload"))

    # Read back the cert PDF to parse it
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored)
    pdf_text = extract_pdf_text(filepath) if os.path.exists(filepath) else ""
    cert_data = parse_cal_tec_cert(pdf_text) if pdf_text else {}

    if create_new == "1":
        # Create a new tool from the certificate data
        log_number = f"CERT-{cert_data.get('tool_id', uuid.uuid4().hex[:6])}"
        # Ensure unique log number
        suffix = 0
        candidate = log_number
        while Tool.query.filter(Tool.log_number == candidate).first():
            suffix += 1
            candidate = f"{log_number}-{suffix}"
        log_number = candidate

        tool = Tool(
            name=cert_data.get("description") or cert_data.get("tool_type") or "Unknown Tool",
            description=cert_data.get("description", ""),
            tool_type=cert_data.get("tool_type", ""),
            manufacturer=cert_data.get("manufacturer", ""),
            model_number=cert_data.get("model_number", ""),
            serial_number=cert_data.get("serial_number", ""),
            tool_id_number=cert_data.get("tool_id", ""),
            log_number=log_number,
            schedule=determine_schedule_from_interval(cert_data.get("cal_interval", "")),
        )
        db.session.add(tool)
        db.session.flush()
        flash(f"Created new tool '{tool.name}' (Log: {tool.log_number}).", "success")
    elif tool_id:
        tool = Tool.query.get_or_404(int(tool_id))
    else:
        flash("Select a tool or choose to create a new one.", "danger")
        return redirect(url_for("bulk_upload"))

    # Create calibration record
    cal_date = cert_data.get("cal_date") or date.today()
    result_code = determine_cert_result(cert_data.get("cal_result", ""))
    
    record = CalibrationRecord(
        tool_id=tool.id,
        calibration_date=cal_date,
        due_date=cert_data.get("cal_due_date"),
        performed_by=cert_data.get("service_technician", ""),
        calibration_company="Cal Tec Labs",
        certificate_number=cert_data.get("cert_number", ""),
        result=result_code,
        as_found=cert_data.get("as_found", ""),
        as_left=cert_data.get("as_left", ""),
        source_company="Cal Tec Labs",
        temperature=cert_data.get("temperature", ""),
        cal_interval=cert_data.get("cal_interval", ""),
        cert_tool_id=cert_data.get("tool_id", ""),
        cert_serial=cert_data.get("serial_number", ""),
        cert_model=cert_data.get("model_number", ""),
        cert_description=cert_data.get("description", ""),
        test_points=json.dumps(cert_data.get("test_points", [])),
        standards_used=json.dumps(cert_data.get("standards_used", [])),
        notes="Manually linked from bulk upload.",
    )
    db.session.add(record)
    db.session.flush()

    attachment = FileAttachment(
        tool_id=tool.id,
        calibration_record_id=record.id,
        filename=stored,
        original_filename=original or stored,
        file_type="cert",
        notes=f"Certificate {cert_data.get('cert_number', '')} - manually linked",
    )
    db.session.add(attachment)

    # Update tool dates
    if not tool.last_calibration_date or cal_date > tool.last_calibration_date:
        tool.last_calibration_date = cal_date
        if cert_data.get("cal_due_date"):
            tool.next_calibration_date = cert_data["cal_due_date"]
        else:
            tool.recalculate_next_date()
    
    if result_code == "fail":
        tool.status = "out_of_cal"
    else:
        tool.refresh_status()

    db.session.commit()
    flash(f"Certificate linked to '{tool.name}' with calibration record created.", "success")
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


# ── Calibration Records Browser ────────────────────────────────────────────

@app.route("/calibrations")
def calibration_list():
    """Browse all calibration records across all tools."""
    records = (
        CalibrationRecord.query
        .order_by(CalibrationRecord.calibration_date.desc())
        .all()
    )
    return render_template("calibration_list.html", records=records)


# ── CSV Import ──────────────────────────────────────────────────────────────

EXPECTED_HEADERS = {"dept", "manufacturer", "type/model", "asset / serial no."}

SCHEDULE_MAP = {
    "monthly": "monthly",
    "quarterly": "quarterly",
    "6 months": "semiannual",
    "6 month": "semiannual",
    "semiannual": "semiannual",
    "semi-annual": "semiannual",
    "yearly": "annual",
    "annual": "annual",
    "1 year": "annual",
    "12 months": "annual",
    "biennial": "biennial",
    "24 months": "biennial",
    "2 years": "biennial",
    "5 years": "custom",
}


def parse_schedule(raw):
    if not raw:
        return "annual"
    cleaned = raw.strip().lower()
    for key, val in SCHEDULE_MAP.items():
        if key in cleaned:
            return val
    m = re.match(r"(\d+)\s*/?\s*years?", cleaned)
    if m:
        n = int(m.group(1))
        if n == 1:
            return "annual"
        if n == 2:
            return "biennial"
        return "custom"
    if "year" in cleaned:
        return "annual"
    return "annual"


def parse_custom_days(raw):
    if not raw:
        return None
    m = re.match(r"(\d+)\s*/?\s*years?", raw.strip().lower())
    if m:
        n = int(m.group(1))
        if n > 2:
            return n * 365
    return None


def try_parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    if raw.lower() in ("x", "missing", "not checked", ""):
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            pass
    paren_match = re.search(r"\((\d{1,2}/\d{1,2}/\d{2,4})\)", raw)
    if paren_match:
        return try_parse_date(paren_match.group(1))
    return None


def find_header_row(lines):
    for idx, line in enumerate(lines):
        lower = line.lower()
        if "dept" in lower and "manufacturer" in lower and "type/model" in lower:
            return idx
    return 0


def make_unique_serial(base_serial, dept, row_num):
    if base_serial:
        return base_serial
    return f"NOSN-{dept[:3].upper()}-{row_num:04d}-{uuid.uuid4().hex[:6]}"


def make_unique_log_number(dept, row_num):
    base = f"CSV-{dept[:3].upper()}-{row_num:04d}"
    candidate = base
    suffix = 0
    while Tool.query.filter(Tool.log_number == candidate).first():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


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
            raw_text = f.stream.read().decode("utf-8", errors="replace")
            lines = raw_text.splitlines()

            if not lines:
                flash("CSV file is empty.", "danger")
                return redirect(url_for("csv_import"))

            header_idx = find_header_row(lines)
            csv_body = "\n".join(lines[header_idx:])

            stream = io.StringIO(csv_body)
            reader = csv.DictReader(stream)

            if reader.fieldnames:
                reader.fieldnames = [h.strip() for h in reader.fieldnames]

            imported = 0
            skipped = 0
            updated = 0
            row_errors = []

            for i, row in enumerate(reader, start=header_idx + 2):
                try:
                    dept = (row.get("DEPT") or "").strip()
                    if not dept or dept.lower() == "dept":
                        continue

                    manufacturer = (row.get("Manufacturer") or "").strip()
                    type_model = (row.get("Type/Model") or "").strip()

                    asset_serial = ""
                    for key in ("Asset / Serial No.", "Asset / Serial No",
                                "Asset / Serial No..", "Asset/Serial No."):
                        val = (row.get(key) or "").strip()
                        if val:
                            asset_serial = val
                            break

                    interval = (row.get("Calibration Interval") or "").strip()
                    cal_company = (row.get("Calibration Company") or "").strip()
                    in_service = (row.get("In-Service Date") or "").strip()
                    out_service = (
                        row.get("Out-of-Service date")
                        or row.get("Out-of-Service Date")
                        or ""
                    ).strip()
                    status_raw = (row.get("Status (Active/Inactive)") or "").strip()
                    person = (
                        row.get("Person Responsible (if applicable)")
                        or row.get("Person Responsible")
                        or ""
                    ).strip()
                    notes = (row.get("Notes") or "").strip()
                    cal_date_raw = (row.get("Calibration Date") or "").strip()
                    cert = (row.get("Calibration/Certificate") or "").strip()

                    if not asset_serial and not type_model and not manufacturer:
                        skipped += 1
                        continue

                    serial = make_unique_serial(asset_serial, dept, i)

                    existing = Tool.query.filter(Tool.serial_number == serial).first()
                    if existing:
                        changed = False
                        if notes and notes not in (existing.comments or ""):
                            existing.comments = (
                                (existing.comments or "")
                                + ("\n" if existing.comments else "")
                                + notes
                            )
                            changed = True
                        if cert and cert.lower() not in ("x", "missing", "not checked"):
                            if cert not in (existing.sticker_id or ""):
                                existing.sticker_id = cert
                                changed = True
                        if person and not existing.owner:
                            existing.owner = person
                            changed = True
                        if changed:
                            updated += 1
                        else:
                            skipped += 1
                        continue

                    name = type_model if type_model else f"{manufacturer} instrument"
                    schedule = parse_schedule(interval)
                    custom_days = parse_custom_days(interval) if schedule == "custom" else None

                    notes_lower = notes.lower()
                    cal_marker = cal_date_raw.lower() if cal_date_raw else ""
                    cert_lower = cert.lower() if cert else ""

                    tool_status = "active"
                    if status_raw.lower() in ("inactive", "retired"):
                        tool_status = "retired"
                    elif "missing" in notes_lower or cal_marker == "missing":
                        tool_status = "not_in_use"
                    elif "broken" in notes_lower or "damaged" in notes_lower:
                        tool_status = "out_of_cal"
                    elif "out of service" in notes_lower:
                        tool_status = "retired"
                    elif "not in spec" in notes_lower or "not in spec" in cert_lower:
                        tool_status = "out_of_cal"
                    elif "rejected" in notes_lower:
                        tool_status = "out_of_cal"
                    elif "fail" in cert_lower:
                        tool_status = "out_of_cal"

                    on_backup = tool_status in ("retired", "not_in_use", "out_of_cal")
                    log_number = make_unique_log_number(dept, i)

                    sticker = ""
                    if cert and cert.lower() not in (
                        "x", "missing", "not checked",
                        "not in spec after calibration",
                        "checked but broken", "found",
                    ):
                        sticker = cert

                    tool = Tool(
                        name=name,
                        tool_type=type_model,
                        manufacturer=manufacturer,
                        serial_number=serial,
                        log_number=log_number,
                        location=dept,
                        owner=person,
                        schedule=schedule,
                        custom_interval_days=custom_days,
                        status=tool_status,
                        on_backup_list=on_backup,
                        comments=notes,
                        sticker_id=sticker,
                    )

                    svc_in = try_parse_date(in_service)
                    if svc_in:
                        tool.service_in_date = svc_in

                    svc_out = try_parse_date(out_service)
                    if svc_out:
                        tool.service_out_date = svc_out

                    cal_date = try_parse_date(cal_date_raw)
                    if not cal_date:
                        cal_date = try_parse_date(notes)
                    if cal_date:
                        tool.last_calibration_date = cal_date
                        tool.recalculate_next_date()

                    db.session.add(tool)
                    imported += 1

                except Exception as row_err:
                    row_errors.append(f"Row {i}: {str(row_err)}")
                    skipped += 1
                    continue

            db.session.commit()

            msg = f"CSV imported: {imported} new tools added, {updated} existing updated, {skipped} rows skipped."
            if row_errors:
                msg += f" ({len(row_errors)} rows had errors — check data.)"
            flash(msg, "success")

        except Exception as e:
            db.session.rollback()
            flash(f"Error reading CSV: {str(e)}", "danger")

        return redirect(url_for("csv_import"))

    return render_template("csv_import.html")


# ── Init DB ─────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()


# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1111, debug=True)
