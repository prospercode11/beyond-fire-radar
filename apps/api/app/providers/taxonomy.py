from __future__ import annotations

import re

TAXONOMY_VERSION = "event-taxonomy.v8"

RESIDENTIAL_STRUCTURE_FIRE = "Residential structure fire"
COMMERCIAL_STRUCTURE_FIRE = "Commercial structure fire"
MULTIFAMILY_STRUCTURE_FIRE = "Multifamily or condominium structure fire"
GENERAL_STRUCTURE_FIRE = "General structure fire"
GENERAL_FIRE = "General fire"
PUBLIC_SERVICE_FIRE = "Public service fire"
EXTINGUISHED_FIRE = "Extinguished fire investigation"
ILLEGAL_BURNING = "Illegal burning"
WORKING_FIRE = "Working fire"
UNKNOWN_SOURCE_CALL = "Unknown source call"
# Kept as a compatibility alias for callers that imported the prior constant. The
# displayed family deliberately no longer implies an unknown call is fire-related.
UNKNOWN_FIRE = UNKNOWN_SOURCE_CALL
MIXED_FIRE_MEDICAL_CALL = "Mixed fire or medical service call"
UNSPECIFIED_SOURCE_CALL = "Unspecified source call"
SMOKE_INSIDE_STRUCTURE = "Smoke inside structure"
ELECTRICAL_STRUCTURAL_EXPOSURE = "Electrical event with structural exposure"
ELECTRICAL_HAZARD = "Electrical hazard"
VEHICLE_STRUCTURAL_EXPOSURE = "Vehicle fire with structural exposure"
TRAFFIC_CRASH_STRUCTURE = "Traffic crash into structure"
TRAFFIC_CRASH = "Traffic crash"
ROUTINE_FIRE_ALARM = "Routine fire alarm"
SMOKE_INVESTIGATION = "Smoke investigation"
GAS_ODOR = "Gas odor"
COOKING_APPLIANCE = "Cooking or appliance incident"
BRUSH_OUTSIDE_FIRE = "Brush or outside fire"
VEHICLE_FIRE = "Vehicle fire without structural exposure"
MEDICAL = "Medical"
PUBLIC_SERVICE = "Public service"
MARINE_RESCUE = "Marine rescue"
ELEVATOR_RESCUE = "Elevator or escalator rescue"
HAZMAT = "Hazmat incident"
EXCLUDED = "Excluded"


def normalize_event_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("&", " AND ").strip().upper())


