"""Telegram connectivity helpers used by manual sync routes."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HEBREW_MATRES = {"ו", "י", "א", "ה"}


@dataclass(frozen=True)
class ClientMatch:
    client_id: int | None
    rate: float | None
    status: str


def load_bot_token(bot_name: str, token_file: Path | None = None) -> str:
    """Load bot token from ~/.telegram where lines look like 'botname = token'."""
    path = token_file or (Path.home() / ".telegram")
    if not path.exists():
        raise RuntimeError(f"Telegram token file was not found: {path}")

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, token = line.split("=", 1)
        if name.strip() == bot_name:
            value = token.strip()
            if not value:
                raise RuntimeError(f"Bot token for '{bot_name}' is empty in {path}")
            return value

    raise RuntimeError(f"Bot '{bot_name}' is missing in {path}")


class TelegramAPI:
    """Tiny Telegram Bot API wrapper using urllib from the standard library."""

    def __init__(self, token: str):
        self._base = f"https://api.telegram.org/bot{token}"

    def get_updates(self, limit: int = 100) -> list[dict[str, Any]]:
        payload = {"timeout": 0, "limit": limit}
        result = self._post("getUpdates", payload)
        return [item for item in result if isinstance(item, dict)]

    def send_message(self, chat_id: int, text: str) -> None:
        self._post("sendMessage", {"chat_id": chat_id, "text": text})

    def _post(self, method: str, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self._base}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Telegram API HTTP error: {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("Could not reach Telegram API.") from exc

        if not data.get("ok"):
            desc = data.get("description") or "Unknown Telegram API error"
            raise RuntimeError(str(desc))
        return data.get("result")


def unread_updates_for_profile(
    updates: list[dict[str, Any]], processed_update_ids: set[int]
) -> list[dict[str, Any]]:
    unread: list[dict[str, Any]] = []
    for upd in updates:
        try:
            uid = int(upd.get("update_id"))
        except (TypeError, ValueError):
            continue
        if uid in processed_update_ids:
            continue
        unread.append(upd)
    return unread


def list_chats_with_unread(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique chats that have unread text messages."""
    by_id: dict[int, dict[str, Any]] = {}
    for upd in updates:
        msg = upd.get("message")
        if not isinstance(msg, dict):
            continue
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat") or {}
        if not text:
            continue
        try:
            chat_id = int(chat.get("id"))
        except (TypeError, ValueError):
            continue

        row = by_id.get(chat_id)
        if row is None:
            row = {
                "chat_id": chat_id,
                "label": _chat_label(chat),
                "count": 0,
                "latest_ts": int(msg.get("date") or 0),
            }
            by_id[chat_id] = row
        row["count"] += 1
        row["latest_ts"] = max(row["latest_ts"], int(msg.get("date") or 0))

    return sorted(by_id.values(), key=lambda r: (r["latest_ts"], r["label"]), reverse=True)


def list_chats_from_updates(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique chats that appear in any text message update."""
    by_id: dict[int, dict[str, Any]] = {}
    for upd in updates:
        msg = upd.get("message")
        if not isinstance(msg, dict):
            continue
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        chat = msg.get("chat") or {}
        try:
            chat_id = int(chat.get("id"))
        except (TypeError, ValueError):
            continue

        row = by_id.get(chat_id)
        if row is None:
            row = {
                "chat_id": chat_id,
                "label": _chat_label(chat),
                "latest_ts": int(msg.get("date") or 0),
                "preview": text.splitlines()[0][:80],
            }
            by_id[chat_id] = row
        else:
            row["latest_ts"] = max(row["latest_ts"], int(msg.get("date") or 0))
            if int(msg.get("date") or 0) >= row["latest_ts"]:
                row["preview"] = text.splitlines()[0][:80]

    return sorted(by_id.values(), key=lambda r: (r["latest_ts"], r["label"]), reverse=True)


def messages_for_chat(updates: list[dict[str, Any]], chat_id: int) -> list[dict[str, Any]]:
    """Return chronologically sorted text messages for a selected chat."""
    items: list[dict[str, Any]] = []
    for upd in updates:
        msg = upd.get("message")
        if not isinstance(msg, dict):
            continue
        chat = msg.get("chat") or {}
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        try:
            msg_chat_id = int(chat.get("id"))
        except (TypeError, ValueError):
            continue
        if msg_chat_id != chat_id:
            continue

        sender = msg.get("from") or {}
        first = (sender.get("first_name") or "").strip()
        last = (sender.get("last_name") or "").strip()
        who = f"{first} {last}".strip() or (sender.get("username") or "Unknown")
        ts = int(msg.get("date") or 0)
        items.append(
            {
                "text": text,
                "timestamp": ts,
                "sender": who,
            }
        )

    items.sort(key=lambda row: row["timestamp"])
    return items


def match_client_name(raw_name: str, clients: list[dict[str, Any]]) -> ClientMatch:
    """Fuzzy match for names, with tolerance for Hebrew mater letters."""
    name = raw_name.strip()
    if not name:
        return ClientMatch(client_id=None, rate=None, status="empty")

    target = _normalize_text(name)
    target_he = _normalize_hebrew_lenient(name)

    exact = [c for c in clients if _normalize_text(c["name"]) == target]
    if len(exact) == 1:
        return ClientMatch(client_id=int(exact[0]["id"]), rate=float(exact[0]["rate"]), status="exact")
    if len(exact) > 1:
        return ClientMatch(client_id=None, rate=None, status="ambiguous")

    hebrew_loose = [c for c in clients if _normalize_hebrew_lenient(c["name"]) == target_he]
    if len(hebrew_loose) == 1:
        c = hebrew_loose[0]
        return ClientMatch(client_id=int(c["id"]), rate=float(c["rate"]), status="hebrew_loose")
    if len(hebrew_loose) > 1:
        return ClientMatch(client_id=None, rate=None, status="ambiguous")

    scored: list[tuple[float, dict[str, Any]]] = []
    for c in clients:
        n1 = _normalize_text(c["name"])
        n2 = _normalize_hebrew_lenient(c["name"])
        score = max(
            SequenceMatcher(None, target, n1).ratio(),
            SequenceMatcher(None, target_he, n2).ratio(),
        )
        scored.append((score, c))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return ClientMatch(client_id=None, rate=None, status="none")
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if best_score >= 0.84 and (best_score - second_score) >= 0.06:
        return ClientMatch(client_id=int(best["id"]), rate=float(best["rate"]), status="fuzzy")

    return ClientMatch(client_id=None, rate=None, status="none")


def _chat_label(chat: dict[str, Any]) -> str:
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


def _normalize_text(text: str) -> str:
    text = _strip_combining_marks(text).casefold().strip()
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[^0-9a-z\u0590-\u05FF ]+", "", text)


def _normalize_hebrew_lenient(text: str) -> str:
    normalized = _normalize_text(text)
    chars: list[str] = []
    for ch in normalized:
        if ch in HEBREW_MATRES:
            continue
        chars.append(ch)
    return "".join(chars)


def _strip_combining_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
