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

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent
AMBIENT_TEMP_C = 25.0            # product needs reefer if max_temp_C < this
RISK_PENALTY_WEIGHT = 1.0        # how much spoilage risk inflates a route's effective cost when choosing
NUM_CANDIDATE_ROUTES = 4         # how many alternate routes to evaluate per shipment group


# --------------------------------------------------------------------------
# DATA LOADING -- all 6 datasets
# --------------------------------------------------------------------------
def load_data(data_dir: Path = DATA_DIR):
    # Wrap in try-except in case files are missing during testing
    try:
        products = pd.read_csv(data_dir / "01_products_master.csv")
        compat = pd.read_csv(data_dir / "02_compatibility_matrix.csv")
        vehicles = pd.read_csv(data_dir / "03_vehicles.csv")
        nodes = pd.read_csv(data_dir / "04_transfer_points.csv")
        sample_shipments = pd.read_csv(data_dir / "05_farmer_shipments.csv")
        trip_history = pd.read_csv(data_dir / "06_historical_trips_delay.csv")
        return products, compat, vehicles, nodes, sample_shipments, trip_history
    except FileNotFoundError:
        print("Warning: One or more CSV datasets not found in the current directory.")
        print("Please ensure the 6 base CSV files are present.")
        sys.exit(1)

def build_delay_rate_lookup(trip_history: pd.DataFrame) -> dict:
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

# --------------------------------------------------------------------------
# STEP 1: REFRIGERATION REQUIREMENT
# --------------------------------------------------------------------------
def needs_refrigeration(product_row) -> bool:
    return product_row["max_temp_C"] < AMBIENT_TEMP_C

# --------------------------------------------------------------------------
# STEP 2: COMPATIBILITY GROUPING 
# --------------------------------------------------------------------------
def build_compatibility_lookup(compat_df: pd.DataFrame) -> dict:
    lookup = {}
    for _, r in compat_df.iterrows():
        key = frozenset([r["product_a"], r["product_b"]])
        lookup[key] = (r["compatible"] == "Y")
    return lookup

def are_compatible(p1: str, p2: str, lookup: dict) -> bool:
    if p1 == p2:
        return True
    return lookup.get(frozenset([p1, p2]), False)

def group_products_by_compatibility(product_list: list, lookup: dict) -> list:
    if len(product_list) <= 1:
        return [product_list] if product_list else []
    g = nx.Graph()
    g.add_nodes_from(product_list)
    for p1, p2 in itertools.combinations(product_list, 2):
        if are_compatible(p1, p2, lookup):
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

# --------------------------------------------------------------------------
# GEOGRAPHY
# --------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def resolve_location(city_name: str, nodes_df: pd.DataFrame, lat=None, lon=None) -> pd.Series:
    match = nodes_df[nodes_df["city"].str.strip().str.lower() == city_name.strip().lower()]
    if not match.empty:
        return match.iloc[0]
    if lat is None or lon is None:
        raise ValueError(
            f"'{city_name}' is not one of the known transfer-point cities. "
            f"Supply its latitude/longitude to include it."
        )
    return pd.Series({
        "node_id": f"EXT-{city_name}", "name": city_name, "city": city_name,
        "node_type": "external", "latitude": float(lat), "longitude": float(lon),
        "supports_road": "Y", "supports_rail": "N", "temp_controlled": "N",
        "avg_handling_time_hr": 0.0,
    })

# --------------------------------------------------------------------------
# STEP 3: VEHICLE SELECTION + COST/TIME PER LEG
# --------------------------------------------------------------------------
def pick_vehicle(weight_kg: float, refrigerated: bool, mode: str, vehicles_df: pd.DataFrame):
    ref_flag = "Y" if refrigerated else "N"
    candidates = vehicles_df[(vehicles_df["mode"] == mode) & (vehicles_df["refrigerated"] == ref_flag)]
    if candidates.empty:
        return None
    fitting = candidates[candidates["weight_capacity_kg"] >= weight_kg]
    if not fitting.empty:
        best = fitting.sort_values("price_per_kg_INR").iloc[0]
        return {"vehicle": best, "num_trips": 1}
    best = candidates.sort_values("weight_capacity_kg", ascending=False).iloc[0]
    num_trips = math.ceil(weight_kg / best["weight_capacity_kg"])
    return {"vehicle": best, "num_trips": num_trips}

