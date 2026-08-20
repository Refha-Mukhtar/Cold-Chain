"""
S17 Logistics Consolidation & Multimodal Routing Model (general-purpose)
==========================================================================

Pipeline:
  1. Read farmer shipment requests (product, origin, destination, weight_kg, max_price_per_kg)
  2. Flag which products need a refrigerated vehicle
  3. Group shipments travelling the same origin->destination into product
     combinations that are mutually compatible (ethylene / temperature / humidity)
  4. For each group, find the cheapest route across a road+rail multimodal
     network of transfer points -- multimodal is only recommended if it is
     CHEAPER than a direct road-only trip
  5. Compute cost, expected time, and profit (farmer's willingness-to-pay minus
     actual transport cost) per group

Reads all 6 datasets:
  01_products_master.csv, 02_compatibility_matrix.csv, 03_vehicles.csv,
  04_transfer_points.csv, 05_farmer_shipments.csv, 06_historical_trips_delay.csv

ORIGIN/DESTINATION IS NOT HARDCODED -- two ways to run this:
  A) Interactive:  python logistics_model.py
                    -> prompts you to type in shipments one at a time
  B) From a file:  python logistics_model.py my_shipments.csv
                    -> reads any CSV with columns:
                       product, origin, destination, weight_kg
                       (optional: origin_lat, origin_lon, dest_lat, dest_lon)

No farmer pricing input is collected. "Profit" is redefined here as the
money SAVED by routing a group multimodally instead of direct road-only --
it's only computed where multimodal actually won; direct-road groups show
blank. A grand total transportation expense across all shipments is also
printed at the end of the run.

A city not already in 04_transfer_points.csv still works -- you'll be asked
(interactive mode) or expected to supply (CSV mode) its lat/lon so it can be
connected into the network as a road-only "last mile" point.

ASSUMPTIONS (change these constants/formulas for your real numbers):
  - AMBIENT_TEMP_C: a product needs refrigeration if its max tolerable
    temperature is below normal ambient transport temperature.
  - Vehicle `price_per_kg_INR` is treated as a rate per kg PER 100 KM
    (the original dataset didn't carry per-km granularity) -- see leg_cost().
  - The transfer-point network is treated as fully connected for road, and
    fully connected for rail among rail-enabled nodes -- real road/rail
    distances should come from OSRM/GraphHopper and Indian Railways FOIS
    data respectively; here distance is straight-line (haversine), a
    reasonable proxy for a demo but not for production.
  - An origin/destination outside the known network is assumed road-only
    (no direct rail access) and adds no extra handling time of its own.
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
DATA_DIR = Path(__file__).resolve().parent   # <-- point at your CSV folder
AMBIENT_TEMP_C = 25.0                                      # product needs reefer if max_temp_C < this


# --------------------------------------------------------------------------
# DATA LOADING -- all 6 datasets
# --------------------------------------------------------------------------
def load_data(data_dir: Path = DATA_DIR):
    products = pd.read_csv(data_dir / "01_products_master.csv")
    compat = pd.read_csv(data_dir / "02_compatibility_matrix.csv")
    vehicles = pd.read_csv(data_dir / "03_vehicles.csv")
    nodes = pd.read_csv(data_dir / "04_transfer_points.csv")
    sample_shipments = pd.read_csv(data_dir / "05_farmer_shipments.csv")   # optional, example format
    trip_history = pd.read_csv(data_dir / "06_historical_trips_delay.csv")  # optional, not used for cost yet
    return products, compat, vehicles, nodes, sample_shipments, trip_history


# --------------------------------------------------------------------------
# STEP 1: REFRIGERATION REQUIREMENT
# --------------------------------------------------------------------------
def needs_refrigeration(product_row) -> bool:
    """A product needs a reefer vehicle if ambient transport temperature
    would exceed what it can tolerate."""
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
    """Maximal cliques in the compatibility graph -> groups that can share one vehicle."""
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
    """
    Any city works here, not just the 20 in the network:
      - if city_name matches a transfer point, use it (road + rail as flagged there)
      - otherwise lat/lon must be supplied -- the point is added as a
        road-only "last mile" location connected into the network
    """
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
# STEP 3: VEHICLE SELECTION + COST PER LEG
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
    """ASSUMPTION: price_per_kg_INR is a rate per kg per 100 km."""
    pick = pick_vehicle(weight_kg, refrigerated, mode, vehicles_df)
    if pick is None:
        return None
    v, trips = pick["vehicle"], pick["num_trips"]
    cost = weight_kg * v["price_per_kg_INR"] * (distance_km / 100.0) * trips + v["fixed_cost_INR"] * trips
    time_hr = distance_km / v["avg_speed_kmph"] if v["avg_speed_kmph"] else None
    return {
        "cost_INR": round(cost, 2),
        "time_hr": round(time_hr, 2) if time_hr else None,
        "vehicle_id": v["vehicle_id"],
        "vehicle_mode": v["mode"],
        "size_class": v["size_class"],
        "num_trips": trips,
    }


# --------------------------------------------------------------------------
# STEP 4: MULTIMODAL ROUTE GRAPH
# --------------------------------------------------------------------------
def build_route_graph(weight_kg: float, refrigerated: bool, nodes_df: pd.DataFrame,
                       vehicles_df: pd.DataFrame, origin_row: pd.Series, dest_row: pd.Series) -> nx.DiGraph:
    all_nodes = pd.concat(
        [nodes_df, pd.DataFrame([origin_row]), pd.DataFrame([dest_row])], ignore_index=True
    ).drop_duplicates(subset="city", keep="first")

    G = nx.DiGraph()
    for _, n in all_nodes.iterrows():
        G.add_node(n["city"], lat=n["latitude"], lon=n["longitude"])

    for a, b in itertools.permutations(all_nodes.itertuples(index=False), 2):
        dist = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
        if dist == 0:
            continue

        if a.supports_road == "Y" and b.supports_road == "Y":
            leg = leg_cost(weight_kg, dist, refrigerated, "Road", vehicles_df)
            if leg and (not G.has_edge(a.city, b.city) or leg["cost_INR"] < G[a.city][b.city].get("cost_INR", float("inf"))):
                G.add_edge(a.city, b.city, mode="Road", distance_km=round(dist, 1), **leg)

        if a.supports_rail == "Y" and b.supports_rail == "Y":
            leg = leg_cost(weight_kg, dist, refrigerated, "Rail", vehicles_df)
            if leg and (not G.has_edge(a.city, b.city) or leg["cost_INR"] < G[a.city][b.city].get("cost_INR", float("inf"))):
                G.add_edge(a.city, b.city, mode="Rail", distance_km=round(dist, 1), **leg)

    return G


def find_best_route(origin_city: str, destination_city: str, weight_kg: float, refrigerated: bool,
                     nodes_df: pd.DataFrame, vehicles_df: pd.DataFrame,
                     origin_latlon=None, destination_latlon=None):
    """origin_latlon / destination_latlon: optional (lat, lon) tuples, only
    needed if the city isn't already in nodes_df."""
    o_lat, o_lon = origin_latlon if origin_latlon else (None, None)
    d_lat, d_lon = destination_latlon if destination_latlon else (None, None)

    try:
        origin_row = resolve_location(origin_city, nodes_df, o_lat, o_lon)
        dest_row = resolve_location(destination_city, nodes_df, d_lat, d_lon)
    except ValueError as e:
        return {"error": str(e)}

    G = build_route_graph(weight_kg, refrigerated, nodes_df, vehicles_df, origin_row, dest_row)

    try:
        path = nx.shortest_path(G, origin_row["city"], dest_row["city"], weight="cost_INR")
    except nx.NetworkXNoPath:
        return {"error": f"No viable route found between {origin_city} and {destination_city}"}

    legs = []
    total_cost = 0.0
    total_time = 0.0
    modes_used = set()
    for u, v in zip(path[:-1], path[1:]):
        edge = G[u][v]
        legs.append({
            "from": u, "to": v, "mode": edge["mode"], "distance_km": edge["distance_km"],
            "vehicle_id": edge["vehicle_id"], "size_class": edge["size_class"],
            "cost_INR": edge["cost_INR"], "time_hr": edge["time_hr"], "num_trips": edge["num_trips"],
        })
        total_cost += edge["cost_INR"]
        total_time += edge["time_hr"] or 0
        modes_used.add(edge["mode"])

    for city in path[1:-1]:
        handling = nodes_df.loc[nodes_df["city"] == city, "avg_handling_time_hr"]
        if not handling.empty:
            total_time += handling.iloc[0]

    direct_dist = haversine_km(origin_row["latitude"], origin_row["longitude"],
                                dest_row["latitude"], dest_row["longitude"])
    baseline = leg_cost(weight_kg, direct_dist, refrigerated, "Road", vehicles_df)

    is_multimodal = len(modes_used) > 1
    savings = round((baseline["cost_INR"] - total_cost), 2) if baseline else None

    return {
        "route": path,
        "legs": legs,
        "total_cost_INR": round(total_cost, 2),
        "total_time_hr": round(total_time, 2),
        "is_multimodal": is_multimodal,
        "modes_used": sorted(modes_used),
        "direct_road_only_cost_INR": baseline["cost_INR"] if baseline else None,
        "savings_vs_direct_road_INR": savings,
    }


