"""Telegram tab blueprint (chat viewer)."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, abort, g, render_template, request

from ..db import get_db
from ..telegram_connectivity import TelegramAPI, load_bot_token

bp = Blueprint("telegram", __name__, url_prefix="/telegram")
BOT_NAME = "MyClients_noam80_bot"


def _require_profile() -> int:
    if not getattr(g, "active_profile", None):
        abort(400, "No active profile selected.")
    return int(g.active_profile["id"])


def _create_telegram_api() -> TelegramAPI:
    token = load_bot_token(BOT_NAME)
    return TelegramAPI(token)


def _chat_label(chat: dict) -> str:
    title = (chat.get("title") or "").strip()
    if title:
        return title
    first = (chat.get("first_name") or "").strip()
    last = (chat.get("last_name") or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full
    username = (chat.get("username") or "").strip()
    if username:
        return f"@{username}"
    return f"Chat {chat.get('id')}"


def _sender_label(sender: dict) -> str:
    first = (sender.get("first_name") or "").strip()
    last = (sender.get("last_name") or "").strip()
    full = f"{first} {last}".strip()
    return full or (sender.get("username") or "Unknown")


def _cache_updates(profile_id: int, updates: list[dict]) -> None:
    rows: list[tuple] = []
    for upd in updates:
        msg = upd.get("message")
        if not isinstance(msg, dict):
            continue

        text = (msg.get("text") or "").strip()
        if not text:
            continue

        chat = msg.get("chat") or {}
        sender = msg.get("from") or {}
        try:
            update_id = int(upd.get("update_id"))
            chat_id = int(chat.get("id"))
            ts = int(msg.get("date") or 0)
        except (TypeError, ValueError):
            continue
        if ts <= 0:
            continue

        rows.append(
            (
                profile_id,
                update_id,
                chat_id,
                _chat_label(chat),
                _sender_label(sender),
                text,
                ts,
            )
        )

    if not rows:
        return

    db = get_db()
    db.executemany(
        "INSERT OR IGNORE INTO telegram_messages_cache "
        "(profile_id, update_id, chat_id, chat_label, sender, message_text, message_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )

    # Keep cache bounded to the last 35 days to limit local DB growth.
    cutoff = int((datetime.now() - timedelta(days=35)).timestamp())
    db.execute(
        "DELETE FROM telegram_messages_cache WHERE profile_id = ? AND message_ts < ?",
        (profile_id, cutoff),
    )
    db.commit()


def _chats_from_cache(profile_id: int, since_ts: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """
        SELECT c.chat_id,
               c.chat_label AS label,
               c.message_ts AS latest_ts,
               c.message_text AS preview
        FROM telegram_messages_cache c
        JOIN (
            SELECT chat_id, MAX(message_ts) AS max_ts
            FROM telegram_messages_cache
            WHERE profile_id = ? AND message_ts >= ?
            GROUP BY chat_id
        ) latest
          ON latest.chat_id = c.chat_id
         AND latest.max_ts = c.message_ts
        WHERE c.profile_id = ?
        ORDER BY c.message_ts DESC, c.chat_label ASC
        """,
        (profile_id, since_ts, profile_id),
    ).fetchall()
    return [dict(r) for r in rows]


def _messages_from_cache(profile_id: int, chat_id: int, since_ts: int) -> list[dict]:
    db = get_db()
    rows = db.execute(
        """
        SELECT sender, message_text, message_ts
        FROM telegram_messages_cache
        WHERE profile_id = ? AND chat_id = ? AND message_ts >= ?
        ORDER BY message_ts ASC, id ASC
        """,
        (profile_id, chat_id, since_ts),
    ).fetchall()

    messages: list[dict] = []
    for row in rows:
        ts = int(row["message_ts"])
        messages.append(
            {
                "sender": row["sender"],
                "text": row["message_text"],
                "timestamp": ts,
                "display_time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return messages


def _read_view_model() -> dict:
    # Profile is required to keep behavior consistent with other tabs.
    profile_id = _require_profile()

    selected_chat_id = request.args.get("chat_id", type=int)
    chats: list[dict] = []
    messages: list[dict] = []
    error: str | None = None
    since_ts = int((datetime.now() - timedelta(days=30)).timestamp())

    try:
        api = _create_telegram_api()
        updates = api.get_updates(limit=100)
        _cache_updates(profile_id, updates)
        chats = _chats_from_cache(profile_id, since_ts)

        if selected_chat_id is None and chats:
            selected_chat_id = int(chats[0]["chat_id"])
        if selected_chat_id is not None:
            messages = _messages_from_cache(profile_id, selected_chat_id, since_ts)
    except RuntimeError as exc:
        error = str(exc)

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
