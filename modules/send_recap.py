def render_send_recaps_tab(ID_INSTANCE, API_TOKEN):
    
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
    # 2. WHATSAPP SETTINGS & STATE SETUP
    # ============================================================
    st.subheader("📱 WhatsApp Settings")

    id_instance = ID_INSTANCE
    api_token = API_TOKEN

    if id_instance:
        st.session_state.wa_id_instance = id_instance
    if api_token:
        st.session_state.wa_api_token = api_token

    # Initialize session states
    if "wa_groups" not in st.session_state:
        st.session_state.wa_groups = []
    if "wa_chats" not in st.session_state:
        st.session_state.wa_chats = []
    if "wa_messages" not in st.session_state:
        st.session_state.wa_messages = {}
    if "wa_seen_message_ids" not in st.session_state:
        st.session_state.wa_seen_message_ids = set()
    if "processing" not in st.session_state:
        st.session_state.processing = False
    if "cancel_requested" not in st.session_state:
        st.session_state.cancel_requested = False
    if "wa_history_count" not in st.session_state:
        st.session_state.wa_history_count = 25

    # Group/Contact Fetch controls
    wa_col1, wa_col2 = st.columns(2)
    with wa_col1:
        fetch_groups = st.button(
            "🔄 Fetch My Groups",
            disabled=not (id_instance and api_token),
            use_container_width=True,
        )
    with wa_col2:
        load_incoming = st.button(
            "📥 Load incoming messages",
            disabled=not (id_instance and api_token),
            use_container_width=True,
        )

    if fetch_groups:
        try:
            with st.spinner("Fetching groups from WhatsApp..."):
                groups = get_whatsapp_groups_greenapi(id_instance, api_token)
                if groups:
                    st.session_state.wa_groups = groups
                    st.success(f"✅ Found {len(groups)} group(s)")
                else:
                    st.warning("No groups found.")
                    st.session_state.wa_groups = []
        except Exception as exc:
            st.error(f"Could not load groups: {exc}")

    if load_incoming:
        loaded_count = 0
        try:
            with st.spinner("Checking Green API notification queue..."):
                for _ in range(100):
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
                            loaded_count += 1
                    if receipt_id:
                        delete_whatsapp_notification_greenapi(str(receipt_id), id_instance, api_token)
                    else:
                        break
            st.success(f"Loaded {loaded_count} incoming message(s).")
        except Exception as exc:
            st.error(f"Could not load incoming messages: {exc}")

    # Target Chat Selector
    groups_available = st.session_state.get("wa_groups", [])
    if groups_available:
        group_options = {f"{g['name']} ({g['id']})": g["id"] for g in groups_available}
        selected_label = st.selectbox("📋 Select Target WhatsApp Group", options=list(group_options.keys()))
        selected_chat_id = group_options[selected_label]
    else:
        selected_chat_id = st.text_input(
            "📋 WhatsApp Group / Contact Chat ID",
            value=st.session_state.get("wa_chat_id", ""),
            placeholder="120363XXXXXXXXXX@g.us or 972501234567@c.us",
        ).strip()

    if selected_chat_id:
        if selected_chat_id != st.session_state.get("wa_chat_id"):
            st.session_state.wa_history_count = 25
            st.session_state.pop(f"wa_history_{selected_chat_id}", None)
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
    # 3. LAYOUT: CONTROLS & CHAT CONVERSATION
    # ============================================================
    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown("### ⚙️ Controls")
        start_clicked = st.button("🚀 Start Processing", use_container_width=True, disabled=st.session_state.processing)
        stop_clicked = st.button("🛑 Stop / Cancel", use_container_width=True, disabled=not st.session_state.processing)

        if start_clicked:
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

    with right_col:
        st.markdown("### 💬 Live Chat & History")
        processing_placeholder = st.container()

        if selected_chat_id and id_instance and api_token:
            history_cache_key = f"wa_history_{selected_chat_id}"
            load_older_col, refresh_col = st.columns(2)

            with load_older_col:
                if st.button("⬆️ Load older messages", use_container_width=True):
                    st.session_state.wa_history_count += 25
                    st.session_state.pop(history_cache_key, None)
                    st.rerun()

            with refresh_col:
                if st.button("🔄 Refresh conversation", use_container_width=True):
                    st.session_state.pop(history_cache_key, None)
                    st.rerun()

            if history_cache_key not in st.session_state:
                try:
                    with st.spinner("Loading conversation..."):
                        raw_history = get_whatsapp_chat_history_greenapi(
                            selected_chat_id, id_instance, api_token,
                            count=st.session_state.wa_history_count,
                        )
                        st.session_state[history_cache_key] = [normalize_message(m) for m in raw_history]
                except Exception as exc:
                    st.error(f"Could not load history: {exc}")
                    st.session_state[history_cache_key] = []

            chat_messages = list(st.session_state.get(history_cache_key, []))
            
            # Merge live-polled messages
            live_messages = st.session_state.wa_messages.get(selected_chat_id, [])
            if live_messages:
                seen_ids = {m.get("id_message") for m in chat_messages if m.get("id_message")}
                for m in live_messages:
                    if m.get("id_message") not in seen_ids:
                        chat_messages.append(m)
                chat_messages.sort(key=lambda m: m.get("timestamp") or 0)

            chat_box = st.container(height=400)
            with chat_box:
                if not chat_messages:
                    st.info("No messages found in this chat history.")
                else:
                    for message in chat_messages:
                        role = "user" if message.get("from_me") else "assistant"
                        name = "You" if message.get("from_me") else message.get("sender_name", "Contact")
                        with st.chat_message(role):
                            st.markdown(f"**{name}**")
                            st.write(message.get("text", ""))

            # Chat input
            text_to_send = st.chat_input("Type a WhatsApp message...")
            if text_to_send:
                try:
                    result = send_text_to_whatsapp_greenapi(text_to_send.strip(), selected_chat_id, id_instance, api_token)
                    if isinstance(result, dict) and result.get("idMessage"):
                        st.session_state.wa_messages.setdefault(selected_chat_id, []).append({
                            "chat_id": selected_chat_id,
                            "text": text_to_send.strip(),
                            "from_me": True,
                            "timestamp": time.time(),
                            "id_message": result["idMessage"],
                            "sender_name": "You",
                        })
                        st.rerun()
                    else:
                        st.error(f"Green API error: {result}")
                except Exception as exc:
                    st.error(f"Failed to send: {exc}")

    # ============================================================
    # 4. PROCESSING & WHATSAPP SENDING LOOP
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
                            target=process_single_file_wrapper, # noqa: F821
                            args=(
                                res_dict, tmp_path, wb_name, output_folder,
                                last_table_tail_cols, lambda msg: log_container.write(f"  📝 {msg}"),
                            ),
                            daemon=True,
                        )

                        start_time = time.time()
                        thread.start()
                        thread.join(timeout=float(file_timeout))
                        elapsed = time.time() - start_time

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

                        progress_bar.progress((idx + 1) / total)

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

            except Exception as e:
                import traceback
                st.error(f"Critical Error: {e}")
                st.code(traceback.format_exc(), language="python")
            finally:
                st.session_state.processing = False