# --------------------------------------------------------------------------
# STEP 5: END-TO-END -- PROCESS A BATCH OF FARMER SHIPMENTS
# --------------------------------------------------------------------------
def process_farmer_shipments(shipments_df: pd.DataFrame, products_df: pd.DataFrame,
                              compat_df: pd.DataFrame, vehicles_df: pd.DataFrame,
                              nodes_df: pd.DataFrame) -> pd.DataFrame:
    """
    shipments_df required columns: product, origin, destination, weight_kg
    optional columns (needed only for cities outside the known network):
      origin_lat, origin_lon, dest_lat, dest_lon

    No farmer price input is used. "Profit" here means the money SAVED by
    routing multimodally instead of direct road-only -- it is only computed
    for groups where a multimodal route was actually chosen; direct-road
    groups have no such saving, so profit_INR is left blank for them.
    """
    products_lookup = products_df.set_index("product")
    compat_lookup = build_compatibility_lookup(compat_df)

    for col in ["origin_lat", "origin_lon", "dest_lat", "dest_lon"]:
        if col not in shipments_df.columns:
            shipments_df[col] = pd.NA

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

                origin_latlon = (o_lat, o_lon) if pd.notna(o_lat) and pd.notna(o_lon) else None
                dest_latlon = (d_lat, d_lon) if pd.notna(d_lat) and pd.notna(d_lon) else None

                route = find_best_route(origin, destination, total_weight, bool(reefer_flag),
                                         nodes_df, vehicles_df, origin_latlon, dest_latlon)

                group_counter += 1
                if "error" in route:
                    results.append({
                        "group_id": f"G{group_counter:04d}", "origin": origin, "destination": destination,
                        "products": ", ".join(group), "refrigerated_required": bool(reefer_flag),
                        "total_weight_kg": total_weight, "error": route["error"],
                    })
                    continue

                cost = route["total_cost_INR"]
                # Profit = money saved vs. direct road-only, ONLY when a
                # multimodal route was actually chosen. Direct-road groups
                # have nothing to compare against, so profit is left blank.
                profit = route["savings_vs_direct_road_INR"] if route["is_multimodal"] else None

                results.append({
                    "group_id": f"G{group_counter:04d}",
                    "origin": origin,
                    "destination": destination,
                    "products": ", ".join(group),
                    "num_farmer_shipments": len(group_shipments),
                    "refrigerated_required": bool(reefer_flag),
                    "total_weight_kg": total_weight,
                    "route": " -> ".join(route["route"]),
                    "route_detail": " | ".join(
                        f"{l['from']}->{l['to']} by {l['mode']} ({l['distance_km']}km, {l['vehicle_id']})"
                        for l in route["legs"]
                    ),
                    "is_multimodal": route["is_multimodal"],
                    "modes_used": ", ".join(route["modes_used"]),
                    "total_cost_INR": cost,
                    "direct_road_only_cost_INR": route["direct_road_only_cost_INR"],
                    "total_time_hr": route["total_time_hr"],
                    "profit_INR (multimodal saving)": profit,
                })

    return pd.DataFrame(results)


