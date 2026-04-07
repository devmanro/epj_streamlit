import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
from datetime import datetime

def render_summary_tab(roro_df: pd.DataFrame, marc_df: pd.DataFrame):
    """Render the summary & export tab."""

    st.markdown("""
    <div style='background: linear-gradient(90deg, #4a1a6b, #7b2d8b);
                padding: 15px; border-radius: 10px; margin-bottom: 20px;'>
        <h2 style='color: white; text-align: center; margin: 0;'>
            📊 TABLEAU DE BORD & EXPORT
        </h2>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI cards ────────────────────────────────────────────────────────────
    roro_total = roro_df["surface"].sum() if "surface" in roro_df.columns else 0
    marc_total = marc_df["surface"].sum() if "surface" in marc_df.columns else 0
    marc_plus20 = marc_df["plus_20_percent"].sum() if "plus_20_percent" in marc_df.columns else 0
    grand_total = roro_total + marc_total

    k1, k2, k3, k4 = st.columns(4)
    _kpi(k1, "🚢 RoRo Total",           f"{roro_total:.2f} M²",  "#1a472a")
    _kpi(k2, "📦 Marchandises Total",   f"{marc_total:.2f} M²",  "#1a3a5c")
    _kpi(k3, "➕ Marchandises +20%",    f"{marc_plus20:.2f} M²", "#5a1a1a")
    _kpi(k4, "📐 GRAND TOTAL",          f"{grand_total:.2f} M²", "#4a1a6b")

    st.markdown("---")

    # ── Charts ───────────────────────────────────────────────────────────────
    st.markdown("### 📈 Visualisations")
    chart1, chart2 = st.columns(2)

    with chart1:
        _render_pie_chart(roro_total, marc_total)

    with chart2:
        _render_roro_bar(roro_df)

    st.markdown("---")
    _render_marc_bar(marc_df)

    st.markdown("---")

    # ── Export ───────────────────────────────────────────────────────────────
    st.markdown("### 💾 Export des données")
    e1, e2 = st.columns(2)

    with e1:
        excel_data = _generate_excel(roro_df, marc_df)
        st.download_button(
            label="📥 Télécharger Excel",
            data=excel_data,
            file_name=f"surfaces_port_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with e2:
        csv_data = _generate_csv(roro_df, marc_df)
        st.download_button(
            label="📥 Télécharger CSV",
            data=csv_data,
            file_name=f"surfaces_port_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _kpi(col, title: str, value: str, bg: str):
    col.markdown(
        f"<div style='background:{bg}; padding:15px; border-radius:10px; "
        f"text-align:center; color:white;'>"
        f"<div style='font-size:0.85em; opacity:0.8;'>{title}</div>"
        f"<div style='font-size:1.5em; font-weight:bold; margin-top:5px;'>{value}</div>"
        f"</div>",
        unsafe_allow_html=True
    )


def _render_pie_chart(roro_total: float, marc_total: float):
    if roro_total + marc_total == 0:
        st.info("Aucune donnée à afficher.")
        return
    fig = px.pie(
        values=[roro_total, marc_total],
        names=["RoRo", "Marchandises"],
        title="Répartition des surfaces",
        color_discrete_map={"RoRo": "#2d6a4f", "Marchandises": "#2e6da4"},
        hole=0.4,
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)


def _render_roro_bar(roro_df: pd.DataFrame):
    active = roro_df[roro_df["surface"] > 0].copy() if "surface" in roro_df.columns else pd.DataFrame()
    if active.empty:
        st.info("Aucune donnée RoRo à afficher.")
        return
    fig = px.bar(
        active,
        x="surface", y="marchandise",
        orientation="h",
        title="Top RoRo par surface",
        color="surface",
        color_continuous_scale="Greens",
        text="surface",
    )
    fig.update_traces(texttemplate="%{text:.1f} M²", textposition="outside")
    fig.update_layout(height=350, showlegend=False, yaxis_title="", xaxis_title="Surface M²")
    st.plotly_chart(fig, use_container_width=True)


def _render_marc_bar(marc_df: pd.DataFrame):
    active = marc_df[marc_df["surface"] > 0].copy() if "surface" in marc_df.columns else pd.DataFrame()
    if active.empty:
        st.info("Aucune donnée Marchandises à afficher.")
        return
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Surface", x=active["marchandise"], y=active["surface"],
        marker_color="#2e6da4", text=active["surface"].round(2),
        textposition="auto",
    ))
    if "plus_20_percent" in active.columns:
        fig.add_trace(go.Bar(
            name="+20%", x=active["marchandise"], y=active["plus_20_percent"],
            marker_color="#90EE90", text=active["plus_20_percent"].round(2),
            textposition="auto",
        ))
    fig.update_layout(
        title="Marchandises : Surface vs +20%",
        barmode="group", height=400,
        xaxis_tickangle=-45,
        yaxis_title="Surface M²",
    )
    st.plotly_chart(fig, use_container_width=True)


def _generate_excel(roro_df: pd.DataFrame, marc_df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        # ── RoRo sheet ───────────────────────────────────────────────────────
        roro_export = roro_df[["marchandise", "surface_per_unit", "quantite", "surface"]].copy()
        roro_export.columns = ["MARCHANDISE", "SURFACE/P M2", "QUANTITE", "SURFACE"]
        roro_export.to_excel(writer, sheet_name="RoRo", index=False, startrow=1)

        wb  = writer.book
        ws  = writer.sheets["RoRo"]

        title_fmt  = wb.add_format({"bold": True, "font_size": 14,
                                    "align": "center", "bg_color": "#c6efce"})
        header_fmt = wb.add_format({"bold": True, "bg_color": "#92d050",
                                    "border": 1, "align": "center"})
        yellow_fmt = wb.add_format({"bg_color": "#ffff00", "border": 1,
                                    "num_format": "0.00", "align": "center"})
        num_fmt    = wb.add_format({"num_format": "0.00", "border": 1, "align": "center"})
        total_fmt  = wb.add_format({"bold": True, "bg_color": "#ffd700",
                                    "num_format": "0.00", "border": 1, "align": "center"})

        ws.merge_range("A1:D1", "SURFACES DES MARCHANDISES RORO", title_fmt)
        for col, name in enumerate(["MARCHANDISE", "SURFACE/P M2", "QUANTITE", "SURFACE"]):
            ws.write(1, col, name, header_fmt)
        for row_i, row in roro_export.iterrows():
            ws.write(row_i + 2, 0, row["MARCHANDISE"])
            ws.write(row_i + 2, 1, row["SURFACE/P M2"], num_fmt)
            ws.write(row_i + 2, 2, row["QUANTITE"],     num_fmt)
            ws.write(row_i + 2, 3, row["SURFACE"],       yellow_fmt)
        last = len(roro_export) + 2
        ws.write(last, 0, "TOTAL", total_fmt)
        ws.write(last, 3, roro_df["surface"].sum(), total_fmt)
        ws.set_column("A:A", 35)
        ws.set_column("B:D", 15)

        # ── Marchandises sheet ───────────────────────────────────────────────
        marc_export = marc_df[["marchandise", "surface_per_unit",
                                "gerbage", "quantite",
                                "surface", "plus_20_percent"]].copy()
        marc_export.columns = ["MARCHANDISE", "SURFACE/P M2",
                                "GERBAGE", "QUANTITE", "SURFACE", "PLUS 20%"]
        marc_export.to_excel(writer, sheet_name="Marchandises", index=False, startrow=1)

        ws2 = writer.sheets["Marchandises"]
        green_fmt = wb.add_format({"bg_color": "#90EE90", "border": 1,
                                   "num_format": "0.00", "align": "center"})
        ws2.merge_range("A1:F1", "SURFACES DES MARCHANDISES", title_fmt)
        for col, name in enumerate(["MARCHANDISE", "SURFACE/P M2",
                                     "GERBAGE", "QUANTITE", "SURFACE", "PLUS 20%"]):
            ws2.write(1, col, name, header_fmt)
        for row_i, row in marc_export.iterrows():
            ws2.write(row_i + 2, 0, row["MARCHANDISE"])
            ws2.write(row_i + 2, 1, row["SURFACE/P M2"], num_fmt)
            ws2.write(row_i + 2, 2, row["GERBAGE"],       num_fmt)
            ws2.write(row_i + 2, 3, row["QUANTITE"],      num_fmt)
            ws2.write(row_i + 2, 4, row["SURFACE"],        yellow_fmt)
            ws2.write(row_i + 2, 5, row["PLUS 20%"],       green_fmt)
        last2 = len(marc_export) + 2
        ws2.write(last2, 0, "TOTAL", total_fmt)
        ws2.write(last2, 4, marc_df["surface"].sum(),        total_fmt)
        ws2.write(last2, 5, marc_df["plus_20_percent"].sum(), total_fmt)
        ws2.set_column("A:A", 35)
        ws2.set_column("B:F", 15)

    return buffer.getvalue()


def _generate_csv(roro_df: pd.DataFrame, marc_df: pd.DataFrame) -> str:
    lines = ["SURFACES DES MARCHANDISES RORO", ""]
    roro_export = roro_df[["marchandise", "surface_per_unit", "quantite", "surface"]].copy()
    roro_export.columns = ["MARCHANDISE", "SURFACE/P M2", "QUANTITE", "SURFACE"]
    lines.append(roro_export.to_csv(index=False))
    lines.append(f"\nTOTAL RORO,,,{roro_df['surface'].sum():.2f}\n")

    lines.append("\nSURFACES DES MARCHANDISES\n")
    marc_export = marc_df[["marchandise", "surface_per_unit",
                            "gerbage", "quantite",
                            "surface", "plus_20_percent"]].copy()
    marc_export.columns = ["MARCHANDISE", "SURFACE/P M2",
                            "GERBAGE", "QUANTITE", "SURFACE", "PLUS 20%"]
    lines.append(marc_export.to_csv(index=False))
    lines.append(
        f"\nTOTAL MARCHANDISES,,,,{marc_df['surface'].sum():.2f},"
        f"{marc_df['plus_20_percent'].sum():.2f}\n"
    )
    return "\n".join(lines)