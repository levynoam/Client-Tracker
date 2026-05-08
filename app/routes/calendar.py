"""Calendar blueprint: month view + day view + session CRUD."""
from __future__ import annotations

import calendar as cal
from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import get_db
from ..telegram_connectivity import (
    TelegramAPI,
    list_chats_with_unread,
    load_bot_token,
    match_client_name,
    unread_updates_for_profile,
)

bp = Blueprint("calendar", __name__, url_prefix="/calendar")
BOT_NAME = "MyClients_noam80_bot"


def _require_profile():
    if not getattr(g, "active_profile", None):
        abort(400, "No active profile selected.")
    return g.active_profile["id"]


def _parse_year_month(args) -> tuple[int, int]:
    today = date.today()
    try:
        y = int(args.get("year", today.year))
        m = int(args.get("month", today.month))
        if not (1 <= m <= 12):
            raise ValueError
    except (TypeError, ValueError):
        y, m = today.year, today.month
    return y, m


def _create_telegram_api() -> TelegramAPI:
    token = load_bot_token(BOT_NAME)
    return TelegramAPI(token)


def _processed_update_ids(pid: int) -> set[int]:
    db = get_db()
    rows = db.execute(
        "SELECT update_id FROM telegram_processed_updates WHERE profile_id = ?",
        (pid,),
    ).fetchall()
    return {int(row["update_id"]) for row in rows}


def _active_clients(pid: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT id, name, rate FROM clients WHERE profile_id = ? AND archived = 0",
        (pid,),
    ).fetchall()
    return [dict(row) for row in rows]


@bp.route("/")
def month_view():
    pid = _require_profile()
    y, m = _parse_year_month(request.args)
    db = get_db()

    first = date(y, m, 1)
    _, last_day = cal.monthrange(y, m)
    last = date(y, m, last_day)

    rows = db.execute(
        """
        SELECT date, COUNT(*) AS sessions, COALESCE(SUM(hours), 0) AS hours
        FROM sessions
        WHERE profile_id = ? AND date BETWEEN ? AND ?
        GROUP BY date
        """,
        (pid, first.isoformat(), last.isoformat()),
    ).fetchall()
    by_date = {r["date"]: r for r in rows}

    # Build a 6-row grid (Mon-first) for rendering.
    weeks: list[list[dict]] = []
    week: list[dict] = []
    # Python: Monday=0; use Sunday-first for clinic convenience.
    # We'll use Sunday-first.
    first_weekday = (first.weekday() + 1) % 7  # Sunday=0
    # Pad leading days
    for i in range(first_weekday):
        week.append({"date": None})
    d = first
    while d <= last:
        info = by_date.get(d.isoformat())
        week.append(
            {
                "date": d,
                "sessions": info["sessions"] if info else 0,
                "hours": info["hours"] if info else 0,
            }
        )
        if len(week) == 7:
            weeks.append(week)
            week = []
        d += timedelta(days=1)
    if week:
        while len(week) < 7:
            week.append({"date": None})
        weeks.append(week)

    prev_y, prev_m = (y - 1, 12) if m == 1 else (y, m - 1)
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)

    return render_template(
        "calendar/month.html",
        year=y,
        month=m,
        month_name=cal.month_name[m],
        weeks=weeks,
        prev_y=prev_y,
        prev_m=prev_m,
        next_y=next_y,
        next_m=next_m,
        today=date.today(),
    )


@bp.route("/telegram-sync")
def telegram_sync():
    pid = _require_profile()
    users: list[dict] = []
    try:
        api = _create_telegram_api()
        updates = api.get_updates(limit=100)
        unread = unread_updates_for_profile(updates, _processed_update_ids(pid))
        users = list_chats_with_unread(unread)
    except RuntimeError as exc:
        flash(f"Telegram sync error: {exc}", "error")

    return render_template("calendar/telegram_sync.html", users=users)


