import os
import time
import logging
import traceback
import io
import zipfile
import tempfile
import streamlit as st
from pathlib import Path
from typing import List, Tuple
import openpyxl
from openpyxl.utils import get_column_letter
import pandas as pd
import numpy as np
#from tools.whatsapp import send_image_to_whatsapp_greenapi ,get_whatsapp_group_metadata_greenapi

from tools.whatsapp import (
    get_whatsapp_chats_greenapi, send_text_to_whatsapp_greenapi,
    send_image_to_whatsapp_greenapi, receive_whatsapp_notification_greenapi,
    delete_whatsapp_notification_greenapi, parse_incoming_notification,
    get_whatsapp_chat_history_greenapi,
)

from tools.tools import ensure_directories
from assets.constants.constants import UPLOAD_DIR, DB_PATH, PATH_DEBRQ, UPLOAD_DIR ,API_TOKEN,ID_INSTANCE

import concurrent.futures
import threading
import time
import queue

# --- Thread-safe log queue ---
log_queue = queue.Queue()

    # ── Constants ─────────────────────────────────────────────────────────
FILE_TIMEOUT_SECONDS = 30  # seconds before skipping a file
# --- Define this helper OUTSIDE or AT THE TOP of your app script ---
def process_single_file_wrapper(result_dict, tmp_path, wb_name, output_folder, last_table_tail_cols, log_fn):
    import traceback
    try:
        import openpyxl
        wb = openpyxl.load_workbook(tmp_path, data_only=True)
        sheet = wb.worksheets[0]
        imgs = get_recap(
            sheet=sheet,
            workbook_name=wb_name,
            output_folder=output_folder,
            last_table_tail_cols=int(last_table_tail_cols),
            log_fn=threadsafe_log,  # ✅ thread-safe, no Streamlit context needed

        )
        wb.close()
        result_dict["images"] = imgs
        result_dict["success"] = True
    except Exception as e:
        # Capture FULL traceback, not just the message
        result_dict["error"] = traceback.format_exc()
        result_dict["success"] = False


def threadsafe_log(msg: str):
    """Put log messages into queue instead of calling Streamlit directly."""
    log_queue.put(msg)

def drain_log_queue(log_container):
    """Call this from the main thread to flush pending log messages."""
    while not log_queue.empty():
        try:
            msg = log_queue.get_nowait()
            log_container.write(f"  📝 {msg}")
        except queue.Empty:
            break



# Import your specific scripts
# from modules.genBorderaux import generate_brd

# from modules.genPv import generate_daily_pv
from modules.utilities import utilities
from modules.staff_manager import staff_m

from modules.Dashboard import Dashboard
from modules.landingManager import render_global_manager
from modules.shipManager import render_single_file_manager
from modules.portMap import show_map  # Import the function

from modules.Generate_Pages import page_generate_sheets

from modules.M_tracker import manifest_tracker
from modules.get_recap import (
    detect_horizontal_tables,
    export_range_as_image,
    get_used_bounds,
    get_visible_rows,
    get_visible_cols,
    find_last_bordered_table,
    get_recap,
    get_whatsapp_groups_greenapi,
    send_images_to_whatsapp,
)

# from modules.genPvs import generate_pv

