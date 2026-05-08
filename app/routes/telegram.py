"""Telegram tab blueprint (chat viewer)."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, g, render_template, request

from ..telegram_connectivity import TelegramAPI, list_chats_from_updates, load_bot_token, messages_for_chat

bp = Blueprint("telegram", __name__, url_prefix="/telegram")
BOT_NAME = "MyClients_noam80_bot"


def _require_profile() -> int:
    if not getattr(g, "active_profile", None):
        abort(400, "No active profile selected.")
    return int(g.active_profile["id"])


def _create_telegram_api() -> TelegramAPI:
    token = load_bot_token(BOT_NAME)
    return TelegramAPI(token)


def _read_view_model() -> dict:
    # Profile is required to keep behavior consistent with other tabs.
    _require_profile()

    selected_chat_id = request.args.get("chat_id", type=int)
    updates: list[dict] = []
    chats: list[dict] = []
    messages: list[dict] = []
    error: str | None = None

    try:
        api = _create_telegram_api()
        updates = api.get_updates(limit=100)
        chats = list_chats_from_updates(updates)

        if selected_chat_id is None and chats:
            selected_chat_id = int(chats[0]["chat_id"])
        if selected_chat_id is not None:
            messages = messages_for_chat(updates, selected_chat_id)
    except RuntimeError as exc:
        error = str(exc)

    for msg in messages:
        ts = msg["timestamp"]
        msg["display_time"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""

    return {
        "chats": chats,
        "messages": messages,
        "selected_chat_id": selected_chat_id,
        "error": error,
    }


@bp.route("/")
def index():
    model = _read_view_model()
    return render_template("telegram/index.html", **model)


@bp.route("/poll")
def poll():
    model = _read_view_model()
    return render_template("telegram/_panel.html", **model)
