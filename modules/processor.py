import pandas as pd

def calculate_daily_totals(df):
    # Example logic to group by Client and Merchandise
    summary = df.groupby(['Client', 'Merchandise']).agg({
        'poids brute': 'sum',
        'nombre colis': 'sum'
    }).reset_index()
    return summary
    