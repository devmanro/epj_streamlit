import pandas as pd

def calculate_daily_totals(df):
    # Example logic to group by Client and Merchandise
    summary = df.groupby(['Client', 'Merchandise']).agg({
        'poids brute': 'sum',
        'nombre colis': 'sum'
    }).reset_index()
    return summary
    
def calculate_surface(input_qty=1,type_good="bulk"):
    qty = input_qty
    # Add your math logic here
    surface = qty * 1.5  # Example multiplier
    return qty