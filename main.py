"""
ASTRA-COLD AI -- FastAPI bridge between index23.html (frontend) and
logistics1.py (backend).

WHAT THIS FILE DOES
--------------------
1. REST API (under /api/...) that wraps logistics1.py's real consolidation /
   multimodal-routing / spoilage-risk engine, so the farmer booking form and
   the fleet registration form get REAL numbers back instead of the
   frontend's own hardcoded/random demo values.
2. A Socket.IO server implementing the exact event contract index23.html's
   JS already expects from "app.js": join-order, register-order-route,
   send-driver-location, driver-trip-status (client -> server) and
   order-route-ready, receive-driver-location, trip-status-changed
   (server -> client). This is what makes the live tracking map work.
3. Serves index23.html itself at "/", so the whole app is one process: run
   this file, open the browser, everything (frontend + API + realtime) comes
   from the same origin.

RUNNING
-------
    pip install -r requirements.txt
    uvicorn main:app --reload

Then open http://127.0.0.1:8000/

DATA
----
logistics1.py needs 6 CSVs (01_products_master.csv ... 06_historical_trips_
delay.csv) in this same folder. Sample ones are included so this runs out of
the box -- swap them for your real dataset any time; the API reads whatever
is in these files at startup.

KNOWN SIMPLIFICATION
---------------------
logistics1.py's multi-farmer pooling (grouping compatible produce from
DIFFERENT farmers onto the same vehicle) happens WITHIN a single call to
process_farmer_shipments(). Each POST /api/shipments/plan call here processes
just the shipment(s) in that one request, so two farmers who submit the web
form separately won't automatically get pooled together the way two rows in
one CLI batch would. The endpoint still accepts a list, so a future "batch/
admin" caller (e.g. a nightly dispatch run over everything still pending)
can get real cross-farmer pooling back -- see the README for the shape of
that if you want to add it.
"""
import json
import sys
import threading
import uuid
from pathlib import Path
from typing import Optional, List

import pandas as pd
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Make sure logistics1.py is importable regardless of the working directory
# uvicorn was launched from.
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
import logistics1 as L  # noqa: E402

# ---------------------------------------------------------------------------
# Shared in-memory state: the 6 datasets (loaded once) + live orders.
# A threading.Lock guards the vehicle fleet since it's read/mutated/persisted
# by concurrent requests (register / free / plan all touch it).
# ---------------------------------------------------------------------------
STATE: dict = {}
STATE_LOCK = threading.Lock()

# order_id -> {"plan": {...last computed shipment plan...}, "pickup": {...},
#              "destination": {...}, "farmerPhone": str, "status": str,
#              "last_location": {"latitude":..., "longitude":...}}
# One dict per order, filled in by both the REST layer (plan) and the
# Socket.IO layer (pickup/destination/status/last_location) -- single source
# of truth per order_id, the same id the frontend already generates.
ORDERS: dict = {}


def _load_state() -> None:
    products, compat, vehicles, nodes, _sample_shipments, trip_history = L.load_data(BASE_DIR)
    STATE["products"] = products
    STATE["compat"] = compat
    STATE["vehicles"] = L.normalize_vehicle_capacity(vehicles)
    STATE["nodes"] = nodes
    STATE["trip_history"] = trip_history


_load_state()


def _records(df: pd.DataFrame) -> list:
    """DataFrame -> JSON-safe list of dicts. Goes through pandas' own to_json
    (not df.to_dict()) so NaN/NaT correctly become null instead of the
    literal token NaN, which is not valid JSON and would break the
    frontend's response.json() calls."""
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _new_order_id() -> str:
    return "ORD-" + uuid.uuid4().hex[:8].upper()


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
api = FastAPI(title="ASTRA-COLD AI API")
api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@api.get("/")
def serve_frontend():
    return FileResponse(str(BASE_DIR / "index23.html"))


@api.get("/api/health")
def health():
    return {"ok": True, "products": len(STATE["products"]), "vehicles": len(STATE["vehicles"]),
            "nodes": len(STATE["nodes"]), "orders": len(ORDERS)}


@api.get("/api/products")
def get_products():
    """Real product master data -- used by the frontend to populate the
    Produce Commodity dropdown instead of 4 hardcoded options."""
    return _records(STATE["products"])


