import pandas as pd

def calculate_roro_surface(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate surface for RoRo items.
    Formula: surface = surface_per_unit * quantity
    """
    df = df.copy()
    df["quantite"] = pd.to_numeric(df["quantite"], errors="coerce").fillna(0)
    df["surface"] = df["surface_per_unit"] * df["quantite"]
    return df

def calculate_marchandises_surface(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate surface for general merchandise.
    Formula: surface = (surface_per_unit / gerbage) * quantity
    Plus 20%: surface * 1.20
    """
    df = df.copy()
    df["quantite"] = pd.to_numeric(df["quantite"], errors="coerce").fillna(0)
    df["gerbage"] = pd.to_numeric(df["gerbage"], errors="coerce")

    # Avoid division by zero
    valid_gerbage = df["gerbage"] > 0
    df["surface"] = 0.0
    df.loc[valid_gerbage, "surface"] = (
        (df.loc[valid_gerbage, "surface_per_unit"] / df.loc[valid_gerbage, "gerbage"])
        * df.loc[valid_gerbage, "quantite"]
    )

    df["plus_20_percent"] = df["surface"] * 1.20
    return df

def get_roro_total(df: pd.DataFrame) -> float:
    return df["surface"].sum()

def get_marchandises_total(df: pd.DataFrame) -> float:
    return df["surface"].sum()

def get_marchandises_total_plus20(df: pd.DataFrame) -> float:
    return df["plus_20_percent"].sum()