"""
S17 Logistics Consolidation, Multimodal Routing & Spoilage-Risk Model
========================================================================

Pipeline:
  1. Read farmer shipments (farmer_name, phone, product, origin, destination, weight_kg, expected_delivery_date)
     -- MULTIPLE FARMERS pool together automatically: consolidation groups
        are formed purely by product compatibility, not by who owns the
        shipment, so two different farmers' compatible produce on the same
        origin->destination gets combined into one vehicle.
  2. Flag which products need a refrigerated vehicle.
  3. Group shipments into product combinations that are mutually compatible
     (ethylene / temperature / humidity), pooling across farmers.
  4. For each group, generate several candidate routes across the road+rail
     transfer-point network (not just the single cheapest one).
  5. For every candidate route, compute:
       - planned travel time (distance / vehicle speed + hub handling time)
       - expected delay (from historical trip data, by mode mix)
       - expected total transit time = planned time + expected delay
       - spoilage risk = expected transit time / weakest shelf life in the group
  6. Pick the route with the best COMBINED score of cost and spoilage risk
     (not cost alone) -- a slightly pricier route that keeps spoilage risk
     low can beat the cheapest one that risks the load.
  7. Report cost, time, delay, spoilage risk, and the other candidate
     routes considered, for transparency.

Reads all 6 datasets:
  01_products_master.csv, 02_compatibility_matrix.csv, 03_vehicles.csv,
  04_transfer_points.csv, 05_farmer_shipments.csv, 06_historical_trips_delay.csv

RUNNING:
  A) Interactive:  python logistics_model.py
"""

import sys
import math
import itertools
from pathlib import Path
import pandas as pd
import networkx as nx

DATA_DIR = Path(__file__).resolve().parent
AMBIENT_TEMP_C = 25.0
RISK_PENALTY_WEIGHT = 1.0
COMPATIBILITY_SCORE_THRESHOLD = 75.0  # scores at/above this are considered safely poolable

KISAN_RAIL_SUBSIDY_RATE = 0.50
KISAN_RAIL_ELIGIBLE_CATEGORIES = {"Fruit", "Vegetable"}

BOOKED_VEHICLES = set()

def load_data(data_dir: Path = DATA_DIR):
    try:
        products = pd.read_csv(data_dir / "01_products_master.csv")
        compat = pd.read_csv(data_dir / "02_compatibility_matrix.csv")
        vehicles = pd.read_csv(data_dir / "03_vehicles.csv")
        nodes = pd.read_csv(data_dir / "04_transfer_points.csv")
        sample_shipments = pd.read_csv(data_dir / "05_farmer_shipments.csv")
        trip_history = pd.read_csv(data_dir / "06_historical_trips_delay.csv")
        return products, compat, vehicles, nodes, sample_shipments, trip_history
    except FileNotFoundError:
        products = pd.read_csv("01_products_master.csv")
        compat = pd.read_csv("02_compatibility_matrix.csv")
        vehicles = pd.read_csv("03_vehicles.csv")
        nodes = pd.read_csv("04_transfer_points.csv") if Path("04_transfer_points.csv").exists() else pd.DataFrame()
        sample_shipments = pd.read_csv("05_farmer_shipments.csv") if Path("05_farmer_shipments.csv").exists() else pd.DataFrame()
        trip_history = pd.read_csv("06_historical_trips_delay.csv") if Path("06_historical_trips_delay.csv").exists() else pd.DataFrame()
        return products, compat, vehicles, nodes, sample_shipments, trip_history

def normalize_vehicle_capacity(vehicles_df: pd.DataFrame) -> pd.DataFrame:
    df = vehicles_df.copy()
    if "remaining_capacity_kg" not in df.columns:
        df["remaining_capacity_kg"] = df["weight_capacity_kg"]
    else:
        rc = pd.to_numeric(df["remaining_capacity_kg"], errors="coerce")
        df["remaining_capacity_kg"] = rc.fillna(df["weight_capacity_kg"])

    if "current_location" not in df.columns:
        hubs = ["Bhubaneswar", "Cuttack", "Puri", "Balasore", "Berhampur", "Sambalpur", "Rourkela", "Angul"]
        df["current_location"] = [hubs[i % len(hubs)] for i in range(len(df))]
    return df

def consume_vehicle_capacity(vehicles_df: pd.DataFrame, vehicle_no: str, weight_kg: float) -> None:
    mask = vehicles_df["vehicle_no"].astype(str) == str(vehicle_no)
    vehicles_df.loc[mask, "remaining_capacity_kg"] = (
        vehicles_df.loc[mask, "remaining_capacity_kg"] - weight_kg
    ).clip(lower=0)

def save_vehicle_capacity(vehicles_df: pd.DataFrame, data_dir: Path = DATA_DIR) -> None:
    """Saves the fleet back to 03_vehicles.csv. Previously this silently fell
    back to writing a SECOND, different copy of the file if the primary save
    failed (e.g. the file was open/locked in Excel) -- which meant a
    successful-looking save could actually be writing to the wrong place.
    Now it tells you exactly which path was written, and warns loudly if the
    primary location failed, instead of failing silently."""
    primary_path = data_dir / "03_vehicles.csv"
    try:
        vehicles_df.to_csv(primary_path, index=False)
        print(f"[Fleet saved to: {primary_path}]")
    except Exception as e:
        fallback_path = Path("03_vehicles.csv").resolve()
        print(f"\n[WARNING] Could not save to {primary_path} ({e}).")
        print(f"[WARNING] If that file is open in Excel, close it and re-run this option.")
        print(f"[WARNING] Falling back to: {fallback_path}")
        vehicles_df.to_csv(fallback_path, index=False)

def build_delay_rate_lookup(trip_history: pd.DataFrame) -> dict:
    if trip_history.empty or "delay_hours" not in trip_history.columns:
        return {"Road-only": 0.5, "Rail-only": 0.5, "Mixed": 0.5}
    df = trip_history.copy()
    df["rate_per_100km"] = (df["delay_hours"] / df["distance_km"]) * 100

    def cat_rate(mode_name):
        subset = df[df["mode"] == mode_name]
        return float(subset["rate_per_100km"].mean()) if not subset.empty else 0.5

    return {
        "Road-only": cat_rate("Road-only"),
        "Rail-only": cat_rate("Rail-only"),
        "Mixed": cat_rate("Road-Rail-Road"),
    }

def needs_refrigeration(product_row) -> bool:
    return float(product_row["max_temp_C"]) < AMBIENT_TEMP_C

def build_compatibility_lookup(compat_df: pd.DataFrame) -> dict:
    lookup = {}
    for _, r in compat_df.iterrows():
        key = frozenset([str(r["product_a"]).strip(), str(r["product_b"]).strip()])
        lookup[key] = (str(r["compatible"]).strip().upper() == "Y")
    return lookup

