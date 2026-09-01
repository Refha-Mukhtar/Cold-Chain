"""
Test script to verify backend-frontend integration.
Tests if the backend returns the required fields for distance, cost, and route options.
"""

import json
import pandas as pd
import logistics1 as L
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def test_shipment_planning():
    """Test that process_farmer_shipments returns all required fields"""
    
    print("=" * 70)
    print("TESTING BACKEND-FRONTEND INTEGRATION")
    print("=" * 70)
    
    # Load data
    print("\n[1/5] Loading backend data...")
    products, compat, vehicles, nodes, sample_shipments, trip_history = L.load_data(BASE_DIR)
    vehicles = L.normalize_vehicle_capacity(vehicles)
    print(f"✓ Loaded {len(products)} products, {len(vehicles)} vehicles, {len(nodes)} nodes")
    
    # Create test shipment
    print("\n[2/5] Creating test shipment...")
    test_shipment = pd.DataFrame([{
        'source_row_id': 'TEST-001',
        'farmer_name': 'Test Farmer',
        'phone': '9999999999',
        'product': products.iloc[0]['product'] if not products.empty else 'Apple',
        'origin': nodes.iloc[0]['city'] if not nodes.empty else 'Nashik',
        'destination': nodes.iloc[1]['city'] if len(nodes) > 1 else nodes.iloc[0]['city'],
        'expected_delivery_date': '2026-12-25',
        'weight_kg': 100
    }])
    print(f"✓ Created test shipment: {test_shipment.iloc[0]['product']} from {test_shipment.iloc[0]['origin']} to {test_shipment.iloc[0]['destination']}")
    
    # Process shipment
    print("\n[3/5] Processing shipment through logistics engine...")
    result = L.process_farmer_shipments(test_shipment, products, compat, vehicles, nodes, trip_history)
    
    if result.empty:
        print("✗ ERROR: No results returned!")
        return False
    
    row = result.iloc[0]
    print(f"✓ Processing complete. Checking required fields...")
    
    # Check required fields
    print("\n[4/5] Verifying required fields...")
    required_fields = [
        'total_distance_km',
        'total_cost_INR',
        'gross_transport_cost_INR',
        'kisan_rail_subsidy_INR',
        'planned_time_hr',
        'expected_delay_hr',
        'total_expected_time_hr',
        'candidate_routes',
        'legs_for_display',
        'predicted_spoilage_risk_pct',
        'predicted_spoilage_risk_level',
        'remaining_shelf_life_at_planned_arrival_hr'
    ]
    
    missing_fields = []
    for field in required_fields:
        if field not in row:
            missing_fields.append(field)
        else:
            print(f"  ✓ {field}: {row[field]}")
    
    if missing_fields:
        print(f"\n✗ Missing fields: {missing_fields}")
        return False
    
    # Verify candidate_routes structure
    print("\n[5/5] Verifying candidate_routes structure...")
    if not isinstance(row['candidate_routes'], list):
        print(f"✗ candidate_routes is not a list! Type: {type(row['candidate_routes'])}")
        return False
    
    if len(row['candidate_routes']) == 0:
        print("✗ candidate_routes is empty!")
        return False
    
    print(f"✓ Found {len(row['candidate_routes'])} route options")
    
    for i, route in enumerate(row['candidate_routes']):
        print(f"\n  Route {i+1}: {route.get('strategy', 'Unknown')}")
        print(f"    - Modes: {route.get('modes_used', 'N/A')}")
        print(f"    - Distance: {route.get('total_distance_km', 'N/A')} km")
        print(f"    - Cost: ₹{route.get('total_cost_INR', 'N/A')}")
        print(f"    - Time: {route.get('total_expected_time_hr', 'N/A')}h")
        print(f"    - Risk: {route.get('risk_pct', 'N/A')}% ({route.get('risk_level', 'N/A')})")
        
        # Check vehicle info in legs
        if 'legs' in route and isinstance(route['legs'], list):
            for leg in route['legs']:
                if 'vehicles' in leg:
                    for veh in leg['vehicles']:
                        print(f"    - Vehicle: {veh.get('vehicle_no', 'N/A')} | Driver: {veh.get('driver_name', 'N/A')} | Phone: {veh.get('driver_contact', 'N/A')}")
    
    # Display summary
    print("\n" + "=" * 70)
    print("INTEGRATION TEST RESULTS")
    print("=" * 70)
    print(f"\n✓ Distance Left (from backend): {row['total_distance_km']} km")
    print(f"✓ Dispatch Tariff (from backend): ₹{row['total_cost_INR']}")
    print(f"✓ Route Options: {len(row['candidate_routes'])} available")
    print(f"✓ Vehicle Allocation: Vehicles with driver info are displayed")
    print(f"✓ Spoilage Risk: {row['predicted_spoilage_risk_pct']}% ({row['predicted_spoilage_risk_level']})")
    print(f"✓ Residual Shelf Life: {row['remaining_shelf_life_at_planned_arrival_hr']}h")
    
    print("\n" + "=" * 70)
    print("INTEGRATION TEST PASSED ✓")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    try:
        success = test_shipment_planning()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
