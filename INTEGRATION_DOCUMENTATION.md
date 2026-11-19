# Backend-Frontend Integration - Complete Documentation

## Overview
Successfully connected the Cold-Chain backend (logistics1.py) with the frontend (index23.html) to display:
- **Distance Left**: Total shipping distance from backend routing
- **Dispatch Tariff**: Total cost from backend logistics engine  
- **Route Options**: All available transport modes (Road, Rail, Road+Rail)
- **Vehicle Allocation**: Driver names, phone numbers, vehicle details

---

## Backend Changes (logistics1.py)

### 1. Added `total_distance_km` Field
**Location**: Line 753 in individual_results.append()
- Added `"total_distance_km": best["total_distance_km"]`
- This field is calculated in `summarize_path()` function

### 2. Created Structured `candidate_routes` Array
**Location**: Lines 695-707 (before shipment processing loop)

```python
candidate_routes = []
for c in result["all_candidates"]:
    candidate_routes.append({
        "strategy": c["strategy"],
        "modes_used": c["modes_used"],
        "total_distance_km": c["total_distance_km"],
        "total_cost_INR": round(c["total_cost_INR"], 2),
        "gross_cost_INR": round(c["gross_cost_INR"], 2),
        "kisan_rail_subsidy_INR": round(c["kisan_rail_subsidy_INR"], 2),
        "planned_time_hr": round(c["planned_time_hr"], 2),
        "expected_delay_hr": round(c["expected_delay_hr"], 2),
        "total_expected_time_hr": round(c["total_expected_time_hr"], 2),
        "risk_pct": round(c["risk_pct"], 1),
        "risk_level": c["risk_level"],
        "legs": c["legs"],
    })
```

### 3. Added `candidate_routes` to Result
**Location**: Line 755 in individual_results.append()
- Added `"candidate_routes": candidate_routes`
- Includes detailed information for each routing option

---

## Frontend Changes (index23.html)

### 1. Updated KPI Display Function
**Location**: `applyShipmentPlanToDashboard()` function (modified)

#### Distance Left Display (NEW)
```javascript
if (kpiDistance) kpiDistance.innerText = `${Number(plan.total_distance_km).toFixed(1)} km`;
if (kpiDistanceEta) {
  const plannedTime = Number(plan.planned_time_hr) || 0;
  const delayTime = Number(plan.expected_delay_hr) || 0;
  const totalTime = plannedTime + delayTime;
  kpiDistanceEta.innerText = `ETA: ${totalTime.toFixed(1)}h (${plannedTime.toFixed(1)}h + ${delayTime.toFixed(1)}h delay)`;
}
```

#### Dispatch Tariff Display (EXISTING - Now Fully Connected)
```javascript
if (kpiCost) kpiCost.innerText = `₹${Math.round(plan.total_cost_INR).toLocaleString('en-IN')}`;
```

### 2. Added Route Options HTML Panel
**Location**: After KPI row in farmer_dashboard view

```html
<!-- ADDED: Route Options Selection Panel -->
<div id="route_options_panel" class="glass-panel" style="display: none;">
  <div id="route_options_container">
    <!-- Route option cards will be inserted here -->
  </div>
  
  <!-- Vehicle Details for Selected Route -->
  <div id="selected_route_vehicles">
    <div id="vehicles_list">
      <!-- Vehicle details will be inserted here -->
    </div>
  </div>
</div>
```

### 3. Added Route Display Functions
**Location**: New JavaScript functions in script section

#### `displayRouteOptions(plan)`
- Creates selectable route cards for each candidate
- Shows strategy (Road-only, Rail-only, Road+Rail)
- Displays metrics: distance, time, cost, spoilage risk
- Marks the best route as recommended
- Pre-selects the first (best) route

#### `selectRoute(routeIndex, event)`
- Handles user selection of alternative routes
- Updates UI to highlight selected route
- Calls `displayRouteVehicles()` to show vehicles for that route

#### `displayRouteVehicles(route, plan)`
- Extracts vehicle information from selected route's legs
- Creates vehicle cards showing:
  - **Vehicle No**: Unique identifier (font-mono, cyan text)
  - **Driver Name**: From backend data
  - **Driver Phone**: From backend data (clickable/copyable)
  - **Size Class**: Vehicle capacity class
  - **Load (kg)**: Weight being carried
  - **Order ID**: Unique order identifier
  - **Route Leg**: From → To by Mode (distance)

