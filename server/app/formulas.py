from datetime import timedelta
from decimal import Decimal


# server/app/formulas.py
def est_metal_weight(tree_weight: float, metal_name: str) -> float:
    """Estimate metal weight directly from tree weight (no gasket)."""
    factor = 1.0
    name = (metal_name or "").upper()

    if "10" in name:
        factor = 11
    elif "14" in name:
        factor = 13.25
    elif "18" in name:
        factor = 16.5
    elif "PLATINUM" in name:
        factor = 21
    elif "SILVER" in name:
        factor = 11

    return round((tree_weight) * factor, 3)


def calc_metal_weight(gasket_weight: float, tree_weight: float, metal_name: str) -> float:

    wax_weight = tree_weight - gasket_weight

    factor = 1.0

    if "10" in metal_name.upper(): 
        factor = 11
    elif "14" in metal_name.upper():
        factor = 13.25
    elif "18" in metal_name.upper():
        factor = 16.5
    elif "PLATINUM" in metal_name.upper():
        factor = 21
    elif "SILVER" in metal_name.upper():
        factor = 11

    return round((wax_weight) * factor, 3)

def calc_alloy_for(metal_name: str, total_metal: float):

    pure, alloy = 0
    factor = 1

    if "10" in metal_name.upper(): 
        factor = 0.417 
    elif "14" in metal_name.upper():
        factor = 0.587
    elif "18" in metal_name.upper():
        factor = 0.752
    elif "PLATINUM" in metal_name.upper():
        factor = 1
    elif "SILVER" in metal_name.upper():
        factor = 1

    pure = factor * total_metal
    alloy = total_metal - pure

    return pure, alloy

def casting_temp_for(metal_name: str) -> float:

    temp = 1000

    if "10" in metal_name.upper(): 
        temp = 1100
    elif "14W" in metal_name.upper():
        temp = 1050
    elif "14Y" in metal_name.upper():
        temp = 1030
    elif "14R" in metal_name.upper():
        temp = 1100
    elif "SILVER" in metal_name.upper():
        temp = 980
    elif "18W" in metal_name.upper():
        temp = 1050
    elif "18Y" in metal_name.upper():
        temp = 1060
    elif "18R" in metal_name.upper():
        temp = 1100
    elif "PLATINUM" in metal_name.upper():
        temp = 1000

    return temp



def oven_temp_for(metal_name: str) -> float:
    temp = 1000

    if "10" in metal_name.upper(): 
        temp = 1100
    elif "14W" in metal_name.upper():
        temp = 1150
    elif "14Y" in metal_name.upper():
        temp = 1050
    elif "14R" in metal_name.upper():
        temp = 1050
    elif "SILVER" in metal_name.upper():
        temp = 980
    elif "18W" in metal_name.upper():
        temp = 1050
    elif "18Y" in metal_name.upper():
        temp = 1050
    elif "18R" in metal_name.upper():
        temp = 1020
    elif "PLATINUM" in metal_name.upper():
        temp = 1000

    return temp

def quenching_minutes_for(metal_name: str) -> int:

    mins = 1

    if "10W" in metal_name.upper(): 
        mins = 15
    elif "10Y" in metal_name.upper(): 
        mins = 15
    elif "10R" in metal_name.upper(): 
        mins = 8
    elif "14W" in metal_name.upper():
        mins = 15
    elif "14Y" in metal_name.upper():
        mins = 15
    elif "14R" in metal_name.upper():
        mins = 7
    elif "SILVER" in metal_name.upper():
        mins = 15
    elif "18W" in metal_name.upper():
        mins = 15
    elif "18Y" in metal_name.upper():
        mins = 15
    elif "18R" in metal_name.upper():
        mins = 3
    elif "PLATINUM" in metal_name.upper():
        mins = 8

    return mins

def ready_at(casting_completed_at, quench_min):
    return casting_completed_at + timedelta(minutes=quench_min)
