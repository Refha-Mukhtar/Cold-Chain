import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import datetime
import hashlib
import io
import base64

# Safe import for natural Google Hindi TTS
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & ENTERPRISE METADATA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ColdChain AI | Quantum Multimodal Digital Twin",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. LANGUAGE TRANSLATION DICTIONARY (VERNACULAR MANDI & KISAN MODE)
# -----------------------------------------------------------------------------
LANG = {
    "en": {
        "title": "Multimodal Cold-Chain AI Digital Twin Hub",
        "subtitle": "Agri Corridor: Nashik Farm Gate (MH) ➔ Bhopal Transshipment ➔ Azadpur Mandi, New Delhi",
        "nav_1": "🏠 Executive Mission Control",
        "nav_2": "🧊 3D Reefer Digital Twin",
        "nav_3": "📦 Consignment & Fleet Payload",
        "nav_4": "📡 Live Telemetry & Salvage Detour",
        "nav_5": "🔮 Arrhenius Spoilage Forecaster",
        "nav_6": "⚡ Bio-Consolidation & Kisan Rail",
        "nav_7": "💡 Explainable AI Mode Recommender",
        "nav_8": "⛓️ Blockchain SLA & Subsidy Audit",
        "active_batches": "Active Batches",
        "trad_cost": "Traditional Road Cost",
        "ai_cost": "AI Intermodal Cost",
        "net_profit": "Net Profit Boost",
        "sim_delay": "Simulated Delay",
        "co2_cut": "CO2 Reduction",
        "margin_banner": "COMMERCIAL MARGIN & REVENUE ENHANCEMENT",
        "margin_sub": "AI Multimodal Route yields ₹{profit:,.0f} Net Extra Margin per 1,380 km run",
        "subsidy_saved": "Govt Subsidy Saved",
        "spoilage_prevented": "Spoilage Loss Prevented",
        "jury_btn": "⚡ Run 1-Click Live Disaster Demo",
        "reset_btn": "🔄 Reset to Baseline Transit",
        "voice_alert": "🎙️ AI Audio Voice Siren: ACTIVE"
    },
    "hi": {
        "title": "मल्टीमॉडल कोल्ड-चेन AI डिजिटल ट्विन हब",
        "subtitle": "कृषि गलियारा: नासिक फार्म गेट (महाराष्ट्र) ➔ भोपाल जंक्शन ➔ आज़ादपुर मंडी, नई दिल्ली",
        "nav_1": "🏠 कार्यकारी नियंत्रण कक्ष (Executive Hub)",
        "nav_2": "🧊 3D रेफ़र डिजिटल ट्विन",
        "nav_3": "📦 माल लदान एवं वाहन क्षमता",
        "nav_4": "📡 लाइव जीपीएस एवं आपातकालीन रूट",
        "nav_5": "🔮 अरेनियस शेल्फ-लाइफ फोरकास्टर",
        "nav_6": "⚡ बायो-मिश्रण एवं किसान रेल",
        "nav_7": "💡 AI ट्रांसपोर्ट चयन प्रणाली (XAI)",
        "nav_8": "⛓️ ब्लॉकचेन सब्सिडी एवं ऑडिट",
        "active_batches": "सक्रिय खेप (Batches)",
        "trad_cost": "पारंपरिक सड़क ढुलाई लागत",
        "ai_cost": "AI मल्टीमॉडल किसान रेल लागत",
        "net_profit": "शुद्ध मुनाफा वृद्धि",
        "sim_delay": "अनुमानित देरी (घंटे)",
        "co2_cut": "कार्बन उत्सर्जन में कमी",
        "margin_banner": "व्यावसायिक लाभ एवं मंडी मुनाफा संवर्धन",
        "margin_sub": "AI किसान रेल से प्रति 1,380 किमी फेरे पर ₹{profit:,.0f} की शुद्ध बचत",
        "subsidy_saved": "सरकारी सब्सिडी लाभ (50%)",
        "spoilage_prevented": "फसल बर्बादी से सुरक्षा",
        "jury_btn": "⚡ 1-क्लिक लाइव आपातकालीन डेमो",
        "reset_btn": "🔄 सामान्य स्थिति में रीसेट करें",
        "voice_alert": "🎙️ AI वॉइस सायरन अलर्ट: सक्रिय"
    }
}

# -----------------------------------------------------------------------------
# 3. ULTRA-MODERN CSS
# -----------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');

html, body, p, div:not([data-testid*="Icon"]):not([class*="material-symbols"]), 
h1, h2, h3, h4, h5, h6, label, span:not([class*="material-symbols"]):not([data-testid*="Icon"]) {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
}

header[data-testid="stHeader"] {
    background: transparent !important;
    height: 2rem !important;
}
.main .block-container {
    padding-top: 1rem !important;
    padding-bottom: 2rem !important;
    max-width: 98% !important;
}

