# AllClad – Calibration Tracking System

Self-hosted, iPad-friendly web app to track every calibrated tool in your shop. Built with Python/Flask + SQLite — runs anywhere, no cloud dependency.

---

## Features

| Requirement | How AllClad Handles It |
|---|---|
| **Track everything calibrated** | Full tool registry with serial #, log #, sticker ID, location, owner, router |
| **Calibration schedules** | Monthly, quarterly, semi-annual (6 mo), annual, biennial, or custom day intervals |
| **Prompts when due** | Dashboard alerts for overdue + due-within-30-days, auto-refreshing badges |
| **Out-of-calibration → invest** | Fail result flags the tool & prompts replacement/investment notes |
| **Location, owner, serial, log #** | Dedicated fields on every tool with full search & filter |
| **Accessible anywhere** | Runs on `0.0.0.0:5000` — hit it from any iPad/phone/laptop on the network |
| **iPad UI** | Touch-friendly responsive layout, swipe-to-open sidebar, large tap targets |
| **Repurposed / not in use** | Status options: backup, not in use, repurposed, retired |
| **Intentional out-of-cal** | Move tools to Backup List, take them off the main tracking |
| **Bring 'em back** | One-click Restore from backup to active tracking |
| **Filter & manipulate data** | Filter by status, schedule, location, owner, router + sortable columns |
| **Move backup to priority** | Restore from backup list instantly re-enters active tracking |
| **Test reports** | Upload reports, link them to calibration records |
| **Documented calibration dates** | Full calibration history with date, company, cert #, pass/fail, notes |
| **Link data to test reports** | Link any calibration record to a test report during logging |
| **Self-hosted** | SQLite database, no external services, run on your own server |
| **Sticker tracking** | Sticker ID field for barcode/label identification |
| **Lookup / scan** | Multi-query search: paste or scan multiple serial/log/sticker IDs at once |
| **File repository** | Upload certs, reports, photos — attached per tool |
| **Router-specific** | Dedicated router field with filter |
| **Pass/fail tracking** | Calibration results: Pass, Fail, Adjusted & Pass, Limited/Conditional |
| **Misc columns** | Comments, service in/out dates, status per tool |

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

The server starts on **http://0.0.0.0:5000** — accessible from any device on your network.

### 3. (Optional) Load demo data

```bash
python seed.py
```

This creates 7 sample tools with calibration records and a test report.

---

## Access from iPad

1. Find your server's IP address (`hostname -I` on Linux)
2. On iPad Safari, go to `http://<your-ip>:5000`
3. Tap **Share → Add to Home Screen** for an app-like experience

---

## Project Structure

```
AllClad/
├── app.py                  # Flask application & routes
├── config.py               # Configuration (DB path, upload limits)
├── models.py               # SQLAlchemy models (Tool, CalibrationRecord, TestReport, FileAttachment)
├── seed.py                 # Demo data seeder
├── requirements.txt        # Python dependencies
├── allclad.db              # SQLite database (auto-created)
├── uploads/                # Uploaded files (certs, reports, photos)
├── static/
│   ├── css/style.css       # iPad-friendly responsive styles
│   └── js/app.js           # Frontend JS (sidebar, alerts, lookup)
└── templates/
    ├── base.html           # Layout with sidebar nav & alerts
    ├── dashboard.html      # Main tool list with filters
    ├── tool_form.html      # Add / edit tool
    ├── tool_detail.html    # Tool detail + history + attachments
    ├── calibration_form.html # Log calibration event
    ├── test_reports.html   # Test report list
    ├── report_form.html    # Add test report
    ├── report_detail.html  # Report detail + linked calibrations
    ├── backup_list.html    # Archived / inactive tools
    └── lookup.html         # Multi-search / barcode scan
```

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