def are_compatible(p1: str, p2: str, lookup: dict, products_lookup=None) -> bool:
    if p1 == p2:
        return True

    # The compatibility matrix is now the FINAL word whenever it has an
    # explicit entry for this pair:
    #   - "N" blocks the pair outright, no further checks.
    #   - "Y" is a human-curated override -- trust it and skip the ethylene/
    #     temperature/humidity/odour checks below, even if the raw product
    #     attributes would otherwise look risky (e.g. two ethylene-sensitive
    #     producers that a human has still decided are fine together).
    # Only a MISSING pair (no row in the CSV at all) falls through to the
    # attribute checks, since nobody has made a judgement call on it yet.
    matrix_entry = lookup.get(frozenset([p1, p2]))
    if matrix_entry is False:
        return False
    if matrix_entry is True:
        return True

    if products_lookup is not None and p1 in products_lookup.index and p2 in products_lookup.index:
        a, b = products_lookup.loc[p1], products_lookup.loc[p2]

        # Ethylene: a producer next to a sensitive item speeds up spoilage.
        a_prod = str(a.get("produces_ethylene", "N")).upper() == "Y"
        b_prod = str(b.get("produces_ethylene", "N")).upper() == "Y"
        a_sens = str(a.get("ethylene_sensitive", "N")).upper() == "Y"
        b_sens = str(b.get("ethylene_sensitive", "N")).upper() == "Y"
        if (a_prod and b_sens) or (b_prod and a_sens):
            return False

        # Temperature: the two products must have SOME overlapping safe range,
        # otherwise no single vehicle setting keeps both of them safe.
        temp_min = max(float(a["min_temp_C"]), float(b["min_temp_C"]))
        temp_max = min(float(a["max_temp_C"]), float(b["max_temp_C"]))
        if temp_max < temp_min:
            return False

        # Humidity: same idea as temperature -- no shared humidity band means
        # one of the two will either dry out or turn soggy/moldy in transit.
        hum_min = max(float(a["humidity_min_pct"]), float(b["humidity_min_pct"]))
        hum_max = min(float(a["humidity_max_pct"]), float(b["humidity_max_pct"]))
        if hum_max < hum_min:
            return False

        # Odour: a high-odour item next to an odour-sensitive item taints the
        # sensitive item's smell/taste even if temperature and humidity match
        # (classic case: Onion/Garlic/Ginger next to Dairy or Apple).
        a_odour = str(a.get("odour_risk", "Low")).upper() == "HIGH"
        b_odour = str(b.get("odour_risk", "Low")).upper() == "HIGH"
        a_odour_sens = str(a.get("odour_sensitive", "N")).upper() == "Y"
        b_odour_sens = str(b.get("odour_sensitive", "N")).upper() == "Y"
        if (a_odour and b_odour_sens) or (b_odour and a_odour_sens):
            return False

    return True

def compatibility_score_detail(p1: str, p2: str, products_lookup, matrix_override: bool = False) -> dict:
    """
    0-100 SOFT score for a pair that already passed are_compatible() -- either
    because the physical checks passed on their own, or because a human "Y"
    entry in the compatibility matrix overrode them (matrix_override=True).
    An override still gets flagged here with an extra penalty + explicit
    warning tip, so a matrix-approved-but-physically-risky pair doesn't look
    identical to a genuinely safe one.
    """
    if p1 == p2 or p1 not in products_lookup.index or p2 not in products_lookup.index:
        return {"score": 100, "tips": []}

    a, b = products_lookup.loc[p1], products_lookup.loc[p2]
    score = 100
    tips = []

    if matrix_override:
        a_prod = str(a.get("produces_ethylene", "N")).upper() == "Y"
        b_prod = str(b.get("produces_ethylene", "N")).upper() == "Y"
        a_sens = str(a.get("ethylene_sensitive", "N")).upper() == "Y"
        b_sens = str(b.get("ethylene_sensitive", "N")).upper() == "Y"
        if (a_prod and b_sens) or (b_prod and a_sens):
            score -= 25
            producer, sensitive = (p1, p2) if a_prod else (p2, p1)
            tips.append(f"Matrix override: {producer} normally can't ride with {sensitive} (ethylene) — human override in place, monitor closely and ventilate well.")

        t_min = max(float(a["min_temp_C"]), float(b["min_temp_C"]))
        t_max = min(float(a["max_temp_C"]), float(b["max_temp_C"]))
        if t_max < t_min:
            score -= 25
            tips.append(f"Matrix override: {p1} and {p2} have NO overlapping safe temperature range — human override in place, extra spoilage risk.")

        h_min = max(float(a["humidity_min_pct"]), float(b["humidity_min_pct"]))
        h_max = min(float(a["humidity_max_pct"]), float(b["humidity_max_pct"]))
        if h_max < h_min:
            score -= 20
            tips.append(f"Matrix override: {p1} and {p2} have NO overlapping safe humidity range — human override in place.")

        a_odour = str(a.get("odour_risk", "Low")).upper() == "HIGH"
        b_odour = str(b.get("odour_risk", "Low")).upper() == "HIGH"
        a_odour_sens = str(a.get("odour_sensitive", "N")).upper() == "Y"
        b_odour_sens = str(b.get("odour_sensitive", "N")).upper() == "Y"
        if (a_odour and b_odour_sens) or (b_odour and a_odour_sens):
            score -= 15
            smelly, sensitive = (p1, p2) if a_odour else (p2, p1)
            tips.append(f"Matrix override: {smelly} may taint {sensitive}'s smell/taste — human override in place.")

    # Temperature: narrow shared window = less margin for the driver's a/c to drift.
    shared_min = max(float(a["min_temp_C"]), float(b["min_temp_C"]))
    shared_max = min(float(a["max_temp_C"]), float(b["max_temp_C"]))
    temp_overlap = shared_max - shared_min
    if temp_overlap < 3:
        score -= 15
        tips.append(f"Narrow shared temperature window ({shared_min:.0f}-{shared_max:.0f}°C) — set the vehicle to this exact range and recheck it mid-route.")
    elif temp_overlap < 6:
        score -= 8
        tips.append(f"Keep the vehicle within {shared_min:.0f}-{shared_max:.0f}°C for both items.")

    # Humidity: same logic as temperature.
    hum_min = max(float(a["humidity_min_pct"]), float(b["humidity_min_pct"]))
    hum_max = min(float(a["humidity_max_pct"]), float(b["humidity_max_pct"]))
    hum_overlap = hum_max - hum_min
    if hum_overlap < 5:
        score -= 10
        tips.append(f"Tight shared humidity window ({hum_min:.0f}-{hum_max:.0f}%) — use a humidity buffer/liner if available.")
    elif hum_overlap < 10:
        score -= 5
        tips.append(f"Keep humidity within {hum_min:.0f}-{hum_max:.0f}% for both items.")

    # Fragility vs rigid packaging: crush risk if stacked together.
    a_fragile = str(a.get("fragility", "Low")).upper() == "HIGH"
    b_fragile = str(b.get("fragility", "Low")).upper() == "HIGH"
    a_rigid = str(a.get("packaging_type", "")).upper().startswith("DRY/RIGID")
    b_rigid = str(b.get("packaging_type", "")).upper().startswith("DRY/RIGID")
    if (a_fragile and b_rigid) or (b_fragile and a_rigid):
        score -= 15
        fragile_item, rigid_item = (p1, p2) if a_fragile else (p2, p1)
        tips.append(f"{fragile_item} is fragile and {rigid_item} is rigid — do not stack directly; use a divider or separate pallets.")

    # Different packaging types: not dangerous, just needs tidier loading.
    if str(a.get("packaging_type", "")) != str(b.get("packaging_type", "")):
        score -= 5
        tips.append(f"Different packaging ({a['packaging_type']} vs {b['packaging_type']}) — keep in separate crates/sections of the vehicle.")

    # Very different shelf lives: the shorter-life item needs to come off first.
    sl_a, sl_b = float(a["shelf_life_hours"]), float(b["shelf_life_hours"])
    if min(sl_a, sl_b) > 0 and max(sl_a, sl_b) / min(sl_a, sl_b) >= 5:
        score -= 10
        shorter = p1 if sl_a < sl_b else p2
        tips.append(f"{shorter} has a much shorter shelf life — load it last, unload it first.")

    # Ethylene producer present (even if nothing here is sensitive to it):
    # still worth a ventilation reminder for general freshness.
    a_produces = str(a.get("produces_ethylene", "N")).upper() == "Y"
    b_produces = str(b.get("produces_ethylene", "N")).upper() == "Y"
    if a_produces or b_produces:
        score -= 5
        producer = p1 if a_produces else p2
        tips.append(f"{producer} gives off ethylene — keep the vehicle ventilated during transit.")

    return {"score": max(0, min(100, score)), "tips": tips}

