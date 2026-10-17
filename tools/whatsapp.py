"""
whatsapp.py — Green API integration helpers
"""

import os
import json
import requests

GREEN_API_BASE = "https://api.green-api.com"
GREEN_MEDIA_BASE = "https://media.green-api.com"  # some instances route media here


def _base_url(id_instance: str, api_token: str, method: str, media: bool = False) -> str:
    root = GREEN_MEDIA_BASE if media else GREEN_API_BASE
    return f"{root}/waInstance{id_instance}/{method}/{api_token}"


# ──────────────────────────────────────────────────────────
# CONTACTS / GROUPS
# ──────────────────────────────────────────────────────────
def get_whatsapp_chats_greenapi(id_instance: str, api_token: str) -> list:
    """
    Returns a unified list of contacts and groups:
    [{'id': '...@c.us' or '...@g.us', 'name': '...', 'type': 'contact'|'group'}]
    """
    url = _base_url(id_instance, api_token, "getContacts")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return []

    chats = []
    for item in data:
        chat_id = item.get("id", "")
        if not chat_id:
            continue
        is_group = chat_id.endswith("@g.us")
        name = item.get("name") or item.get("contactName") or chat_id.split("@")[0]
        chats.append({
            "id": chat_id,
            "name": name,
            "type": "group" if is_group else "contact",
        })

    # De-duplicate by id, keep groups first for convenience
    seen = set()
    unique_chats = []
    for c in sorted(chats, key=lambda x: x["type"] != "group"):
        if c["id"] not in seen:
            seen.add(c["id"])
            unique_chats.append(c)

    return unique_chats


def get_whatsapp_group_metadata_greenapi(group_id: str, id_instance: str, api_token: str) -> dict:
    url = _base_url(id_instance, api_token, "getGroupData")
    resp = requests.post(url, json={"groupId": group_id}, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except json.JSONDecodeError:
        return {}


# ──────────────────────────────────────────────────────────
# SENDING
# ──────────────────────────────────────────────────────────
def send_text_to_whatsapp_greenapi(message: str, chat_id: str, id_instance: str, api_token: str) -> dict:
    url = _base_url(id_instance, api_token, "sendMessage")
    payload = {"chatId": chat_id, "message": message}

    resp = requests.post(url, json=payload, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(
            f"{resp.status_code} error from sendMessage: {resp.text}"
        )

    try:
        return resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from sendMessage: {resp.text}")


def send_image_to_whatsapp_greenapi(
    image_path: str,
    chat_id: str,
    caption: str,
    id_instance: str,
    api_token: str,
) -> dict:
    """
    Sends an image via Green API's sendFileByUpload endpoint.
    Uses proper multipart/form-data — do NOT set a custom Content-Type header,
    requests will set the correct multipart boundary automatically.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    url = _base_url(id_instance, api_token, "sendFileByUpload")
    file_name = os.path.basename(image_path)

    # Guess mime type
    ext = os.path.splitext(file_name)[1].lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(ext, "application/octet-stream")

    with open(image_path, "rb") as f:
        files = {
            "file": (file_name, f, mime_type),
        }
        data = {
            "chatId": chat_id,
            "caption": caption or "",
            "fileName": file_name,   # Green API requires this explicitly
        }

        resp = requests.post(url, data=data, files=files, timeout=60)

    if resp.status_code != 200:
        # Surface the ACTUAL error body from Green API instead of a generic 500
        raise RuntimeError(
            f"{resp.status_code} error from sendFileByUpload for '{file_name}': {resp.text}"
        )

    try:
        return resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Non-JSON response from sendFileByUpload: {resp.text}"
        )


# ──────────────────────────────────────────────────────────
# RECEIVING NOTIFICATIONS
# ──────────────────────────────────────────────────────────
def receive_whatsapp_notification_greenapi(id_instance: str, api_token: str):
    """
    Polls the notification queue. Returns None if there is nothing to read.
    Handles empty-body / literal 'null' responses which previously caused
    'Expecting value: line 1 column 1 (char 0)' JSON decode errors.
    """
    url = _base_url(id_instance, api_token, "receiveNotification")
    resp = requests.get(url, timeout=30)

    if resp.status_code == 204:
        return None

    if resp.status_code != 200:
        raise RuntimeError(
            f"{resp.status_code} error from receiveNotification: {resp.text}"
        )

    text = resp.text.strip()
    if not text or text == "null":
        return None

    try:
        data = resp.json()
    except json.JSONDecodeError:
        # Defensive fallback — treat malformed body as "nothing to read"
        return None

    if data is None:
        return None

    return data


def delete_whatsapp_notification_greenapi(receipt_id: str, id_instance: str, api_token: str) -> bool:
    url = _base_url(id_instance, api_token, "deleteNotification") + f"/{receipt_id}"
    resp = requests.delete(url, timeout=30)

    if resp.status_code != 200:
        # Don't crash the polling loop over a failed delete — just report it
        return False

    try:
        result = resp.json()
        return bool(result.get("result", False))
    except json.JSONDecodeError:
        return False


# ──────────────────────────────────────────────────────────
# PARSING INCOMING NOTIFICATIONS
# ──────────────────────────────────────────────────────────
def parse_incoming_notification(notification: dict) -> dict | None:
    """
    Normalizes a Green API webhook/notification body into:
    {
        'chat_id': str,
        'text': str,
        'from_me': bool,
        'timestamp': int | None,
        'id_message': str | None,
        'sender_name': str,
    }
    Returns None if the notification isn't a message we can display
    (e.g. status updates, delivery receipts, etc.)
    """
    if not notification:
        return None

    body = notification.get("body", {})
    type_webhook = body.get("typeWebhook")

    if type_webhook not in ("incomingMessageReceived", "outgoingMessageReceived", "outgoingAPIMessageReceived"):
        return None

    sender_data = body.get("senderData", {})
    message_data = body.get("messageData", {})

    chat_id = sender_data.get("chatId")
    if not chat_id:
        return None

    msg_type = message_data.get("typeMessage", "")

    text = ""
    if msg_type == "textMessage":
        text = message_data.get("textMessageData", {}).get("textMessage", "")
    elif msg_type == "extendedTextMessage":
        text = message_data.get("extendedTextMessageData", {}).get("text", "")
    elif msg_type == "imageMessage":
        caption = message_data.get("fileMessageData", {}).get("caption", "")
        text = f"[Image] {caption}".strip()
    else:
        text = f"[{msg_type}]"

    return {
        "chat_id": chat_id,
        "text": text,
        "from_me": type_webhook in ("outgoingMessageReceived", "outgoingAPIMessageReceived"),
        "timestamp": body.get("timestamp"),
        "id_message": body.get("idMessage"),
        "sender_name": sender_data.get("senderName") or sender_data.get("sender", "Contact"),
    }





# ============================================================
# ========== YOUR CREDENTIALS ================================
# ============================================================

ID_INSTANCE = "7107651033"          # ← paste yours
API_TOKEN   = "9d9983de28a546eeab96421d62ebac6d30e27257edb147589c" # ← paste yours