def leg_cost(weight_kg: float, distance_km: float, refrigerated: bool, mode: str,
             vehicles_df: pd.DataFrame):
    pick = pick_vehicle(weight_kg, refrigerated, mode, vehicles_df)
    if pick is None:
        return None
    v, trips = pick["vehicle"], pick["num_trips"]
    cost = weight_kg * v["price_per_kg_INR"] * (distance_km / 100.0) * trips + v["fixed_cost_INR"] * trips
    time_hr = distance_km / v["avg_speed_kmph"] if v["avg_speed_kmph"] else None
    return {
        "cost_INR": round(cost, 2),
        "time_hr": round(time_hr, 2) if time_hr else None,
        "vehicle_no": v["vehicle_no"],
        "vehicle_mode": v["mode"],
        "size_class": v["size_class"],
        "num_trips": trips,
    }

# --------------------------------------------------------------------------
# STEP 4: MULTIMODAL ROUTE GRAPH + CANDIDATE ROUTES
# --------------------------------------------------------------------------
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
        if dist == 0:
            continue
        if a.supports_road == "Y" and b.supports_road == "Y":
            leg = leg_cost(weight_kg, dist, refrigerated, "Road", vehicles_df)
            if leg:
                G.add_edge(a.city, b.city, key="Road", mode="Road", distance_km=round(dist, 1), **leg)
        if a.supports_rail == "Y" and b.supports_rail == "Y":
            leg = leg_cost(weight_kg, dist, refrigerated, "Rail", vehicles_df)
            if leg:
                G.add_edge(a.city, b.city, key="Rail", mode="Rail", distance_km=round(dist, 1), **leg)

    return G

def _mode_subgraph(G: nx.MultiDiGraph, mode: str) -> nx.DiGraph:
    H = nx.DiGraph()
    H.add_nodes_from(G.nodes(data=True))
    for u, v, k, d in G.edges(keys=True, data=True):
        if d["mode"] == mode:
            H.add_edge(u, v, **d)
    return H

def _cheapest_collapsed_graph(G: nx.MultiDiGraph) -> nx.DiGraph:
    H = nx.DiGraph()
    H.add_nodes_from(G.nodes(data=True))
    for u, v, k, d in G.edges(keys=True, data=True):
        if not H.has_edge(u, v) or d["cost_INR"] < H[u][v]["cost_INR"]:
            H.add_edge(u, v, **d)
    return H

def summarize_path(G: nx.DiGraph, path: list, nodes_df: pd.DataFrame, delay_rates: dict) -> dict:
    legs = []
    total_cost = 0.0
    total_distance = 0.0
    planned_time = 0.0
    modes_used = set()

    for u, v in zip(path[:-1], path[1:]):
        edge = G[u][v]
        legs.append({
            "from": u, "to": v, "mode": edge["mode"], "distance_km": edge["distance_km"],
            "vehicle_no": edge["vehicle_no"], "size_class": edge["size_class"],
            "cost_INR": edge["cost_INR"], "time_hr": edge["time_hr"], "num_trips": edge["num_trips"],
        })
        total_cost += edge["cost_INR"]
        total_distance += edge["distance_km"]
        planned_time += edge["time_hr"] or 0
        modes_used.add(edge["mode"])

    handling_time = 0.0
    for city in path[1:-1]:
        h = nodes_df.loc[nodes_df["city"] == city, "avg_handling_time_hr"]
        if not h.empty:
            handling_time += h.iloc[0]
    planned_time += handling_time

    if modes_used == {"Road"}:
        delay_category = "Road-only"
    elif modes_used == {"Rail"}:
        delay_category = "Rail-only"
    else:
        delay_category = "Mixed"
    expected_delay_hr = delay_rates.get(delay_category, 0.5) * (total_distance / 100.0)

    return {
        "route": path,
        "legs": legs,
        "total_cost_INR": round(total_cost, 2),
        "total_distance_km": round(total_distance, 1),
        "planned_time_hr": round(planned_time, 2),
        "expected_delay_hr": round(expected_delay_hr, 2),
        "total_expected_time_hr": round(planned_time + expected_delay_hr, 2),
        "delay_category": delay_category,
        "is_multimodal": len(modes_used) > 1,
        "modes_used": sorted(modes_used),
    }

