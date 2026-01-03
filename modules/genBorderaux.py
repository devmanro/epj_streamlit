import os
import pandas as pd
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import math
from assets.constants.constants import PATH_BRDX,PATH_TEMPLATES

if not os.path.exists(PATH_BRDX):
    os.makedirs(PATH_BRDX)

def format_entry_docx(doc, row):
    client = str(row.get("client", "")).strip()
    # Initial commodity from excel
    raw_commodity = str(row.get("type", "")).strip().upper() 

    nb_colis = row.get("qte") or 0
    tonnage = row.get("poids") or 0.0
    rec_qty = row.get("rec_qty") or 0
    # nb_colis =   0     if pd.notna(row.get("nb_colis")) else  row.get("nb_colis")
    # tonnage  =   0.0   if pd.notna(row.get("tonnage"))  else  row.get("tonnage")
    #rec_qty  =0 if pd.notna(row.get("rec_qty"))  else  row.get("rec_qty")

        
    # print(f"client------{client}")
    
    if rec_qty is None or (isinstance(rec_qty, float) and math.isnan(rec_qty)):
        rec_qty = 0

    # Create table
    table = doc.add_table(rows=5, cols=2)
    table.autofit = True
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    tonnage_str = f"{tonnage:.2f}".lstrip("0") if tonnage < 1 else f"{tonnage:.2f}"
    manifest_qty_str = f"{int(nb_colis):02d}"
    rec_str = f"{int(rec_qty):02d}"
    
    
    # Define lines based on type
    # Logic to adjust Commodity name based on type
    # Initialize defaults
    commodity = raw_commodity
    received_lines = []
    total_rec_str=rec_str
    
    # Logic to adjust Commodity name and Define Lines based on type
    if "BIG BAG" in raw_commodity:
        commodity = "Big Bags"
        total_rec_str=f"{rec_str}  Big Bags"
        received_lines = [
            "BIG BAGS FOUND TORN ON BOARD",
            "BIG BAGS FOUND BROKEN ON BOARD",
            "EMPTY BAG ON BOARD"
        ]

    elif any(x in raw_commodity for x in ["PLYWOOD", "MDF", "CTP"]):
        commodity = raw_commodity
        received_lines = [
            f"Crates of {commodity} Found Dismembered on board",
            f"Crates of {commodity} wet on board (Packing and/or Contents)",
            f"Crates of {commodity} moldy on board (Packing and/or Contents)"
        ]
        total_rec_str=f"{rec_str}  Crates of {commodity}"

    elif "PIPES" in raw_commodity:
        commodity = "Pipes"
        received_lines = ["Pipes.", "Pipes Damaged on board"]
        total_rec_str=f"{rec_str}  {commodity}"

    elif "BEAMS" in raw_commodity:
        commodity = "Bundles of Beams"
        received_lines = ["Bundles of Beams.", "Bundles of Beams Found Dismembered on board"]
        total_rec_str=f"{rec_str}  {commodity}"

    elif "FIL MACHINE" in raw_commodity:
        commodity = "FIL MACHINE"
        received_lines = ["RLX FOUND DISMEMBERED ON BOARD"]
        total_rec_str=f"{rec_str}  {commodity}"

    elif "COIL" in raw_commodity:
        commodity = "Coils"
        received_lines = ["Coils Found Rusty on board", "Coils Packaging damaged on board"]

    elif any(wood in raw_commodity for wood in ["WHITE WOOD", "BEECH WOOD", "RED WOOD"]):
        # Keeping raw_commodity (e.g., "WHITE WOOD") as the name
        commodity = "Bundles" 
        received_lines = [
            f"Bundles of {raw_commodity} Found Dismembered on board",
            f"Bundles of {raw_commodity} wet on board (Packing and/or Contents)",
            f"Bundles of {raw_commodity} moldy on board (Packing and/or Contents)"
        ]
        total_rec_str=f"{rec_str}  Bundles of {raw_commodity}"


    elif "UNIT" in raw_commodity or "PACKAGE" in raw_commodity:
        commodity = "Units + Packages"
        received_lines = ["Units", "Units Damaged on board"]
        total_rec_str=f"{rec_str}  {commodity}"

    elif not raw_commodity:
        commodity = "Units + Package"
        received_lines = ["Packaging damaged on board"]
        total_rec_str=f"{rec_str}  {commodity}"

    else:
        # Final Fallback
        commodity = raw_commodity if raw_commodity else "General Cargo"
        received_lines = ["Packaging damaged on board"]
        total_rec_str=f"{rec_str}  {commodity}"


    # Row 0: Receiver / Commodity
    row0 = table.rows[0].cells
    row0[0].width = Cm(9)
    p0 = row0[0].paragraphs[0]
    p0.add_run("Receiver : ").bold = True
    p0.add_run(client)
    p0.alignment = WD_ALIGN_PARAGRAPH.LEFT

    row0[1].width = Cm(9)
    p1 = row0[1].paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_c = p1.add_run("Commodity : ")
    run_c1 = p1.add_run(commodity)
    run_c.bold = True
    run_c.font.name = "Agency FB"
    run_c1.font.name = "Agency FB"

    # Row 1: Manifested Quantity / Tonnage
    row1 = table.rows[1].cells
    row1[0].width = Cm(12)
    p2 = row1[0].paragraphs[0]
    p2.add_run("Manifested Quantity : ").bold = True
    p2.add_run(f"{manifest_qty_str} {commodity}")
    p2.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    row1[1].width = Cm(5)
    p3 = row1[1].paragraphs[0]
    p3.add_run("Tonnage : ").bold = True
    p3.add_run(f"{tonnage_str} Mt")
    p3.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # --- DYNAMIC RECEIVED AREA (Replaces Row 2) ---
    row2 = table.rows[2].cells
    row2[0].width = Cm(30)

    row2_cell = table.rows[2].cells[0]

    # Merge row 2 cells to give more space for the text
    # row2_cell.merge(table.rows[2].cells[1])
  
    # Clear default paragraph and add the formatted lines
    row2_cell.paragraphs[0].clear()
    for i, line in enumerate(received_lines):
        if i == 0:
            p = row2_cell.paragraphs[0]
        else:
            p = row2_cell.add_paragraph()
        
        run_label = p.add_run("Received:    ")
        run_label.bold = True
        p.add_run(line)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # --- END DYNAMIC AREA ---

    # Row 3: Total Received
    row3 = table.rows[3].cells

    row3[0].width = Cm(12)

    # row3[0].merge(row3[1])
    p4 = row3[0].paragraphs[0]
    p4.add_run("Total Received: ").bold = True
    p4.add_run(f" {total_rec_str}")
    p4.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Row 4: Final line
    row4 = table.rows[4].cells

    row4[0].width = Cm(25)

    # row4[0].merge(row4[1])
    p5 = row4[0].paragraphs[0]
    full = p5.add_run("The Quantity Will Be confirmed after delivery Cargo.")
    full.bold = True

    # Border Line
    p_sep = doc.add_paragraph()
    p_sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sep = p_sep.add_run("=*"*29)
    run_sep.bold = True