@api.get("/api/network/cities")
def get_cities():
    """Known routing-network cities -- used by the frontend as a datalist so
    typed Origin Hub / Destination Mandi values have a real chance of
    resolving on the backend's routing graph, without forcing free text
    entry (still geocoded via Nominatim for the live map either way)."""
    return _records(STATE["nodes"])


@api.get("/api/vehicles")
def get_vehicles():
    """Current fleet -- real backend state, for the Fleet Admin manifest."""
    with STATE_LOCK:
        return _records(STATE["vehicles"])


class VehicleRegisterRequest(BaseModel):
    vehicle_no: str
    mode: str
    size_class: str = ""
    refrigerated: bool = True
    weight_capacity_kg: float
    volume_capacity_m3: float = 0.0
    temp_control_min_C: Optional[float] = None
    temp_control_max_C: Optional[float] = None
    price_per_kg_INR: float = 0.0
    fixed_cost_INR: float = 0.0
    avg_speed_kmph: float = 40.0
    driver_name: str = ""
    driver_contact: str = ""
    origin: str = ""
    destination: str = ""
    remaining_capacity_kg: Optional[float] = None


@api.post("/api/vehicles/register")
def register_vehicle_endpoint(req: VehicleRegisterRequest):
    with STATE_LOCK:
        updated, new_row, error = L.register_vehicle(
            STATE["vehicles"],
            vehicle_no=req.vehicle_no, mode=req.mode, size_class=req.size_class,
            refrigerated="Y" if req.refrigerated else "N",
            weight_capacity_kg=req.weight_capacity_kg, volume_capacity_m3=req.volume_capacity_m3,
            temp_control_min_C=("" if req.temp_control_min_C is None else req.temp_control_min_C),
            temp_control_max_C=("" if req.temp_control_max_C is None else req.temp_control_max_C),
            price_per_kg_INR=req.price_per_kg_INR, fixed_cost_INR=req.fixed_cost_INR,
            avg_speed_kmph=req.avg_speed_kmph, driver_name=req.driver_name,
            driver_contact=req.driver_contact, origin=req.origin, destination=req.destination,
            remaining_capacity_kg=req.remaining_capacity_kg,
        )
        if error:
            raise HTTPException(status_code=400, detail=error)

        STATE["vehicles"] = updated
        L.save_vehicle_capacity(updated, data_dir=BASE_DIR)
        fleet_count = len(updated)

    return {"vehicle": _records(pd.DataFrame([new_row]))[0], "fleet_count": fleet_count}


class VehicleFreeRequest(BaseModel):
    vehicle_no: str


@api.post("/api/vehicles/free")
def free_vehicle_endpoint(req: VehicleFreeRequest):
    with STATE_LOCK:
        updated, restored, error = L.free_up_vehicle(STATE["vehicles"], req.vehicle_no)
        if error:
            raise HTTPException(status_code=404, detail=error)
        STATE["vehicles"] = updated
        L.save_vehicle_capacity(updated, data_dir=BASE_DIR)

    return {"vehicle_no": req.vehicle_no, "restored_capacity_kg": restored}


class ShipmentIn(BaseModel):
    order_id: Optional[str] = None
    farmer_name: str
    phone: str = ""
    product: str
    origin: str
    destination: str
    weight_kg: float
    expected_delivery_date: str = ""


class PlanRequest(BaseModel):
    shipments: List[ShipmentIn] = Field(..., min_length=1)


@api.post("/api/shipments/plan")
def plan_shipments(req: PlanRequest):
    """Runs the real consolidation / multimodal-routing / spoilage-risk
    engine for the submitted shipment(s) and returns the actual numbers
    (cost, route, spoilage risk, compatibility tips) -- this is what
    handleFarmerSubmit() in index23.html now calls instead of only showing
    locally-fabricated KPI values."""
    rows = []
    for s in req.shipments:
        order_id = (s.order_id or "").strip() or _new_order_id()
        rows.append({
            "source_row_id": order_id,
            "farmer_name": s.farmer_name, "phone": s.phone, "product": s.product,
            "origin": s.origin, "destination": s.destination,
            "expected_delivery_date": s.expected_delivery_date, "weight_kg": s.weight_kg,
        })
    shipments_df = pd.DataFrame(rows)

    try:
        with STATE_LOCK:
            vehicles_df = STATE["vehicles"]
            result_df = L.process_farmer_shipments(
                shipments_df, STATE["products"], STATE["compat"], vehicles_df,
                STATE["nodes"], STATE["trip_history"],
            )
            # process_farmer_shipments consumes vehicle capacity in place --
            # persist it so the next booking sees an accurate fleet.
            STATE["vehicles"] = vehicles_df
            L.save_vehicle_capacity(vehicles_df, data_dir=BASE_DIR)
    except Exception as exc:  # keep a bad request from taking the server down
        raise HTTPException(status_code=500, detail=f"Planning failed: {exc}")

    out = []
    for row in _records(result_df):
        order_id = row.get("source_row_id") or _new_order_id()
        row["order_id"] = order_id
        ORDERS.setdefault(order_id, {})["plan"] = row
        out.append(row)

    return {"results": out}


