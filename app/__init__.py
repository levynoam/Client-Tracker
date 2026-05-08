"""Flask application factory."""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, g, redirect, request, url_for

from . import db
from .routes import billing, calendar, clients, profiles, telegram


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # Allow DATABASE path via environment variable, or use default.
    default_db = Path(app.root_path).parent / "data" / "app.sqlite3"
    db_path = os.environ.get("DATABASE") or str(default_db)
    
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        DATABASE=db_path,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    app.register_blueprint(profiles.bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(calendar.bp)
    app.register_blueprint(billing.bp)
    app.register_blueprint(telegram.bp)

    @app.before_request
    def _load_active_profile():
        # Active profile id is stored in a cookie; resolve to a row when present.
        g.active_profile = None
        g._set_active_profile_cookie = None
        pid = request.cookies.get("active_profile_id")
        if pid:
            try:
                row = db.get_db().execute(
                    "SELECT * FROM profiles WHERE id = ? AND archived = 0",
                    (int(pid),),
                ).fetchone()
                g.active_profile = row
            except (ValueError, TypeError):
                g.active_profile = None

        # Fresh browsers (for example another LAN machine) will not have the cookie yet.
        # Fall back to the first active profile so protected routes can load.
        if g.active_profile is None:
            row = db.get_db().execute(
                "SELECT * FROM profiles WHERE archived = 0 ORDER BY name LIMIT 1"
            ).fetchone()
            if row:
                g.active_profile = row
                g._set_active_profile_cookie = str(row["id"])

        # If no profiles exist at all, force user to the profiles tab to create one.
        if request.endpoint and not request.endpoint.startswith("static"):
            any_profile = db.get_db().execute(
                "SELECT 1 FROM profiles WHERE archived = 0 LIMIT 1"
            ).fetchone()
            if not any_profile and request.endpoint != "profiles.index" and request.endpoint != "profiles.create":
                return redirect(url_for("profiles.index"))

    @app.after_request
    def _persist_active_profile_cookie(response):
        pid = getattr(g, "_set_active_profile_cookie", None)
        if pid:
            response.set_cookie("active_profile_id", pid, max_age=60 * 60 * 24 * 365)
        return response

    @app.context_processor
    def _inject_globals():
        all_profiles = []
        try:
            all_profiles = db.get_db().execute(
                "SELECT * FROM profiles WHERE archived = 0 ORDER BY name"
            ).fetchall()
        except Exception:
            pass
        return {
            "active_profile": getattr(g, "active_profile", None),
            "all_profiles": all_profiles,
        }

    @app.route("/")
    def index():
        return redirect(url_for("calendar.month_view"))

    return app
