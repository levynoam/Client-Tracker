# Clinic Clients Tracker

## Overview

The goal of this project is to create a web-based tool to track clinic customers, making it easy to bill them at the end of each month.

The tool runs locally (no authentication, single user) and is built as a small server-rendered web app.

## Tech Stack

- **Backend**: Python 3.11+ with **Flask**.
- **Frontend**: Server-rendered Jinja2 templates + **HTMX** for partial updates (autocomplete, inline edits, tab/day navigation). No JS build step.
- **Storage**: **SQLite** (single file in the app data directory). All writes are transactional, giving us "auto-save" for free.
- **Tests**: `pytest` with Flask's test client.

## Project Layout (target)

```
clients/
├── app/
│   ├── __init__.py        # Flask app factory
│   ├── db.py              # SQLite connection + schema/migrations
│   ├── models.py          # Profile / Client / Session helpers
│   ├── routes/            # Blueprints: profiles, calendar, clients, billing
│   ├── templates/         # Jinja2 + HTMX partials
│   └── static/            # CSS, minimal JS, htmx.min.js
├── tests/
├── data/                  # SQLite file lives here (gitignored)
└── pyproject.toml
```

## Requirements

### State & Persistence

- All data is stored in a single SQLite file; every change is committed immediately ("auto-save").
- Closing and reopening the tool instantly restores the previous state.
- No login is required; the tool assumes it runs on a local server or local machine.
- A simple **CSV export** is supported for monthly billing (see Monthly Billing tab).
- Dates are stored as `YYYY-MM-DD` in the user's **local time**; no timezone is persisted.

### Profiles

- The tool allows creation, renaming, and **archiving** of profiles (see "Soft Delete" below).
- Each profile has a completely independent set of clients, sessions, and calendar entries.
- An **active profile** is selected via a dropdown in the page header, visible on every tab.
- On first launch, if no profile exists, the user is prompted to create one before any other tab is usable.

### Clients

- The tool allows creating, **editing**, and **archiving** clients.
- A client has:
  - A unique **name** within its profile (English or Hebrew; RTL is rendered correctly).
  - A **billing price per hour** (positive number, decimals allowed).
- **Archiving (soft delete)**: deleting a client does *not* remove past sessions. Instead, the client is marked archived, hidden from autocomplete and from new-session UI, but their historical sessions remain intact for accurate past billing. Archived clients can be restored.
- Billing is done in ILS, but the tool does not handle currency formatting — values are plain numbers, and all clients are assumed to bill in the same currency.
- Editing a client's hourly rate **does not** change historical sessions: each session snapshots the rate at creation time (see below).

### Sessions (Calendar Entries)

- A session belongs to a profile, a client, and a single **date** (date-only, no time-of-day).
- Each session stores:
  - **Date** (required)
  - **Client** (required, must exist and not be archived at creation time)
  - **Rate snapshot** (required, auto-filled from the client's current hourly rate at creation; editable per session)
  - **Hours** (default `1`, decimals allowed, must be > 0)
  - **Notes** (free text, default empty)
- Sessions can be **added, edited, and deleted**. Deleting a session is a hard delete (it has no dependents).
- Validation: hours must be > 0; rate must be ≥ 0.

### Concurrency

- Concurrent edits from multiple browser tabs use **last-write-wins**. This is acceptable for a single-user local tool.

## Telegram Connectivity

We will connect the app to a telegram bot.
The bot name is MyClients_noam80_bot and the API key appears in the file $USER$\.telegram stored as 
botname = API KEY
Do not read the file directly into your context - write a program that reads and uses the API key

At the end of each day, the user can write a list of clients in an EOL seperated list like so:
Sheldon
Howard
Amy

Upon pressing the 'sync to telegram' button in the Calendar tab, the app will show a list of users who messaged the bot; selecting the user, the app will read all the (unread) messages the Bot recieved and add sessions to names that match in the day the message was recieved, After completion, the app will reply in the bot channel with a list of the days updated and hours added in each day, in addition to errors

There is no need to listen to the telegram channel. Updates will only be made by pressing on the 'sync' button.

### Name Matching
Name matching should accomodate minor typos; especially vowel letter in hebrew. For example, the hebrew names נעם and נועם should be matched.

## Appearance

The tool is displayed as a web page with a header (containing the active-profile selector) and integrated tabs.

### 1. Calendar Tab (default)

This is the default tab shown when the tool is opened (after a profile is selected).

#### 1.1 Month View

- A month-view calendar.
- The month can be selected via standard calendar navigation; the default is the current month.
- Each day displays the **total number of hours** logged that day (and, secondarily, the session count).
- Clicking on any day opens the day view for that day.
- A button to sync to telegram appears in this tab

#### 1.2 Day View

- Shows a list of client sessions as a table with columns: client, hours, rate, notes, delete.
- A new entry is created by typing the first letters of the client name (HTMX-powered autocomplete).
  - Only existing, non-archived clients can be added.
  - Only once a valid client is entered does the line become editable; rate is pre-filled from the client's current rate.
- Each row is editable inline (hours, rate, notes).
- A row can be erased by clicking the **"x"** displayed next to it.
- A **Back** button returns to the month calendar view.

### 2. Clients Tab

- Lists all clients in the active profile, with a toggle to show/hide archived clients.
- Allows **adding**, **editing** (name, hourly rate), and **archiving / restoring** clients.
- A client must be added with a unique name (within the profile) and a positive price-per-hour value.
- Names can be in English or Hebrew; Hebrew names are rendered RTL.

### 3. Monthly Billing Tab

- Operates on the **active profile**.
- Allows selecting a billing month (default: previous month).
- Displays a table with one row per client that had any sessions in the selected month, showing:
  - Client name
  - Total hours
  - Effective rate(s) used (since rates are per-session, this may be a single value or a range)
  - Total billing amount
- Includes a **grand total** row.
- Provides a **"Download CSV"** button to export the table for the selected month.

### 4. Profiles Tab

- Allows creating, renaming, archiving, and restoring profiles.
- Archiving a profile hides it from the active-profile dropdown but preserves all data.
- The currently active profile cannot be archived; the user must switch first.

## Out of Scope (explicitly)

- Authentication / multi-user support.
- Currency conversion or formatting beyond plain numbers.
- Time-of-day scheduling, reminders, or notifications.
- PDF invoice generation (CSV export only for v1).
- Cloud sync or remote backup (the user is responsible for backing up the SQLite file).