def group_compatibility_recommendation(group: list, products_lookup, compat_lookup: dict = None) -> dict:
    if len(group) <= 1:
        return {"score": 100, "headline": "Single product load — no special handling needed.", "tips": []}

    scores = []
    tips = []
    for p1, p2 in itertools.combinations(group, 2):
        matrix_override = bool(compat_lookup) and compat_lookup.get(frozenset([p1, p2])) is True
        detail = compatibility_score_detail(p1, p2, products_lookup, matrix_override=matrix_override)
        scores.append(detail["score"])
        for tip in detail["tips"]:
            if tip not in tips:
                tips.append(tip)

    group_score = min(scores) if scores else 100

    # Score bands -> plain-English handling instruction for the farmer/driver.
    if group_score >= 90:
        headline = "Safe to pool — no special precautions needed."
    elif group_score >= 75:
        headline = "Safe to pool with minor care — see handling notes below."
    elif group_score >= 60:
        headline = "Poolable, but follow the handling notes closely."
    else:
        headline = "Technically compatible, but consider shipping separately if possible."

    return {"score": group_score, "headline": headline, "tips": tips}

def group_products_by_compatibility(product_list: list, lookup: dict, products_lookup=None) -> list:
    if len(product_list) <= 1:
        return [product_list] if product_list else []
    
    g = nx.Graph()
    g.add_nodes_from(product_list)
    for p1, p2 in itertools.combinations(product_list, 2):
        if are_compatible(p1, p2, lookup, products_lookup):
            g.add_edge(p1, p2)
            
    cliques = sorted((list(c) for c in nx.find_cliques(g)), key=len, reverse=True)
    assigned = set()
    groups = []
    for clique in cliques:
        remaining = [p for p in clique if p not in assigned]
        if remaining:
            groups.append(remaining)
            assigned.update(remaining)
    return groups

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def resolve_location(city_name: str, nodes_df: pd.DataFrame) -> pd.Series:
    match = nodes_df[nodes_df["city"].str.strip().str.lower() == city_name.strip().lower()]
    if not match.empty:
        return match.iloc[0]
    raise ValueError(f"'{city_name}' is not in network nodes.")

def pick_vehicles_for_weight(weight_kg: float, distance_km: float, refrigerated: bool, mode: str,
                             origin_city: str, vehicles_df: pd.DataFrame):
    ref_flag = "Y" if refrigerated else "N"

    all_candidates = vehicles_df[
        (vehicles_df["mode"] == mode)
        & (vehicles_df["refrigerated"] == ref_flag)
        & (vehicles_df["remaining_capacity_kg"] > 0)
        & (~vehicles_df["vehicle_no"].isin(BOOKED_VEHICLES))
    ].copy()

    if all_candidates.empty:
        all_candidates = vehicles_df[
            (vehicles_df["mode"] == mode)
            & (vehicles_df["refrigerated"] == ref_flag)
            & (vehicles_df["remaining_capacity_kg"] > 0)
        ].copy()

    if all_candidates.empty:
        return None

    loc_match = all_candidates[
        all_candidates["current_location"].astype(str).str.strip().str.lower() == origin_city.strip().lower()
    ]

    # Prefer a single vehicle already at the origin city if one fits the whole load.
    fitting_loc = loc_match[loc_match["remaining_capacity_kg"] >= weight_kg]
    if not fitting_loc.empty:
        fitting_loc = fitting_loc.copy()
        fitting_loc["total_estimated_trip_cost"] = (
            weight_kg * fitting_loc["price_per_kg_INR"] * (distance_km / 100.0) + fitting_loc["fixed_cost_INR"]
        )
        best = fitting_loc.sort_values("total_estimated_trip_cost").iloc[0]
        return [{"vehicle": best, "weight_kg": weight_kg, "trips": 1}]

    # No single vehicle at origin fits -- try any single vehicle in the wider fleet.
    fitting_any = all_candidates[all_candidates["remaining_capacity_kg"] >= weight_kg]
    if not fitting_any.empty:
        fitting_any = fitting_any.copy()
        fitting_any["total_estimated_trip_cost"] = (
            weight_kg * fitting_any["price_per_kg_INR"] * (distance_km / 100.0) + fitting_any["fixed_cost_INR"]
        )
        best = fitting_any.sort_values("total_estimated_trip_cost").iloc[0]
        return [{"vehicle": best, "weight_kg": weight_kg, "trips": 1}]

    # Load doesn't fit in ANY single vehicle -- split it across several instead
    # of cancelling the order. Use origin-city vehicles first (biggest first),
    # then draw on the rest of the matching fleet from other locations if
    # still short -- never give up just because the origin-only pool alone
    # wasn't big enough, as long as the fleet overall has the capacity.
    ordered_loc = loc_match.sort_values("remaining_capacity_kg", ascending=False)
    remaining_pool = all_candidates.drop(loc_match.index).sort_values("remaining_capacity_kg", ascending=False)
    pool = pd.concat([ordered_loc, remaining_pool])

    remaining = weight_kg
    assignments = []
    for _, v in pool.iterrows():
        if remaining <= 0:
            break
        take = min(remaining, v["remaining_capacity_kg"])
        assignments.append({"vehicle": v, "weight_kg": take, "trips": 1})
        remaining -= take

    return assignments if remaining <= 0 else None

