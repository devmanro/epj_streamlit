import os
import io
import time
import zipfile
import tempfile
import threading
from pathlib import Path

import concurrent.futures
import time
import queue

from tools.whatsapp import (
    get_whatsapp_chats_greenapi, 
    send_image_to_whatsapp_greenapi,
)

# ⚠️ Import get_recap — adjust this path to match where get_recap is actually defined!
from modules.get_recap import get_recap


# --- Thread-safe log queue ---
log_queue = queue.Queue()
RECAP_LOCK = threading.Lock()

# ── Constants ─────────────────────────────────────────────────────────
FILE_TIMEOUT_SECONDS = 30  # seconds before skipping a file


def process_single_file_wrapper(
    result_dict, tmp_path, wb_name, output_folder,
    last_table_tail_cols, log_fn=None
):
    import traceback
    wb = None

    try:
        import openpyxl

        with RECAP_LOCK:
            wb = openpyxl.load_workbook(tmp_path, data_only=True)
            sheet = wb.worksheets[0]

            imgs = get_recap(
                sheet=sheet,
                workbook_name=wb_name,
                output_folder=output_folder,
                last_table_tail_cols=int(last_table_tail_cols),
                log_fn=threadsafe_log,
            )

            result_dict["images"] = imgs
            result_dict["success"] = True

    except Exception:
        result_dict["error"] = traceback.format_exc()
        result_dict["success"] = False

    finally:
        if wb is not None:
            wb.close()


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