def spoilage_risk(total_expected_time_hr: float, shelf_life_hours: float) -> dict:
    if shelf_life_hours <= 0:
        fraction = 1.0
    else:
        fraction = total_expected_time_hr / shelf_life_hours
    if fraction < 0.4:
        level = "Low"
    elif fraction < 0.7:
        level = "Medium"
    elif fraction < 1.0:
        level = "High"
    else:
        level = "Critical"
    return {"risk_fraction": round(fraction, 3), "risk_pct": round(fraction * 100, 1), "risk_level": level}

def select_best_route(candidates: list) -> dict:
    for c in candidates:
        c["combined_score"] = c["total_cost_INR"] * (1 + RISK_PENALTY_WEIGHT * c["risk_fraction"])
    return min(candidates, key=lambda c: (c["combined_score"], c["total_cost_INR"]))

def find_candidate_routes(origin_city: str, destination_city: str, weight_kg: float, refrigerated: bool,
                           shelf_life_hours: float, nodes_df: pd.DataFrame, vehicles_df: pd.DataFrame,
                           delay_rates: dict, origin_latlon=None, destination_latlon=None,
                           k: int = NUM_CANDIDATE_ROUTES):
    o_lat, o_lon = origin_latlon if origin_latlon else (None, None)
    d_lat, d_lon = destination_latlon if destination_latlon else (None, None)
    try:
        origin_row = resolve_location(origin_city, nodes_df, o_lat, o_lon)
        dest_row = resolve_location(destination_city, nodes_df, d_lat, d_lon)
    except ValueError as e:
        return {"error": str(e)}

    G = build_route_graph(weight_kg, refrigerated, nodes_df, vehicles_df, origin_row, dest_row)
    origin_city_key, dest_city_key = origin_row["city"], dest_row["city"]

    def make_candidate(path, path_graph):
        summary = summarize_path(path_graph, path, nodes_df, delay_rates)
        risk = spoilage_risk(summary["total_expected_time_hr"], shelf_life_hours)
        summary.update(risk)
        return summary

    candidates = {}
    road_only_G = _mode_subgraph(G, "Road")
    try:
        path = nx.shortest_path(road_only_G, origin_city_key, dest_city_key, weight="cost_INR")
        candidates["Road only"] = make_candidate(path, road_only_G)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass

    rail_only_G = _mode_subgraph(G, "Rail")
    try:
        path = nx.shortest_path(rail_only_G, origin_city_key, dest_city_key, weight="cost_INR")
        candidates["Rail only"] = make_candidate(path, rail_only_G)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass

    collapsed_G = _cheapest_collapsed_graph(G)
    try:
        path_gen = nx.shortest_simple_paths(collapsed_G, origin_city_key, dest_city_key, weight="cost_INR")
        checked = 0
        for path in path_gen:
            checked += 1
            if checked > max(k, 10):
                break
            cand = make_candidate(path, collapsed_G)
            if cand["is_multimodal"]:
                candidates["Road+Rail"] = cand
                break
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass

    if not candidates:
        return {"error": f"No viable route found between {origin_city} and {destination_city}"}

    candidate_list = list(candidates.values())
    for name, c in candidates.items():
        c["strategy"] = name

    best = select_best_route(candidate_list)
    cheapest = min(candidate_list, key=lambda c: c["total_cost_INR"])
    best["was_cheapest"] = (best is cheapest) or (best["total_cost_INR"] == cheapest["total_cost_INR"])
    best["cheapest_cost_INR"] = cheapest["total_cost_INR"]
    best["cheapest_risk_pct"] = cheapest["risk_pct"]

    return {"best": best, "all_candidates": candidate_list}

