from __future__ import annotations

import re

TAXONOMY_VERSION = "event-taxonomy.v1"

RESIDENTIAL_STRUCTURE_FIRE = "Residential structure fire"
COMMERCIAL_STRUCTURE_FIRE = "Commercial structure fire"
MULTIFAMILY_STRUCTURE_FIRE = "Multifamily or condominium structure fire"
GENERAL_STRUCTURE_FIRE = "General structure fire"
WORKING_FIRE = "Working fire"
UNKNOWN_FIRE = "Unknown fire situation"
SMOKE_INSIDE_STRUCTURE = "Smoke inside structure"
ELECTRICAL_STRUCTURAL_EXPOSURE = "Electrical event with structural exposure"
VEHICLE_STRUCTURAL_EXPOSURE = "Vehicle fire with structural exposure"
TRAFFIC_CRASH_STRUCTURE = "Traffic crash into structure"
ROUTINE_FIRE_ALARM = "Routine fire alarm"
SMOKE_INVESTIGATION = "Smoke investigation"
COOKING_APPLIANCE = "Cooking or appliance incident"
BRUSH_OUTSIDE_FIRE = "Brush or outside fire"
VEHICLE_FIRE = "Vehicle fire without structural exposure"
MEDICAL = "Medical"
PUBLIC_SERVICE = "Public service"
EXCLUDED = "Excluded"


def normalize_event_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("&", " AND ").strip().upper())


def classify_event(original_event_type: str) -> str:
    """Map only source-supported wording; this function never infers a working fire."""

    event = normalize_event_text(original_event_type)
    if not event:
        return UNKNOWN_FIRE
    if event in {"EXCLUDED", "IGNORE", "TEST EVENT"}:
        return EXCLUDED
    if "WORKING FIRE" in event:
        return WORKING_FIRE
    if "COMMERCIAL STRUCTURE FIRE" in event:
        return COMMERCIAL_STRUCTURE_FIRE
    if "RESIDENTIAL STRUCTURE FIRE" in event:
        return RESIDENTIAL_STRUCTURE_FIRE
    if "MULTIFAMILY" in event or "CONDOMINIUM" in event:
        return MULTIFAMILY_STRUCTURE_FIRE
    if "TRAFFIC CRASH" in event and "STRUCTURE" in event:
        return TRAFFIC_CRASH_STRUCTURE
    if "VEHICLE FIRE" in event:
        if "STRUCTURE" in event or "EXPOSURE" in event:
            return VEHICLE_STRUCTURAL_EXPOSURE
        return VEHICLE_FIRE
    if "STRUCTURE FIRE" in event:
        return GENERAL_STRUCTURE_FIRE
    if "ELECTRICAL" in event and any(
        token in event for token in ("STRUCTURE", "BUILDING", "INSIDE")
    ):
        return ELECTRICAL_STRUCTURAL_EXPOSURE
    if "COOKING" in event or "APPLIANCE" in event:
        return COOKING_APPLIANCE
    if "SMOKE" in event and any(token in event for token in ("INSIDE", "STRUCTURE", "BUILDING")):
        return SMOKE_INSIDE_STRUCTURE
    if "SMOKE" in event or "ODOR" in event:
        return SMOKE_INVESTIGATION
    if "ALARM" in event:
        return ROUTINE_FIRE_ALARM
    if "BRUSH" in event or "OUTSIDE FIRE" in event or "WILDLAND" in event:
        return BRUSH_OUTSIDE_FIRE
    if "MEDICAL" in event:
        return MEDICAL
    if "PUBLIC SERVICE" in event:
        return PUBLIC_SERVICE
    return UNKNOWN_FIRE
