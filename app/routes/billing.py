"""Monthly billing blueprint."""
from __future__ import annotations

import csv
import io
from datetime import date

from flask import Blueprint, Response, abort, g, render_template, request

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
    """Return list of rows: client_name, total_hours, min_rate, max_rate, total_amount."""
    db = get_db()
    prefix = f"{year:04d}-{month:02d}-"
    rows = db.execute(
        """
        SELECT c.name AS client_name,
               SUM(s.hours) AS total_hours,
               MIN(s.rate) AS min_rate,
               MAX(s.rate) AS max_rate,
               SUM(s.hours * s.rate) AS total_amount
        FROM sessions s
        JOIN clients c ON c.id = s.client_id
        WHERE s.profile_id = ? AND s.date LIKE ?
        GROUP BY c.id, c.name
        ORDER BY c.name
        """,
        (profile_id, prefix + "%"),
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
    writer.writerow(["Client", "Hours", "Rate (min)", "Rate (max)", "Total"])
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
            ]
        )
        grand_hours += r["total_hours"] or 0
        grand_total += r["total_amount"] or 0
    writer.writerow([])
    writer.writerow(["TOTAL", f"{grand_hours:g}", "", "", f"{grand_total:g}"])

    profile_name = g.active_profile["name"]
    filename = f"billing_{profile_name}_{y:04d}-{m:02d}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