# --------------------------------------------------------------------------
# STEP 5: END-TO-END -- PROCESS A BATCH OF FARMER SHIPMENTS
# --------------------------------------------------------------------------
def process_farmer_shipments(shipments_df: pd.DataFrame, products_df: pd.DataFrame,
                              compat_df: pd.DataFrame, vehicles_df: pd.DataFrame,
                              nodes_df: pd.DataFrame, trip_history: pd.DataFrame) -> pd.DataFrame:
    
    products_lookup = products_df.set_index("product")
    compat_lookup = build_compatibility_lookup(compat_df)
    delay_rates = build_delay_rate_lookup(trip_history)

    for col in ["origin_lat", "origin_lon", "dest_lat", "dest_lon"]:
        if col not in shipments_df.columns:
            shipments_df[col] = pd.NA
    if "farmer_name" not in shipments_df.columns:
        shipments_df["farmer_name"] = "UNKNOWN_FARMER"

    results = []
    group_counter = 0

    group_keys = ["origin", "destination", "origin_lat", "origin_lon", "dest_lat", "dest_lon"]
    for keys, leg_df in shipments_df.groupby(group_keys, dropna=False):
        origin, destination, o_lat, o_lon, d_lat, d_lon = keys
        leg_df = leg_df.copy()
        leg_df["needs_reefer"] = leg_df["product"].apply(
            lambda p: needs_refrigeration(products_lookup.loc[p]) if p in products_lookup.index else True
        )

        for reefer_flag, ref_df in leg_df.groupby("needs_reefer"):
            distinct_products = ref_df["product"].unique().tolist()
            product_groups = group_products_by_compatibility(distinct_products, compat_lookup)

            for group in product_groups:
                group_shipments = ref_df[ref_df["product"].isin(group)]
                total_weight = float(group_shipments["weight_kg"].sum())
                farmer_names = sorted(group_shipments["farmer_name"].astype(str).unique().tolist())

                shelf_lives = [
                    products_lookup.loc[p, "shelf_life_hours"]
                    for p in group if p in products_lookup.index
                ]
                group_shelf_life_hours = min(shelf_lives) if shelf_lives else 1e9

                origin_latlon = (o_lat, o_lon) if pd.notna(o_lat) and pd.notna(o_lon) else None
                dest_latlon = (d_lat, d_lon) if pd.notna(d_lat) and pd.notna(d_lon) else None

                result = find_candidate_routes(
                    origin, destination, total_weight, bool(reefer_flag), group_shelf_life_hours,
                    nodes_df, vehicles_df, delay_rates, origin_latlon, dest_latlon
                )

                group_counter += 1
                if "error" in result:
                    results.append({
                        "group_id": f"G{group_counter:04d}", "origin": origin, "destination": destination,
                        "products": ", ".join(group), "farmer_names": ", ".join(farmer_names),
                        "num_farmers": len(farmer_names), "refrigerated_required": bool(reefer_flag),
                        "total_weight_kg": total_weight, "error": result["error"],
                    })
                    continue

                best = result["best"]
                alt_summary = " | ".join(
                    f"{c['strategy']}: cost=INR{c['total_cost_INR']:.0f}, "
                    f"time={c['total_expected_time_hr']:.1f}hr, risk={c['risk_pct']:.0f}% ({c['risk_level']})"
                    for c in result["all_candidates"]
                )

                results.append({
                    "group_id": f"G{group_counter:04d}",
                    "origin": origin,
                    "destination": destination,
                    "products": ", ".join(group),
                    "farmer_names": ", ".join(farmer_names),
                    "num_farmers": len(farmer_names),
                    "num_farmer_shipments": len(group_shipments),
                    "refrigerated_required": bool(reefer_flag),
                    "total_weight_kg": total_weight,
                    "route": " -> ".join(best["route"]),
                    "route_detail": " | ".join(
                        f"{l['from']}->{l['to']} by {l['mode']} ({l['distance_km']}km, {l['vehicle_no']})"
                        for l in best["legs"]
                    ),
                    "is_multimodal": best["is_multimodal"],
                    "modes_used": ", ".join(best["modes_used"]),
                    "total_cost_INR": best["total_cost_INR"],
                    "planned_time_hr": best["planned_time_hr"],
                    "expected_delay_hr": best["expected_delay_hr"],
                    "total_expected_time_hr": best["total_expected_time_hr"],
                    "shelf_life_hours": group_shelf_life_hours,
                    "spoilage_risk_pct": best["risk_pct"],
                    "spoilage_risk_level": best["risk_level"],
                    "chosen_route_is_cheapest": best["was_cheapest"],
                    "cheapest_alt_cost_INR": best["cheapest_cost_INR"],
                    "cheapest_alt_risk_pct": best["cheapest_risk_pct"],
                    "extra_cost_paid_to_reduce_risk_INR": round(best["total_cost_INR"] - best["cheapest_cost_INR"], 2),
                    "all_candidate_routes": alt_summary,
                })

    return pd.DataFrame(results)