def leg_cost(weight_kg: float, distance_km: float, refrigerated: bool, mode: str,
             origin_city: str, vehicles_df: pd.DataFrame):
    assignments = pick_vehicles_for_weight(weight_kg, distance_km, refrigerated, mode, origin_city, vehicles_df)
    if not assignments:
        return None

    total_cost = 0.0
    max_time = 0.0
    vehicles_out = []

    for a in assignments:
        v, w, trips = a["vehicle"], a["weight_kg"], a["trips"]
        cost = w * v["price_per_kg_INR"] * (distance_km / 100.0) * trips + v["fixed_cost_INR"] * trips
        one_way_time = (distance_km / v["avg_speed_kmph"]) if v["avg_speed_kmph"] else 0.0
        
        total_cost += cost
        max_time = max(max_time, one_way_time)
        vehicles_out.append({
            "vehicle_no": v["vehicle_no"],
            "size_class": v["size_class"],
            "current_location": v.get("current_location", origin_city),
            "weight_kg": round(w, 1),
            "trips": trips,
            "driver_name": "" if pd.isna(v.get("driver_name")) else str(v.get("driver_name")).strip(),
            "driver_contact": "" if pd.isna(v.get("driver_contact")) else str(v.get("driver_contact")).strip(),
        })

    primary = vehicles_out[0]
    return {
        "cost_INR": round(total_cost, 2),
        "time_hr": round(max_time, 2) if max_time else None,
        "vehicle_no": primary["vehicle_no"],
        "vehicle_mode": mode,
        "size_class": primary["size_class"],
        "num_trips": primary["trips"],
        "driver_name": primary["driver_name"],
        "driver_contact": primary["driver_contact"],
        "vehicles": vehicles_out,
    }

def build_route_graph(weight_kg: float, refrigerated: bool, nodes_df: pd.DataFrame,
                       vehicles_df: pd.DataFrame, origin_row: pd.Series, dest_row: pd.Series) -> nx.MultiDiGraph:
    all_nodes = pd.concat(
        [nodes_df, pd.DataFrame([origin_row]), pd.DataFrame([dest_row])], ignore_index=True
    ).drop_duplicates(subset="city", keep="first")

    G = nx.MultiDiGraph()
    for _, n in all_nodes.iterrows():
        G.add_node(n["city"], lat=n["latitude"], lon=n["longitude"])

    for a, b in itertools.permutations(all_nodes.itertuples(index=False), 2):
        dist = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
        if dist > 0:
            if a.supports_road == "Y" and b.supports_road == "Y":
                leg = leg_cost(weight_kg, dist, refrigerated, "Road", a.city, vehicles_df)
                if leg:
                    G.add_edge(a.city, b.city, key="Road", mode="Road", distance_km=round(dist, 1), **leg)

            if a.supports_rail == "Y" and b.supports_rail == "Y":
                leg = leg_cost(weight_kg, dist, refrigerated, "Rail", a.city, vehicles_df)
                if leg:
                    G.add_edge(a.city, b.city, key="Rail", mode="Rail", distance_km=round(dist, 1), **leg)

    return G

def is_kisan_rail_eligible_product(product_name: str, products_df: pd.DataFrame) -> bool:
    row = products_df.loc[
        products_df["product"].astype(str).str.strip().str.lower() == str(product_name).strip().lower()
    ]
    if row.empty:
        return False
    return str(row.iloc[0]["category"]).strip().title() in KISAN_RAIL_ELIGIBLE_CATEGORIES

def summarize_path(G: nx.DiGraph, path: list, nodes_df: pd.DataFrame, delay_rates: dict,
                   total_weight_kg: float, kisan_eligible_weight_kg: float = 0.0) -> dict:
    legs = []
    gross_cost = 0.0
    subsidy_amount = 0.0
    total_distance = 0.0
    planned_time = 0.0
    modes_used = set()

    eligible_fraction = (min(max(kisan_eligible_weight_kg / total_weight_kg, 0.0), 1.0) if total_weight_kg > 0 else 0.0)

    for u, v in zip(path[:-1], path[1:]):
        edge = G[u][v]
        leg_gross = float(edge["cost_INR"])
        leg_subsidy = (leg_gross * eligible_fraction * KISAN_RAIL_SUBSIDY_RATE) if edge["mode"] == "Rail" else 0.0

        legs.append({
            "from": u, "to": v, "mode": edge["mode"], "distance_km": edge["distance_km"],
            "vehicle_no": edge["vehicle_no"], "size_class": edge["size_class"],
            "cost_INR": round(leg_gross - leg_subsidy, 2),
            "gross_cost_INR": round(leg_gross, 2),
            "kisan_rail_subsidy_INR": round(leg_subsidy, 2),
            "time_hr": edge["time_hr"], "num_trips": edge["num_trips"],
            "driver_name": edge.get("driver_name", ""),
            "driver_contact": edge.get("driver_contact", ""),
            "vehicles": edge.get("vehicles", []),
        })
        gross_cost += leg_gross
        subsidy_amount += leg_subsidy
        total_distance += edge["distance_km"]
        planned_time += edge["time_hr"] or 0
        modes_used.add(edge["mode"])

    handling_time = sum(
        nodes_df.loc[nodes_df["city"] == city, "avg_handling_time_hr"].iloc[0]
        for city in path[1:-1] if not nodes_df.loc[nodes_df["city"] == city].empty
    )
    planned_time += handling_time

    delay_category = "Road-only" if modes_used == {"Road"} else ("Rail-only" if modes_used == {"Rail"} else "Mixed")
    expected_delay_hr = delay_rates.get(delay_category, 0.5) * (total_distance / 100.0)

    return {
        "route": path, "legs": legs,
        "gross_cost_INR": round(gross_cost, 2),
        "kisan_rail_subsidy_INR": round(subsidy_amount, 2),
        "total_cost_INR": round(gross_cost - subsidy_amount, 2),
        "total_distance_km": round(total_distance, 1),
        "transfer_handling_time_hr": round(handling_time, 2),
        "planned_time_hr": round(planned_time, 2),
        "expected_delay_hr": round(expected_delay_hr, 2),
        "total_expected_time_hr": round(planned_time + expected_delay_hr, 2),
        "is_multimodal": len(modes_used) > 1,
        "modes_used": sorted(modes_used),
    }

