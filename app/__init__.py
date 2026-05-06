"""Flask application factory."""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, g, redirect, request, url_for

from . import db
from .routes import billing, calendar, clients, profiles


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    default_db = Path(app.root_path).parent / "data" / "app.sqlite3"
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        DATABASE=str(default_db),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    app.register_blueprint(profiles.bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(calendar.bp)
    app.register_blueprint(billing.bp)

    @app.before_request
    def _load_active_profile():
        # Active profile id is stored in a cookie; resolve to a row when present.
        g.active_profile = None
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

        # If no profiles exist at all, force user to the profiles tab to create one.
        if request.endpoint and not request.endpoint.startswith("static"):
            any_profile = db.get_db().execute(
                "SELECT 1 FROM profiles WHERE archived = 0 LIMIT 1"
            ).fetchone()
            if not any_profile and request.endpoint != "profiles.index" and request.endpoint != "profiles.create":
                return redirect(url_for("profiles.index"))

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