# st.set_page_config(page_title="Djendjen Logistics Portal", layout="wide")
def show_main_app():
    # --- CSS for styling ---
    st.markdown(
        """
        <style>
        .main { background-color: #f9f7f9; }
        .stButton>button { width: 100%; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    # --- Sidebar Navigation ---
    st.sidebar.title("🚢 Port Operations")
    menu = [
        "Dashboard",
        "Manifest Tracker",
        "State Manager",
        "Port Map",
        "Workforce Tracking",
        "Logistics Tools",
        "Templates",
        "Send_Recaps",
        "Generate_Sheets",
    ]
    # choice = st.sidebar.radio("Navigation", menu)
    choice = st.sidebar.radio("Navigation", menu, index=2)
    
    # # --- Helper: File Management Logic ---
    # if not os.path.exists(UPLOAD_DIR):
    #     os.makedirs(UPLOAD_DIR)
    
    if "active_download" not in st.session_state:
        # Will store a dict: {"path": ..., "type": ...}
        st.session_state.active_download = None
    
    
    # Callback to clear state
    def clear_downloads():
        st.session_state.active_download = None
    
    
    # ---------------------------------------------------------
    # 0. DASHBOARD
    # ---------------------------------------------------------
    if choice == "Dashboard":
        # Pass UPLOAD_DIR if your dashboard needs to scan the files for stats
        ensure_directories()
        # Dashboard()
    
    # Add to your navigation choices
    if choice == "Manifest Tracker":
        manifest_tracker(UPLOAD_DIR)
    
    # ---------------------------------------------------------
    # 1 & 5. FILE MANAGER & GLOBAL DATABASE
    # ---------------------------------------------------------
    if choice == "State Manager":
        st.header("⚓ State Manager")
    
        # Initialize session state for downloads if not exists
        if "active_download" not in st.session_state:
            st.session_state.active_download = None
    
        # Create the Tabs
        tab1, tab2 = st.tabs(["🌍 Global Loading Manager", "📂 Single File Manager"])
    
        # TAB 1: Global View (The new feature)
        with tab1:
            # Call the function from Part 1
            # Make sure render_global_manager is defined or imported
            render_global_manager()
    
        # TAB 2: Single File Manager (The original feature)
        with tab2:
            # Call the function from Part 2
            # We pass your existing helper functions to keep it modular
            render_single_file_manager(clear_downloads)
    
    
    # ---------------------------------------------------------
    # 6. PORT MAP MODULE (Interactive Overlay)
    # ---------------------------------------------------------
    elif choice == "Port Map":
        st.header("📍 Port Djendjen Interactive Map")
        show_map()  # Call the function
    
        # # This uses a scatter plot over your image to simulate "positions"
        # import plotly.express as px
        # from PIL import Image
    
        # img = Image.open("assets/map/port_map.png")
    
        # # Placeholder data for ship positions (You would store this in a JSON/CSV)
        # map_data = pd.DataFrame({
        #     'x': [100, 250, 400],
        #     'y': [200, 150, 300],
        #     'Ship': ['Ship A', 'Ship B', 'Ship C'],
        #     'Client': ['CMA CGM', 'MSC', 'Maersk'],
        #     'Type': ['Containers', 'General Cargo', 'Bulk']
        # })
    
        # fig = px.scatter(map_data, x='x', y='y', text='Ship', color='Client',
        #                  hover_data=['Type'])
        # fig.update_layout(images=[dict(source=img, xref="x", yref="y", x=0, y=500,
        #                                sizex=1000, sizey=500, sizing="stretch", layer="below")])
        # fig.update_xaxes(showgrid=False, range=[0, 1000])
        # fig.update_yaxes(showgrid=False, range=[0, 500])
    
        # st.plotly_chart(fig, width='stretch')
    
        st.write("### Manage Positions")
        # Add form here to update x, y coordinates for specific ships
    
    # ---------------------------------------------------------
    # 8. LOGISTICS TOOLS
    # ---------------------------------------------------------
    elif choice == "Logistics Tools":
        st.header("🧮 Calculateur de Surfaces Portuaires 🚢")
        utilities(st)
    
    # ---------------------------------------------------------
    # 9. WORKFORCE TRACKING
    # ---------------------------------------------------------
    elif choice == "Workforce Tracking":
        staff_m()
    # ---------------------------------------------------------
    # 10. Send_Recaps
    # ---------------------------------------------------------
    # Assumes 'choice' is already defined by your sidebar/menu
    
    # ==========================================================
    # ========== STREAMLIT UI ==================================
    # ==========================================================
    elif choice == "Generate_Sheets":
        page_generate_sheets()     # ← add this line
    
    elif choice == "Send_Recaps":
        st.header("📤 Send Recaps via WhatsApp")
    
        # ============================================================
        # 1. FILE INPUTS
        # ============================================================
        uploaded_files = st.file_uploader(
            "Select Excel Files",
            type=["xlsx", "xlsm", "xls"],
            accept_multiple_files=True
        )
        output_folder = st.text_input("Output Folder Path", value="/tmp/output")
        last_table_tail_cols = st.number_input(
            "Ending columns for last table tail", value=6, min_value=1
        )
        file_timeout = st.number_input(
            "⏱️ Per-file timeout (seconds)", value=30, min_value=5
        )
    
        st.divider()
    
        # ============================================================
        # 2. WHATSAPP SETTINGS
        # ============================================================
        st.subheader("📱 WhatsApp Settings")
    
        # wa_col1, wa_col2 = st.columns(2)
        
        # with wa_col1:
        #     id_instance = ID_INSTANCE
        #     # st.text_input(
        #     #     "Green API — ID Instance",
        #     #     value=st.session_state.get(API_TOKEN,ID_INSTANCE, ""),
        #     #     placeholder="e.g. 1101234567",
        #     #     help="Found in your Green API dashboard",
        #     # )
    
        # with wa_col2:
        #     api_token=API_TOKEN
        #     # = st.text_input(
        #     #     "Green API — API Token",
        #     #     value=st.session_state.get("wa_api_token", ""),
        #     #     placeholder="e.g. abc123xyz...",
        #     #     type="password",
        #     #     help="Found in your Green API dashboard",
        #     # )
    
              # ============================================================
               # ============================================================
        # SETUP
        # ============================================================
        id_instance = ID_INSTANCE
        api_token = API_TOKEN

        if id_instance:
            st.session_state.wa_id_instance = id_instance
        if api_token:
            st.session_state.wa_api_token = api_token

        if "wa_chats" not in st.session_state:
            st.session_state.wa_chats = []
        if "wa_messages" not in st.session_state:
            st.session_state.wa_messages = {}  # chat_id -> list of live-polled messages
        if "wa_seen_message_ids" not in st.session_state:
            st.session_state.wa_seen_message_ids = set()
        if "processing" not in st.session_state:
            st.session_state.processing = False
        if "cancel_requested" not in st.session_state:
            st.session_state.cancel_requested = False
        if "wa_history_count" not in st.session_state:
            st.session_state.wa_history_count = 25

        # ============================================================
        # LAYOUT: LEFT = Controls / Buttons, RIGHT = Chat + Processing
        # ============================================================
        left_col, right_col = st.columns([1, 2])

        # ------------------------------------------------------------
        # LEFT COLUMN — CONTROLS
        # ------------------------------------------------------------
        with left_col:
            st.markdown("### ⚙️ Controls")

            fetch_chats = st.button(
                "🔄 Load contacts and groups",
                disabled=not (id_instance and api_token),
                use_container_width=True,
            )
            load_incoming = st.button(
                "📥 Load incoming messages",
                disabled=not (id_instance and api_token),
                use_container_width=True,
            )

            if fetch_chats:
                try:
                    with st.spinner("Loading WhatsApp contacts and groups..."):
                        st.session_state.wa_chats = get_whatsapp_chats_greenapi(id_instance, api_token)
                    if st.session_state.wa_chats:
                        st.success(f"Loaded {len(st.session_state.wa_chats)} chats.")
                    else:
                        st.warning("No chats returned. Check that your Green API instance is connected.")
                except Exception as exc:
                    st.error(f"Could not load chats: {exc}")

            if load_incoming:
                loaded_count = 0
                try:
                    with st.spinner("Checking Green API notification queue..."):
                        for _ in range(100):  # cap each click so the UI does not hang
                            notification = receive_whatsapp_notification_greenapi(id_instance, api_token)
                            if not notification:
                                break
                            receipt_id = notification.get("receiptId")
                            parsed = parse_incoming_notification(notification)
                            if parsed:
                                message_id = parsed.get("id_message")
                                if not message_id or message_id not in st.session_state.wa_seen_message_ids:
                                    st.session_state.wa_messages.setdefault(parsed["chat_id"], []).append(parsed)
                                    if message_id:
                                        st.session_state.wa_seen_message_ids.add(message_id)
                                    loaded_count += 1
                            if receipt_id:
                                delete_whatsapp_notification_greenapi(str(receipt_id), id_instance, api_token)
                            else:
                                break
                    st.success(f"Loaded {loaded_count} incoming message(s).")
                except Exception as exc:
                    st.error(f"Could not load incoming messages: {exc}")

            st.divider()

            send_to_whatsapp = st.checkbox(
                "📨 Send processed images to selected chat",
                value=st.session_state.get("send_to_whatsapp", False),
            )
            st.session_state.send_to_whatsapp = send_to_whatsapp

            wa_delay = st.slider(
                "⏳ Delay between images (s)",
                min_value=1.0,
                max_value=10.0,
                value=2.0,
                step=0.5,
                disabled=not send_to_whatsapp,
                help="Prevents WhatsApp rate limiting / spam detection",
            )

            st.divider()

            start_clicked = st.button(
                "🚀 Start Processing",
                use_container_width=True,
                disabled=st.session_state.processing,
            )
            stop_clicked = st.button(
                "🛑 Stop / Cancel",
                use_container_width=True,
                disabled=not st.session_state.processing,
            )

            if start_clicked:
                st.session_state.processing = True
                st.session_state.cancel_requested = False
                st.session_state.pop("zip_buffer", None)
                st.rerun()

            if stop_clicked:
                st.session_state.cancel_requested = True
                st.warning("Stop signal sent. Will stop after current file attempt.")

            st.divider()

            if st.session_state.get("zip_buffer"):
                st.download_button(
                    label="⬇️ Download All Images (ZIP)",
                    data=st.session_state.zip_buffer,
                    file_name="exported_tables.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        # ------------------------------------------------------------
        # RIGHT COLUMN — CHAT (contact on top, processing, conversation)
        # ------------------------------------------------------------
        with right_col:
            st.subheader("💬 WhatsApp Chat")

            # ── Contact / Group selector (TOP) ───────────────────
            chats = st.session_state.wa_chats
            chat_options = {
                f"{'👥' if chat['type'] == 'group' else '👤'} {chat['name']} — {chat['id']}": chat["id"]
                for chat in chats
            }

            if chat_options:
                labels = list(chat_options.keys())
                previous_id = st.session_state.get("wa_chat_id", "")
                default_index = next((i for i, label in enumerate(labels)
                                      if chat_options[label] == previous_id), 0)
                selected_label = st.selectbox("Chat", labels, index=default_index)
                selected_chat_id = chat_options[selected_label]

                # Reset pagination window + cache when switching chats
                if selected_chat_id != st.session_state.get("wa_chat_id"):
                    st.session_state.wa_history_count = 25
                    st.session_state.pop(f"wa_history_{selected_chat_id}", None)

                st.session_state.wa_chat_id = selected_chat_id
            else:
                selected_chat_id = st.text_input(
                    "Contact or group chat ID",
                    value=st.session_state.get("wa_chat_id", ""),
                    placeholder="213XXXXXXXXX@c.us or 1203XXXXXXXXX@g.us",
                    help="Use a contact ID ending in @c.us or a group ID ending in @g.us.",
                ).strip()
                if selected_chat_id:
                    st.session_state.wa_chat_id = selected_chat_id

            # Validation warning
            if send_to_whatsapp:
                missing = []
                if not id_instance:
                    missing.append("ID Instance")
                if not api_token:
                    missing.append("API Token")
                if not selected_chat_id:
                    missing.append("Chat ID / Group")

                if missing:
                    st.warning(f"⚠️ Missing WhatsApp fields: {', '.join(missing)}")
                else:
                    st.info(f"📲 Images will be sent to:\n\n`{selected_chat_id}`")

            st.divider()

            # ── IMAGE PROCESSING (upper area of messages) ───────
            st.markdown("### 🖼️ Image Processing")
            processing_placeholder = st.container()

            st.divider()

            # ── CONVERSATION (bubble-style, lazy-loaded) ────────
            st.markdown("#### Conversation")

            if selected_chat_id and id_instance and api_token:
                history_cache_key = f"wa_history_{selected_chat_id}"

                load_older_col, refresh_col = st.columns(2)
                with load_older_col:
                    if st.button("⬆️ Load older messages", use_container_width=True):
                        st.session_state.wa_history_count += 25
                        st.session_state.pop(history_cache_key, None)

                with refresh_col:
                    if st.button("🔄 Refresh conversation", use_container_width=True):
                        st.session_state.pop(history_cache_key, None)

                if history_cache_key not in st.session_state:
                    try:
                        with st.spinner("Loading conversation..."):
                            history = get_whatsapp_chat_history_greenapi(
                                selected_chat_id, id_instance, api_token,
                                count=st.session_state.wa_history_count,
                            )
                        st.session_state[history_cache_key] = history
                    except Exception as exc:
                        st.error(f"Could not load chat history: {exc}")
                        st.session_state[history_cache_key] = []

                chat_messages = list(st.session_state.get(history_cache_key, []))

                # Merge in any live messages captured via notification polling
                live_messages = st.session_state.wa_messages.get(selected_chat_id, [])
                if live_messages:
                    seen_ids = {m.get("id_message") for m in chat_messages if m.get("id_message")}
                    for m in live_messages:
                        if m.get("id_message") not in seen_ids:
                            chat_messages.append(m)
                    chat_messages.sort(key=lambda m: m.get("timestamp") or 0)

                # ── Chat bubble rendering ──────────────────────
                chat_box = st.container(height=400)
                with chat_box:
                    if not chat_messages:
                        st.info("No messages yet for this chat.")
                    else:
                        for message in chat_messages:
                            role = "user" if message.get("from_me") else "assistant"
                            name = "You" if message.get("from_me") else message.get("sender_name", "Contact")
                            with st.chat_message(role):
                                st.markdown(f"**{name}**")
                                st.write(message.get("text", ""))

                # Auto-scroll to bottom (smooth)
                st.markdown(
                    """
                    <script>
                        var chatBoxes = window.parent.document.querySelectorAll(
                            'div[data-testid="stVerticalBlockBorderWrapper"]'
                        );
                        if (chatBoxes.length > 0) {
                            var lastBox = chatBoxes[chatBoxes.length - 1];
                            lastBox.scrollTo({top: lastBox.scrollHeight, behavior: 'smooth'});
                        }
                    </script>
                    """,
                    unsafe_allow_html=True,
                )

                # ── Message input (chat-bot style) ─────────────
                text_to_send = st.chat_input("Type a WhatsApp message...")
                if text_to_send:
                    try:
                        result = send_text_to_whatsapp_greenapi(
                            text_to_send.strip(), selected_chat_id, id_instance, api_token
                        )
                        if result.get("idMessage"):
                            st.session_state.wa_messages.setdefault(selected_chat_id, []).append({
                                "chat_id": selected_chat_id,
                                "text": text_to_send.strip(),
                                "from_me": True,
                                "timestamp": None,
                                "id_message": result["idMessage"],
                                "sender_name": "You",
                            })
                            st.rerun()
                        else:
                            st.error(f"Green API did not confirm the message: {result}")
                    except Exception as exc:
                        st.error(f"Message sending failed: {exc}")
            else:
                st.info("Select or enter a chat above to start messaging.")

        # ============================================================
        # 4. PROCESSING LOOP (renders inside the chat area's upper section)
        # ============================================================
        if st.session_state.processing:
            with processing_placeholder:
                status_text  = st.empty()
                progress_bar = st.progress(0)
                log_container = st.container()

                Path(output_folder).mkdir(parents=True, exist_ok=True)
                all_images      = []
                timed_out_files = []
                failed_files    = []

                try:
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        total = len(uploaded_files)

                        if total == 0:
                            st.warning("No files uploaded!")
                            st.session_state.processing = False
                            st.stop()

                        # ── Per-file loop ──────────────────────────
                        for idx, up_file in enumerate(uploaded_files):
                            if st.session_state.cancel_requested:
                                log_container.warning("🛑 Cancelled by user.")
                                break

                            wb_name = Path(up_file.name).stem
                            status_text.text(
                                f"Processing {idx+1}/{total}: {wb_name}..."
                            )
                            log_container.write(
                                f"---\n📂 Starting: **{wb_name}**"
                            )

                            # Save to temp disk
                            tmp_path = os.path.join(tmp_dir, up_file.name)
                            with open(tmp_path, "wb") as f:
                                f.write(up_file.getbuffer())

                            file_size = os.path.getsize(tmp_path)
                            log_container.write(
                                f"  💾 Saved: {file_size} bytes → `{tmp_path}`"
                            )

                            if file_size == 0:
                                log_container.error("  ❌ Empty file! Skipping.")
                                failed_files.append((wb_name, "Empty file after save"))
                                continue

                            # Run in thread with timeout
                            res_dict = {"images": [], "success": False, "error": None}

                            thread = threading.Thread(
                                target=process_single_file_wrapper,
                                args=(
                                    res_dict,
                                    tmp_path,
                                    wb_name,
                                    output_folder,
                                    last_table_tail_cols,
                                    lambda msg: log_container.write(f"  📝 {msg}"),
                                ),
                                daemon=True,
                            )

                            start_time = time.time()
                            thread.start()
                            thread.join(timeout=float(file_timeout))
                            elapsed = time.time() - start_time

                            if thread.is_alive():
                                log_container.warning(
                                    f"  ⏱️ TIMEOUT after {elapsed:.1f}s "
                                    f"(limit: {file_timeout}s) — **{wb_name}** skipped"
                                )
                                timed_out_files.append(wb_name)

                            else:
                                log_container.write(
                                    f"  ⏱️ Completed in {elapsed:.1f}s"
                                )

                                if res_dict["success"]:
                                    imgs = res_dict.get("images", [])
                                    valid_imgs = []

                                    for img_path in imgs:
                                        if os.path.exists(img_path):
                                            valid_imgs.append(img_path)
                                        else:
                                            log_container.warning(
                                                f"  ⚠️ Missing: `{img_path}`"
                                            )

                                    log_container.write(
                                        f"  ✅ Success — {len(valid_imgs)} image(s)"
                                    )
                                    all_images.extend(valid_imgs)

                                else:
                                    error_detail = res_dict.get("error", "Unknown error")
                                    log_container.error(f"  ❌ FAILED: {wb_name}")
                                    with log_container.expander(
                                        f"🔍 Full error for {wb_name}"
                                    ):
                                        st.code(error_detail, language="python")
                                    failed_files.append((wb_name, error_detail))

                            progress_bar.progress((idx + 1) / total)

                    # ============================================================
                    # WHATSAPP SENDING BLOCK — uses selected_chat_id from chat area
                    # ============================================================
                    if (
                        send_to_whatsapp
                        and all_images
                        and id_instance
                        and api_token
                        and selected_chat_id
                        and not st.session_state.cancel_requested
                    ):
                        st.divider()
                        st.subheader("📱 Sending to WhatsApp...")

                        wa_status   = st.empty()
                        wa_progress = st.progress(0)
                        wa_log      = st.container()

                        wa_total = len(all_images)
                        wa_success, wa_fail = 0, 0

                        for i, img_path in enumerate(all_images, start=1):

                            # Respect cancel between sends
                            if st.session_state.cancel_requested:
                                wa_log.warning("🛑 WhatsApp sending cancelled.")
                                break

                            caption = Path(img_path).stem.replace("__", " | ")
                            wa_status.text(
                                f"📤 Sending image {i}/{wa_total}: "
                                f"{Path(img_path).name}"
                            )

                            try:
                                result = send_image_to_whatsapp_greenapi(
                                    image_path=img_path,
                                    chat_id=selected_chat_id,
                                    caption=caption,
                                    id_instance=id_instance,
                                    api_token=api_token,
                                )

                                if "idMessage" in result:
                                    wa_log.write(
                                        f"  ✅ Sent ({i}/{wa_total}): "
                                        f"{Path(img_path).name}"
                                    )
                                    wa_success += 1
                                else:
                                    wa_log.warning(
                                        f"  ⚠️ Failed ({i}/{wa_total}): "
                                        f"{Path(img_path).name} → {result}"
                                    )
                                    wa_fail += 1

                            except Exception as wa_exc:
                                wa_log.error(
                                    f"  ❌ Error sending "
                                    f"{Path(img_path).name}: {wa_exc}"
                                )
                                wa_fail += 1

                            wa_progress.progress(i / wa_total)

                            # Delay between sends (skip after last)
                            if i < wa_total:
                                time.sleep(wa_delay)

                        # WhatsApp summary
                        wa_col_a, wa_col_b = st.columns(2)
                        wa_col_a.metric("✅ WA Sent",   wa_success)
                        wa_col_b.metric("❌ WA Failed", wa_fail)

                        if wa_fail == 0:
                            wa_status.success(
                                f"🎉 All {wa_success} images sent to WhatsApp!"
                            )
                        else:
                            wa_status.warning(
                                f"⚠️ {wa_success} sent, {wa_fail} failed."
                            )

                    elif send_to_whatsapp and not all_images:
                        st.info("ℹ️ No images to send to WhatsApp.")

                    elif send_to_whatsapp and st.session_state.cancel_requested:
                        st.warning("🛑 WhatsApp sending skipped — cancelled.")

                    # ============================================================
                    # SUMMARY & ZIP DOWNLOAD
                    # ============================================================
                    st.divider()
                    col1, col2, col3 = st.columns(3)
                    col1.metric("✅ Images Generated", len(all_images))
                    col2.metric("⏱️ Timed Out",        len(timed_out_files))
                    col3.metric("❌ Failed",            len(failed_files))

                    if timed_out_files:
                        st.warning(f"**Timed out:** {', '.join(timed_out_files)}")

                    if failed_files:
                        st.error("**Failed files:**")
                        for fname, err in failed_files:
                            with st.expander(f"❌ {fname}"):
                                st.code(err, language="python")

                    if all_images:
                        zip_buf = io.BytesIO()
                        with zipfile.ZipFile(
                            zip_buf, "w", zipfile.ZIP_DEFLATED
                        ) as zf:
                            for img in all_images:
                                zf.write(img, arcname=Path(img).name)
                        st.session_state.zip_buffer = zip_buf.getvalue()
                        status_text.text(
                            f"✅ Done! {len(all_images)} images ready."
                        )
                    else:
                        status_text.text(
                            "⚠️ No images generated. Check errors above."
                        )

                except Exception as e:
                    import traceback
                    st.error(f"**Critical Error:** {e}")
                    st.code(traceback.format_exc(), language="python")

                finally:
                    st.session_state.processing = False
        else:
            with processing_placeholder:
                st.caption("No processing in progress. Click **🚀 Start Processing** on the left.")