def excel_to_docx_custom(input_excel, sheet_name=0, template_path=None, output_docx=None):
    if not output_docx:
        return
    df = pd.read_excel(input_excel, sheet_name=sheet_name, engine="openpyxl",header=0)
    doc = Document(template_path) if template_path else Document()

    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri (Corps)"
    font.size = Pt(12)

    for idx, row in df.iterrows():
        format_entry_docx(doc, row)
    
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0 #

    if os.path.exists(output_docx):
        os.remove(output_docx)
        #print(f"{output_docx} has been deleted.")

    doc.save(output_docx)
    #print(f"New File {output_docx} Saved")

def generate_brd(sourcefile, sheet_name=0, template_name="template.docx"):
    base_name = os.path.basename(sourcefile) 
    file_name_only = os.path.splitext(base_name)[0]
    output_docx=f"{PATH_BRDX}/{file_name_only}.docx"
    template_path=f"{PATH_TEMPLATES}/{template_name}"
    excel_to_docx_custom(sourcefile, sheet_name, template_path, output_docx)
    return output_docx

#if __name__ == "__main__":
    # Ensure book1.xlsx exists in your directory
    # excel_to_docx_custom("book1.xlsx", output_docx="entries.docx")
    # column_names = ["type", "client", "qte", "poids", "rec_qty"]
    # names=column_names
#    generate_brd("source.xlsx", sheet_name=0, template_path="template.docx", output_docx="entries.docx")






    



    