def classify_event(original_event_type: str) -> str:
    """Map only source-supported wording; this function never infers a working fire."""

    event = normalize_event_text(original_event_type)
    if not event:
        return UNSPECIFIED_SOURCE_CALL
    if event in {"EXCLUDED", "IGNORE", "TEST EVENT"}:
        return EXCLUDED
    if event in {"FIRE", "FIRE EVENT"}:
        return GENERAL_FIRE
    if "FIRE ALARM" in event:
        return ROUTINE_FIRE_ALARM
    # eFirstAlert explicitly combines these calls. Apparatus labels such as E/R
    # cannot safely resolve the incident type, so this remains non-fire evidence.
    if "FIRE OR MEDICAL SERVICE CALL" in event:
        return MIXED_FIRE_MEDICAL_CALL
    if "SOURCE CALL TYPE BLANK" in event:
        return UNSPECIFIED_SOURCE_CALL
    # The Broward feed also emits opaque one- or two-character call codes.
    # Without a documented codebook they are not evidence of a fire.
    if re.fullmatch(r"[A-Z0-9]{1,2}", event):
        return UNSPECIFIED_SOURCE_CALL
    if "PUBLIC SERVICE FIRE" in event:
        return PUBLIC_SERVICE_FIRE
    if "EXTINGUISHED FIRE" in event:
        return EXTINGUISHED_FIRE
    if "ILLEGAL BURNING" in event:
        return ILLEGAL_BURNING
    if "WORKING FIRE" in event:
        return WORKING_FIRE
    if "COMMERCIAL STRUCTURE FIRE" in event:
        return COMMERCIAL_STRUCTURE_FIRE
    if "RESIDENTIAL STRUCTURE FIRE" in event:
        return RESIDENTIAL_STRUCTURE_FIRE
    if "MULTIFAMILY" in event or "CONDOMINIUM" in event:
        return MULTIFAMILY_STRUCTURE_FIRE
    if any(term in event for term in ("TRAFFIC CRASH", "CRASH W/INJURY", "COLLISION", "ACCIDENT")):
        return TRAFFIC_CRASH_STRUCTURE if "STRUCTURE" in event else TRAFFIC_CRASH
    if "VEHICLE FIRE" in event:
        if "STRUCTURE" in event or "EXPOSURE" in event:
            return VEHICLE_STRUCTURAL_EXPOSURE
        return VEHICLE_FIRE
    if "FIRE STRUCTURE" in event or "STRUCTURE FIRE" in event:
        return GENERAL_STRUCTURE_FIRE
    if "FIRE AUTO" in event or "AUTO FIRE" in event:
        return VEHICLE_FIRE
    if "ELECTRICAL" in event and "FIRE" in event:
        return GENERAL_FIRE
    if "ELECTRICAL" in event:
        if any(token in event for token in ("STRUCTURE", "BUILDING", "INSIDE")):
            return ELECTRICAL_STRUCTURAL_EXPOSURE
        return ELECTRICAL_HAZARD
    if "COOKING" in event or "APPLIANCE" in event:
        return COOKING_APPLIANCE
    if "SMOKE" in event and any(token in event for token in ("INSIDE", "STRUCTURE", "BUILDING")):
        return SMOKE_INSIDE_STRUCTURE
    if "GAS ODOR" in event:
        return GAS_ODOR
    if "SMOKE" in event or "ODOR" in event:
        return SMOKE_INVESTIGATION
    if "MARINE RESCUE" in event:
        return MARINE_RESCUE
    if "ELEVATOR" in event or "ESCALATOR" in event:
        return ELEVATOR_RESCUE
    if "HAZMAT" in event or "HAZARDOUS MATERIAL" in event:
        return HAZMAT
    if "BRUSH" in event or "OUTSIDE FIRE" in event or "WILDLAND" in event:
        return BRUSH_OUTSIDE_FIRE
    if "FIRE" in event:
        return GENERAL_FIRE
    if any(
        term in event
        for term in (
            "MEDICAL",
            "SICK PERSON",
            "CHEST PAIN",
            "BACK PAIN",
            "ALLERGIC REACTION",
            "HEMORRHAGE",
            "LACERATION",
            "MENTAL ILLNESS",
            "CARDIAC/RESPIRATORY ARREST",
            "CARDIAC ARREST",
            "RESPIRATORY ARREST",
            "TROUBLE BREATHING",
            "UNCONSCIOUS",
            "FAINTING",
            "SEIZURE",
            "DIABETIC",
            "FALL ",
            "PREGNANCY",
            "CHILDBIRTH",
            "CHOKING",
            "ASSAULT",
            " INJURY",
            "HIT AND RUN",
            "STINGS",
        )
    ):
        return MEDICAL
    # Alarm calls contain the word FIRE in both Miami-Dade and Broward feeds, but
    # an alarm is not source evidence that a fire occurred. Keep this boundary
    # ahead of the generic FIRE fallback so alarms cannot become opportunities.
    if "ALARM" in event:
        return ROUTINE_FIRE_ALARM
    if "PUBLIC SERVICE" in event:
        return PUBLIC_SERVICE
    if "LOCK IN" in event or "LOCK OUT" in event or event == "ASSIST":
        return PUBLIC_SERVICE
    return UNKNOWN_FIRE
