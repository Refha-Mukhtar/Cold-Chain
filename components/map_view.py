import streamlit as st
import folium
from streamlit_folium import st_folium

def render_corridor_map(breakdown_active=False):
    """
    Renders an interactive Folium corridor map (Nashik -> Bhopal -> Delhi).
    If breakdown_active is True, it draws an emergency detour line to Bhopal Cold Hub.
    """
    # Base map centered on Central India
    m = folium.Map(location=[24.0, 77.0], zoom_start=6, tiles="CartoDB dark_matter")

    # Corridor Waypoints
    nashik = [19.9975, 73.7898]
    bhopal = [23.2599, 77.4126]
    delhi = [28.7159, 77.1770]

    # Primary Kisan Rail Corridor Route
    folium.PolyLine(
        locations=[nashik, bhopal, delhi],
        color="#38BDF8",
        weight=4,
        opacity=0.8,
        tooltip="Main Kisan Rail Corridor (Nashik -> Delhi)"
    ).add_to(m)

    # Origin Marker: Nashik Farm Gate
    folium.Marker(
        nashik,
        popup="<b>Nashik Farm Gate</b><br>EV First-Mile Dispatch Point",
        icon=folium.Icon(color="green", icon="leaf")
    ).add_to(m)

    # Destination Marker: Azadpur Mandi, Delhi
    folium.Marker(
        delhi,
        popup="<b>Azadpur Mandi, Delhi</b><br>Target Market Destination",
        icon=folium.Icon(color="blue", icon="shopping-cart")
    ).add_to(m)

    # Emergency Breakdown / Reroute Behavior
    if breakdown_active:
        # Highlight Bhopal as Emergency Salvage Cold Hub
        folium.Marker(
            bhopal,
            popup="<b>🚨 Bhopal Emergency Cold Hub</b><br>Backup EV Reefer Dispatched",
            icon=folium.Icon(color="red", icon="warning-sign")
        ).add_to(m)

        # Red Dashed Detour Line
        folium.PolyLine(
            locations=[nashik, bhopal],
            color="#EF4444",
            weight=6,
            dash_array="8, 8",
            tooltip="🚨 EMERGENCY DETOUR: Rerouted to Bhopal Cold Hub"
        ).add_to(m)
        
        st.error("🚨 **Emergency Detour Active:** Transit breakdown detected! Route redirected to Bhopal Cold Hub.")
    else:
        folium.Marker(
            bhopal,
            popup="<b>Bhopal Transit Junction</b><br>Rail Dwell Time: 15 mins",
            icon=folium.Icon(color="gray", icon="info-sign")
        ).add_to(m)

    # Display Map in Streamlit
    st_folium(m, width="100%", height=420)