def spoilage_risk(total_expected_time_hr: float, shelf_life_hours: float) -> dict:
    fraction = 1.0 if shelf_life_hours <= 0 else (total_expected_time_hr / shelf_life_hours)
    level = "Low" if fraction < 0.4 else ("Medium" if fraction < 0.7 else ("High" if fraction < 1.0 else "Critical"))
    return {"risk_fraction": round(fraction, 3), "risk_pct": round(fraction * 100, 1), "risk_level": level}

def select_best_route(candidates: list) -> dict:
    for c in candidates:
        c["combined_score"] = c["total_cost_INR"] * (1 + RISK_PENALTY_WEIGHT * c["risk_fraction"])
    return min(candidates, key=lambda c: (c["combined_score"], c["total_cost_INR"]))

def find_candidate_routes(origin_city: str, destination_city: str, weight_kg: float, refrigerated: bool,
                           shelf_life_hours: float, nodes_df: pd.DataFrame, vehicles_df: pd.DataFrame,
                           delay_rates: dict, kisan_eligible_weight_kg: float = 0.0):
    try:
        origin_row = resolve_location(origin_city, nodes_df)
        dest_row = resolve_location(destination_city, nodes_df)
    except ValueError as e:
        return {"error": str(e)}

    G = build_route_graph(weight_kg, refrigerated, nodes_df, vehicles_df, origin_row, dest_row)
    
    def make_candidate(path, path_graph):
        summary = summarize_path(path_graph, path, nodes_df, delay_rates, weight_kg, kisan_eligible_weight_kg)
        summary.update(spoilage_risk(summary["total_expected_time_hr"], shelf_life_hours))
        return summary

    candidates = []
    try:
        road_g = nx.DiGraph([(u, v, d) for u, v, k, d in G.edges(keys=True, data=True) if d['mode'] == 'Road'])
        p = nx.shortest_path(road_g, origin_city, destination_city, weight="cost_INR")
        c = make_candidate(p, road_g)
        c["strategy"] = "Road only"
        candidates.append(c)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass

    try:
        rail_g = nx.DiGraph([(u, v, d) for u, v, k, d in G.edges(keys=True, data=True) if d['mode'] == 'Rail'])
        p = nx.shortest_path(rail_g, origin_city, destination_city, weight="cost_INR")
        c = make_candidate(p, rail_g)
        c["strategy"] = "Rail only"
        candidates.append(c)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass

    def route_signature(cand):
        # (from, to, mode) per leg -- NOT just the city sequence, so a direct
        # hop taken by Road and the *same* direct hop taken by Rail are
        # recognised as genuinely different options instead of being treated
        # as duplicates and silently dropped (this previously hid cheaper
        # Rail-only opportunities whenever they used the same city pair as
        # the Road-only candidate).
        return tuple((leg["from"], leg["to"], leg["mode"]) for leg in cand["legs"])

    try:
        all_g = nx.DiGraph()
        for u, v, k, d in G.edges(keys=True, data=True):
            if not all_g.has_edge(u, v) or d["cost_INR"] < all_g[u][v]["cost_INR"]:
                all_g.add_edge(u, v, **d)
        p = nx.shortest_path(all_g, origin_city, destination_city, weight="cost_INR")
        c = make_candidate(p, all_g)
        c["strategy"] = "Road+Rail"
        existing_signatures = {route_signature(x) for x in candidates}
        if route_signature(c) not in existing_signatures:
            candidates.append(c)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass

    if not candidates:
        return {"error": f"No valid route found between {origin_city} and {destination_city}"}

    best = select_best_route(candidates)
    return {"best": best, "all_candidates": candidates}