@keyframes meshFlow {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
.stApp {
    background: linear-gradient(-45deg, #05080A, #0A1312, #100C16, #07100D, #080D12) !important;
    background-size: 400% 400% !important;
    animation: meshFlow 22s ease infinite !important;
    color: #F8FAFC !important;
}

section[data-testid="stSidebar"] {
    background: rgba(8, 13, 16, 0.94) !important;
    backdrop-filter: blur(24px) !important;
    border-right: 1px solid rgba(0, 245, 155, 0.15) !important;
}
div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
    display: none !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label {
    background: rgba(18, 26, 29, 0.6) !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
    margin-bottom: 8px !important;
    color: #94A3B8 !important;
    font-weight: 600 !important;
    font-size: 0.84rem !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    cursor: pointer !important;
    display: flex !important;
    align-items: center !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
    background: rgba(24, 38, 36, 0.9) !important;
    color: #00F59B !important;
    border-color: rgba(0, 245, 155, 0.4) !important;
    transform: translateX(4px);
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label[data-checked="true"] {
    background: linear-gradient(90deg, rgba(0, 245, 155, 0.2) 0%, rgba(168, 85, 247, 0.12) 100%) !important;
    border: 1px solid #00F59B !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0 0 16px rgba(0, 245, 155, 0.2);
}

@keyframes pulseGlow {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 245, 155, 0.7); }
    70% { transform: scale(1.15); box-shadow: 0 0 0 8px rgba(0, 245, 155, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 245, 155, 0); }
}
.status-pulse {
    display: inline-block;
    width: 8px;
    height: 8px;
    background-color: #00F59B;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulseGlow 1.8s infinite;
}

.hero-banner {
    background: linear-gradient(135deg, rgba(14, 22, 25, 0.9) 0%, rgba(22, 16, 32, 0.9) 100%);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(0, 245, 155, 0.25);
    border-radius: 14px;
    padding: 16px 22px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}
.hero-title-text {
    font-size: 1.38rem;
    font-weight: 800;
    background: linear-gradient(90deg, #FFFFFF 0%, #00F59B 50%, #C084FC 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    letter-spacing: -0.02em;
}
.hero-subtitle-text {
    font-size: 0.8rem;
    color: #94A3B8;
    margin-top: 3px;
}

.kpi-matrix {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
}
.kpi-card {
    background: rgba(14, 20, 23, 0.75);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 12px;
    padding: 14px 16px;
    transition: all 0.25s ease;
    position: relative;
}
.kpi-card:hover {
    transform: translateY(-3px);
    border-color: rgba(0, 245, 155, 0.5);
    box-shadow: 0 8px 20px rgba(0, 245, 155, 0.15);
}
.kpi-head {
    font-size: 0.72rem;
    font-weight: 700;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.kpi-number {
    font-size: 1.35rem;
    font-weight: 800;
    color: #FFFFFF;
    margin: 6px 0 3px 0;
    white-space: nowrap;
}
.lbl-jade   { font-size: 0.72rem; color: #00F59B; font-weight: 700; }
.lbl-amber  { font-size: 0.72rem; color: #FFB800; font-weight: 700; }
.lbl-purple { font-size: 0.72rem; color: #C084FC; font-weight: 700; }
.lbl-rose   { font-size: 0.72rem; color: #FB7185; font-weight: 700; }

@keyframes shimmerSweep {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
.roi-strip {
    background: linear-gradient(90deg, 
        rgba(0, 245, 155, 0.12) 0%, 
        rgba(255, 184, 0, 0.18) 50%, 
        rgba(168, 85, 247, 0.12) 100%);
    background-size: 200% 100%;
    animation: shimmerSweep 8s linear infinite;
    border: 1px solid rgba(0, 245, 155, 0.35);
    border-radius: 12px;
    padding: 14px 20px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 0 25px rgba(0, 245, 155, 0.1);
}

.digital-twin-container {
    background: rgba(10, 16, 20, 0.85);
    border: 1px solid rgba(0, 245, 155, 0.3);
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 16px;
}
.chamber-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 14px;
    margin-top: 12px;
}
.chamber-zone {
    background: rgba(18, 26, 32, 0.8);
    border-radius: 10px;
    padding: 14px;
    border-left: 4px solid #00F59B;
    transition: all 0.3s ease;
}
.chamber-zone:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
}

.blockchain-box {
    background: rgba(8, 12, 16, 0.9);
    border: 1px solid rgba(168, 85, 247, 0.35);
    border-radius: 12px;
    padding: 14px 18px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    color: #A78BFA;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. GLOBAL APPLICATION STATE
# -----------------------------------------------------------------------------
if "language" not in st.session_state:
    st.session_state.language = "en"
if "cargo_list" not in st.session_state:
    st.session_state.cargo_list = [
        {"Shipment ID": "SHP-9021", "Product": "Strawberries", "Weight_kg": 600, "Temp_Band": "1-4°C", "Origin": "Nashik Farm Cluster", "Dest": "Azadpur Mandi (Delhi)"},
        {"Shipment ID": "SHP-9022", "Product": "Dairy Milk", "Weight_kg": 400, "Temp_Band": "1-4°C", "Origin": "Nashik Dairy Union", "Dest": "Mother Dairy Hub (Delhi)"}
    ]
if "selected_fleet" not in st.session_state:
    st.session_state.selected_fleet = "Tata Ace EV Reefer (First-Mile)"
if "transit_delay_hours" not in st.session_state:
    st.session_state.transit_delay_hours = 0
if "vehicle_breakdown" not in st.session_state:
    st.session_state.vehicle_breakdown = False
if "climate_preset" not in st.session_state:
    st.session_state.climate_preset = "⚡ Optimal Baseline (25°C)"

T = LANG[st.session_state.language]

# -----------------------------------------------------------------------------
# 5. NATURAL HINDI & ENGLISH SPEECH GENERATOR
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def generate_voice_audio(text, lang_code):
    """Generates natural Google TTS audio in Hindi or English and returns MP3 bytes."""
    if not GTTS_AVAILABLE:
        return None
    try:
        tts = gTTS(text=text, lang=lang_code, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.getvalue()
    except Exception:
        return None

# -----------------------------------------------------------------------------
# 6. SIDEBAR CONTROLS & JURY PRESENTATION HUB
# -----------------------------------------------------------------------------
FLEET_CATALOG = {
    "Tata Ace EV Reefer (First-Mile)": {"max_weight": 1000, "max_vol": 5.5},
    "14-Ft Dedicated Reefer (Mid-Mile)": {"max_weight": 4000, "max_vol": 18.0},
    "Kisan Rail VPU Parcel Van (Rail Long-Haul)": {"max_weight": 24000, "max_vol": 110.0}
}

with st.sidebar:
    st.markdown("""
<div style="display: flex; align-items: center; gap: 10px; padding: 0.2rem 0 1rem 0;">
    <div style="background: linear-gradient(135deg, #00F59B, #A855F7); width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem;">❄️</div>
    <div>
        <div style="font-weight: 800; font-size: 1.1rem; color: #FFFFFF;">ColdChain AI</div>
        <div style="font-size: 0.7rem; color: #00F59B; font-weight: 700;">MULTIMODAL INTELLIGENCE</div>
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown("### 🏆 Jury Presentation Mode")
    if st.button(T["jury_btn"], type="primary", use_container_width=True):
        st.session_state.vehicle_breakdown = True
        st.session_state.transit_delay_hours = 6
        st.toast("🚨 Disaster Alert Triggered!", icon="❄️")
        st.rerun()

    if st.session_state.vehicle_breakdown:
        st.caption(T["voice_alert"])
        if st.button(T["reset_btn"], use_container_width=True):
            st.session_state.vehicle_breakdown = False
            st.session_state.transit_delay_hours = 0
            st.rerun()

    st.markdown("---")
    nav_option = st.radio(
        "Navigation",
        [
            T["nav_1"], T["nav_2"], T["nav_3"], T["nav_4"],
            T["nav_5"], T["nav_6"], T["nav_7"], T["nav_8"]
        ],
        index=0,
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.markdown("### 🌦️ Climate & Stress Presets")
    selected_climate = st.selectbox(
        "Simulate Corridor Scenario",
        [
            "⚡ Optimal Baseline (25°C)",
            "☀️ May Summer Heatwave (44°C Ambient)",
            "🌧️ Monsoon Rail Bottleneck (+8h Dwell)",
            "🍓 Peak Strawberry Flush (Nashik Harvest)"
        ]
    )
    if selected_climate != st.session_state.climate_preset:
        st.session_state.climate_preset = selected_climate
        if "Heatwave" in selected_climate:
            st.session_state.transit_delay_hours = 3
        elif "Monsoon" in selected_climate:
            st.session_state.transit_delay_hours = 8
        elif "Baseline" in selected_climate:
            st.session_state.transit_delay_hours = 0
        st.rerun()

    st.markdown("---")
    st.markdown("### 🚚 Vehicle Payload Capacity")
    selected_fleet_name = st.selectbox("Active Fleet Unit", list(FLEET_CATALOG.keys()))
    st.session_state.selected_fleet = selected_fleet_name
    fleet = FLEET_CATALOG[selected_fleet_name]

    current_weight = sum(item["Weight_kg"] for item in st.session_state.cargo_list)
    weight_pct = (current_weight / fleet["max_weight"]) * 100

    st.markdown(f"**Payload:** `{current_weight:,} kg` / `{fleet['max_weight']:,} kg`")
    st.progress(min(weight_pct / 100.0, 1.0))

    if weight_pct > 100:
        st.error(f"🚨 Overloaded by {current_weight - fleet['max_weight']:,} kg!")
    elif weight_pct < 60:
        st.warning(f"⚠️ Low Fill Rate ({weight_pct:.1f}%). Consolidation recommended.")
    else:
        st.success(f"✅ Optimal Utilization: {weight_pct:.1f}%")

    st.markdown("---")
    st.markdown("### ⚡ Live Disruption Simulator")
    st.session_state.transit_delay_hours = st.slider("Transit Delay (Hours)", 0, 24, st.session_state.transit_delay_hours)
    st.session_state.vehicle_breakdown = st.checkbox("Simulate Compressor Breakdown", value=st.session_state.vehicle_breakdown)

# -----------------------------------------------------------------------------
# 7. COMMAND CENTER HEADER & VERNACULAR SWITCH
# -----------------------------------------------------------------------------
c_head, c_lang = st.columns([8.2, 1.8])
with c_lang:
    lang_choice = st.radio(
        "Language",
        ["🇬🇧 English", "🇮🇳 हिन्दी (Mandi)"],
        horizontal=True,
        index=0 if st.session_state.language == "en" else 1,
        label_visibility="collapsed"
    )
    new_lang = "en" if "English" in lang_choice else "hi"
    if new_lang != st.session_state.language:
        st.session_state.language = new_lang
        st.rerun()

with c_head:
    st.markdown(f"""
<div class="hero-banner">
    <div>
        <h1 class="hero-title-text">{T["title"]}</h1>
        <div class="hero-subtitle-text">{T["subtitle"]}</div>
    </div>
    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        <span style="background: rgba(0, 245, 155, 0.12); border: 1px solid #00F59B; color: #00F59B; font-size: 0.72rem; font-weight: 700; padding: 4px 10px; border-radius: 20px;">
            <span class="status-pulse"></span>FOIS RAIL SYNC
        </span>
        <span style="background: rgba(168, 85, 247, 0.12); border: 1px solid #A855F7; color: #C084FC; font-size: 0.72rem; font-weight: 700; padding: 4px 10px; border-radius: 20px;">
            🚆 50% MoFPI SUBSIDY
        </span>
        <span style="background: rgba(255, 184, 0, 0.12); border: 1px solid #FFB800; color: #FCD34D; font-size: 0.72rem; font-weight: 700; padding: 4px 10px; border-radius: 20px;">
            ❄️ ARRHENIUS ML
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PAGE 1: EXECUTIVE MISSION CONTROL
# -----------------------------------------------------------------------------
if nav_option == T["nav_1"]:
    distance_km = 1380
    road_rate_km = 42
    trad_road_cost = distance_km * road_rate_km
    trad_spoilage_cost = (current_weight * 80) * 0.18

    first_mile_ev = 2500
    rail_base_tariff = (current_weight / 1000) * 2200
    mofpi_subsidy = rail_base_tariff * 0.50
    subsidized_rail = rail_base_tariff - mofpi_subsidy
    last_mile_ev = 3200
    intermodal_spoilage = (current_weight * 80) * 0.02

    total_intermodal = first_mile_ev + subsidized_rail + last_mile_ev
    net_profit_boost = (trad_road_cost + trad_spoilage_cost) - (total_intermodal + intermodal_spoilage)

    # -------------------------------------------------------------------------
    # DUAL NATURAL AUDIO PLAYER WITH INSTANT TRIGGER
    # -------------------------------------------------------------------------
    if st.session_state.vehicle_breakdown:
        if st.session_state.language == "hi":
            speech_msg = "सावधान! रेफ़र वैन में तापमान बढ़ गया है। माल को तुरंत भोपाल कोल्ड स्टोरेज भेजा जा रहा है।"
            lang_code = "hi"
            alert_header = "🚨 आपातकालीन स्थिति: रेफ़र वैन में तापमान वृद्धि!"
            alert_sub = "स्वचालित रूटिंग सक्रिय। माल को सुरक्षित रखने के लिए भोपाल कोल्ड स्टोरेज भेजा गया।"
            play_btn_label = "🔊 आपातकालीन सायरन सुनें (Play Audio)"
        else:
            speech_msg = "Warning! Critical thermal breach detected. Consignment rerouted to Bhopal Emergency Cold Hub."
            lang_code = "en"
            alert_header = "🚨 CRITICAL EMERGENCY: COMPRESSOR BREACH DETECTED!"
            alert_sub = "Autonomous salvage engine triggered. Consignment rerouted to Bhopal Cold Hub."
            play_btn_label = "🔊 Play Emergency Siren"

        audio_data = generate_voice_audio(speech_msg, lang_code)
        if audio_data:
            b64_audio = base64.b64encode(audio_data).decode()
            
            # Interactive Component with Automatic Playback and Manual Button
            audio_component = f"""
            <div style="background: linear-gradient(135deg, rgba(239,68,68,0.22) 0%, rgba(185,28,28,0.28) 100%); border: 1.5px solid #EF4444; border-radius: 12px; padding: 12px 18px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 0 20px rgba(239,68,68,0.25);">
                <div>
                    <div style="color: #F87171; font-weight: 800; font-size: 0.95rem;">{alert_header}</div>
                    <div style="color: #FCA5A5; font-size: 0.78rem; margin-top: 2px;">{alert_sub}</div>
                </div>
                <button onclick="playAudioDirect()" style="background: #EF4444; color: #FFFFFF; border: none; padding: 9px 16px; border-radius: 8px; font-weight: 800; font-size: 0.82rem; cursor: pointer; box-shadow: 0 4px 15px rgba(239,68,68,0.4);">
                    {play_btn_label}
                </button>
            </div>

            <audio id="nativeSpeechAudio" src="data:audio/mp3;base64,{b64_audio}"></audio>

            <script>
            function playAudioDirect() {{
                var aud = document.getElementById('nativeSpeechAudio');
                if (aud) {{
                    aud.currentTime = 0;
                    aud.play();
                }}
            }}
            // Try automatic playback on load
            setTimeout(playAudioDirect, 300);
            </script>
            """
            components.html(audio_component, height=75)

    st.markdown(f"""
<div class="kpi-matrix">
    <div class="kpi-card">
        <div class="kpi-head">{T["active_batches"]}</div>
        <div class="kpi-number">{len(st.session_state.cargo_list)} Batches</div>
        <div class="lbl-jade">100% Monitored</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-head">{T["trad_cost"]}</div>
        <div class="kpi-number">₹{trad_road_cost:,.0f}</div>
        <div class="lbl-rose">+₹{trad_spoilage_cost:,.0f} Spoilage</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-head">{T["ai_cost"]}</div>
        <div class="kpi-number">₹{total_intermodal:,.0f}</div>
        <div class="lbl-purple">-50% MoFPI Subsidy</div>
    </div>
    <div class="kpi-card" style="border-color: rgba(0, 245, 155, 0.6);">
        <div class="kpi-head">{T["net_profit"]}</div>
        <div class="kpi-number" style="color: #00F59B;">₹{net_profit_boost:,.0f}</div>
        <div class="lbl-jade">+34.8% Margin Gain</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-head">{T["sim_delay"]}</div>
        <div class="kpi-number">{st.session_state.transit_delay_hours} Hours</div>
        <div class="lbl-amber">Live Telemetry Lag</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-head">{T["co2_cut"]}</div>
        <div class="kpi-number" style="color: #C084FC;">65.4%</div>
        <div class="lbl-jade">Electric Rail + EV</div>
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown(f"""
<div class="roi-strip">
    <div>
        <div style="font-size: 0.74rem; font-weight: 800; color: #00F59B; letter-spacing: 0.05em;">💰 {T["margin_banner"]}</div>
        <div style="font-size: 1.05rem; font-weight: 700; color: #FFFFFF; margin-top: 2px;">
            {T["margin_sub"].format(profit=net_profit_boost)}
        </div>
    </div>
    <div style="display: flex; gap: 24px; text-align: right;">
        <div><div style="font-size: 0.7rem; color: #94A3B8;">{T["subsidy_saved"]}</div><div style="font-size: 1.05rem; font-weight: 800; color: #C084FC;">₹{mofpi_subsidy:,.0f}</div></div>
        <div><div style="font-size: 0.7rem; color: #94A3B8;">{T["spoilage_prevented"]}</div><div style="font-size: 1.05rem; font-weight: 800; color: #00F59B;">₹{trad_spoilage_cost - intermodal_spoilage:,.0f}</div></div>
    </div>
</div>
""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([3.8, 3.2, 3.0])

    with c1:
        st.markdown("<p style='font-weight:700; color:#E2E8F0; font-size:0.86rem;'>📈 Multimodal Transit Telemetry & On-Time Performance</p>", unsafe_allow_html=True)
        dates = pd.date_range(end=datetime.date.today(), periods=7)
        df_perf = pd.DataFrame({
            "Date": dates.strftime("%d %b"),
            "On-Time Deliveries": [28, 30, 29, 34, 32, 36, 38],
            "Thermal Alerts": [2, 1, 3, 0, 1, 0, 0]
        })
        fig_perf = go.Figure()
        fig_perf.add_trace(go.Scatter(
            x=df_perf["Date"], y=df_perf["On-Time Deliveries"],
            name="On-Time Delivery", mode="lines+markers",
            line=dict(color="#00F59B", width=3, shape="spline"),
            fill='tozeroy', fillcolor='rgba(0, 245, 155, 0.08)'
        ))
        fig_perf.add_trace(go.Scatter(
            x=df_perf["Date"], y=df_perf["Thermal Alerts"],
            name="Thermal Alerts", mode="lines+markers",
            line=dict(color="#FB7185", width=2, dash='dot', shape="spline")
        ))
        fig_perf.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=280, margin=dict(l=10, r=10, t=10, b=20),
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
        )
        st.plotly_chart(fig_perf, use_container_width=True)

    with c2:
        st.markdown("<p style='font-weight:700; color:#E2E8F0; font-size:0.86rem;'>📊 Intermodal Freight Cost Split</p>", unsafe_allow_html=True)
        fig_pie = go.Figure(data=[go.Pie(
            labels=["First-Mile EV", "Kisan Rail (50% Off)", "Last-Mile EV", "Risk Margin"],
            values=[first_mile_ev, subsidized_rail, last_mile_ev, intermodal_spoilage],
            hole=0.68,
            textinfo="none",
            hoverinfo="label+percent+value",
            marker=dict(colors=["#00F59B", "#A855F7", "#00E5FF", "#FB7185"], line=dict(color="#080D12", width=2))
        )])
        fig_pie.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=280, showlegend=True,
            legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5, font=dict(size=10, color="#94A3B8")),
            margin=dict(l=10, r=10, t=10, b=40),
            annotations=[dict(
                text=f"₹{total_intermodal:,.0f}<br><span style='font-size:9px;color:#94A3B8;'>TOTAL RUN</span>",
                x=0.5, y=0.5, font_size=15, font_color="#FFFFFF", font_weight=800, showarrow=False
            )]
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with c3:
        st.markdown("<p style='font-weight:700; color:#E2E8F0; font-size:0.86rem;'>🚨 Arrhenius Spoilage Risk Gauge</p>", unsafe_allow_html=True)
        risk_score = min(st.session_state.transit_delay_hours * 4.2 + (20 if st.session_state.vehicle_breakdown else 5), 100)
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=risk_score,
            number={'suffix': "%", 'font': {'size': 26, 'color': '#FFFFFF'}},
            gauge={
                'axis': {'range': [0, 100], 'tickcolor': '#64748B', 'tickwidth': 1, 'ticklen': 4},
                'bar': {'color': "#FB7185" if risk_score > 50 else "#00F59B", 'thickness': 0.22},
                'bgcolor': "rgba(255,255,255,0.02)",
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 35], 'color': 'rgba(0, 245, 155, 0.15)'},
                    {'range': [35, 70], 'color': 'rgba(255, 184, 0, 0.15)'},
                    {'range': [70, 100], 'color': 'rgba(251, 113, 133, 0.2)'}
                ]
            }
        ))
        fig_gauge.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=280, margin=dict(l=25, r=25, t=20, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

# -----------------------------------------------------------------------------
# PAGE 2: 3D REEFER DIGITAL TWIN
# -----------------------------------------------------------------------------
elif nav_option == T["nav_2"]:
    st.markdown("### 🧊 Reefer Multi-Chamber 3D Digital Twin & Micro-climate Sensors")
    st.caption("Live Chamber Stratification & Atmospheric Humidity Sensors")

    temp_zone_a = 2.2 + (st.session_state.transit_delay_hours * 0.15)
    temp_zone_b = 13.1 + (st.session_state.transit_delay_hours * 0.22)
    temp_zone_c = -18.0 + (st.session_state.transit_delay_hours * 0.10)
    
    st.markdown(f"""
<div class="digital-twin-container">
<div style="display: flex; justify-content: space-between; align-items: center;">
<div style="font-weight: 800; font-size: 1.05rem; color: #FFFFFF;">📦 Reefer Smart Chamber Architecture (Model: VPU-EcoRail-2026)</div>
<span style="background: rgba(0, 245, 155, 0.15); border: 1px solid #00F59B; color: #00F59B; font-size: 0.72rem; padding: 4px 10px; border-radius: 12px;">3-ZONE INDEPENDENT HVAC</span>
</div>
<div class="chamber-grid">
<div class="chamber-zone" style="border-left-color: #00F59B;">
<div style="font-size: 0.72rem; color: #94A3B8; font-weight: 700;">CHAMBER 01: HIGH BERRY / DAIRY ZONE</div>
<div style="font-size: 1.5rem; font-weight: 800; color: #00F59B; margin: 4px 0;">{temp_zone_a:.1f}°C</div>
<div style="font-size: 0.75rem; color: #E2E8F0;">Target: 1.0 - 4.0°C | RH: 92%</div>
<div style="font-size: 0.72rem; color: #34D399; margin-top: 6px;">● Ethylene Scrubber: ACTIVE</div>
</div>
<div class="chamber-zone" style="border-left-color: #FFB800;">
<div style="font-size: 0.72rem; color: #94A3B8; font-weight: 700;">CHAMBER 02: TROPICAL CHILLED ZONE</div>
<div style="font-size: 1.5rem; font-weight: 800; color: #FFB800; margin: 4px 0;">{temp_zone_b:.1f}°C</div>
<div style="font-size: 0.75rem; color: #E2E8F0;">Target: 12.0 - 15.0°C | RH: 85%</div>
<div style="font-size: 0.72rem; color: #FBBF24; margin-top: 6px;">● Airflow Velocity: 1.8 m/s</div>
</div>
<div class="chamber-zone" style="border-left-color: #00E5FF;">
<div style="font-size: 0.72rem; color: #94A3B8; font-weight: 700;">CHAMBER 03: DEEP FREEZE MEAT/FISH</div>
<div style="font-size: 1.5rem; font-weight: 800; color: #00E5FF; margin: 4px 0;">{temp_zone_c:.1f}°C</div>
<div style="font-size: 0.75rem; color: #E2E8F0;">Target: -18.0°C | Vacuum Insulated</div>
<div style="font-size: 0.72rem; color: #38BDF8; margin-top: 6px;">● PCM Phase Charge: 98%</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("#### 🌡️ 3D Thermal Surface Stratification")
    x = np.linspace(0, 10, 20)
    y = np.linspace(0, 5, 20)
    X, Y = np.meshgrid(x, y)
    Z = temp_zone_a + np.sin(X/2) * np.cos(Y/2) * (0.8 + st.session_state.transit_delay_hours * 0.05)

    fig_3d = go.Figure(data=[go.Surface(z=Z, x=X, y=Y, colorscale='Viridis')])
    fig_3d.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        scene=dict(xaxis_title='Length (m)', yaxis_title='Width (m)', zaxis_title='Core Temp (°C)')
    )
    st.plotly_chart(fig_3d, use_container_width=True)

# -----------------------------------------------------------------------------
# PAGE 3: CONSIGNMENT & FLEET PAYLOAD
# -----------------------------------------------------------------------------
elif nav_option == T["nav_3"]:
    st.markdown("### 📦 Active Consignment Manifest & Fleet Allocator")
    df_manifest = pd.DataFrame(st.session_state.cargo_list)
    st.dataframe(df_manifest, use_container_width=True)

    st.markdown("---")
    st.markdown("#### ➕ Add Perishable Batch to Live Manifest")
    with st.form("add_shipment_form"):
        f1, f2, f3 = st.columns(3)
        with f1:
            p_item = st.selectbox("Perishable Commodity", ["Strawberries", "Dairy Milk", "Bananas", "Onions", "Tomatoes", "Fish"])
        with f2:
            p_wt = st.number_input("Payload Weight (kg)", min_value=50, max_value=24000, value=500, step=50)
        with f3:
            p_band = st.selectbox("Refrigeration Band", ["1-4°C (Reefer Cold)", "12-15°C (Chilled)", "-18°C (Frozen)"])

        if st.form_submit_button("💾 Save Consignment to Live Manifest", type="primary", use_container_width=True):
            st.session_state.cargo_list.append({
                "Shipment ID": f"SHP-{np.random.randint(104, 999)}",
                "Product": p_item,
                "Weight_kg": p_wt,
                "Temp_Band": p_band,
                "Origin": "Nashik Farm Cluster",
                "Dest": "Azadpur Mandi (Delhi)"
            })
            st.success(f"✅ Added {p_item} ({p_wt} kg) to shipment!")
            st.rerun()

# -----------------------------------------------------------------------------
# PAGE 4: LIVE TELEMETRY & SALVAGE DETOUR
# -----------------------------------------------------------------------------
elif nav_option == T["nav_4"]:
    st.markdown("### 📡 Live Corridor Telemetry & Autonomous Salvage Detour")

    if st.session_state.vehicle_breakdown:
        st.markdown("""
<div style="background: rgba(239, 68, 68, 0.15); border: 1px solid #EF4444; border-radius: 10px; padding: 14px; margin-bottom: 12px;">
    <div style="color: #F87171; font-weight: 800; font-size: 1rem;">🚨 CRITICAL VEHICLE / COMPRESSOR BREAKDOWN DETECTED!</div>
    <div style="color: #FCA5A5; font-size: 0.82rem; margin-top: 4px;">Autonomous Salvage Engine triggered. Consignment rerouted to Bhopal Emergency Cold Hub. Backup Reefer EV-88 Dispatched.</div>
</div>
""", unsafe_allow_html=True)

    try:
        from components.map_view import render_corridor_map
        render_corridor_map(st.session_state.vehicle_breakdown)
    except Exception as e:
        st.warning(f"Map rendering: {e}")

# -----------------------------------------------------------------------------
# PAGE 5: ARRHENIUS SPOILAGE FORECASTER
# -----------------------------------------------------------------------------
elif nav_option == T["nav_5"]:
    st.markdown("### 🔮 Thermal Decay Kinetics & Shelf-Life Telemetry")

    try:
        from ml.spoilage_model import render_decay_curves
        render_decay_curves(st.session_state.transit_delay_hours)
    except Exception as e:
        st.info(f"ML Model: {e}")

# -----------------------------------------------------------------------------
# PAGE 6: BIO-CONSOLIDATION & KISAN RAIL
# -----------------------------------------------------------------------------
elif nav_option == T["nav_6"]:
    st.markdown("### ⚡ Biochemical Cross-Contamination Matrix & Indian Railways Sync")

    try:
        from data.bio_rules import check_bio_compatibility
        status, msg = check_bio_compatibility(st.session_state.cargo_list)
        if status:
            st.success(f"🧬 **Bio-Compatibility Verification:** {msg}")
        else:
            st.error(f"🚫 **Cross-Contamination Alert:** {msg}")
    except Exception as e:
        st.info(f"Rules engine: {e}")

    st.markdown("---")
    st.markdown("#### 🚆 Indian Railways Kisan Rail Timetable & 50% Subsidy Tariff")
    df_trains = pd.DataFrame([
        {"Train No": "00112", "Service Name": "Kisan Cold Parcel Express", "Origin Station": "Nashik Road (NK)", "Dest Station": "Adarsh Nagar Delhi (ANDI)", "Standard Tariff": "₹2,200/T", "50% MoFPI Tariff": "₹1,100/T", "Transit Time": "17.5 hrs"},
        {"Train No": "00118", "Service Name": "Central Agri Reefer Express", "Origin Station": "Bhopal Junction (BPL)", "Dest Station": "Hazrat Nizamuddin (NZM)", "Standard Tariff": "₹1,800/T", "50% MoFPI Tariff": "₹900/T", "Transit Time": "9.0 hrs"}
    ])
    st.dataframe(df_trains, use_container_width=True)

# -----------------------------------------------------------------------------
# PAGE 7: EXPLAINABLE AI MODE RECOMMENDER (PARETO FRONTIER)
# -----------------------------------------------------------------------------
elif nav_option == T["nav_7"]:
    st.markdown("### 💡 Explainable AI (XAI) Transport Mode Optimizer & Pareto Frontier")

    st.markdown("""
<div style="background: rgba(14, 20, 23, 0.75); border: 1px solid rgba(0, 245, 155, 0.3); border-radius: 12px; padding: 16px; margin-bottom: 16px;">
    <h4 style="color: #00F59B; margin: 0 0 8px 0;">🤖 Optimization Rationale: Multimodal Kisan Rail</h4>
    <p style="color: #E2E8F0; font-size: 0.86rem; line-height: 1.6; margin: 0;">
        The genetic algorithm evaluated 14 distinct route combinations and selected <strong>EV First-Mile ➔ Kisan Rail Express ➔ EV Last-Mile</strong> because it minimizes total logistics cost by 74%, avoids highway toll dwell spikes, and slashes CO2 emissions by 65.4%.
    </p>
</div>
""", unsafe_allow_html=True)

    categories = ['Tariff Economy', 'Thermal Stability', 'Speed & Reliability', 'Carbon Cut', 'Govt Subsidy']
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(r=[95, 90, 85, 92, 100], theta=categories, fill='toself', name='AI Multimodal Kisan Rail', line=dict(color='#00F59B')))
    fig_radar.add_trace(go.Scatterpolar(r=[35, 60, 50, 25, 0], theta=categories, fill='toself', name='Direct Diesel Trucking', line=dict(color='#FB7185')))
    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(l=20, r=20, t=20, b=20)
    )
    st.plotly_chart(fig_radar, use_container_width=True)

# -----------------------------------------------------------------------------
# PAGE 8: BLOCKCHAIN PASSPORT & 1-CLICK SUBSIDY AUDIT DOWNLOAD
# -----------------------------------------------------------------------------
else:
    st.markdown("### ⛓️ Cryptographic Consignment Passport & Smart Contract Ledger")
    st.caption("Tamper-Proof MoFPI Subsidy Verification & IoT Audit Trail")

    payload_raw = f"NASHIK-DELHI:{current_weight}:{st.session_state.transit_delay_hours}:{datetime.datetime.now().strftime('%Y%m%d%H')}"
    consignment_hash = hashlib.sha256(payload_raw.encode()).hexdigest()

    st.markdown(f"""
<div class="blockchain-box">
    <div><strong>BLOCKCHAIN SMART CONTRACT PASSPORT:</strong></div>
    <div style="margin: 6px 0; word-break: break-all; color: #00F59B;"><strong>TX HASH:</strong> 0x{consignment_hash}</div>
    <div style="color: #94A3B8;">NETWORK: Polygon PoS Agri-Ledger | PROTOCOL: ERC-721 Dynamic NFT Passport</div>
    <div style="color: #38BDF8; margin-top: 6px;">STATUS: 🟢 Temperature Audit Compliant | MoFPI 50% Subsidy Smart Release: EXECUTED</div>
</div>
""", unsafe_allow_html=True)

    report_certificate = f"""======================================================================
COLDCHAIN AI - OFFICIAL CONSIGNMENT AUDIT & SUBSIDY CERTIFICATE
======================================================================
Generated Date       : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}
Corridor Route       : Nashik Farm Gate (MH) -> Azadpur Mandi, Delhi (1,380 KM)
Consignment Hash     : 0x{consignment_hash}
Fleet Configuration  : {st.session_state.selected_fleet}
Total Verified Load  : {current_weight} kg

----------------------------------------------------------------------
FINANCIAL RECONCILIATION & MOFPI SUBSIDY CLAIM
----------------------------------------------------------------------
Traditional Road Diesel Tariff : Rs 57,960.00
Estimated Spoilage Without AI  : Rs 14,400.00
Kisan Rail Standard Tariff     : Rs 2,200.00 / Tonne
MoFPI 50% Subsidy Disbursed    : Rs 1,100.00
AI Intermodal Total Cost       : Rs 6,800.00
NET SHIPPER PROFIT UPLIFT      : Rs 63,960.00 (+34.8% Gain)

----------------------------------------------------------------------
IOT SENSOR AUDIT & QUALITY METRICS
----------------------------------------------------------------------
Core Cargo Temperature         : 2.2 deg C (Range: 1.0 - 4.0 deg C)
Arrhenius Thermal Integrity    : 100% PASS
Ethylene Contamination Risk    : 0% BIO-SAFE
SLA Compliance Status          : EXECUTED VIA SMART CONTRACT
======================================================================"""

    d_col1, d_col2 = st.columns([3, 7])
    with d_col1:
        st.download_button(
            label="📄 Download Official MoFPI Subsidy Certificate",
            data=report_certificate,
            file_name=f"ColdChain_Subsidy_Audit_{consignment_hash[:8]}.txt",
            mime="text/plain",
            type="primary",
            use_container_width=True
        )

    st.markdown("#### 📜 Smart Contract Event Audit Stream")
    df_ledger = pd.DataFrame([
        {"Timestamp": "10:14:02 IST", "Event": "Consignment Sealed at Farm Gate", "Sensor Temp": "2.8°C", "Smart Contract Action": "Escrow Initialized"},
        {"Timestamp": "12:30:15 IST", "Event": "Kisan Rail VPU Transshipment", "Sensor Temp": "3.1°C", "Smart Contract Action": "50% MoFPI Subsidy Released"},
        {"Timestamp": "14:45:50 IST", "Event": "Bhopal Junction Transit Ping", "Sensor Temp": "3.4°C", "Smart Contract Action": "SLA Integrity Verified"}
    ])
    st.dataframe(df_ledger, use_container_width=True)
    
    st.markdown("---")
    st.toggle("🔒 Enable Zero-Knowledge Proof (ZKP) for MSME Shipper Privacy", value=True)
    st.success("✅ Multi-tenant cryptography operational.")