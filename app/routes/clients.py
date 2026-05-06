"""Clients blueprint."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import get_db

bp = Blueprint("clients", __name__, url_prefix="/clients")


def _require_profile():
    if not getattr(g, "active_profile", None):
        abort(400, "No active profile selected.")
    return g.active_profile["id"]


@bp.route("/")
def index():
    pid = _require_profile()
    db = get_db()
    show_archived = request.args.get("archived") == "1"
    if show_archived:
        rows = db.execute(
            "SELECT * FROM clients WHERE profile_id = ? ORDER BY archived, name",
            (pid,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM clients WHERE profile_id = ? AND archived = 0 ORDER BY name",
            (pid,),
        ).fetchall()
    return render_template("clients/index.html", clients=rows, show_archived=show_archived)


@bp.route("/create", methods=["POST"])
def create():
    pid = _require_profile()
    name = (request.form.get("name") or "").strip()
    rate_raw = (request.form.get("rate") or "").strip()
    if not name:
        flash("Client name is required.", "error")
        return redirect(url_for("clients.index"))
    try:
        rate = float(rate_raw)
        if rate < 0:
            raise ValueError
    except ValueError:
        flash("Rate must be a non-negative number.", "error")
        return redirect(url_for("clients.index"))

    db = get_db()
    try:
        db.execute(
            "INSERT INTO clients (profile_id, name, rate) VALUES (?, ?, ?)",
            (pid, name, rate),
        )
        db.commit()
    except Exception:
        db.rollback()
        flash(f"A client named '{name}' already exists in this profile.", "error")
    return redirect(url_for("clients.index"))


@bp.route("/<int:cid>/edit", methods=["POST"])
def edit(cid: int):
    pid = _require_profile()
    name = (request.form.get("name") or "").strip()
    rate_raw = (request.form.get("rate") or "").strip()
    if not name:
        flash("Client name is required.", "error")
        return redirect(url_for("clients.index"))
    try:
        rate = float(rate_raw)
        if rate < 0:
            raise ValueError
    except ValueError:
        flash("Rate must be a non-negative number.", "error")
        return redirect(url_for("clients.index"))

    db = get_db()
    try:
        db.execute(
            "UPDATE clients SET name = ?, rate = ? WHERE id = ? AND profile_id = ?",
            (name, rate, cid, pid),
        )
        db.commit()
    except Exception:
        db.rollback()
        flash(f"A client named '{name}' already exists in this profile.", "error")
    return redirect(url_for("clients.index"))


@bp.route("/<int:cid>/archive", methods=["POST"])
def archive(cid: int):
    pid = _require_profile()
    db = get_db()
    db.execute(
        "UPDATE clients SET archived = 1 WHERE id = ? AND profile_id = ?",
        (cid, pid),
    )
    db.commit()
    return redirect(url_for("clients.index", archived=1))


@bp.route("/<int:cid>/restore", methods=["POST"])
def restore(cid: int):
    pid = _require_profile()
    db = get_db()
    db.execute(
        "UPDATE clients SET archived = 0 WHERE id = ? AND profile_id = ?",
        (cid, pid),
    )
    db.commit()
    return redirect(url_for("clients.index", archived=1))


@bp.route("/autocomplete")
def autocomplete():
    """HTMX endpoint: returns a small HTML snippet of matching clients."""
    pid = _require_profile()
    q = (request.args.get("q") or "").strip()
    db = get_db()
    if not q:
        rows = []
    else:
        rows = db.execute(
            "SELECT id, name, rate FROM clients "
            "WHERE profile_id = ? AND archived = 0 AND name LIKE ? "
            "ORDER BY name LIMIT 10",
            (pid, f"%{q}%"),
        ).fetchall()
    return render_template("clients/_autocomplete.html", clients=rows, q=q)