def process_farmer_shipments(shipments_df: pd.DataFrame, products_df: pd.DataFrame,
                              compat_df: pd.DataFrame, vehicles_df: pd.DataFrame,
                              nodes_df: pd.DataFrame, trip_history: pd.DataFrame) -> pd.DataFrame:
    global BOOKED_VEHICLES
    BOOKED_VEHICLES.clear()

    products_lookup = products_df.set_index("product")
    compat_lookup = build_compatibility_lookup(compat_df)
    delay_rates = build_delay_rate_lookup(trip_history)

    individual_results = []
    group_counter = 0

    for (origin, destination), leg_df in shipments_df.groupby(["origin", "destination"]):
        leg_df = leg_df.copy()
        leg_df["needs_reefer"] = leg_df["product"].apply(
            lambda p: needs_refrigeration(products_lookup.loc[p]) if p in products_lookup.index else True
        )

        for reefer_flag, ref_df in leg_df.groupby("needs_reefer"):
            distinct_products = ref_df["product"].unique().tolist()
            product_groups = group_products_by_compatibility(distinct_products, compat_lookup, products_lookup)

            for group in product_groups:
                group_counter += 1
                group_shipments = ref_df[ref_df["product"].isin(group)].copy()
                
                total_group_weight = float(group_shipments["weight_kg"].sum())
                kisan_eligible_weight = float(
                    group_shipments.loc[
                        group_shipments["product"].apply(lambda p: is_kisan_rail_eligible_product(p, products_df)),
                        "weight_kg"
                    ].sum()
                )

                shelf_lives = [float(products_lookup.loc[p, "shelf_life_hours"]) for p in group if p in products_lookup.index]
                group_shelf_life = min(shelf_lives) if shelf_lives else 1e9

                result = find_candidate_routes(
                    origin, destination, total_group_weight, bool(reefer_flag), group_shelf_life,
                    nodes_df, vehicles_df, delay_rates, kisan_eligible_weight_kg=kisan_eligible_weight
                )

                if "error" in result:
                    for _, shp in group_shipments.iterrows():
                        individual_results.append({**shp.to_dict(), "error": result["error"]})
                    continue

                best = result["best"]

                # Give every vehicle used in this group's route a farmer-trackable
                # order ID -- one per truck, e.g. "G0001-T1", "G0001-T2" -- so a
                # split-across-multiple-vehicles shipment can be tracked piece by piece.
                truck_counter = 0
                for leg in best["legs"]:
                    for veh in leg.get("vehicles", []):
                        truck_counter += 1
                        veh["order_id"] = f"G{group_counter:04d}-T{truck_counter}"

                for leg in best["legs"]:
                    for veh in leg.get("vehicles", []):
                        v_no = veh["vehicle_no"]
                        consume_vehicle_capacity(vehicles_df, v_no, veh["weight_kg"])
                        BOOKED_VEHICLES.add(v_no)

                rec = group_compatibility_recommendation(group, products_lookup, compat_lookup)
                
                alt_summary_list = []
                for c in result["all_candidates"]:
                    alt_summary_list.append(
                        f"- {c['strategy']}: expected transit={c['total_expected_time_hr']:.2f} hr, net cost=INR{c['total_cost_INR']:.2f}, predicted spoilage risk={c['risk_pct']:.1f}% ({c['risk_level']})"
                    )
                alt_summary = "\n".join(alt_summary_list)

                for _, shp in group_shipments.iterrows():
                    weight_ratio = shp["weight_kg"] / total_group_weight
                    allocated_net_cost = round(best["total_cost_INR"] * weight_ratio, 2)
                    allocated_gross_cost = round(best["gross_cost_INR"] * weight_ratio, 2)
                    allocated_subsidy = round(best["kisan_rail_subsidy_INR"] * weight_ratio, 2)

                    p_name = shp["product"]
                    p_shelf = float(products_lookup.loc[p_name, "shelf_life_hours"]) if p_name in products_lookup.index else group_shelf_life
                    p_spoil = spoilage_risk(best["total_expected_time_hr"], p_shelf)

                    group_str = ", ".join(group) if len(group) > 1 else f"{p_name}: single-product load"

                    individual_results.append({
                        "group_id": f"G{group_counter:04d}",
                        "farmer_name": shp["farmer_name"],
                        "product": p_name,
                        "weight_kg": shp["weight_kg"],
                        "origin": origin,
                        "destination": destination,
                        "products_in_group": ", ".join(group),
                        "total_group_weight_kg": total_group_weight,
                        "refrigerated_required": bool(reefer_flag),
                        "route": " -> ".join(best["route"]),
                        "legs_for_display": best["legs"],
                        "is_multimodal": best["is_multimodal"],
                        "modes_used": ", ".join(best["modes_used"]),
                        "total_cost_INR": allocated_net_cost,
                        "gross_transport_cost_INR": allocated_gross_cost,
                        "kisan_rail_subsidy_INR": allocated_subsidy,
                        "planned_time_hr": best["planned_time_hr"],
                        "transfer_handling_time_hr": best["transfer_handling_time_hr"],
                        "expected_delay_hr": best["expected_delay_hr"],
                        "total_expected_time_hr": best["total_expected_time_hr"],
                        "shelf_life_hours": p_shelf,
                        "remaining_shelf_life_at_planned_arrival_hr": round(max(p_shelf - best["total_expected_time_hr"], 0.0), 2),
                        "predicted_spoilage_risk_pct": p_spoil["risk_pct"],
                        "predicted_spoilage_risk_level": p_spoil["risk_level"],
                        "compatibility_score": rec["score"],
                        "compatibility_headline": rec["headline"],
                        "compatibility_tips": rec["tips"],
                        "group_summary_text": group_str,
                        "route_selection_explanation": f"Selected {best['modes_used'][0] if len(best['modes_used'])==1 else 'Multimodal'} because its risk-adjusted cost was lowest. "
                                                        f"Gross cost INR {allocated_gross_cost:.2f}; Kisan Rail subsidy INR {allocated_subsidy:.2f}; "
                                                        f"net cost INR {allocated_net_cost:.2f}; expected transit {best['total_expected_time_hr']:.2f} hr.",
                        "all_candidate_routes": alt_summary
                    })

    return pd.DataFrame(individual_results)

def collect_shipments_interactively(products_df: pd.DataFrame, nodes_df: pd.DataFrame) -> pd.DataFrame:
    product_map = {str(p).strip().lower(): str(p).strip() for p in products_df["product"]}
    city_map = {str(c).strip().lower(): str(c).strip() for c in nodes_df["city"]}

    print("\nKnown products: " + ", ".join(sorted(products_df["product"].unique())))
    print("Known network cities: " + ", ".join(sorted(nodes_df["city"].unique())))
    
    print("\n--- Farmer / Business Owner Details ---")
    rows = []
    farmer_name = input("Farmer Name / Business Owner Name: ").strip()
    phone = input("Phone (optional): ").strip()
    
    try:
        num_products = int(input("How many products? ").strip())
    except ValueError:
        return pd.DataFrame()

    for i in range(num_products):
        print(f"\n  --- Product {i+1} of {num_products} ---")
        p_in = input("  Product: ").strip()
        if p_in.lower() not in product_map:
            print(f"  [Error] Product '{p_in}' invalid. Skipping.")
            continue
        product = product_map[p_in.lower()]

        o_in = input("  Origin city: ").strip()
        if o_in.lower() not in city_map:
            print(f"  [Error] Origin city '{o_in}' is not in the known network cities. Skipping this product.")
            continue
        origin = city_map[o_in.lower()]

        d_in = input("  Destination city: ").strip()
        if d_in.lower() not in city_map:
            print(f"  [Error] Destination city '{d_in}' is not in the known network cities. Skipping this product.")
            continue
        destination = city_map[d_in.lower()]
        
        expected_delivery_date = input("  Expected delivery date (e.g. 2026-11-20): ").strip()
        weight_kg = float(input("  Quantity (kg): ").strip())

        rows.append({
            "farmer_name": farmer_name, "phone": phone,
            "product": product, "origin": origin, "destination": destination,
            "expected_delivery_date": expected_delivery_date, "weight_kg": weight_kg
        })
        print("  added.\n")

    return pd.DataFrame(rows)

