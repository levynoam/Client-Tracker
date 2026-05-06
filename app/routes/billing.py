"""Monthly billing blueprint."""
from __future__ import annotations

import csv
import io
from datetime import date

from flask import Blueprint, Response, abort, g, redirect, render_template, request, url_for

from ..db import get_db

bp = Blueprint("billing", __name__, url_prefix="/billing")


def _require_profile():
    if not getattr(g, "active_profile", None):
        abort(400, "No active profile selected.")
    return g.active_profile["id"]


def _default_year_month() -> tuple[int, int]:
    today = date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def _parse_year_month(args) -> tuple[int, int]:
    dy, dm = _default_year_month()
    try:
        y = int(args.get("year", dy))
        m = int(args.get("month", dm))
        if not (1 <= m <= 12):
            raise ValueError
    except (TypeError, ValueError):
        y, m = dy, dm
    return y, m


def _query_billing(profile_id: int, year: int, month: int):
    """Return list of rows: client_id, client_name, total_hours, min_rate, max_rate,
    total_amount, invoice_sent, invoice_paid."""
    db = get_db()
    prefix = f"{year:04d}-{month:02d}-"
    rows = db.execute(
        """
        SELECT c.id   AS client_id,
               c.name AS client_name,
               SUM(s.hours) AS total_hours,
               MIN(s.rate)  AS min_rate,
               MAX(s.rate)  AS max_rate,
               SUM(s.hours * s.rate) AS total_amount,
               COALESCE(b.invoice_sent, 0) AS invoice_sent,
               COALESCE(b.invoice_paid, 0) AS invoice_paid
        FROM sessions s
        JOIN clients c ON c.id = s.client_id
        LEFT JOIN billing_status b
            ON b.profile_id = s.profile_id
            AND b.client_id = c.id
            AND b.year = ?
            AND b.month = ?
        WHERE s.profile_id = ? AND s.date LIKE ?
        GROUP BY c.id, c.name, b.invoice_sent, b.invoice_paid
        ORDER BY c.name
        """,
        (year, month, profile_id, prefix + "%"),
    ).fetchall()
    return rows


@bp.route("/")
def index():
    pid = _require_profile()
    y, m = _parse_year_month(request.args)
    rows = _query_billing(pid, y, m)
    grand_hours = sum((r["total_hours"] or 0) for r in rows)
    grand_total = sum((r["total_amount"] or 0) for r in rows)
    return render_template(
        "billing/index.html",
        year=y,
        month=m,
        rows=rows,
        grand_hours=grand_hours,
        grand_total=grand_total,
    )


@bp.route("/export.csv")
def export_csv():
    pid = _require_profile()
    y, m = _parse_year_month(request.args)
    rows = _query_billing(pid, y, m)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Client", "Hours", "Rate (min)", "Rate (max)", "Total", "Invoice sent", "Invoice paid"])
    grand_hours = 0.0
    grand_total = 0.0
    for r in rows:
        writer.writerow(
            [
                r["client_name"],
                f"{r['total_hours']:g}",
                f"{r['min_rate']:g}",
                f"{r['max_rate']:g}",
                f"{r['total_amount']:g}",
                "yes" if r["invoice_sent"] else "no",
                "yes" if r["invoice_paid"] else "no",
            ]
        )
        grand_hours += r["total_hours"] or 0
        grand_total += r["total_amount"] or 0
    writer.writerow([])
    writer.writerow(["TOTAL", f"{grand_hours:g}", "", "", f"{grand_total:g}", "", ""])

    profile_name = g.active_profile["name"]
    filename = f"billing_{profile_name}_{y:04d}-{m:02d}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/status", methods=["POST"])
def set_status():
    """Toggle invoice_sent / invoice_paid flags for a (client, year, month)."""
    pid = _require_profile()
    try:
        client_id = int(request.form["client_id"])
        year = int(request.form["year"])
        month = int(request.form["month"])
    except (KeyError, ValueError):
        abort(400)
    field = request.form.get("field")
    if field not in ("invoice_sent", "invoice_paid"):
        abort(400)
    value = 1 if request.form.get("value") == "1" else 0

    db = get_db()
    # Ensure the client belongs to the active profile.
    owned = db.execute(
        "SELECT 1 FROM clients WHERE id = ? AND profile_id = ?",
        (client_id, pid),
    ).fetchone()
    if not owned:
        abort(404)

    db.execute(
        """
        INSERT INTO billing_status (profile_id, client_id, year, month, invoice_sent, invoice_paid)
        VALUES (?, ?, ?, ?, 0, 0)
        ON CONFLICT(profile_id, client_id, year, month) DO NOTHING
        """,
        (pid, client_id, year, month),
    )
    db.execute(
        f"UPDATE billing_status SET {field} = ? "
        "WHERE profile_id = ? AND client_id = ? AND year = ? AND month = ?",
        (value, pid, client_id, year, month),
    )
    db.commit()
    return redirect(url_for("billing.index", year=year, month=month))
