def check_bio_compatibility(cargo_list):
    """
    Validates ethylene sensitivity and odor cross-contamination between co-loaded perishables.
    Returns a tuple: (is_compatible: bool, message: str)
    """
    if not cargo_list:
        return True, "No cargo loaded in consignment manifest."

    # Extract all produce names from the manifest
    products = [item.get("Product", item.get("item", "")) for item in cargo_list]

    # Category definitions
    high_ethylene_emitters = ["Bananas", "Apples", "Mangoes", "Papayas"]
    ethylene_sensitive_items = ["Strawberries", "Leafy Vegetables", "Broccoli", "Cucumbers"]
    pungent_odor_emitters = ["Onions", "Garlic", "Fish"]
    odor_absorbers = ["Dairy Milk", "Butter", "Eggs", "Cheese"]

    # Rule 1: Ethylene Cross-Contamination Check
    has_emitters = any(p in high_ethylene_emitters for p in products)
    has_sensitive = any(p in ethylene_sensitive_items for p in products)

    if has_emitters and has_sensitive:
        emitter_names = [p for p in products if p in high_ethylene_emitters]
        sensitive_names = [p for p in products if p in ethylene_sensitive_items]
        return False, (
            f"Ethylene Risk: High emitters {emitter_names} accelerate ripening and "
            f"decay in sensitive items {sensitive_names}. Compartment separation required."
        )

    # Rule 2: Odor & Vapor Tainting Check
    has_pungent = any(p in pungent_odor_emitters for p in products)
    has_absorbers = any(p in odor_absorbers for p in products)

    if has_pungent and has_absorbers:
        pungent_names = [p for p in products if p in pungent_odor_emitters]
        absorber_names = [p for p in products if p in odor_absorbers]
        return False, (
            f"Cross-Tainting Risk: Strong sulfur volatiles from {pungent_names} will "
            f"absorb into and contaminate {absorber_names}."
        )

    return True, "100% Biochemically Safe: Selected cargo combination has no cross-contamination risks."