# --------------------------------------------------------------------------
# OPTION 1: FARMER / BUSINESS OWNER INPUT
# --------------------------------------------------------------------------
def collect_shipments_interactively(products_df: pd.DataFrame, nodes_df: pd.DataFrame) -> pd.DataFrame:
    # Create mapping dictionaries to resolve user input to original dataset casing
    product_map = {str(p).strip().lower(): p for p in products_df["product"]}
    city_map = {str(c).strip().lower(): c for c in nodes_df["city"]}

    print("\n--- Farmer / Business Owner Mode ---")
    print(f"Known products: {', '.join(sorted(product_map.values()))}")
    print(f"Known network cities: {', '.join(sorted(city_map.values()))}\n")

    rows = []
    
    print("--- Farmer / Business Owner Details ---")
    farmer_name = input("Farmer Name / Business Owner Name: ").strip()
    phone = input("Phone (optional): ").strip()
    
    try:
        num_products = int(input("How many products? ").strip())
    except ValueError:
        print("  Please enter a valid number. Returning to main menu.\n")
        return pd.DataFrame()

    for i in range(num_products):
        print(f"\n  --- Product {i+1} of {num_products} ---")
        product_input = input("  Product: ").strip()
        if product_input.lower() not in product_map:
            print(f"  '{product_input}' not in product master -- skipping this entry.")
            continue
        # Standardize casing to exactly what the database expects
        product = product_map[product_input.lower()]

        origin_input = input("  Origin city: ").strip()
        origin_lat = origin_lon = None
        if origin_input.lower() not in city_map:
            origin = origin_input # Off-network retains exact user input
            origin_lat = float(input(f"    '{origin}' is off-network -- latitude: "))
            origin_lon = float(input(f"    longitude: "))
        else:
            # Standardize casing
            origin = city_map[origin_input.lower()]

        destination_input = input("  Destination city: ").strip()
        dest_lat = dest_lon = None
        if destination_input.lower() not in city_map:
            destination = destination_input # Off-network retains exact user input
            dest_lat = float(input(f"    '{destination}' is off-network -- latitude: "))
            dest_lon = float(input(f"    longitude: "))
        else:
            # Standardize casing
            destination = city_map[destination_input.lower()]
        
        expected_delivery_date = input("  Expected delivery date (e.g. 2024-11-20): ").strip()
        # Ask for Quantity, but store as weight_kg to keep routing math intact
        weight_kg = float(input("  Quantity (kg): ").strip())

        rows.append({
            "farmer_name": farmer_name, 
            "phone": phone,
            "product": product, 
            "origin": origin, 
            "destination": destination,
            "expected_delivery_date": expected_delivery_date,
            "weight_kg": weight_kg,
            "origin_lat": origin_lat, "origin_lon": origin_lon,
            "dest_lat": dest_lat, "dest_lon": dest_lon,
        })
        print("  added.\n")

    return pd.DataFrame(rows)

