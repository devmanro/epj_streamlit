"""
whatsapp.py — Green API integration helpers
"""

import os
import json
import requests

import mimetypes
import time
from pathlib import Path


try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

GREEN_API_BASE = "https://api.green-api.com"


GREEN_API_HOST_OVERRIDE = os.getenv("GREEN_API_HOST", "")

def _base_url(id_instance: str, api_token: str, method: str) -> str:
    if GREEN_API_HOST_OVERRIDE:
        host = GREEN_API_HOST_OVERRIDE.rstrip("/")
    else:
        host = f"https://{str(id_instance)[:4]}.api.greenapi.com"
    return f"{host}/waInstance{id_instance}/{method}/{api_token}"
    





# ──────────────────────────────────────────────────────────
# CONTACTS / GROUPS
# ──────────────────────────────────────────────────────────
def get_whatsapp_chats_greenapi(id_instance: str, api_token: str) -> list:
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
# CHAT HISTORY (for lazy-loaded conversation UI)
# ──────────────────────────────────────────────────────────
def get_whatsapp_chat_history_greenapi(
    chat_id: str, id_instance: str, api_token: str, count: int = 25
) -> list:
    """
    Fetches up to `count` of the most recent messages for a chat.
    Returns a chronologically ordered list (oldest first), normalized to:
    {
        'chat_id', 'text', 'from_me', 'timestamp', 'id_message', 'sender_name'
    }

    To "load older messages", call again with a larger `count` and
    merge/dedupe by id_message — Green API doesn't support cursor-based
    pagination, only a growing window of recent history.
    """
    url = _base_url(id_instance, api_token, "getChatHistory")
    payload = {"chatId": chat_id, "count": count}
    resp = requests.post(url, json=payload, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} error from getChatHistory: {resp.text}")

    text = resp.text.strip()
    if not text or text == "null":
        return []

    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from getChatHistory: {resp.text}")

    if not isinstance(data, list):
        return []

    messages = []
    for item in data:
        parsed = _parse_history_item(item, chat_id)
        if parsed:
            messages.append(parsed)

    # Green API returns newest-first; reverse to chronological order
    messages.reverse()
    return messages


def _parse_history_item(item: dict, chat_id: str) -> dict | None:
    msg_type = item.get("typeMessage", "")

    if msg_type == "textMessage":
        text = item.get("textMessage", "")
    elif msg_type == "extendedTextMessage":
        text = (
            item.get("extendedTextMessageData", {}).get("text")
            or item.get("caption", "")
            or ""
        )
    elif msg_type in ("imageMessage", "videoMessage", "documentMessage"):
        label = msg_type.replace("Message", "").capitalize()
        caption = item.get("caption", "")
        text = f"[{label}] {caption}".strip()
    else:
        text = item.get("textMessage") or f"[{msg_type or 'message'}]"

    is_outgoing = item.get("type") == "outgoing"

    return {
        "chat_id": chat_id,
        "text": text,
        "from_me": is_outgoing,
        "timestamp": item.get("timestamp"),
        "id_message": item.get("idMessage"),
        "sender_name": item.get("senderName") or ("You" if is_outgoing else "Contact"),
    }


# ──────────────────────────────────────────────────────────
# SENDING TEXT
# ──────────────────────────────────────────────────────────
def send_text_to_whatsapp_greenapi(message: str, chat_id: str, id_instance: str, api_token: str) -> dict:
    url = _base_url(id_instance, api_token, "sendMessage")
    payload = {"chatId": chat_id, "message": message}

    resp = requests.post(url, json=payload, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} error from sendMessage: {resp.text}")

    try:
        return resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from sendMessage: {resp.text}")


# ──────────────────────────────────────────────────────────
# SENDING IMAGES — with automatic fallback
# ──────────────────────────────────────────────────────────
def _ensure_reasonable_file_size(image_path: str, max_bytes: int = 5 * 1024 * 1024) -> str:
    """
    If the image is larger than max_bytes, compress it to JPEG to reduce
    the chance of the upload crashing the upstream Green API service.
    Returns the path to send (original, or a compressed copy).
    """
    size = os.path.getsize(image_path)
    if size <= max_bytes or not PIL_AVAILABLE:
        return image_path

    try:
        img = Image.open(image_path)
        compressed_path = os.path.splitext(image_path)[0] + "_compressed.jpg"
        img.convert("RGB").save(compressed_path, "JPEG", quality=85, optimize=True)
        return compressed_path
    except Exception:
        # If compression fails for any reason, just try sending the original
        return image_path


def _send_file_by_upload(image_path: str, chat_id: str, caption: str, id_instance: str, api_token: str) -> dict:
    url = _base_url(id_instance, api_token, "sendFileByUpload")
    file_name = os.path.basename(image_path)

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
        files = {"file": (file_name, f, mime_type)}
        data = {
            "chatId": chat_id,
            "caption": caption or "",
            "fileName": file_name,
        }
        resp = requests.post(url, data=data, files=files, timeout=90)

    if resp.status_code != 200:
        raise RuntimeError(
            f"{resp.status_code} error from sendFileByUpload for '{file_name}': {resp.text}"
        )

    try:
        return resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from sendFileByUpload: {resp.text}")


