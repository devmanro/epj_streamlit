import json
import pandas as pd
from datetime import datetime
from assets.constants.constants import (
    COL_ESCALE,
    COL_NAVIRE,
    COL_DATE,
    COL_BL,
    COL_ARTICLE,
    COL_DESIGNATION,
    COL_QUANTITE,
    COL_TONAGE,
    COL_CLIENT,
    COL_CHASSIS_SERIAL,
    COL_MODELE,
    COL_RESTE_TP,
    COL_TYPE,
    COL_PRODUIT,
    COL_SITUATION,
    COL_OBSERVATION,
    COL_POSITION,
    COL_TRANSIT,
    COL_CLES,
    COL_SURFACE,
    COL_DRB_TYPE,
    COL_DATE_ENLEV,
    COL_CARGO_TYPE,
    COL_IMO_NAVIRE
)

def extract_to_excel_flattened(json_path, output_path, st_upload=False):
    if st_upload:
        # Load JSON directly from the Streamlit UploadedFile object
        data = json.load(json_path)
    else:
        # Load JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

    # The manifest data is in the first element of the root list
    connaissements = data[0].get('connaissements', [])
    raw_date = data[0].get('date_manifeste')
    date_col = datetime.strptime(raw_date, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')

    escale=data[0].get('numero_escale')
    imo_navire = data[0].get('imo_navire')
    ship_name=data[0].get('nom_navire')
    cargo_type =data[0].get('type_manifeste') # type_manifeste(diver/roro/etc...)

    final_rows = []

    for bl in connaissements:
        # Get basic BL info
        bl_no = bl.get('num_bl')
        n_article = bl.get('article')
        client = bl.get('client_final')
        nombre_colis = bl.get('nombre_colis')
        surface = bl.get('surface')
       
        conditionnement = bl.get('conditionnement')
        description = bl.get('description_marchandise')
        # Convert Global Weight from KG to Tons (poids_brute / 1000)
        poids_kg = bl.get('poids_brute') or bl.get('poids') 
        weight_tons = (poids_kg / 1000) if poids_kg is not None else 0
        
        # 1. Add the BL Header Row
        row = {
            COL_ESCALE:escale,                        # NAVIRE
            COL_NAVIRE:ship_name ,                    # NAVIRE
            COL_DATE: date_col,                       # DATE
            COL_BL: bl_no,                            # B/L
            COL_ARTICLE: n_article,                   #COL_ARTICLE
            COL_DESIGNATION: description,             # DESIGNATION
            COL_QUANTITE: nombre_colis,               # QUANTITE
            COL_TONAGE: weight_tons,                  # TONAGE
            COL_CLIENT: client,                       # CLIENT
            COL_TYPE:conditionnement ,                # TYPE
            COL_CHASSIS_SERIAL: "-",                  # CHASSIS/SERIAL
            COL_MODELE:"-",
            COL_PRODUIT:"" ,                          # COL_PRODUIT
            COL_RESTE_TP: "-",                        # RESTE T/P
            COL_SITUATION: "-",                       # SITUATION
            COL_OBSERVATION: "-",                     # OBSERVATION
            COL_POSITION: "-",                        # POSITION
            COL_TRANSIT: "-",                         # TRANSIT
            COL_CLES: "-",                            # CLES
            COL_SURFACE: surface,                         # SURFACE
            # DAEMO BREAKER (DRB) TOP BOX TYPE
            COL_DRB_TYPE: "-",
            COL_DATE_ENLEV: "-",                      # DATE ENLEV
            COL_CARGO_TYPE:cargo_type,               # type_manifeste(diver/roro/etc...)
            COL_IMO_NAVIRE: imo_navire,

        }
        final_rows.append(row)

        # 2. Add individual vehicle/unit rows if they exist
        items = bl.get('roulants', [])
        if items:
            for item in items:
                item_row = {
                    COL_ESCALE:escale,
                    COL_NAVIRE: ship_name,                       # NAVIRE
                    COL_DATE: date_col,                    # DATE
                    COL_BL: bl_no,                         # B/L
                    COL_DESIGNATION: description,          # DESIGNATION
                    COL_QUANTITE: "-",                     # QUANTITE
                    COL_TONAGE:  (item.get('poids') / 1000) ,         # TONAGE
                    COL_CLIENT: client,                    # CLIENT
                    # CHASSIS/SERIAL
                    COL_TYPE: item.get('type'),            # TYPE
                    COL_CHASSIS_SERIAL: item.get('numero_chassis'),
                    COL_MODELE:item.get('modele'),
                    COL_PRODUIT:"" ,                       # COL_PRODUIT
                    COL_RESTE_TP: "-",                     # RESTE T/P
                    COL_SITUATION: "-",                    # SITUATION
                    COL_OBSERVATION: (
                        f"{item.get('marque', '')}".strip() or "-"
                        # OBSERVATION (Brand/Model)
                    ),
                    COL_POSITION: "-",                     # POSITION
                    COL_TRANSIT: "-",                      # TRANSIT
                    COL_CLES: "-",                         # CLES
                    COL_SURFACE: surface,                         # SURFACE
                    # DAEMO BREAKER (DRB) TOP BOX TYPE
                    COL_DRB_TYPE: "-",
                    COL_DATE_ENLEV: "-",                   # DATE ENLEV
                    COL_CARGO_TYPE:cargo_type,               # type_manifeste(diver/roro/etc...)
                }
                final_rows.append(item_row)

    # Create DataFrame and Export
    df = pd.DataFrame(final_rows)

    df = df.sort_values(by=COL_CLIENT)
    
    df.to_excel(output_path, index=False)

    # style = doc.styles["Normal"]
    # font = style.font
    # font.name = "Times New Roman"
    # font.size = Pt(12)

    return output_path

 