# --------------------------------------------------------------------------
# OPTION 2: FLEET INPUT
# --------------------------------------------------------------------------
def collect_fleet_interactively(data_dir: Path):
    print("\n--- Fleet Mode ---")
    print("Enter Information to register a new vehicle.\n")
    
    vehicle_no = input("Vehicle no. (e.g.,OD-02-CB-8765): ").strip()
    mode = input("Vehicle mode (Road / Rail): ").strip().capitalize()
    if mode=="Road":
        size_class = input("Size class (e.g., Small, Medium, Large): ").strip()
    else:
        size_class = input("Size class (e.g., Wagon-Small, Wagon-Large): ").strip()
    refrigerated = input("Refrigerated (Y/N): ").strip().upper()
    
    try:
        weight_capacity_kg = float(input("Weight capacity (kg): ").strip())
        volume_capacity_m3 = float(input("Volume capacity (m3): ").strip())
    except ValueError:
        print("Invalid number entered for capacity. Returning to main menu.")
        return

    # Handle temperature settings for refrigerated vehicles
    temp_control_min_C = ""
    temp_control_max_C = ""
    if refrigerated == "Y":
        temp_control_min_C = input("Temp control min (C): ").strip()
        temp_control_max_C = input("Temp control max (C): ").strip()

    try:
        price_per_kg_INR = float(input("Price per kg (INR): ").strip())
        fixed_cost_INR = float(input("Fixed cost (INR): ").strip())
        avg_speed_kmph = float(input("Average speed (kmph): ").strip())
    except ValueError:
        print("Invalid number entered for cost or speed. Returning to main menu.")
        return
    
    # Store exactly according to 03_vehicles.csv structure (column name must
    # match the file's actual header, "vehicle_no")
    new_vehicle = {
        "vehicle_no": vehicle_no,
        "mode": mode,
        "size_class": size_class,
        "refrigerated": refrigerated,
        "weight_capacity_kg": weight_capacity_kg,
        "volume_capacity_m3": volume_capacity_m3,
        "temp_control_min_C": temp_control_min_C,
        "temp_control_max_C": temp_control_max_C,
        "price_per_kg_INR": price_per_kg_INR,
        "fixed_cost_INR": fixed_cost_INR,
        "avg_speed_kmph": avg_speed_kmph
    }

    file_path = data_dir / "03_vehicles.csv"

    # Guard against duplicate vehicle IDs
    if file_path.is_file():
        try:
            existing = pd.read_csv(file_path)
            if vehicle_no in existing["vehicle_no"].astype(str).values:
                print(f"  A vehicle with ID '{vehicle_no}' is already registered. "
                      f"Please use a unique vehicle ID. Returning to main menu.\n")
                return
        except (pd.errors.EmptyDataError, KeyError):
            pass  # file exists but is empty/headerless -- fine, we'll write fresh

    df = pd.DataFrame([new_vehicle])

    if file_path.is_file() and file_path.stat().st_size > 0:
        # Make sure the file ends with a newline before appending, or the new
        # row gets glued onto the end of the last existing row instead of
        # starting on its own line (this previously corrupted the file).
        with open(file_path, "rb+") as f:
            f.seek(0, 2)  # end of file
            if f.tell() > 0:
                f.seek(-1, 2)
                last_byte = f.read(1)
                if last_byte not in (b"\n", b"\r"):
                    f.write(b"\n")
        df.to_csv(file_path, mode='a', header=False, index=False)
    else:
        df.to_csv(file_path, index=False)

    print("  Fleet entry added.")
    print(f"  Saved new fleet entry directly to {file_path.name}")


