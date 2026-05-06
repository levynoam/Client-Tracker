# Clinic Clients Tracker

Local web tool to track clinic clients and produce monthly billing.

See [Project.md](Project.md) for the full spec.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Run

```powershell
python run.py
```

Then open <http://127.0.0.1:5000/> in a browser. On first launch you'll be sent to the **Profiles** tab to create one.

## Test

```powershell
pytest
```

## Data

The SQLite database is created automatically at `data/app.sqlite3`. Back up that file to back up your data.
