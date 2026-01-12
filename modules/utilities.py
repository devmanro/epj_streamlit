
from modules.processor import calculate_daily_totals,calculate_surface


def utilities(st):
    with st.expander("Surface Area Calculator"):
        inp_qty=st.number_input("Quantity/Weight", min_value=1)
        surface=calculate_surface(inp_qty)
        st.success(f"Estimated Surface Needed: {surface} m²")

    












    
