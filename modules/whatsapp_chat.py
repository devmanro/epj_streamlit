"""
whatsapp_client.py — Standalone WhatsApp Chat Tab Component for Streamlit
"""

import os
import time
import tempfile
from pathlib import Path

from tools.whatsapp import (
    get_whatsapp_chats_greenapi,
    get_whatsapp_chat_history_greenapi,
    send_text_to_whatsapp_greenapi,
    send_image_to_whatsapp_greenapi,
    receive_whatsapp_notification_greenapi,
    delete_whatsapp_notification_greenapi,
    parse_incoming_notification,
    normalize_message,
)

def render_whatsapp_chat_tab(id_instance: str, api_token: str, st):
    """
    Renders a complete WhatsApp Web-style chat interface as a Streamlit tab component.
    """
    

    # ──────────────────────────────────────────────────────────
    # SESSION STATE INITIALIZATION (Namespaced to avoid collisions)
    # ──────────────────────────────────────────────────────────
    if "wa_chats" not in st.session_state:
        st.session_state.wa_chats = []
    if "wa_messages" not in st.session_state:
        st.session_state.wa_messages = {}  # {chat_id: [messages]}
    if "wa_seen_message_ids" not in st.session_state:
        st.session_state.wa_seen_message_ids = set()
    if "wa_chat_id" not in st.session_state:
        st.session_state.wa_chat_id = ""
    if "wa_history_count" not in st.session_state:
        st.session_state.wa_history_count = 25

    st.header("💬 WhatsApp Web Client")

    if not (id_instance and api_token):
        st.warning("⚠️ Green API ID Instance and API Token are missing. Please configure your credentials.")
        return

    # ──────────────────────────────────────────────────────────
    # CONTROLS & CHAT SELECTOR BAR
    # ──────────────────────────────────────────────────────────
    col_sync, col_fetch, col_input = st.columns([1, 1, 2])
    
    with col_sync:
        if st.button("🔄 Sync Chats", use_container_width=True):
            try:
                with st.spinner("Fetching chats..."):
                    st.session_state.wa_chats = get_whatsapp_chats_greenapi(id_instance, api_token)
                st.success(f"Loaded {len(st.session_state.wa_chats)} chats")
            except Exception as e:
                st.error(f"Error: {e}")

    with col_fetch:
        if st.button("📥 Fetch New", use_container_width=True):
            loaded = 0
            try:
                for _ in range(50):
                    notification = receive_whatsapp_notification_greenapi(id_instance, api_token)
                    if not notification:
                        break
                    receipt_id = notification.get("receiptId")
                    parsed = parse_incoming_notification(notification)
                    if parsed:
                        norm = normalize_message(parsed)
                        msg_id = norm.get("id_message")
                        if not msg_id or msg_id not in st.session_state.wa_seen_message_ids:
                            st.session_state.wa_messages.setdefault(norm["chat_id"], []).append(norm)
                            if msg_id:
                                st.session_state.wa_seen_message_ids.add(msg_id)
                            loaded += 1
                    if receipt_id:
                        delete_whatsapp_notification_greenapi(str(receipt_id), id_instance, api_token)
                st.success(f"+{loaded} new messages")
            except Exception as e:
                st.error(f"Error: {e}")

    with col_input:
        chats_available = st.session_state.get("wa_chats", [])
        if chats_available:
            chat_options = {
                f"{'👥' if c['type'] == 'group' else '👤'} {c['name']}": c["id"]
                for c in chats_available
            }
            selected_label = st.selectbox("Select Chat", options=list(chat_options.keys()))
            selected_chat_id = chat_options[selected_label]
        else:
            selected_chat_id = st.text_input("Direct Chat ID", placeholder="120363xxx@g.us or 213xxx@c.us", value=st.session_state.get("wa_chat_id", ""))

    if selected_chat_id and selected_chat_id != st.session_state.get("wa_chat_id", ""):
        st.session_state.wa_chat_id = selected_chat_id
        st.session_state.wa_history_count = 25

    if not selected_chat_id:
        st.info("👈 Select or sync your chats to begin messaging.")
        return

    st.divider()

    # ──────────────────────────────────────────────────────────
    # CONVERSATION PANEL & HISTORY CONTROLS
    # ──────────────────────────────────────────────────────────
    head_col1, head_col2 = st.columns([2, 2])
    with head_col1:
        if st.button("⬆️ Load Older Messages", use_container_width=True):
            st.session_state.wa_history_count += 25
            st.session_state.pop(f"wa_history_{selected_chat_id}", None)
            st.rerun()
    with head_col2:
        if st.button("🔄 Refresh Conversation", use_container_width=True):
            st.session_state.pop(f"wa_history_{selected_chat_id}", None)
            st.rerun()

    # Load / Cache History
    history_key = f"wa_history_{selected_chat_id}"
    if history_key not in st.session_state:
        try:
            with st.spinner("Loading messages..."):
                raw_history = get_whatsapp_chat_history_greenapi(
                    selected_chat_id, id_instance, api_token, count=st.session_state.wa_history_count
                )
                st.session_state[history_key] = [normalize_message(m) for m in raw_history]
        except Exception as exc:
            st.error(f"Failed to fetch chat history: {exc}")
            st.session_state[history_key] = []

    # Merge History + Live Incoming Messages
    all_messages = list(st.session_state.get(history_key, []))
    live_messages = st.session_state.wa_messages.get(selected_chat_id, [])
    if live_messages:
        seen_ids = {m.get("id_message") for m in all_messages if m.get("id_message")}
        for m in live_messages:
            if m.get("id_message") not in seen_ids:
                all_messages.append(m)
        all_messages.sort(key=lambda x: x.get("timestamp") or 0)

    # Display Chat Window
    chat_container = st.container(height=450)
    with chat_container:
        if not all_messages:
            st.caption("No messages in this chat history.")
        else:
            for msg in all_messages:
                role = "user" if msg.get("from_me") else "assistant"
                sender_name = "You" if msg.get("from_me") else msg.get("sender_name", "Contact")
                with st.chat_message(role):
                    st.markdown(f"**{sender_name}**")
                    st.write(msg.get("text", ""))

    # ──────────────────────────────────────────────────────────
    # MESSAGE INPUT & ATTACHMENTS
    # ──────────────────────────────────────────────────────────
    st.divider()

    with st.expander("📷 Attach Image / File to Send"):
        uploaded_file = st.file_uploader("Choose an image", type=["png", "jpg", "jpeg", "webp", "gif"], key="chat_file_upload")
        file_caption = st.text_input("Caption for image", placeholder="Optional caption...", key="chat_file_caption")
        
        if st.button("📤 Send Attached Image", disabled=not uploaded_file):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_file_path = os.path.join(tmp_dir, uploaded_file.name)
                    with open(tmp_file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    with st.spinner("Sending image via Green API..."):
                        res = send_image_to_whatsapp_greenapi(
                            image_path=tmp_file_path,
                            chat_id=selected_chat_id,
                            caption=file_caption,
                            id_instance=id_instance,
                            api_token=api_token,
                        )

                    if isinstance(res, dict) and res.get("idMessage"):
                        st.success("✅ Image sent successfully!")
                        st.session_state.wa_messages.setdefault(selected_chat_id, []).append({
                            "chat_id": selected_chat_id,
                            "text": f"[Image] {file_caption}".strip(),
                            "from_me": True,
                            "timestamp": time.time(),
                            "id_message": res["idMessage"],
                            "sender_name": "You",
                        })
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Failed to send image: {res}")
            except Exception as e:
                st.error(f"Error sending file: {e}")

    # Text Input Prompt
    text_prompt = st.chat_input("Type a WhatsApp message...")
    if text_prompt:
        try:
            res = send_text_to_whatsapp_greenapi(text_prompt.strip(), selected_chat_id, id_instance, api_token)
            if isinstance(res, dict) and res.get("idMessage"):
                st.session_state.wa_messages.setdefault(selected_chat_id, []).append({
                    "chat_id": selected_chat_id,
                    "text": text_prompt.strip(),
                    "from_me": True,
                    "timestamp": time.time(),
                    "id_message": res["idMessage"],
                    "sender_name": "You",
                })
                st.rerun()
            else:
                st.error(f"Green API error: {res}")
        except Exception as exc:
            st.error(f"Failed to send message: {exc}")