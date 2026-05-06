"""Calendar blueprint: month view + day view + session CRUD."""
from __future__ import annotations

import calendar as cal
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import get_db

bp = Blueprint("calendar", __name__, url_prefix="/calendar")


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
