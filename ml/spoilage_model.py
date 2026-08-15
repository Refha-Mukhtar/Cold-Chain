import streamlit as st
import numpy as np
import plotly.graph_objects as go

def render_decay_curves(delay_hours=0):
    """
    Simulates Arrhenius thermal decay kinetics and renders Plotly freshness curves.
    Calculates Remaining Shelf Life (RSL) based on simulated transit delay.
    """
    initial_rsl_hours = 48.0
    
    # Thermal acceleration stress factor based on transit delay
    thermal_stress = 1.0 + (delay_hours * 0.075)
    remaining_rsl = max(0.0, initial_rsl_hours - (delay_hours * 1.6 * thermal_stress))
    freshness_pct = max(0, int((remaining_rsl / initial_rsl_hours) * 100))

    # Top Metric Scorecards
    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Remaining Shelf Life (RSL)", 
        f"{remaining_rsl:.1f} Hours", 
        delta=f"{freshness_pct}% Quality Retained"
    )
    m2.metric(
        "Cargo Core Temp", 
        f"{3.5 + (delay_hours * 0.18):.1f} °C", 
        delta="Target Range: 1.0 - 4.0 °C"
    )
    m3.metric(
        "Ambient Exposure", 
        "38.5 °C", 
        delta="Summer Highway Heat", 
        delta_color="inverse"
    )

    # Generate Decay Simulation Timeline (0 to 48 Hours)
    timeline_hours = np.linspace(0, 48, 60)
    
    # Core temperature climb curve over time
    core_temps = 3.5 + (0.12 * timeline_hours) + (0.004 * (timeline_hours ** 2))
    
    # Freshness degradation index curve
    quality_curve = np.clip(100 - (1.85 * timeline_hours * thermal_stress), 0, 100)

    # Plot Dual-Axis Temperature & Freshness Chart
    fig = go.Figure()
    
    # Freshness Curve
    fig.add_trace(go.Scatter(
        x=timeline_hours, 
        y=quality_curve,
        name="Freshness Index (%)",
        mode="lines",
        line=dict(color="#10B981" if remaining_rsl > 12 else "#EF4444", width=3)
    ))
    
    # Internal Reefer Temp Curve
    fig.add_trace(go.Scatter(
        x=timeline_hours, 
        y=core_temps,
        name="Core Temp (°C)",
        mode="lines",
        line=dict(color="#F59E0B", width=2, dash="dot"),
        yaxis="y2"
    ))

    # Chart Styling
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        height=320,
        margin=dict(l=10, r=10, t=25, b=10),
        xaxis=dict(title="Transit Elapsed Time (Hours)", showgrid=True, gridcolor="#1F2937"),
        yaxis=dict(title="Freshness Quality (%)", range=[0, 105], showgrid=True, gridcolor="#1F2937"),
        yaxis2=dict(title="Core Temp (°C)", overlaying="y", side="right", range=[0, 25]),
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center")
    )

    st.plotly_chart(fig, use_container_width=True)