def render_send_recaps_tab(ID_INSTANCE, API_TOKEN, st):

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
    # 2. WHATSAPP SETTINGS & TARGET CHAT SETUP
    # ============================================================
    st.subheader("📱 WhatsApp Settings")

    id_instance = ID_INSTANCE
    api_token = API_TOKEN

    if id_instance:
        st.session_state.wa_id_instance = id_instance
    if api_token:
        st.session_state.wa_api_token = api_token

    # Initialize session states
    if "wa_chats" not in st.session_state:
        st.session_state.wa_chats = []
    if "processing" not in st.session_state:
        st.session_state.processing = False
    if "cancel_requested" not in st.session_state:
        st.session_state.cancel_requested = False

    # Contact/Group Fetch control
    fetch_chats = st.button(
        "🔄 Load contacts and groups",
        disabled=not (id_instance and api_token),
        use_container_width=True,
    )

    if fetch_chats:
        try:
            with st.spinner("Loading WhatsApp contacts and groups..."):
                st.session_state.wa_chats = get_whatsapp_chats_greenapi(id_instance, api_token)
            if st.session_state.wa_chats:
                st.success(f"✅ Loaded {len(st.session_state.wa_chats)} chat(s)")
            else:
                st.warning("No chats returned. Check that your Green API instance is connected.")
        except Exception as exc:
            st.error(f"Could not load chats: {exc}")

    # Target Chat Selector (contacts + groups)
    chats_available = st.session_state.get("wa_chats", [])
    if chats_available:
        chat_options = {
            f"{'👥' if chat['type'] == 'group' else '👤'} {chat['name']} — {chat['id']}": chat["id"]
            for chat in chats_available
        }
        labels = list(chat_options.keys())
        previous_id = st.session_state.get("wa_chat_id", "")
        default_index = next(
            (i for i, label in enumerate(labels) if chat_options[label] == previous_id), 0
        )
        selected_label = st.selectbox(
            "📋 Select Target WhatsApp Chat (Contact or Group)",
            options=labels,
            index=default_index,
        )
        selected_chat_id = chat_options[selected_label]
    else:
        selected_chat_id = st.text_input(
            "📋 WhatsApp Group / Contact Chat ID",
            value=st.session_state.get("wa_chat_id", ""),
            placeholder="120363XXXXXXXXXX@g.us or 972501234567@c.us",
        ).strip()

    if selected_chat_id:
        st.session_state.wa_chat_id = selected_chat_id

    send_to_whatsapp = st.checkbox(
        "📨 Send processed images to selected chat",
        value=st.session_state.get("send_to_whatsapp", False),
    )
    st.session_state.send_to_whatsapp = send_to_whatsapp

    wa_delay = st.slider(
        "⏳ Delay between images (s)",
        min_value=1.0, max_value=10.0, value=2.0, step=0.5,
        disabled=not send_to_whatsapp,
        help="Prevents WhatsApp rate limiting / spam detection",
    )

    st.divider()

    # ============================================================
    # 3. CONTROLS & EXECUTION
    # ============================================================
    st.markdown("### ⚙️ Controls")
    
    col1, col2 = st.columns(2)
    with col1:
        start_clicked = st.button("🚀 Start Processing", use_container_width=True, disabled=st.session_state.processing)
    with col2:
        stop_clicked = st.button("🛑 Stop / Cancel", use_container_width=True, disabled=not st.session_state.processing)

    if start_clicked:
        if not uploaded_files:
            st.warning("⚠️ Please upload at least one Excel file before starting.")
        else:
            st.session_state.processing = True
            st.session_state.cancel_requested = False
            st.session_state.pop("zip_buffer", None)
            st.rerun()

    if stop_clicked:
        st.session_state.cancel_requested = True
        st.warning("Stop signal sent. Will stop after current file attempt.")

    if st.session_state.get("zip_buffer"):
        st.download_button(
            label="⬇️ Download All Images (ZIP)",
            data=st.session_state.zip_buffer,
            file_name="exported_tables.zip",
            mime="application/zip",
            use_container_width=True,
        )

    processing_placeholder = st.container()

    # ============================================================
    # 4. PROCESSING & WHATSAPP SENDING LOOP
    # ============================================================
    if st.session_state.processing:
        with processing_placeholder:
            status_text  = st.empty()
            progress_bar = st.progress(0)
            log_container = st.container()

            Path(output_folder).mkdir(parents=True, exist_ok=True)
            all_images       = []
            timed_out_files = []
            failed_files    = []

            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    total = len(uploaded_files)
                    if total == 0:
                        st.warning("No files uploaded!")
                        st.session_state.processing = False
                        st.stop()

                    for idx, up_file in enumerate(uploaded_files):
                        if st.session_state.cancel_requested:
                            log_container.warning("🛑 Cancelled by user.")
                            break

                        wb_name = Path(up_file.name).stem
                        status_text.text(f"Processing {idx+1}/{total}: {wb_name}...")
                        log_container.write(f"---\n📂 Starting: **{wb_name}**")

                        tmp_path = os.path.join(tmp_dir, up_file.name)
                        with open(tmp_path, "wb") as f:
                            f.write(up_file.getbuffer())

                        file_size = os.path.getsize(tmp_path)
                        if file_size == 0:
                            log_container.error("  ❌ Empty file! Skipping.")
                            failed_files.append((wb_name, "Empty file"))
                            continue

                        res_dict = {"images": [], "success": False, "error": None}
                        thread = threading.Thread(
                            target=process_single_file_wrapper,
                            args=(
                                res_dict, tmp_path, wb_name, output_folder,
                                last_table_tail_cols, None,
                            ),
                            daemon=True,
                        )

                        start_time = time.time()
                        thread.start()

                        while thread.is_alive() and (time.time() - start_time) < float(file_timeout):
                            drain_log_queue(log_container)
                            thread.join(timeout=0.25)

                        elapsed = time.time() - start_time
                        drain_log_queue(log_container)

                        if thread.is_alive():
                            log_container.warning(f"  ⏱️ TIMEOUT after {elapsed:.1f}s — **{wb_name}** skipped")
                            timed_out_files.append(wb_name)
                        else:
                            if res_dict["success"]:
                                valid_imgs = [img for img in res_dict.get("images", []) if os.path.exists(img)]
                                all_images.extend(valid_imgs)
                                log_container.write(f"  ✅ Success — {len(valid_imgs)} image(s)")
                            else:
                                err = res_dict.get("error", "Unknown error")
                                failed_files.append((wb_name, err))
                                log_container.error(f"  ❌ Failed: {wb_name}")
                                with log_container.expander(f"Show error for {wb_name}"):
                                    st.code(err, language="python")

                        progress_bar.progress((idx + 1) / total)

                # Summary of failures/timeouts
                if failed_files:
                    st.subheader("❌ Failed Files")
                    for name, err in failed_files:
                        with st.expander(name):
                            st.code(err, language="python")

                if timed_out_files:
                    st.subheader("⏱️ Timed Out Files")
                    st.write(", ".join(timed_out_files))

                # Sending Images to WhatsApp
                if send_to_whatsapp and all_images and selected_chat_id and not st.session_state.cancel_requested:
                    st.subheader("📱 Sending images to WhatsApp...")
                    wa_status = st.empty()
                    wa_progress = st.progress(0)
                    wa_log = st.container()

                    wa_total = len(all_images)
                    wa_success, wa_fail = 0, 0

                    for i, img_path in enumerate(all_images, start=1):
                        if st.session_state.cancel_requested:
                            break
                        caption = Path(img_path).stem.replace("__", " | ")
                        wa_status.text(f"📤 Sending image {i}/{wa_total}: {Path(img_path).name}")
                        try:
                            res = send_image_to_whatsapp_greenapi(
                                image_path=img_path,
                                chat_id=selected_chat_id,
                                caption=caption,
                                id_instance=id_instance,
                                api_token=api_token,
                            )
                            if isinstance(res, dict) and "idMessage" in res:
                                wa_success += 1
                                wa_log.write(f"  ✅ Sent: {Path(img_path).name}")
                            else:
                                wa_fail += 1
                                wa_log.warning(f"  ⚠️ Failed: {res}")
                        except Exception as ex:
                            wa_fail += 1
                            wa_log.error(f"  ❌ Error: {ex}")

                        wa_progress.progress(i / wa_total)
                        if i < wa_total:
                            time.sleep(wa_delay)

                    st.metric("✅ WA Sent", wa_success)
                    st.metric("❌ WA Failed", wa_fail)

                # ZIP creation & summary
                if all_images:
                    zip_buf = io.BytesIO()
                    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for img in all_images:
                            zf.write(img, arcname=Path(img).name)
                    st.session_state.zip_buffer = zip_buf.getvalue()
                    st.success(f"✅ Done! {len(all_images)} image(s) ready for download.")
                else:
                    st.warning("⚠️ No images were generated.")

            except Exception as e:
                import traceback
                st.error(f"Critical Error: {e}")
                st.code(traceback.format_exc(), language="python")
            finally:
                st.session_state.processing = False
                st.rerun()  # 👈 This forces Streamlit to refresh and unlock the UI/buttons immediately