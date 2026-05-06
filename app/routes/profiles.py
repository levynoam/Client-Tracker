"""Profiles blueprint."""
from __future__ import annotations

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for

from ..db import get_db

bp = Blueprint("profiles", __name__, url_prefix="/profiles")


@bp.route("/")
def index():
    db = get_db()
    show_archived = request.args.get("archived") == "1"
    if show_archived:
        rows = db.execute("SELECT * FROM profiles ORDER BY archived, name").fetchall()
    else:
        rows = db.execute("SELECT * FROM profiles WHERE archived = 0 ORDER BY name").fetchall()
    return render_template("profiles/index.html", profiles=rows, show_archived=show_archived)


@bp.route("/create", methods=["POST"])
def create():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Profile name is required.", "error")
        return redirect(url_for("profiles.index"))
    db = get_db()
    try:
        cur = db.execute("INSERT INTO profiles (name) VALUES (?)", (name,))
        db.commit()
        new_id = cur.lastrowid
    except Exception:
        db.rollback()
        flash(f"A profile named '{name}' already exists.", "error")
        return redirect(url_for("profiles.index"))

    # If no active profile, set this one active.
    resp = make_response(redirect(url_for("profiles.index")))
    if not request.cookies.get("active_profile_id"):
        resp.set_cookie("active_profile_id", str(new_id), max_age=60 * 60 * 24 * 365)
    return resp


@bp.route("/<int:pid>/rename", methods=["POST"])
def rename(pid: int):
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Profile name is required.", "error")
        return redirect(url_for("profiles.index"))
    db = get_db()
    try:
        db.execute("UPDATE profiles SET name = ? WHERE id = ?", (name, pid))
        db.commit()
    except Exception:
        db.rollback()
        flash(f"A profile named '{name}' already exists.", "error")
    return redirect(url_for("profiles.index"))


@bp.route("/<int:pid>/archive", methods=["POST"])
def archive(pid: int):
    active = request.cookies.get("active_profile_id")
    if active and int(active) == pid:
        flash("You cannot archive the currently active profile. Switch first.", "error")
        return redirect(url_for("profiles.index"))
    db = get_db()
    db.execute("UPDATE profiles SET archived = 1 WHERE id = ?", (pid,))
    db.commit()
    return redirect(url_for("profiles.index", archived=1))


@bp.route("/<int:pid>/restore", methods=["POST"])
def restore(pid: int):
    db = get_db()
    db.execute("UPDATE profiles SET archived = 0 WHERE id = ?", (pid,))
    db.commit()
    return redirect(url_for("profiles.index", archived=1))


@bp.route("/switch", methods=["POST"])
def switch():
    pid = request.form.get("profile_id")
    if not pid:
        return redirect(url_for("profiles.index"))
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM profiles WHERE id = ? AND archived = 0", (pid,)
    ).fetchone()
    if not row:
        abort(404)
    next_url = request.form.get("next") or url_for("calendar.month_view")
    resp = make_response(redirect(next_url))
    resp.set_cookie("active_profile_id", str(pid), max_age=60 * 60 * 24 * 365)
    return resp