# --------------------------------------------------------------------------
# INPUT MODE A: INTERACTIVE (type in any origin/destination at runtime)
# --------------------------------------------------------------------------
def collect_shipments_interactively(products_df: pd.DataFrame, nodes_df: pd.DataFrame) -> pd.DataFrame:
    known_products = set(products_df["product"])
    known_cities = set(nodes_df["city"])

    print("Enter farmer shipments one at a time. Type 'done' as the product name to finish.\n")
    print(f"Known products: {', '.join(sorted(known_products))}\n")
    print(f"Known network cities: {', '.join(sorted(known_cities))}")
    print("(Any other city is fine too -- you'll just be asked for its lat/lon.)\n")

    rows = []
    while True:
        product = input("Product (or 'done'): ").strip()
        if product.lower() == "done":
            break
        if product not in known_products:
            print(f"  '{product}' not in product master -- skipping this entry.")
            continue

        origin = input("Origin city: ").strip()
        origin_lat = origin_lon = None
        if origin not in known_cities:
            origin_lat = float(input(f"  '{origin}' is off-network -- enter its latitude: "))
            origin_lon = float(input(f"  enter its longitude: "))

        destination = input("Destination city: ").strip()
        dest_lat = dest_lon = None
        if destination not in known_cities:
            dest_lat = float(input(f"  '{destination}' is off-network -- enter its latitude: "))
            dest_lon = float(input(f"  enter its longitude: "))

        weight_kg = float(input("Weight (kg): ").strip())

        rows.append({
            "product": product, "origin": origin, "destination": destination,
            "weight_kg": weight_kg,
            "origin_lat": origin_lat, "origin_lon": origin_lon,
            "dest_lat": dest_lat, "dest_lon": dest_lon,
        })
        print("  added.\n")

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# INPUT MODE B: FROM A CSV FILE
# --------------------------------------------------------------------------
def load_shipments_from_csv(path: str) -> pd.DataFrame:
    """CSV must have: product, origin, destination, weight_kg
    Optional: origin_lat, origin_lon, dest_lat, dest_lon (for off-network cities)."""
    return pd.read_csv(path)


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
if __name__ == "__main__":
    products_df, compat_df, vehicles_df, nodes_df, sample_shipments, trip_history = load_data()

    if len(sys.argv) > 1:
        farmer_input = load_shipments_from_csv(sys.argv[1])
        print(f"Loaded {len(farmer_input)} shipment rows from {sys.argv[1]}\n")
    else:
        farmer_input = collect_shipments_interactively(products_df, nodes_df)

    if farmer_input.empty:
        print("No shipments entered -- nothing to process.")
        sys.exit(0)

    output = process_farmer_shipments(farmer_input, products_df, compat_df, vehicles_df, nodes_df)

    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.width", 160)
    print("\n" + output.to_string(index=False))

    # ---- Summary: total expense + total multimodal savings ----
    valid = output[~output.columns.str.contains("error")] if "error" in output.columns else output
    total_expense = output["total_cost_INR"].sum() if "total_cost_INR" in output.columns else 0
    total_multimodal_saving = output["profit_INR (multimodal saving)"].sum(skipna=True) \
        if "profit_INR (multimodal saving)" in output.columns else 0
    num_multimodal = int(output["is_multimodal"].sum()) if "is_multimodal" in output.columns else 0

    print("\n----- SUMMARY -----")
    print(f"Total transportation expense across all shipments: INR {total_expense:,.2f}")
    print(f"Groups routed multimodally: {num_multimodal} / {len(output)}")
    print(f"Total profit from multimodal routing (savings vs. road-only): INR {total_multimodal_saving:,.2f}")

    output.to_csv("shipment_plan_output9.csv", index=False)
    print("\nSaved: shipment_plan_output9.csv")