@bp.route("/telegram-sync/run", methods=["POST"])
def telegram_sync_run():
    pid = _require_profile()
    chat_id_raw = (request.form.get("chat_id") or "").strip()
    if not chat_id_raw:
        flash("Please select a Telegram user first.", "error")
        return redirect(url_for("calendar.telegram_sync"))

    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        flash("Selected Telegram user is invalid.", "error")
        return redirect(url_for("calendar.telegram_sync"))

    try:
        api = _create_telegram_api()
        updates = api.get_updates(limit=100)
    except RuntimeError as exc:
        flash(f"Telegram sync error: {exc}", "error")
        return redirect(url_for("calendar.telegram_sync"))

    db = get_db()
    unread = unread_updates_for_profile(updates, _processed_update_ids(pid))
    clients = _active_clients(pid)

    by_day: dict[str, float] = defaultdict(float)
    errors: list[str] = []
    processed: list[tuple[int, int, int]] = []

    for upd in unread:
        msg = upd.get("message")
        if not isinstance(msg, dict):
            continue
        try:
            uid = int(upd.get("update_id"))
            msg_chat_id = int((msg.get("chat") or {}).get("id"))
        except (TypeError, ValueError):
            continue
        if msg_chat_id != chat_id:
            continue

        processed.append((pid, uid, chat_id))
        timestamp = msg.get("date")
        try:
            msg_day = date.fromtimestamp(int(timestamp)).isoformat()
        except (TypeError, ValueError):
            errors.append("Can't read message date for one Telegram update")
            continue

        text = (msg.get("text") or "").strip()
        if not text:
            continue

        for raw_line in text.splitlines():
            name = raw_line.strip()
            if not name:
                continue
            match = match_client_name(name, clients)
            if match.client_id is None or match.rate is None:
                errors.append(f"Can't match {name} on day {msg_day}")
                continue

            db.execute(
                "INSERT INTO sessions (profile_id, client_id, date, hours, rate, notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, match.client_id, msg_day, 1.0, match.rate, "Telegram sync"),
            )
            by_day[msg_day] += 1.0

    if processed:
        db.executemany(
            "INSERT OR IGNORE INTO telegram_processed_updates (profile_id, update_id, chat_id) "
            "VALUES (?, ?, ?)",
            processed,
        )
    db.commit()

    summary_lines = ["Telegram sync completed."]
    if by_day:
        summary_lines.append("Days updated:")
        for d in sorted(by_day.keys()):
            summary_lines.append(f"- {d}: {by_day[d]:g} hours")
    else:
        summary_lines.append("No matching client names were added.")

    if errors:
        summary_lines.append("Errors:")
        for err in errors:
            summary_lines.append(f"- {err}")

    summary = "\n".join(summary_lines)
    try:
        api.send_message(chat_id, summary)
    except RuntimeError as exc:
        flash(f"Sync completed, but failed to send Telegram reply: {exc}", "error")

    flash(
        f"Sync done: {sum(by_day.values()):g} hours added across {len(by_day)} day(s).",
        "message",
    )
    if errors:
        flash(f"{len(errors)} unmatched line(s) were reported in Telegram.", "error")
    return redirect(url_for("calendar.telegram_sync"))


@bp.route("/day/<string:day>")
def day_view(day: str):
    pid = _require_profile()
    try:
        d = date.fromisoformat(day)
    except ValueError:
        abort(404)
    db = get_db()
    sessions = db.execute(
        """
        SELECT s.*, c.name AS client_name, c.archived AS client_archived
        FROM sessions s
        JOIN clients c ON c.id = s.client_id
        WHERE s.profile_id = ? AND s.date = ?
        ORDER BY s.id
        """,
        (pid, d.isoformat()),
    ).fetchall()
    return render_template("calendar/day.html", day=d, sessions=sessions)


@bp.route("/day/<string:day>/sessions", methods=["POST"])
def create_session(day: str):
    pid = _require_profile()
    try:
        d = date.fromisoformat(day)
    except ValueError:
        abort(404)
    client_id = request.form.get("client_id")
    if not client_id:
        flash("Please pick a client.", "error")
        return redirect(url_for("calendar.day_view", day=d.isoformat()))

    db = get_db()
    client = db.execute(
        "SELECT * FROM clients WHERE id = ? AND profile_id = ? AND archived = 0",
        (client_id, pid),
    ).fetchone()
    if not client:
        flash("Selected client is not valid.", "error")
        return redirect(url_for("calendar.day_view", day=d.isoformat()))

    hours_raw = (request.form.get("hours") or "1").strip()
    try:
        hours = float(hours_raw)
        if hours <= 0:
            raise ValueError
    except ValueError:
        flash("Hours must be greater than 0.", "error")
        return redirect(url_for("calendar.day_view", day=d.isoformat()))

    notes = request.form.get("notes") or ""
    rate = client["rate"]

    db.execute(
        "INSERT INTO sessions (profile_id, client_id, date, hours, rate, notes)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (pid, client["id"], d.isoformat(), hours, rate, notes),
    )
    db.commit()
    return redirect(url_for("calendar.day_view", day=d.isoformat()))


@bp.route("/sessions/<int:sid>/edit", methods=["POST"])
def edit_session(sid: int):
    pid = _require_profile()
    db = get_db()
    s = db.execute(
        "SELECT * FROM sessions WHERE id = ? AND profile_id = ?", (sid, pid)
    ).fetchone()
    if not s:
        abort(404)

    hours_raw = (request.form.get("hours") or "").strip()
    rate_raw = (request.form.get("rate") or "").strip()
    notes = request.form.get("notes") or ""

    try:
        hours = float(hours_raw)
        if hours <= 0:
            raise ValueError
    except ValueError:
        flash("Hours must be greater than 0.", "error")
        return redirect(url_for("calendar.day_view", day=s["date"]))
    try:
        rate = float(rate_raw)
        if rate < 0:
            raise ValueError
    except ValueError:
        flash("Rate must be non-negative.", "error")
        return redirect(url_for("calendar.day_view", day=s["date"]))

    db.execute(
        "UPDATE sessions SET hours = ?, rate = ?, notes = ? WHERE id = ?",
        (hours, rate, notes, sid),
    )
    db.commit()
    return redirect(url_for("calendar.day_view", day=s["date"]))


@bp.route("/sessions/<int:sid>/delete", methods=["POST"])
def delete_session(sid: int):
    pid = _require_profile()
    db = get_db()
    s = db.execute(
        "SELECT * FROM sessions WHERE id = ? AND profile_id = ?", (sid, pid)
    ).fetchone()
    if not s:
        abort(404)
    db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
    db.commit()
    return redirect(url_for("calendar.day_view", day=s["date"]))
