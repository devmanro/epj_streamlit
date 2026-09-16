import os
import math
import pandas as pd
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from assets.constants.constants import (
    PATH_BRDX,
    PATH_TEMPLATES,
    COL_CLIENT,
    COL_TYPE,
    COL_QUANTITE,
    COL_TONAGE,
    COL_RESTE_TP,
    # add more if you need them
)

from modules.M_tracker import COL_PRODUIT
import streamlit as st

from tools.tools import _compute_commodity_and_received_lines, _fill_entry_paragraph, group_sourcefile_by_client

if not os.path.exists(PATH_BRDX):
    os.makedirs(PATH_BRDX)

def clean_excel_val(val):
    # Convert to string and remove whitespace
    s_val = str(val).strip()

    # Handle common non-numeric Excel markers
    if s_val in ["", "-", "nan", "None"]:
        return 0.0

    # Validate if it's a number (handles "10" and "10.0")
    if s_val.replace('.', '', 1).isdigit():
        return float(s_val)
    
    # Return 0.0 for any other text to prevent crashes
    return 0.0


def format_entry_docx(doc, row):
    client = str(row.get(COL_CLIENT, "")).strip()
    # Initial commodity from excel
    raw_commodity = str(row.get(COL_TYPE, "")).strip().upper()
    
    # nb_colis =   0     if pd.notna(row.get("nb_colis")) else  row.get("nb_colis")
    # tonnage  =   0.0   if pd.notna(row.get("tonnage"))  else  row.get("tonnage")
    # rec_qty  =0 if pd.notna(row.get("rec_qty"))  else  row.get("rec_qty")

    # print(f"client------{client}")
    nb_colis = row.get(COL_QUANTITE)
    tonnage = row.get(COL_TONAGE)
    rec_qty = row.get(COL_RESTE_TP)
    

    nb_colis = clean_excel_val(nb_colis)
    tonnage = clean_excel_val(tonnage)
    rec_qty = clean_excel_val(rec_qty)

    tonnage_str = f"{tonnage:.2f}".lstrip(
        "0") if tonnage < 1 else f"{tonnage:.2f}"
    manifest_qty_str = f"{int(nb_colis):02d}"

    rec_str = f"{int(float(rec_qty or 0)):02d}"

    # Define lines based on type
    # Logic to adjust Commodity name based on type
    # Initialize defaults
    commodity, received_lines, total_rec_str = _compute_commodity_and_received_lines(
        raw_commodity,
        rec_str,
    )

    # --- use helper to fill paragraphs instead of table in the document ---
    _fill_entry_paragraph(
        doc=doc,
        client=client,
        commodity=commodity,
        manifest_qty_str=manifest_qty_str,
        tonnage_str=tonnage_str,
        received_lines=received_lines,
        total_rec_str=total_rec_str,
    )


def excel_to_docx_custom(input_excel, sheet_name=0, template_path=None, output_docx=None):
    if output_docx is None or input_excel is None:
        return
    
    # Accept either a path or a DataFrame
    if isinstance(input_excel, str):
        df = pd.read_excel(input_excel, sheet_name=sheet_name,
                           engine="openpyxl", header=0)
    else:
        df = input_excel  # already a DataFrame

        doc = Document(template_path) if template_path else Document()

    # Set document author metadata
    doc.core_properties.author = "abdallah bouhannache"

    # Configure global A4 page dimensions and margins once
    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.left_margin = Cm(1.5)
        section.right_margin = Cm(1.5)
        section.top_margin = Cm(5.0)
        section.bottom_margin = Cm(4.5)

        # Remove all leading empty paragraphs from template to prevent leading blank pages
    while doc.paragraphs and not doc.paragraphs[0].text.strip():
        p_element = doc.paragraphs[0]._element
        p_element.getparent().remove(p_element)

    style = doc.styles["Normal"]
    font = style.font
    font.name = "Times New Roman"
    font.size = Pt(12)

    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0

    # Track vertical height estimation per page (A4 printable height ~ 20.2 cm)
    current_page_height_cm = 0.0
    max_page_height_cm = 20.2 # Calculated printable height (29.7 - 5.0 - 4.5)

    for idx, row in df.iterrows():
        # Pre-calculate entry height: ~2.5cm base + 0.6cm per received line
        raw_commodity = str(row.get(COL_TYPE, "")).strip().upper()
        rec_qty = clean_excel_val(row.get(COL_RESTE_TP))
        rec_str = f"{int(float(rec_qty or 0)):02d}"
        _, received_lines, _ = _compute_commodity_and_received_lines(raw_commodity, rec_str)
        
        # Estimation: 5 fixed lines + len(received_lines) + separator
        block_height = 2.5 + (len(received_lines) * 0.6)

        # If adding this block exceeds printable page height, break page
        if current_page_height_cm + block_height > max_page_height_cm:
            doc.add_page_break()
            current_page_height_cm = 0.0

        format_entry_docx(doc, row)
        current_page_height_cm += block_height

    if os.path.exists(output_docx):
        os.remove(output_docx)

    doc.save(output_docx)

def generate_brd(sourcefile, sheet_name=0, template_name="template.docx"):
    base_name = os.path.basename(sourcefile)
    file_name_only = os.path.splitext(base_name)[0]
    output_docx = f"{PATH_BRDX}/{file_name_only}.docx"
    template_path = f"{PATH_TEMPLATES}/{template_name}"
 
    grouped_df = group_sourcefile_by_client(sourcefile, skip_units_packages=False,bl_aggregated=True)
    st.dataframe(grouped_df)      #    nicer interactive table
    
    excel_to_docx_custom(grouped_df, sheet_name, template_path, output_docx)

    return output_docx