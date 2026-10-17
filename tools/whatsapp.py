import mimetypes
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any

import requests

GREEN_API_BASE = "https://api.green-api.com"


def _api_url(method: str, id_instance: str, api_token: str) -> str:
    return f"{GREEN_API_BASE}/waInstance{id_instance}/{method}/{api_token}"


def _json_response(response: requests.Response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except ValueError:
        return {"error": response.text, "status_code": response.status_code}


def send_image_to_whatsapp_greenapi(
    image_path: str, chat_id: str, caption: str,
    id_instance: str, api_token: str,
) -> dict:
    url = _api_url("sendFileByUpload", id_instance, api_token)
    file_name = Path(image_path).name
    mime_type, _ = mimetypes.guess_type(image_path)
    with open(image_path, "rb") as file_obj:
        response = requests.post(
            url,
            data={"chatId": chat_id, "caption": caption},
            files={"file": (file_name, file_obj, mime_type or "application/octet-stream")},
            timeout=60,
        )
    response.raise_for_status()
    return _json_response(response)


def send_text_to_whatsapp_greenapi(
    message: str, chat_id: str, id_instance: str, api_token: str,
) -> dict:
    response = requests.post(
        _api_url("sendMessage", id_instance, api_token),
        json={"chatId": chat_id, "message": message},
        timeout=30,
    )
    response.raise_for_status()
    return _json_response(response)


def get_whatsapp_chats_greenapi(id_instance: str, api_token: str) -> List[dict]:
    """Return contacts and groups from Green API getChats."""
    response = requests.get(_api_url("getChats", id_instance, api_token), timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        return []
    chats = []
    for item in data:
        chat_id = item.get("id") or item.get("chatId") or ""
        if not chat_id:
            continue
        chats.append({
            "id": chat_id,
            "name": item.get("name") or item.get("contactName") or item.get("subject") or chat_id,
            "type": "group" if chat_id.endswith("@g.us") else "contact",
        })
    return sorted(chats, key=lambda c: (c["type"] != "contact", c["name"].lower()))


def get_whatsapp_groups_greenapi(id_instance: str, api_token: str) -> List[dict]:
    """Backward-compatible helper: return groups only."""
    return [c for c in get_whatsapp_chats_greenapi(id_instance, api_token)
            if c["type"] == "group"]


def get_whatsapp_group_metadata_greenapi(
    group_id: str, id_instance: str, api_token: str,
) -> dict:
    response = requests.post(
        _api_url("getGroupMetadata", id_instance, api_token),
        json={"groupJid": group_id}, timeout=30,
    )
    response.raise_for_status()
    return _json_response(response)


def receive_whatsapp_notification_greenapi(
    id_instance: str, api_token: str,
) -> dict | None:
    """Fetch one queued webhook notification. None means queue is empty."""
    response = requests.get(
        _api_url("receiveNotification", id_instance, api_token), timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) and data else None


def delete_whatsapp_notification_greenapi(
    receipt_id: str, id_instance: str, api_token: str,
) -> dict:
    response = requests.delete(
        _api_url(f"deleteNotification/{receipt_id}", id_instance, api_token),
        timeout=30,
    )
    response.raise_for_status()
    return _json_response(response)


def parse_incoming_notification(notification: dict) -> dict | None:
    """Normalize common incoming text notifications into a small chat message."""
    body = notification.get("body") or {}
    webhook_type = body.get("typeWebhook", "")
    if webhook_type not in ("incomingMessageReceived", "incomingMessageReceivedNew"):
        return None

    sender = body.get("senderData") or {}
    chat_id = sender.get("chatId") or ""
    if not chat_id:
        return None

    message_data = body.get("messageData") or {}
    message_type = message_data.get("typeMessage", "unknown")
    text = ""
    if message_type == "textMessage":
        text = (message_data.get("textMessageData") or {}).get("textMessage", "")
    elif message_type == "extendedTextMessage":
        text = (message_data.get("extendedTextMessageData") or {}).get("text", "")
    elif message_type == "quotedMessage":
        quoted = message_data.get("quotedMessage") or {}
        text = (quoted.get("stanzaId", "") + " " +
                (quoted.get("textMessage", "") or "")).strip()
    else:
        text = f"[{message_type or 'non-text message'}]"

    timestamp = body.get("timestamp")
    return {
        "chat_id": chat_id,
        "text": text or "[Empty message]",
        "from_me": False,
        "timestamp": timestamp,
        "id_message": (body.get("idMessage") or ""),
        "sender_name": sender.get("senderName") or sender.get("chatName") or chat_id,
        "message_type": message_type,
    }


def send_images_to_whatsapp(
    image_paths: List[str], chat_id: str, id_instance: str, api_token: str,
    log_fn, delay_seconds: float = 1.5,
) -> Tuple[int, int]:
    success = fail = 0
    for i, image_path in enumerate(image_paths, start=1):
        caption = Path(image_path).stem.replace("__", " | ")
        try:
            result = send_image_to_whatsapp_greenapi(
                image_path, chat_id, caption, id_instance, api_token
            )
            if result.get("idMessage"):
                log_fn(f"✅ Sent ({i}/{len(image_paths)}): {Path(image_path).name}")
                success += 1
            else:
                log_fn(f"⚠️ Failed ({i}/{len(image_paths)}): {Path(image_path).name} → {result}")
                fail += 1
        except Exception as exc:
            log_fn(f"❌ Error sending {Path(image_path).name}: {exc}")
            fail += 1
        if i < len(image_paths):
            time.sleep(delay_seconds)
    return success, fail







# ============================================================
# ========== YOUR CREDENTIALS ================================
# ============================================================

ID_INSTANCE = "7107651033"          # ← paste yours
API_TOKEN   = "9d9983de28a546eeab96421d62ebac6d30e27257edb147589c" # ← paste yours

