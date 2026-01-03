import json
import pandas as pd

def extract_to_excel_flattened(json_path, output_path):
    # Load JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # The manifest data is in the first element of the root list
    connaissements = data[0].get('connaissements', [])
    
    final_rows = []

    for bl in connaissements:
        # Get basic BL info
        bl_no = bl.get('num_bl')
        client = bl.get('client_final')
        description = bl.get('description_marchandise')
        
        # Convert Global Weight from KG to Tons (poids_brute / 1000)
        poids_kg = bl.get('poids_brute')
        weight_tons = (poids_kg / 1000) if poids_kg is not None else 0
        
        # 1. Add the BL Header Row
        row = {
            "BL Number": bl_no,
            "Client": client,
            "Description": description,
            "Weight (Tons)": weight_tons,
            "Quantity": bl.get('nombre_colis'),
            "Item Type": bl.get('conditionnement'),
            "Brand": "-",
            "Model": "-",
            "Chassis/Serial": "-",
        }
        final_rows.append(row)
        
        # 2. Add individual vehicle/unit rows if they exist
        items = bl.get('roulants', [])
        if items:
            for item in items:
                item_row = {
                    "BL Number": bl_no,
                    "Client": client,
                    "Description": description,
                    "Item Type": item.get('type'),
                    "Quantity": "-",
                    "Weight (Tons)": "-",
                    "Brand": item.get('marque'),
                    "Model": item.get('modele'),
                    "Chassis/Serial": item.get('numero_chassis'),
                }
                final_rows.append(item_row)

    # Create DataFrame and Export
    df = pd.DataFrame(final_rows)
    
    # Optional: Round the Weight column to 3 decimal places for clean display
    # df['Weight (Tons)'] = pd.to_numeric(df['Weight (Tons)'], errors='coerce').round(3)

    df.to_excel(output_path, index=False)
    
    print(f"Extraction finished.")
    print(f"Total rows generated: {len(df)}")
    print(f"Weights have been converted to Tons.")
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    # Ensure this matches your actual filename
    extract_to_excel_flattened('input.json', 'Manifest_Full_Detail.xlsx')