@api.get("/api/shipments/{order_id}")
def get_shipment(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"No order found for '{order_id}'.")
    return order


@api.get("/api/orders")
def get_orders():
    # Return all orders that have a pickup and destination
    active = {}
    for k, v in ORDERS.items():
        if v.get("pickup") and v.get("destination"):
            active[k] = v
    return active

# ---------------------------------------------------------------------------
# Socket.IO -- live order tracking. Event names/payloads match exactly what
# index23.html already sends/listens for (see its "LIVE ORDER TRACKING"
# comment block), so no frontend changes were needed for this part.
# ---------------------------------------------------------------------------
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@sio.event
async def connect(sid, environ):
    return True


@sio.on("join-order")
async def join_order(sid, data):
    order_id = str((data or {}).get("orderId", "")).strip()
    if not order_id:
        return
    await sio.enter_room(sid, order_id)

    order = ORDERS.get(order_id)
    if not order:
        return

    # Mirrors the frontend's own comment: fires immediately on join if this
    # order was already registered, so a late join (typed Order ID, Fleet
    # "Track" button, revisit) doesn't have to wait for a fresh event.
    if order.get("pickup") or order.get("destination"):
        await sio.emit("order-route-ready", {
            "orderId": order_id,
            "pickup": order.get("pickup"),
            "destination": order.get("destination"),
            "farmerPhone": order.get("farmerPhone"),
        }, to=sid)

    if order.get("status"):
        await sio.emit("trip-status-changed", {"orderId": order_id, "status": order["status"]}, to=sid)

    if order.get("last_location"):
        await sio.emit("receive-driver-location", {
            "orderId": order_id,
            "latitude": order["last_location"]["latitude"],
            "longitude": order["last_location"]["longitude"],
        }, to=sid)


@sio.on("register-order-route")
async def register_order_route(sid, data):
    data = data or {}
    order_id = str(data.get("orderId", "")).strip()
    if not order_id:
        return
    order = ORDERS.setdefault(order_id, {})
    order["pickup"] = data.get("pickup")
    order["destination"] = data.get("destination")
    order["farmerPhone"] = data.get("farmerPhone")

    await sio.emit("order-route-ready", {
        "orderId": order_id,
        "pickup": order["pickup"],
        "destination": order["destination"],
        "farmerPhone": order["farmerPhone"],
    }, room=order_id)


@sio.on("send-driver-location")
async def send_driver_location(sid, data):
    data = data or {}
    order_id = str(data.get("orderId", "")).strip()
    if not order_id:
        return
    latitude, longitude = data.get("latitude"), data.get("longitude")
    order = ORDERS.setdefault(order_id, {})
    order["last_location"] = {"latitude": latitude, "longitude": longitude}

    await sio.emit("receive-driver-location", {
        "orderId": order_id, "latitude": latitude, "longitude": longitude,
    }, room=order_id, skip_sid=sid)


@sio.on("driver-trip-status")
async def driver_trip_status(sid, data):
    data = data or {}
    order_id = str(data.get("orderId", "")).strip()
    if not order_id:
        return
    status = data.get("status")
    order = ORDERS.setdefault(order_id, {})
    order["status"] = status

    await sio.emit("trip-status-changed", {"orderId": order_id, "status": status}, room=order_id)


# Combined ASGI app: Socket.IO handles /socket.io/*, everything else (the
# REST API + serving index23.html) falls through to the FastAPI app. Point
# uvicorn at THIS name (`uvicorn main:app`), not `api`, or the frontend's
# `io()` call and every live-tracking button will 404.
app = socketio.ASGIApp(sio, other_asgi_app=api, socketio_path="socket.io")
