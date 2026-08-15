import pandas as pd

def get_xai_tradeoff_matrix():
    """
    Returns a multi-criteria decision comparison matrix between
    Traditional Road Freight and Multimodal Kisan Rail.
    """
    tradeoff_data = {
        "Decision Metric": [
            "Freight Tariff per Tonne",
            "Govt Subsidy Eligibility",
            "Thermal Integrity Protection",
            "Highway Toll / RTO Delays",
            "Carbon Footprint Reduction"
        ],
        "Direct Road Reefer": [
            "₹4,200 / Tonne",
            "0% (No Subsidy)",
            "Moderate (Compressor strain in peak summer)",
            "High (3-5 hours average toll & border dwell)",
            "Baseline (High diesel emissions)"
        ],
        "AI Multimodal (Kisan Rail)": [
            "₹1,100 / Tonne",
            "50% MoFPI Subsidy Applied",
            "High (Hermetically insulated rail parcel vans)",
            "Zero (Dedicated green transit corridor)",
            "-65.4% Carbon Emissions (EV + Electric Rail)"
        ],
        "AI Winning Score": [
            "🏆 Rail (74% cheaper)",
            "🏆 Kisan Rail Exclusive",
            "🏆 Rail VPU",
            "🏆 Rail Corridors",
            "🏆 EV + Rail Sync"
        ]
    }
    return pd.DataFrame(tradeoff_data)