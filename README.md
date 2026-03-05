# AllClad – Calibration Tracking System

Self-hosted, iPad-friendly web app to track every calibrated tool in your shop. Built with Python/Flask + SQLite — runs anywhere, no cloud dependency.

---

## Features

| Requirement | How AllClad Handles It |
|---|---|
| **Track everything calibrated** | Full tool registry with serial #, log #, sticker ID, department, location, retained by |
| **Calibration schedules** | Monthly, quarterly, semi-annual (6 mo), annual, biennial, or custom day intervals |
| **Prompts when due** | Dashboard alerts for overdue + due-within-30-days, auto-refreshing badges |
| **Out-of-calibration → invest** | Fail result flags the tool & prompts replacement/investment notes |
| **Department, retained by, serial, log #** | Dedicated fields on every tool with full search & filter |
| **Accessible anywhere** | Runs on `0.0.0.0:1111` — hit it from any iPad/phone/laptop on the network |
| **iPad UI** | Touch-friendly responsive layout, swipe-to-open sidebar, large tap targets |
| **Repurposed / not in use** | Status options: backup, not in use, repurposed, retired |
| **Intentional out-of-cal** | Move tools to Backup List, take them off the main tracking |
| **Bring 'em back** | One-click Restore from backup to active tracking |
| **Pass/fail tracking** | Calibration results: Pass, Fail, Adjusted & Pass, Limited/Conditional |
| **Bulk PDF upload** | Upload multi-certificate PDFs — auto-split, parse, and match to tools |
| **CSV import** | Import tools in bulk from spreadsheets |
| **Certificate storage** | Upload certs & reports attached per calibration record |
| **Lookup / scan** | Multi-query search: paste or scan multiple serial/log/sticker IDs at once |
| **Self-hosted** | SQLite database, no external services, run on your own server |

---

## Quick Start

### 1. Install dependencies

```bash
cd AllClad
pip install -r requirements.txt
```

### 2. Run the app

```bash
python app.py
```

The server starts on **http://0.0.0.0:1111** — accessible from any device on your network.

### 3. (Optional) Load demo data

```bash
python seed.py
```

This creates sample tools with calibration records for testing.

---

## Access from iPad

1. Find your server's IP address (`hostname -I` on Linux)
2. On iPad Safari, go to `http://<your-ip>:1111`
3. Tap **Share → Add to Home Screen** for an app-like experience

---

## Project Structure

```
AllClad/
├── app.py                  # Flask application & routes
├── config.py               # Configuration (DB path, upload limits)
├── models.py               # SQLAlchemy models (Tool, CalibrationRecord, FileAttachment)
├── seed.py                 # Demo data seeder
├── requirements.txt        # Python dependencies
├── allclad.db              # SQLite database (auto-created)
├── uploads/                # Uploaded files (certs, reports, photos)
├── static/
│   ├── css/style.css       # iPad-friendly responsive styles
│   └── js/app.js           # Frontend JS (sidebar, alerts, lookup)
└── templates/
    ├── base.html           # Layout with sidebar nav & alerts
    ├── dashboard.html      # Main tool list with filters & pagination
    ├── tool_form.html      # Add / edit tool
    ├── tool_detail.html    # Tool detail + history + attachments
    ├── calibration_form.html # Log calibration event
    ├── calibration_list.html # Browse all calibration records
    ├── backup_list.html    # Archived / inactive tools
    ├── bulk_upload.html    # Bulk PDF certificate upload & auto-link
    ├── csv_import.html     # CSV tool import
    └── lookup.html         # Multi-search / barcode scan
```

---

## Data Model

### Tool
Name, type, serial number, sticker ID, I.D. number, log number, manufacturer, model number, department, location, retained by, calibration performed by, schedule, status, dates (last cal, next cal, service in/out), comments.

### CalibrationRecord
Calibration date, result (pass/fail/adjusted/limited), calibration company, certificate number, notes, test report link, replacement flag & notes.

### FileAttachment
Uploaded files (certs, photos, reports) linked to tools and calibration records.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/alerts` | Get overdue and due-soon tools (JSON) |
| `POST` | `/api/lookup` | Search by serial/log/sticker IDs (JSON body: `{ "queries": [...] }`) |
| `PATCH` | `/api/tools/<id>/status` | Quick status change (JSON body: `{ "status": "..." }`) |

---

## Configuration

Edit `config.py` or set environment variables:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | (built-in) | Flask session secret — **change in production** |
| `DATABASE_URL` | `sqlite:///allclad.db` | Database connection string |
| `UPLOAD_FOLDER` | `./uploads` | File upload directory |
| `MAX_CONTENT_LENGTH` | 50 MB | Max upload file size |

---

## License

See [LICENSE](LICENSE).

# Made with ❤ by RangerDevv
