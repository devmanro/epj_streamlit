import requests
import mimetypes
import time
from pathlib import Path
from typing import List, Tuple


# ============================================================
# ========== GREEN API WHATSAPP SENDER =======================
# ============================================================


def send_image_to_whatsapp_greenapi(
    image_path: str,
    chat_id: str,
    caption: str,
    id_instance: str,
    api_token: str,
) -> dict:
    url = (
        f"https://api.green-api.com"
        f"/waInstance{id_instance}"
        f"/sendFileByUpload"
        f"/{api_token}"
    )

    file_name = Path(image_path).name
    mime_type, _ = mimetypes.guess_type(image_path)
    mime_type = mime_type or "image/png"

    with open(image_path, "rb") as f:
        files = {"file": (file_name, f, mime_type)}
        data  = {"chatId": chat_id, "caption": caption}
        response = requests.post(url, data=data, files=files, timeout=60)

    try:
        return response.json()
    except Exception:
        return {"error": response.text}


def send_text_to_whatsapp_greenapi(
    message: str,
    chat_id: str,
    id_instance: str,
    api_token: str,
) -> dict:
    """Send a plain text message."""
    url = (
        f"https://api.green-api.com"
        f"/waInstance{id_instance}"
        f"/sendMessage"
        f"/{api_token}"
    )
    payload = {
        "chatId": chat_id,
        "message": message,
    }
    response = requests.post(url, json=payload, timeout=30)
    try:
        return response.json()
    except Exception:
        return {"error": response.text}


def send_images_to_whatsapp(
    image_paths: List[str],
    chat_id: str,
    id_instance: str,
    api_token: str,
    log_fn,
    delay_seconds: float = 1.5,
) -> Tuple[int, int]:
    """Send multiple images. Returns (success_count, fail_count)."""
    success, fail = 0, 0

    for i, img_path in enumerate(image_paths, start=1):
        caption = Path(img_path).stem.replace("__", " | ")
        try:
            result = send_image_to_whatsapp_greenapi(
                image_path=img_path,
                chat_id=chat_id,
                caption=caption,
                id_instance=id_instance,
                api_token=api_token,
            )

            if "idMessage" in result:
                log_fn(f"✅ Sent ({i}/{len(image_paths)}): {Path(img_path).name}")
                success += 1
            else:
                log_fn(f"⚠️ Failed ({i}/{len(image_paths)}): {Path(img_path).name} → {result}")
                fail += 1

        except Exception as exc:
            log_fn(f"❌ Error sending {Path(img_path).name}: {exc}")
            fail += 1

        if i < len(image_paths):
            time.sleep(delay_seconds)

    return success, fail


def get_whatsapp_groups_greenapi(
    id_instance: str,
    api_token: str,
) -> List[dict]:
    """Fetch all groups you are in."""
    url = f"https://api.green-api.com/waInstance{id_instance}/getChats/{api_token}"
    try:
        resp  = requests.get(url, timeout=30)
        chats = resp.json()
        return [
            {"id": c.get("id", ""), "name": c.get("name", c.get("id", ""))}
            for c in chats
            if str(c.get("id", "")).endswith("@g.us")
        ]
    except Exception:
        return []


# ============================================================
# ========== YOUR CREDENTIALS ================================
# ============================================================

ID_INSTANCE = "7107651033"          # ← paste yours
API_TOKEN   = "9d9983de28a546eeab96421d62ebac6d30e27257edb147589c" # ← paste yours

