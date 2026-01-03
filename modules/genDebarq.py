import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, PatternFill, Font
from openpyxl.utils import get_column_letter
from datetime import datetime, timedelta
from assets.constants.constants import PATH_DEBRQ

# --- GLOBAL SETTINGS ---
SHIP_NAME_PLACEHOLDER = "SHIP NAME: [ENTER NAME HERE]"

def get_manual_color(product_name):
    """Maps product names to specific hex colors as requested."""
    name = product_name.upper()
    colors = {
        "CTP": "73a64c",      # Green
        "BIGBAG": "4d97a1",   # Blue
        "TUBE": "753032",     # Brown
        "BOBINE": "ad5a17",   # Light Red
    }
    return colors.get(name, None) # Returns None (White) if not found or for 'Others'

def create_product_table(ws, product_name, product_data, start_col, is_others=False):
    # --- Color Selection ---
    raw_color = get_manual_color(product_name) if not is_others else None

    # --- Styles ---
    header_fill = PatternFill(start_color=raw_color, end_color=raw_color, fill_type="solid") if raw_color else PatternFill(fill_type=None)
    header_font = Font(bold=True, size=11)
    title_font = Font(bold=True, size=12)
    border = Border(left=Side(style='thin'), right=Side(style='thin'),
                    top=Side(style='thin'), bottom=Side(style='thin'))
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # --- Column Setup ---
    client_col = 'CLIENT' if 'CLIENT' in product_data.columns else 'Client'
    prod_col = 'PRODUITS' if 'PRODUITS' in product_data.columns else 'produits'
    clients = product_data[client_col].unique().tolist()
    
    col_mapping = {}
    for i, client in enumerate(clients):
        col_letter = get_column_letter(start_col + 2 + i)
        col_mapping[client] = col_letter
        ws.column_dimensions[col_letter].width = 22

    ws.column_dimensions[get_column_letter(start_col)].width = 15
    ws.column_dimensions[get_column_letter(start_col + 1)].width = 12

    num_extra_cols = 3 
    start_col_idx = start_col + 2
    last_col_idx = start_col_idx + len(clients) + num_extra_cols - 1
    last_col_letter = get_column_letter(last_col_idx)
    
    # --- Row 4: Product Title Header ---
    ws.merge_cells(f'{get_column_letter(start_col_idx)}4:{last_col_letter}4')
    title_cell = ws[f'{get_column_letter(start_col_idx)}4']
    title_cell.value = product_name
    title_cell.font = title_font
    title_cell.alignment = center
    title_cell.fill = header_fill
    for col_i in range(start_col_idx, last_col_idx + 1):
        ws.cell(row=4, column=col_i).border = border

    # --- Row 5: Client Names ---
    for c_idx in range(start_col_idx, last_col_idx + 1):
        cell = ws.cell(row=5, column=c_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = center
        
    for client, col in col_mapping.items():
        ws[f"{col}5"].value = str(client)

    # --- Row 6: Alignment logic ---
    if is_others:
        for client, col in col_mapping.items():
            try:
                prod_val = product_data[product_data[client_col] == client][prod_col].iloc[0]
            except:
                prod_val = "-"
            c = ws[f"{col}6"]
            c.value = str(prod_val)
            c.font = Font(size=10, italic=True)
            c.alignment = center
            c.border = border
    else:
        for c_idx in range(start_col_idx, last_col_idx + 1):
            ws.cell(row=6, column=c_idx).border = border

    # --- Row 7: BL Numbers / Headers ---
    bl_row = 7
    for col_idx in range(start_col, last_col_idx + 1):
        cell = ws.cell(row=bl_row, column=col_idx)
        cell.border = border
        cell.alignment = center
        if col_idx >= start_col_idx:
            cell.fill = header_fill
            cell.font = header_font

    ws[f"{get_column_letter(start_col)}{bl_row}"].value = "DATE"
    ws[f"{get_column_letter(start_col+1)}{bl_row}"].value = "SHIFT"
    
    bl_col_name = 'N° BL' if 'N° BL' in product_data.columns else 'N°BL'
    qty_col_name = 'NOMBRE COLIS' if 'NOMBRE COLIS' in product_data.columns else 'nombre colis'

    for client, col in col_mapping.items():
        try:
            bl_num = product_data[product_data[client_col] == client][bl_col_name].iloc[0]
        except:
            bl_num = "-"
        ws[f"{col}{bl_row}"].value = str(bl_num)

    extra_headers = ["INC", "TOTAL", "TOTAL/J"]
    extra_cols = []
    for i, h in enumerate(extra_headers):
        col_idx = start_col + 2 + len(clients) + i
        col_letter = get_column_letter(col_idx)
        extra_cols.append(col_letter)
        ws[f"{col_letter}{bl_row}"].value = h

    # --- Data Rows (Starting at Row 8 for 15 Days) ---
    base_date = datetime(2025, 2, 10)
    shifts = ["MATIN", "SOIR", "NUIT", "NUIT -2-"]
    data_start_row = 8
    curr_data_row = data_start_row
    
    for day_offset in range(15):
        d_str = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        day_start_row = curr_data_row
        for shift in shifts:
            ws[f"{get_column_letter(start_col)}{curr_data_row}"].value = d_str
            ws[f"{get_column_letter(start_col+1)}{curr_data_row}"].value = shift
            
            for client, col in col_mapping.items():
                ws[f"{col}{curr_data_row}"].value = 0 
            
            inc_col = extra_cols[0]
            ws[f"{inc_col}{curr_data_row}"].value = 0
            
            total_col = extra_cols[1]
            first_client_col = get_column_letter(start_col + 2)
            ws[f"{total_col}{curr_data_row}"].value = f"=SUM({first_client_col}{curr_data_row}:{inc_col}{curr_data_row})"
            
            for c_idx in range(start_col, last_col_idx + 1):
                cell = ws.cell(row=curr_data_row, column=c_idx)
                cell.border = border
                cell.alignment = center
            curr_data_row += 1
        
        ws.merge_cells(f"{get_column_letter(start_col)}{day_start_row}:{get_column_letter(start_col)}{curr_data_row-1}")
        totalj_col = extra_cols[2]
        ws.merge_cells(f"{totalj_col}{day_start_row}:{totalj_col}{curr_data_row-1}")
        ws[f"{totalj_col}{day_start_row}"].value = f"=SUM({extra_cols[1]}{day_start_row}:{extra_cols[1]}{day_start_row+3})"
        ws[f"{totalj_col}{day_start_row}"].alignment = center
        ws[f"{totalj_col}{day_start_row}"].font = Font(bold=True)
        ws[f"{totalj_col}{day_start_row}"].border = border

    # --- Summary Rows ---
    summary_start_row = curr_data_row
    labels = ["TOTAL DECHARGER", "QUANTITE MANIFEST", "RESTE A BORD"]
    summary_rows = []
    for i, label in enumerate(labels):
        r = summary_start_row + i
        label_cell = ws[f"{get_column_letter(start_col)}{r}"]
        label_cell.value = label
        label_cell.font = Font(bold=True)
        label_cell.border = border
        ws[f"{get_column_letter(start_col+1)}{r}"].border = border
        summary_rows.append(r)

    for client, col in list(col_mapping.items()) + [(None, extra_cols[0])]:
        ws[f"{col}{summary_rows[0]}"].value = f"=SUM({col}{data_start_row}:{col}{curr_data_row-1})"
        q_manifest = product_data[product_data[client_col] == client][qty_col_name].sum() if client else product_data[qty_col_name].sum()
        ws[f"{col}{summary_rows[1]}"].value = q_manifest
        ws[f"{col}{summary_rows[2]}"].value = f"={col}{summary_rows[1]}-{col}{summary_rows[0]}"
        for r in summary_rows:
            ws[f"{col}{r}"].font = Font(bold=True)
            ws[f"{col}{r}"].border = border
            ws[f"{col}{r}"].alignment = center

    for r in summary_rows:
        ws[f"{extra_cols[1]}{r}"].value = f"=SUM({get_column_letter(start_col+2)}{r}:{extra_cols[0]}{r})"
        ws[f"{extra_cols[1]}{r}"].font = Font(bold=True)
        ws[f"{extra_cols[1]}{r}"].border = border
        ws[f"{extra_cols[1]}{r}"].alignment = center
        ws[f"{extra_cols[2]}{r}"].value = f"={extra_cols[1]}{r}"
        ws[f"{extra_cols[2]}{r}"].font = Font(bold=True)
        ws[f"{extra_cols[2]}{r}"].border = border
        ws[f"{extra_cols[2]}{r}"].alignment = center

    return last_col_idx

def gen_table(filepath=None):
    # --- MAIN EXECUTION ---
   if not filepath:
        return False
    try:
        base_name = os.path.basename(sourcefile) 
        file_name_only = os.path.splitext(base_name)[0]

        source_df = pd.read_excel(filepath)
        source_df.columns = source_df.columns.str.strip().str.upper()
        
        wb = Workbook()
        ws = wb.active
        ws.title = f"{file_name_only}"

        ws.merge_cells('A1:G1')
        ws['A1'].value = SHIP_NAME_PLACEHOLDER
        ws['A1'].font = Font(bold=True, size=14)

        specific_keywords = ["BOBINE", "TUBE", "CTP", "BIGBAG"]
        start_col = 1
        all_matched_indices = pd.Index([])

        for keyword in specific_keywords:
            mask = source_df['PRODUITS'].astype(str).str.contains(keyword, case=False, na=False)
            p_data = source_df[mask]
            if not p_data.empty:
                all_matched_indices = all_matched_indices.union(p_data.index)
                last_col_idx = create_product_table(ws, keyword.upper(), p_data, start_col, is_others=False)
                start_col = last_col_idx + 3

        others_data = source_df.drop(all_matched_indices)
        if not others_data.empty:
            create_product_table(ws, "UNITS + PACKAGES", others_data, start_col, is_others=True)

        output_fn = f"{file_name_only}.xlsx"
        wb.save(output_fn)
#        print(f"File '{output_fn}' created successfully.")
        
        output_docx=f"{PATH_DEBRQ}/{file_name_only}.xlsx"
        return output_docx
    except Exception as e:
        print(f"An error occurred: {e}")