# --------------------------------------------------------------------------
# TERMINAL-FRIENDLY OUTPUT
# --------------------------------------------------------------------------
def print_shipment_plan(output: pd.DataFrame):
    """Print one readable card per shipment group instead of one giant
    wide table -- the wide to_string() dump wraps/truncates unpredictably
    in a normal terminal width and is hard to read top-to-bottom."""
    if output.empty:
        print("No routed groups to display.")
        return

    for _, row in output.iterrows():
        print("=" * 70)
        print(f"Group {row.get('group_id', '?')}: {row.get('origin', '?')} -> {row.get('destination', '?')}")
        print("-" * 70)

        if "error" in row and pd.notna(row.get("error")):
            print(f"  Products            : {row.get('products', '')}")
            print(f"  ERROR                : {row['error']}")
            continue

        print(f"  Products             : {row.get('products', '')}")
        print(f"  Farmers              : {row.get('farmer_names', '')} "
              f"({row.get('num_farmers', '?')} farmer(s), {row.get('num_farmer_shipments', '?')} shipment(s))")
        print(f"  Total weight         : {row.get('total_weight_kg', '?')} kg")
        print(f"  Refrigeration needed : {'Yes' if row.get('refrigerated_required') else 'No'}")
        print()
        print(f"  Route                : {row.get('route', '')}")
        print(f"    -> {row.get('route_detail', '')}")
        print(f"  Mode(s) used         : {row.get('modes_used', '')} "
              f"({'multimodal' if row.get('is_multimodal') else 'single mode'})")
        print()
        print(f"  Cost                 : INR {row.get('total_cost_INR', 0):,.2f}")
        print(f"  Planned time         : {row.get('planned_time_hr', '?')} hr")
        print(f"  Expected delay       : {row.get('expected_delay_hr', '?')} hr")
        print(f"  Total expected time  : {row.get('total_expected_time_hr', '?')} hr")
        print(f"  Shelf life           : {row.get('shelf_life_hours', '?')} hr")
        print(f"  Spoilage risk        : {row.get('spoilage_risk_pct', '?')}% ({row.get('spoilage_risk_level', '?')})")
        print()
        if row.get("chosen_route_is_cheapest"):
            print("  Chosen route is the cheapest option available.")
        else:
            extra = row.get("extra_cost_paid_to_reduce_risk_INR", 0)
            print(f"  Chosen route is NOT the cheapest -- paid INR {extra:,.2f} extra "
                  f"over the cheapest option (INR {row.get('cheapest_alt_cost_INR', 0):,.2f}) "
                  f"to cut spoilage risk to {row.get('cheapest_alt_risk_pct', '?')}% -> {row.get('spoilage_risk_pct', '?')}%.")
        if row.get("all_candidate_routes"):
            print(f"  All candidates       : {row['all_candidate_routes']}")

    print("=" * 70)


# --------------------------------------------------------------------------
# MAIN MENU / EXECUTION
# --------------------------------------------------------------------------
if __name__ == "__main__":
    
    print("=====================================================")
    print("       S17 Logistics Consolidation System            ")
    print("=====================================================")
    print("1: Farmer / Business Owner (Plan Shipments)")
    print("2: Fleet (Register Vehicles)")
    print("=====================================================")
    
    choice = input("Select an option (1 or 2): ").strip()
    
    if choice == '1':
        products_df, compat_df, vehicles_df, nodes_df, sample_shipments, trip_history = load_data()
        
        farmer_input = collect_shipments_interactively(products_df, nodes_df)

        if farmer_input.empty:
            print("No shipments entered -- nothing to process.")
            sys.exit(0)

        print("\nProcessing logistics routing...")
        output = process_farmer_shipments(farmer_input, products_df, compat_df, vehicles_df, nodes_df, trip_history)

        print()
        print_shipment_plan(output)

        total_expense = output["total_cost_INR"].sum() if "total_cost_INR" in output.columns else 0
        num_multimodal = int(output["is_multimodal"].sum()) if "is_multimodal" in output.columns else 0
        num_farmers_total = farmer_input["farmer_name"].nunique() if "farmer_name" in farmer_input.columns else None
        high_risk = output[output["spoilage_risk_level"].isin(["High", "Critical"])] if "spoilage_risk_level" in output.columns else pd.DataFrame()

        print("\n----- SUMMARY -----")
        print(f"Farmers pooled: {num_farmers_total}")
        print(f"Total transportation expense across all shipments: INR {total_expense:,.2f}")
        print(f"Groups routed multimodally: {num_multimodal} / {len(output)}")
        print(f"Groups with High/Critical spoilage risk: {len(high_risk)} / {len(output)}")

        # Save to a single master file, appending new data to the bottom without rewriting the header
        plan_file_path = "all_shipments_plan.csv"
        if Path(plan_file_path).is_file():
            output.to_csv(plan_file_path, mode='a', header=False, index=False)
        else:
            output.to_csv(plan_file_path, index=False)
            
        print(f"\nSaved plan to: {plan_file_path}")
        
    elif choice == '2':
        collect_fleet_interactively(DATA_DIR)
        
    else:
        print("Invalid choice. Please run the script again and select 1 or 2.")