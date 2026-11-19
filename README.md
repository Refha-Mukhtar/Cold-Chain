# ASTRA-COLD AI — frontend/backend integration

`index23.html` (frontend) and `logistics1.py` (backend) are now wired
together through a FastAPI + Socket.IO bridge (`main.py`). Run one command,
open one URL, and the whole app — live map tracking, farmer booking, fleet
registration — is backed by the real routing/spoilage-risk engine instead of
hardcoded demo numbers.

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open **http://127.0.0.1:8000/** — that's it, frontend + API + realtime all
come from this one process.

(Run `uvicorn main:app`, not `main:api` — `app` is the combined Socket.IO +
FastAPI app; `api` alone is missing the realtime layer and the live map
won't work.)

## Files

| File | What it is |
|---|---|
| `main.py` | **New.** FastAPI REST API + Socket.IO server + serves `index23.html`. |
| `logistics1.py` | Your backend, lightly extended (see below) — not rewritten. |
| `index23.html` | Your frontend, with the buttons wired to `main.py` (see below). |
| `01_products_master.csv` … `06_historical_trips_delay.csv` | **New, sample data.** None of these were uploaded, so `logistics1.py` couldn't actually load or run. See "About the sample data" below. |
| `requirements.txt` | Python dependencies. |

## What changed in `logistics1.py`

Nothing about the core routing/spoilage/consolidation logic was touched.
Two things were added so the API can call it:

- **`register_vehicle(...)`** and **`free_up_vehicle(...)`** — non-interactive
  versions of `register_vehicle_interactively()` / `free_up_vehicle_interactively()`.
  The originals used `input()`, which can't work over HTTP. The interactive
  CLI functions now just collect the same prompts and delegate to these —
  running `python logistics1.py` still behaves exactly as before.
- **`source_row_id`** — one extra passthrough field on each result row.
  `process_farmer_shipments()` groups/reorders shipments internally, so this
  is what lets the API match each result back to the request that produced
  it.

## What changed in `index23.html`

- **Farmer booking form** (`handleFarmerSubmit`) now calls
  `POST /api/shipments/plan` and fills in the dashboard's spoilage-risk,
  shelf-life, cost, and "AI Route Directive" panel with the real computed
  numbers. The live map/SMS-preview flow (`registerOrderAsFarmer`) is
  untouched and runs in parallel.
- **Fleet registration form** (`handleFleetSubmit`) now calls
  `POST /api/vehicles/register`, so a registered vehicle is actually added
  to the fleet (`03_vehicles.csv`) and can really be matched to bookings —
  not just a client-side-only table row.
- **Fleet manifest** now loads from `GET /api/vehicles` whenever that view
  opens, so it reflects real backend state.
- **Produce Commodity dropdown** and **Origin/Destination city suggestions**
  now populate from `GET /api/products` / `GET /api/network/cities` on page
  load (with the original hardcoded lists kept as a fallback if the backend
  isn't reachable).
- **Small form fixes**: the original fleet form had a Driver Mobile input,
  Vehicle Size select, and Tariff Rate input with no `id` — meaning nothing
  ever read them — plus no field at all for Driver Name, Fixed Cost, or
  Average Speed, all of which the backend's vehicle model needs. IDs were
  added and one new field row was added for those three.
- **Socket.IO (live map)** — no frontend change needed. `main.py` implements
  the exact event contract `index23.html` already expected from "app.js"
  (`join-order`, `register-order-route`, `send-driver-location`,
  `driver-trip-status` → `order-route-ready`, `receive-driver-location`,
  `trip-status-changed`), including replaying an order's current route/
  status/last-known-location immediately when a client joins late.

## About the sample data

`logistics1.py` needs all 6 CSVs to run, and none were uploaded, so a
realistic sample set was built instead — Odisha hub cities (Bhubaneswar,
Cuttack, Puri, Balasore, Berhampur, Sambalpur, Rourkela, Angul) plus Kolkata
and Delhi as mandi destinations, 12 products (including coastal Odisha
items like Fish and Prawns), and a 14-vehicle fleet across road and rail.
Swap these for your real dataset any time — the API just reads whatever is
in these files at startup. City lat/lon and rail-connectivity flags are
approximate, for demo purposes.

## Known simplification

`process_farmer_shipments()` pools compatible produce from *different*
farmers when they're in the *same batch call*. Each `POST /api/shipments/plan`
here only contains the one booking that triggered it, so two farmers
submitting the web form separately won't get pooled onto the same vehicle
the way two rows in one CLI run would. The endpoint still accepts a list of
shipments (`{"shipments": [...]}`), so a future batch/admin job — e.g. "run
consolidation over everything still pending every 30 minutes" — can get
real cross-farmer pooling back without changing `logistics1.py` again.

## Not wired to a button yet

`POST /api/vehicles/free` (resets a vehicle to full capacity — the API
equivalent of CLI option 3) exists but isn't called from anywhere in the
UI, because the driver panel never asks a driver for their vehicle number
in the first place — only an Order ID. Worth adding if "end trip" should
also free up that specific vehicle.

## API reference

| Endpoint | Purpose |
|---|---|
| `GET /api/products` | Product master data |
| `GET /api/network/cities` | Known routing-network cities |
| `GET /api/vehicles` | Current fleet |
| `POST /api/vehicles/register` | Register a vehicle |
| `POST /api/vehicles/free` | Reset a vehicle to full capacity |
| `POST /api/shipments/plan` | Run the routing/spoilage engine for shipment(s) |
| `GET /api/shipments/{order_id}` | Retrieve a previously computed plan |