def print_shipment_plan(output: pd.DataFrame, audience: str = "farmer"):
    """audience="farmer" (default): reassuring, no raw 0-100 score shown --
    just a plain-English headline plus handling tips when extra care is
    needed. audience="fleet": full detail for ops/drivers, including the
    raw score and the numeric threshold, so risk can be tracked/triaged."""
    if output.empty:
        return

    print("\nProcessing logistics routing...\n")
    total_spend = 0.0
    pooled_groups = output["group_id"].nunique() if "group_id" in output.columns else output.shape[0]

    for _, row in output.iterrows():
        # A row with an "error" (e.g. an unresolvable city name) never got a
        # route computed -- it has no legs_for_display, cost, etc. Handle it
        # explicitly instead of letting the missing fields crash the printer.
        if "error" in row and pd.notna(row.get("error")):
            print("=" * 70)
            print("                 SHIPMENT COULD NOT BE ROUTED")
            print("=" * 70)
            print(f"Product:     {row.get('product', '?')}")
            print(f"Farmer:      {row.get('farmer_name', '?')}")
            print(f"FROM: {row.get('origin', '?')}   TO: {row.get('destination', '?')}")
            print(f"Reason: {row['error']}")
            print("=" * 70 + "\n")
            continue

        total_spend += row.get("total_cost_INR", 0.0)
        legs = row["legs_for_display"]
        primary_leg = legs[0] if legs else {}

        # Check if multiple products are sharing this group/vehicle
        group_id = row.get("group_id")
        group_items = output[output["group_id"] == group_id]["product"].tolist() if "group_id" in output.columns else [row["product"]]
        is_co_loaded = len(group_items) > 1

        print("=" * 70)
        print("                 YOUR SHIPMENT PLAN")
        print("=" * 70)

        # Print co-loaded items dynamically if paired
        if is_co_loaded:
            print(f"Product(s) Co-Loaded: {', '.join(group_items)} (PAIRED IN SAME VEHICLE)")
            print(f"This Item:           {row['product']} ({row['weight_kg']} kg)\n")
        else:
            print(f"Product(s): {row['product']}")
            print(f"Quantity:   {row['weight_kg']} kg\n")

        print(f"FROM: {row['origin']}")
        print(f"TO:   {row['destination']}\n")
        
        print("YOUR ROUTE")
        print(f"{row['route']}")
        print(f"  Mode: {row['modes_used']}\n")

        print("TRANSPORT DETAILS")
        for leg in legs:
            print(f"{leg['from']} -> {leg['to']} by {leg['mode']}")
            leg_vehicles = leg.get("vehicles") or []
            if len(leg_vehicles) > 1:
                # Load didn't fit in one truck -- it was split across several.
                # Show every vehicle so the farmer can reach every driver.
                print(f"  Load split across {len(leg_vehicles)} vehicles (no single truck had enough room):")
                for veh in leg_vehicles:
                    driver = veh.get("driver_name") or "NOT REGISTERED"
                    contact = veh.get("driver_contact") or "NOT REGISTERED"
                    order_id = veh.get("order_id", "")
                    print(f"    - {veh['vehicle_no']}: {veh['weight_kg']} kg | Driver: {driver} | Contact: {contact} | Order ID: {order_id}")
            else:
                print(f"  Vehicle/service: {leg['vehicle_no']}")
                print(f"  Driver: {leg['driver_name']}")
                print(f"  Contact: {leg['driver_contact']}")
                single_order_id = (leg_vehicles[0].get("order_id", "") if leg_vehicles else "")
                print(f"  Order ID: {single_order_id}")
            if is_co_loaded:
                print(f"  Cargo Manifest:  {', '.join(group_items)} (Shared vehicle load)")
            print(f"  Road-network distance: {leg['distance_km']} km\n")

        print("TIMING")
        print(f"Driving/rail planned time: {row['planned_time_hr']:.2f} hr")
        print(f"Transfer/handling time:     {row['transfer_handling_time_hr']:.2f} hr")
        print(f"Expected delay:             {row['expected_delay_hr']:.2f} hr")
        print(f"EXPECTED TOTAL TRANSIT:     {row['total_expected_time_hr']:.2f} hr\n")

        print("COLD-CHAIN / SHELF LIFE")
        print(f"Initial shelf life:         {row['shelf_life_hours']:.2f} hr")
        print(f"Remaining at expected arrival: {row['remaining_shelf_life_at_planned_arrival_hr']:.2f} hr")
        print(f"Predicted spoilage risk:    {row['predicted_spoilage_risk_pct']:.1f}% ({row['predicted_spoilage_risk_level']})\n")

        print("COST")
        print(f"Gross transport cost:       INR {row['gross_transport_cost_INR']:,.2f}")
        print(f"Kisan Rail subsidy:         INR {row['kisan_rail_subsidy_INR']:,.2f}")
        print(f"FARMER PAYS:                INR {row['total_cost_INR']:,.2f}\n")

        print("WHY THIS ROUTE?")
        print(str(row["route_selection_explanation"]) + "\n")

        print("COMPATIBILITY & CO-LOADING")
        if is_co_loaded:
            print(f"Group Pairings: {', '.join(group_items)}")
        if "compatibility_score" in row:
            score = row['compatibility_score']
            tips = row.get("compatibility_tips") or []
            needs_care = score < COMPATIBILITY_SCORE_THRESHOLD

            if audience == "fleet":
                # Full detail for ops/drivers: raw score + threshold + explicit flag.
                print(f"Compatibility Score: {score}/100 (threshold: {COMPATIBILITY_SCORE_THRESHOLD:.0f}/100) — {row.get('compatibility_headline', 'Compatible load')}")
                if needs_care:
                    print("BELOW THRESHOLD — reason(s):")
                    if tips:
                        for tip in tips:
                            print(f"  - {tip}")
                    else:
                        print(f"  - Score fell below the {COMPATIBILITY_SCORE_THRESHOLD:.0f}/100 threshold based on the combined risk factors for this load.")
                elif tips:
                    print("Handling instructions:")
                    for tip in tips:
                        print(f"  - {tip}")
            else:
                # Farmer-facing: lead with reassurance, no raw number, friendly tone.
                print("Your shipment is confirmed and on its way.")
                if needs_care:
                    print("This load needs a little extra care in transit:")
                    if tips:
                        for tip in tips:
                            print(f"  - {tip}")
                    else:
                        print("  - Please follow the driver's handling instructions for this load.")
                else:
                    print(f"{row.get('compatibility_headline', 'Safe to pool — no special precautions needed.')}")
                    if tips:
                        for tip in tips:
                            print(f"  - {tip}")
            print()
        else:
            print("Compatibility: Products validated as safe for co-loading\n")

        print("WHO TO CONTACT")
        # Collect every vehicle across every leg (not just the first leg's
        # first vehicle) so a split-load shipment lists every driver once.
        seen_vehicles = set()
        contact_lines = []
        for leg in legs:
            for veh in (leg.get("vehicles") or []):
                v_no = veh.get("vehicle_no", "")
                if not v_no or v_no in seen_vehicles:
                    continue
                seen_vehicles.add(v_no)
                driver = veh.get("driver_name") or "NOT REGISTERED"
                contact = veh.get("driver_contact") or "NOT REGISTERED"
                contact_lines.append(f"{v_no} | Driver: {driver} | Contact: {contact} | Carrying: {veh.get('weight_kg', '?')} kg | Order ID: {veh.get('order_id', '')}")
        if not contact_lines:
            contact_lines.append(f"{primary_leg.get('vehicle_no', '')} | Driver: {primary_leg.get('driver_name', '')} | Contact: {primary_leg.get('driver_contact', '')}")
        for line in contact_lines:
            print(line)
        print()

        print("ALL ROUTE OPTIONS CONSIDERED")
        print(row["all_candidate_routes"])
        print("=" * 70 + "\n")

    
    if "modes_used" in output.columns and "group_id" in output.columns:
        multimodal_groups = output.loc[output["is_multimodal"] == True, "group_id"].nunique()
    else:
        multimodal_groups = 0

    farmers_pooled = output["farmer_name"].nunique() if "farmer_name" in output.columns else 0
    high_risk_groups = (
        output.loc[output["predicted_spoilage_risk_level"].isin(["High", "Critical"]), "group_id"].nunique()
        if "predicted_spoilage_risk_level" in output.columns and "group_id" in output.columns else 0
    )

    print(f"\n----- SUMMARY -----")
    print(f"Farmers pooled: {farmers_pooled}")
    print(f"Total transportation expense across all shipments: INR {total_spend:,.2f}")
    print(f"Groups routed multimodally: {multimodal_groups} / {pooled_groups}")
    print(f"Groups with High/Critical spoilage risk: {high_risk_groups} / {pooled_groups}\n")

