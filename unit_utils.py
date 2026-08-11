UNIT_FACTORS = {
    'kg': 1000.0,
    'g': 1.0,
    'gram': 1.0,
    'liter': 1000.0,
    'l': 1000.0,
    'ml': 1.0,
    'milliliter': 1.0,
    'piece': 1.0,
    'unit': 1.0,
    'pcs': 1.0,
    'pc': 1.0,
}

BASE_UNITS = {
    'kg': 'g',
    'g': 'g',
    'gram': 'g',
    'liter': 'ml',
    'l': 'ml',
    'ml': 'ml',
    'milliliter': 'ml',
    'piece': 'pcs',
    'unit': 'pcs',
    'pcs': 'pcs',
    'pc': 'pcs',
}


def normalize_quantity(quantity, unit):
    unit_key = (unit or 'pcs').strip().lower()
    factor = UNIT_FACTORS.get(unit_key, 1.0)
    return float(quantity) * factor if quantity is not None else 0.0


def base_unit(unit):
    unit_key = (unit or 'pcs').strip().lower()
    return BASE_UNITS.get(unit_key, unit_key)