def _send_file_by_url_fallback(image_path: str, chat_id: str, caption: str, id_instance: str, api_token: str) -> dict:
    """
    Fallback path: upload file to Green API storage first, then send by URL.
    More reliable for larger files or when sendFileByUpload crashes upstream.
    """
    upload_url = _base_url(id_instance, api_token, "uploadFile")
    file_name = os.path.basename(image_path)

    with open(image_path, "rb") as f:
        file_bytes = f.read()

    upload_resp = requests.post(
        upload_url,
        data=file_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "GreenAPI-File-Name": file_name,
        },
        timeout=90,
    )

    if upload_resp.status_code != 200:
        raise RuntimeError(f"{upload_resp.status_code} error from uploadFile: {upload_resp.text}")

    try:
        upload_data = upload_resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from uploadFile: {upload_resp.text}")

    file_url = upload_data.get("urlFile")
    if not file_url:
        raise RuntimeError(f"uploadFile did not return a urlFile: {upload_data}")

    send_url = _base_url(id_instance, api_token, "sendFileByUrl")
    payload = {
        "chatId": chat_id,
        "urlFile": file_url,
        "fileName": file_name,
        "caption": caption or "",
    }
    send_resp = requests.post(send_url, json=payload, timeout=30)

    if send_resp.status_code != 200:
        raise RuntimeError(f"{send_resp.status_code} error from sendFileByUrl: {send_resp.text}")

    try:
        return send_resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response from sendFileByUrl: {send_resp.text}")






def send_image_to_whatsapp_greenapi(
    image_path: str,
    chat_id: str,
    caption: str,
    id_instance: str,
    api_token: str,
    max_retries: int = 2,
    retry_delay: float = 2.0,
) -> dict:
    """
    Send an image via Green API's sendFileByUpload endpoint.
    Simple, single-path implementation (no fragile fallback chain).
    """
    url = (
        f"https://media.green-api.com"
        f"/waInstance{id_instance}"
        f"/sendFileByUpload"
        f"/{api_token}"
    )

    file_name = Path(image_path).name
    mime_type, _ = mimetypes.guess_type(image_path)
    mime_type = mime_type or "image/png"

    last_error = None

    for attempt in range(1, max_retries + 2):  # 1 initial + retries
        try:
            with open(image_path, "rb") as f:
                files = {"file": (file_name, f, mime_type)}
                data = {"chatId": chat_id, "caption": caption}
                response = requests.post(url, data=data, files=files, timeout=60)

            if response.status_code == 200:
                try:
                    result = response.json()
                except Exception:
                    result = {"error": response.text}

                if isinstance(result, dict) and result.get("idMessage"):
                    return result
                else:
                    last_error = f"Unexpected response: {result}"
            else:
                last_error = f"{response.status_code} error from sendFileByUpload: {response.text[:300]}"

        except Exception as exc:
            last_error = f"Exception during upload: {exc}"

        if attempt <= max_retries:
            time.sleep(retry_delay)

    return {"error": last_error}
    

# ──────────────────────────────────────────────────────────
# RECEIVING NOTIFICATIONS (live incoming messages only)
# ──────────────────────────────────────────────────────────
def receive_whatsapp_notification_greenapi(id_instance: str, api_token: str):
    url = _base_url(id_instance, api_token, "receiveNotification")
    resp = requests.get(url, timeout=30)

    if resp.status_code == 204:
        return None

    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} error from receiveNotification: {resp.text}")

    text = resp.text.strip()
    if not text or text == "null":
        return None

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return None

    return data if data is not None else None


def delete_whatsapp_notification_greenapi(receipt_id: str, id_instance: str, api_token: str) -> bool:
    url = _base_url(id_instance, api_token, "deleteNotification") + f"/{receipt_id}"
    resp = requests.delete(url, timeout=30)

    if resp.status_code != 200:
        return False

    try:
        result = resp.json()
        return bool(result.get("result", False))
    except json.JSONDecodeError:
        return False


def parse_incoming_notification(notification: dict) -> dict | None:
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

def normalize_message(msg, is_from_me=False):
    """Normalizes incoming vs history message dictionaries for uniform rendering."""
    return {
        "chat_id": msg.get("chatId") or msg.get("chat_id"),
        "text": msg.get("textMessage") or msg.get("caption") or msg.get("text", ""),
        "from_me": msg.get("typeWebhook") == "outgoingMessageReceived" or msg.get("from_me", is_from_me),
        "timestamp": msg.get("timestamp") or 0,
        "id_message": msg.get("idMessage") or msg.get("id_message"),
        "sender_name": "You" if (msg.get("from_me", is_from_me)) else msg.get("senderName", msg.get("sender_name", "Contact")),
    }

# ============================================================
# ========== YOUR CREDENTIALS ================================
# ============================================================

ID_INSTANCE = "7107651033"          # ← paste yours
API_TOKEN   = "9d9983de28a546eeab96421d62ebac6d30e27257edb147589c" # ← paste yours