---

## Data Flow

```
User submits shipment form
    ↓
handleFarmerSubmit() → POST /api/shipments/plan
    ↓
Backend: process_farmer_shipments()
    - Compute all route candidates
    - Calculate distance, cost, time, risk for each
    - Allocate vehicles with driver info
    - Return structured candidate_routes
    ↓
Frontend: applyShipmentPlanToDashboard()
    - Display KPIs (spoilage, shelf life, distance, cost)
    - Call displayRouteOptions()
    ↓
Frontend: displayRouteOptions()
    - Create clickable route cards
    - Show: strategy, distance, cost, time, risk
    - Pre-select best route
    - Call displayRouteVehicles()
    ↓
Frontend: displayRouteVehicles()
    - Show allocated vehicles for selected route
    - Display driver name, phone, vehicle no
    - Show route legs (pickup/destination per leg)
```

---

## Testing Results

**Integration Test Status**: ✅ PASSED

### Test Output Summary:
```
✓ Distance Left: 18.9 km (from backend)
✓ Dispatch Tariff: ₹2,856.58 (from backend)
✓ Route Options: 2 available (Road only, Rail only)
✓ Vehicle Allocation: Complete with driver info
✓ Spoilage Risk: 0.2% (Low)
✓ Residual Shelf Life: 335.48h
```

### Sample Route Data Returned:
- **Route 1**: Road-only, 18.9 km, ₹2,856.58, 0.52h
  - Vehicle: OD-09-M-2005, Driver: Ashok Jena, Phone: 9812345679
- **Route 2**: Rail-only, 18.9 km, ₹20,009.90, 0.47h
  - Vehicle: 30024, Driver: Biswajit Nayak, Phone: 9812345689

---

## Files Modified

1. **logistics1.py** (Backend)
   - Lines 695-707: Create candidate_routes array
   - Line 753: Add total_distance_km field
   - Line 755: Add candidate_routes to result

2. **index23.html** (Frontend)
   - Added route_options_panel HTML section
   - Updated applyShipmentPlanToDashboard() function
   - Added displayRouteOptions() function
   - Added selectRoute() function
   - Added displayRouteVehicles() function

3. **test_integration.py** (New)
   - Integration test script
   - Validates all required fields
   - Verifies data structure

---

## Features Now Available

✅ **Distance Display**: Shows total shipping distance from backend
✅ **Tariff Display**: Shows dispatch cost from backend
✅ **Route Options**: Displays Road, Rail, and Multimodal options
✅ **Route Selection**: Users can choose between available routes
✅ **Vehicle Details**: Shows driver name, phone, vehicle number
✅ **Cost Breakdown**: Shows gross cost, subsidies, net cost
✅ **Time Breakdown**: Shows planned time vs expected delays
✅ **Risk Assessment**: Shows spoilage risk for each route
✅ **Multi-leg Support**: Handles split loads across multiple vehicles

---

## Next Steps / Future Enhancements

1. Add live tracking on selected route
2. Add SMS/WhatsApp notifications with driver contact
3. Add real-time vehicle location updates
4. Add route change functionality during transit
5. Add performance analytics per route/driver
6. Add cost comparison charts
7. Add historical route performance metrics

---

## API Endpoints Utilized

- `POST /api/shipments/plan` - Submit shipment and get all routing options
- Response includes: candidate_routes with all metadata
- Driver info embedded in vehicle objects within route legs

---

## Browser Compatibility

- ✅ Chrome/Edge (latest)
- ✅ Firefox (latest)
- ✅ Safari (latest)
- Requires modern CSS Grid and Flexbox support
- Requires ES6 JavaScript features

---

## Performance Notes

- Route options render instantly (pre-computed by backend)
- Vehicle display updates on selection (no API call required)
- All data transmitted in single POST request
- Frontend handles formatting and display
- No polling needed for static shipment data

---

Created: 2026-08-31
Last Updated: 2026-08-31
Status: ✅ Complete and Tested
