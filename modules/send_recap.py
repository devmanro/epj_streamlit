import os
import io
import time
import zipfile
import tempfile
import threading
import queue
import traceback
from pathlib import Path

import openpyxl
import streamlit as st

from assets.constants.constants import GROUP_NUM
from modules.get_recap import get_recap
from tools.whatsapp import (
    send_image as send_image_wahero,
    send_message as send_message_wahero,
)

log_queue = queue.Queue()
RECAP_LOCK = threading.Lock()


def threadsafe_log(message):
    log_queue.put(message)


def drain_log_queue(container):
    while True:
        try:
            message = log_queue.get_nowait()
            container.write(f"📝 {message}")
        except queue.Empty:
            break


def process_single_file(
    result, file_path, workbook_name,
    output_folder, last_table_tail_cols
):
    workbook = None

    try:
        with RECAP_LOCK:
            workbook = openpyxl.load_workbook(
                file_path, data_only=True
            )

            images = get_recap(
                sheet=workbook.worksheets[0],
                workbook_name=workbook_name,
                output_folder=output_folder,
                last_table_tail_cols=int(last_table_tail_cols),
                log_fn=threadsafe_log,
            )

        result["images"] = images
        result["success"] = True

    except Exception:
        result["error"] = traceback.format_exc()
        result["success"] = False

    finally:
        if workbook:
            workbook.close()


def render_send_recaps_tab(ID_INSTANCE=None, API_TOKEN=None, st=st):
    st.header("📤 Generate and Send Recaps via WA Hero")

    uploaded_files = st.file_uploader(
        "Select Excel files",
        type=["xlsx", "xlsm"],
        accept_multiple_files=True,
    )

    output_folder = st.text_input(
        "Output folder", value="/tmp/output"
    )

    last_table_tail_cols = st.number_input(
        "Ending columns for last table tail",
        min_value=1,
        value=6,
    )

    st.subheader("📱 WA Hero settings")

    image_phone = st.text_input(
        "Recipient phone number",
        placeholder="213XXXXXXXXX",
        value=GROUP_NUM,
        help="Country code + number, digits only.",
        key="wahero_image_phone",
    ).strip()

    send_images = st.checkbox(
        "Send generated images through WA Hero",
        value=True,
    )

    image_delay = st.slider(
        "Delay between images (seconds)",
        min_value=1.0,
        max_value=10.0,
        value=2.0,
        step=0.5,
        disabled=not send_images,
    )

    send_text = st.checkbox(
        "Also send a text message",
        value=False,
    )

    text_phone = st.text_input(
        "Text recipient phone number",
        placeholder="213XXXXXXXXX",
        disabled=not send_text,
    ).strip()

    text_message = st.text_area(
        "Text message",
        value="Your recap images have been generated.",
        disabled=not send_text,
    )

    if "processing" not in st.session_state:
        st.session_state.processing = False

    if "cancel_requested" not in st.session_state:
        st.session_state.cancel_requested = False

    col1, col2 = st.columns(2)

    with col1:
        start = st.button(
            "🚀 Start processing",
            disabled=st.session_state.processing,
            use_container_width=True,
        )

    with col2:
        stop = st.button(
            "🛑 Stop",
            disabled=not st.session_state.processing,
            use_container_width=True,
        )

    if stop:
        st.session_state.cancel_requested = True
        st.warning("Cancellation requested.")

    if start:
        if not uploaded_files:
            st.warning("Upload at least one Excel file.")
            return

        if send_images and not image_phone:
            st.warning("Enter the image recipient's phone number.")
            return

        st.session_state.processing = True
        st.session_state.cancel_requested = False
        st.rerun()

    if not st.session_state.processing:
        return

    progress = st.progress(0)
    status = st.empty()
    logs = st.container()

    Path(output_folder).mkdir(parents=True, exist_ok=True)

    all_images = []
    failed_files = []

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            total = len(uploaded_files)

            for index, uploaded in enumerate(uploaded_files):
                if st.session_state.cancel_requested:
                    logs.warning("Processing cancelled.")
                    break

                name = Path(uploaded.name).stem
                status.write(
                    f"Processing {index + 1}/{total}: {name}"
                )

                temp_path = os.path.join(
                    tmp_dir, uploaded.name
                )

                with open(temp_path, "wb") as file:
                    file.write(uploaded.getbuffer())

                result = {
                    "images": [],
                    "success": False,
                    "error": None,
                }

                thread = threading.Thread(
                    target=process_single_file,
                    args=(
                        result,
                        temp_path,
                        name,
                        output_folder,
                        last_table_tail_cols,
                    ),
                    daemon=True,
                )

                thread.start()
                thread.join(timeout=30)

                drain_log_queue(logs)

                if thread.is_alive():
                    failed_files.append(
                        (name, "Processing timed out after 30 seconds")
                    )
                elif result["success"]:
                    images = [
                        image for image in result["images"]
                        if os.path.isfile(image)
                    ]
                    all_images.extend(images)
                    logs.success(
                        f"{name}: generated {len(images)} image(s)"
                    )
                else:
                    failed_files.append(
                        (name, result["error"] or "Unknown error")
                    )

                progress.progress((index + 1) / total)

        # Send images using WA Hero
        if send_images and all_images:
            st.subheader("📨 Sending images")
            send_progress = st.progress(0)
            send_logs = st.container()
            sent, failed = 0, 0

            for index, image_path in enumerate(all_images):
                if st.session_state.cancel_requested:
                    break

                caption = Path(image_path).stem.replace("__", " | ")

                try:
                    response = send_image_wahero(
                        image_path=image_path,
                        phone=image_phone,
                        caption=caption,
                    )

                    sent += 1
                    send_logs.success(
                        f"Sent: {Path(image_path).name}"
                    )

                except Exception as exc:
                    failed += 1
                    send_logs.error(
                        f"{Path(image_path).name}: {exc}"
                    )

                send_progress.progress(
                    (index + 1) / len(all_images)
                )

                if index + 1 < len(all_images):
                    time.sleep(image_delay)

            st.metric("Images sent", sent)
            st.metric("Images failed", failed)

        # Optional text message
        if send_text and not st.session_state.cancel_requested:
            if text_phone and text_message.strip():
                try:
                    result = send_message_wahero(
                        phone=text_phone,
                        message=text_message,
                    )
                    st.success(f"Text message accepted: {result}")
                except Exception as exc:
                    st.error(f"Text message failed: {exc}")
            else:
                st.warning("Enter the text recipient and message.")

        # Show processing failures
        if failed_files:
            st.subheader("⚠️ Failed files")
            for name, error in failed_files:
                with st.expander(name):
                    st.code(error)

        # ZIP download
        if all_images:
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(
                zip_buffer, "w", zipfile.ZIP_DEFLATED
            ) as archive:
                for image_path in all_images:
                    archive.write(
                        image_path,
                        arcname=Path(image_path).name,
                    )

            st.download_button(
                "⬇️ Download generated images",
                data=zip_buffer.getvalue(),
                file_name="exported_tables.zip",
                mime="application/zip",
            )

    except Exception as exc:
        st.error(f"Processing error: {exc}")
        st.code(traceback.format_exc())

    finally:
        st.session_state.processing = False