def register_vehicle_interactively(vehicles_df: pd.DataFrame) -> pd.DataFrame:
    """Option 2: register a new vehicle into the fleet. Appends one row to
    03_vehicles.csv with everything the routing engine needs to actually use
    this vehicle (mode, capacity, cost, speed), plus the fields explicitly
    requested: driver name, phone, origin (home base), destination, and
    min/max temperature control."""
    print("\n--- Register a New Vehicle ---")

    vehicle_no = input("Vehicle number/ID (e.g. OD-20-M-2010): ").strip()
    if vehicle_no and vehicle_no in vehicles_df["vehicle_no"].astype(str).values:
        print(f"  [Error] Vehicle number '{vehicle_no}' is already registered. Cancelling.")
        return vehicles_df

    mode = ""
    while mode not in ("Road", "Rail"):
        mode = input("Mode (Road/Rail): ").strip().capitalize()

    size_class = input("Size class (Small/Medium/Large/X-Large): ").strip()

    ref_in = ""
    while ref_in not in ("Y", "N"):
        ref_in = input("Refrigerated? (Y/N): ").strip().upper()
    refrigerated = ref_in

    temp_min, temp_max = "", ""
    if refrigerated == "Y":
        temp_min = input("Min controllable temperature (°C): ").strip()
        temp_max = input("Max controllable temperature (°C): ").strip()

    def ask_float(prompt, default=0.0):
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print(f"  Not a number, defaulting to {default}.")
            return default

    weight_capacity_kg = ask_float("Weight capacity (kg): ")
    volume_capacity_m3 = ask_float("Volume capacity (m3, enter 0 if unknown): ")
    price_per_kg_INR = ask_float("Price per kg (INR/kg per 100km): ")
    fixed_cost_INR = ask_float("Fixed cost per trip (INR): ")
    avg_speed_kmph = ask_float("Average speed (km/h): ", default=40.0)

    driver_name = input("Driver name: ").strip()
    driver_contact = input("Driver phone number: ").strip()
    origin = input("Origin / home base city: ").strip()
    destination = input("Usual destination city (informational only, not used for routing): ").strip()

    new_row = {
        "vehicle_no": vehicle_no,
        "mode": mode,
        "size_class": size_class,
        "refrigerated": refrigerated,
        "weight_capacity_kg": weight_capacity_kg,
        "volume_capacity_m3": volume_capacity_m3,
        "temp_control_min_C": temp_min,
        "temp_control_max_C": temp_max,
        "price_per_kg_INR": price_per_kg_INR,
        "fixed_cost_INR": fixed_cost_INR,
        "avg_speed_kmph": avg_speed_kmph,
        "driver_name": driver_name,
        "driver_contact": driver_contact,
        "remaining_capacity_kg": weight_capacity_kg,
        "current_location": origin,
        "usual_destination": destination,
    }

    updated = pd.concat([vehicles_df, pd.DataFrame([new_row])], ignore_index=True)
    print(f"\nVehicle {vehicle_no} registered with {weight_capacity_kg} kg capacity, based at {origin}.\n")
    return updated

def free_up_vehicle_interactively(vehicles_df: pd.DataFrame) -> pd.DataFrame:
    """Option 3: mark one vehicle's trip as completed -- resets that single
    vehicle's remaining_capacity_kg back to its full weight_capacity_kg."""
    print("\n--- Free Up Vehicle (Trip Completed) ---")
    vehicle_no = input("Vehicle number to free up: ").strip()

    mask = vehicles_df["vehicle_no"].astype(str) == vehicle_no
    if not mask.any():
        print(f"  [Error] Vehicle '{vehicle_no}' not found in the fleet. No changes made.\n")
        return vehicles_df

    updated = vehicles_df.copy()
    full_capacity = updated.loc[mask, "weight_capacity_kg"].iloc[0]
    updated.loc[mask, "remaining_capacity_kg"] = full_capacity
    print(f"\n{vehicle_no} is now free with full capacity ({full_capacity} kg) restored.\n")
    return updated

if __name__ == "__main__":
    print("=====================================================")
    print("       S17 Logistics Consolidation System            ")
    print("=====================================================")
    print("1: Farmer / Business Owner (Plan Shipments)")
    print("2: Fleet (Register Vehicles)")
    print("3: Fleet (Free Up Vehicle — Trip Completed)")
    print("=====================================================")
    
    choice = input("Select an option (1, 2 or 3): ").strip()
    if choice == '1':
        products_df, compat_df, vehicles_df, nodes_df, sample_shipments, trip_history = load_data()
        vehicles_df = normalize_vehicle_capacity(vehicles_df)
        
        farmer_input = collect_shipments_interactively(products_df, nodes_df)
        if not farmer_input.empty:
            output = process_farmer_shipments(farmer_input, products_df, compat_df, vehicles_df, nodes_df, trip_history)
            print_shipment_plan(output)
            output.to_csv("all_shipments_plan.csv", mode='a', header=not Path("all_shipments_plan.csv").exists(), index=False)
            save_vehicle_capacity(vehicles_df)
            print("Saved plan to: all_shipments_plan.csv")
    elif choice == '2':
        products_df, compat_df, vehicles_df, nodes_df, sample_shipments, trip_history = load_data()
        vehicles_df = normalize_vehicle_capacity(vehicles_df)
        vehicles_df = register_vehicle_interactively(vehicles_df)
        save_vehicle_capacity(vehicles_df)
    elif choice == '3':
        products_df, compat_df, vehicles_df, nodes_df, sample_shipments, trip_history = load_data()
        vehicles_df = normalize_vehicle_capacity(vehicles_df)
        vehicles_df = free_up_vehicle_interactively(vehicles_df)
        save_vehicle_capacity(vehicles_df)
    else:
        print("Invalid option.")