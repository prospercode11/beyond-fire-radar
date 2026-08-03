from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Optional

from app.properties.address import normalize_address
from app.properties.importers import iter_normalized_csv_file, parse_property_file
from fastapi.testclient import TestClient


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "admin@example.com", "password": "development-password-123"},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _property_file() -> tuple[str, bytes]:
    path = Path(__file__).parents[1] / "fixtures" / "sample_sarasota_property_appraiser.csv"
    return path.name, path.read_bytes()


def _import_properties(
    client: TestClient,
    headers: dict[str, str],
    *,
    key: str = "property-import-1",
    effective_at: Optional[str] = None,
) -> dict:
    filename, payload = _property_file()
    data = {
        "provider_id": "fixture.sarasota.property_appraiser",
        "source_version": "fixture-property-2026-01",
        "idempotency_key": key,
        "import_mode": "full",
        "authorized_snapshot": "false",
    }
    if effective_at:
        data["effective_at"] = effective_at
    response = client.post(
        "/api/v1/properties/imports",
        headers=headers,
        files={"file": (filename, payload, "text/csv")},
        data=data,
    )
    response.raise_for_status()
    return response.json()


def _create_incident(
    client: TestClient, headers: dict[str, str], location: str, source_id: str
) -> str:
    payload = json.dumps(
        {
            "records": [
                {
                    "source_record_id": source_id,
                    "source_event_id": f"EVENT-{source_id}",
                    "event_time": "2026-01-15T14:22:00Z",
                    "event_type": "STRUCTURE FIRE",
                    "location": location,
                }
            ]
        }
    ).encode()
    upload = client.post(
        "/api/v1/providers/fixture.sarasota.dispatch/snapshots",
        headers={**headers, "Idempotency-Key": f"dispatch-{source_id}"},
        files={"file": (f"{source_id}.json", payload, "application/json")},
        data={"authorized_snapshot": "false"},
    )
    upload.raise_for_status()
    process = client.post(
        f"/api/v1/incidents/process/retrievals/{upload.json()['retrieval_id']}", headers=headers
    )
    process.raise_for_status()
    incidents = client.get(
        "/api/v1/incidents?provider_id=fixture.sarasota.dispatch", headers=headers
    )
    incidents.raise_for_status()
    return incidents.json()[-1]["id"]


def test_address_normalization_handles_precision_and_variants() -> None:
    exact = normalize_address("100 Example Avenue, Sarasota, FL 34236")
    assert exact.precision == "exact_address"
    assert exact.house_number == "100"
    assert exact.street_name == "EXAMPLE"
    assert exact.street_type == "AVENUE"
    assert exact.municipality == "SARASOTA"
    assert exact.postal_code == "34236"
    dispatch_style = normalize_address("11704 ALTAMONTE CT")
    assert dispatch_style.precision == "exact_address"
    assert dispatch_style.house_number == "11704"
    assert dispatch_style.postal_code is None
    assert dispatch_style.normalized == "11704 ALTAMONTE COURT"

    unit = normalize_address("400 OAK AVE UNIT 2")
    assert unit.precision == "exact_address_with_unit"
    assert unit.unit == "2"
    assert normalize_address("400 OAK AVE #2").unit == "2"
    block = normalize_address("100-120 MAIN ST, Sarasota")
    assert block.precision == "street_block"
    assert block.municipality == "SARASOTA"
    county_road = normalize_address("123 COUNTY ROAD 41, Venice FL 34285")
    assert county_road.precision == "highway"
    assert county_road.municipality == "VENICE"
    assert county_road.street_name == "COUNTY ROAD 41"
    assert normalize_address("MAIN ST & OAK AVE").precision == "intersection"
    assert normalize_address("US 41 N near airport").precision == "highway"


def test_property_parser_supports_xlsx_zip_and_mapping() -> None:
    xlsx = io.BytesIO()
    worksheet = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Folio</t></is></c><c r="B1" t="inlineStr"><is><t>Site Address</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>X-1</t></is></c><c r="B2" t="inlineStr"><is><t>1 TEST ST</t></is></c></row></sheetData></worksheet>"""
    workbook = """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    relationships = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>"""
    with zipfile.ZipFile(xlsx, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    parsed_xlsx = parse_property_file(
        xlsx.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "property.xlsx",
    )
    assert parsed_xlsx.format == "xlsx"
    assert parsed_xlsx.rows[0].fields["parcel_id"] == "X-1"
    assert parsed_xlsx.rows[0].fields["situs_original"] == "1 TEST ST"
    assert parsed_xlsx.rows[0].fields["situs_original"] == "1 TEST ST"

    archive_payload = io.BytesIO()
    with zipfile.ZipFile(archive_payload, "w") as archive:
        archive.writestr("property.csv", b"Folio,Site Address\nX-2,2 TEST ST\n")
        archive.writestr("property-2.csv", b"parcel_number,property_address\nX-3,3 TEST ST\n")
    parsed_zip = parse_property_file(archive_payload.getvalue(), "application/zip", "property.zip")
    assert parsed_zip.format == "zip"
    assert {row.fields["parcel_id"] for row in parsed_zip.rows} == {"X-2", "X-3"}


def test_large_csv_iterator_preserves_source_row_numbers() -> None:
    path = Path(__file__).parents[1] / "fixtures" / "sample_sarasota_property_appraiser.csv"
    parsed_rows = [
        row for chunk in iter_normalized_csv_file(path, chunk_rows=2) for row in chunk.rows
    ]
    assert len(parsed_rows) == 8
    assert parsed_rows[0].row_number == 2
    assert parsed_rows[-1].row_number == 9


def test_property_import_replay_partial_failure_full_removal_and_rollback(
    client: TestClient,
) -> None:
    headers = _auth(client)
    imported = _import_properties(client, headers)
    assert imported["status"] == "imported"
    assert imported["normalized_row_count"] == 8
    replay = _import_properties(client, headers)
    assert replay["replayed"] is True
    assert replay["property_import_id"] == imported["property_import_id"]

    malformed = b"parcel_id,situs_address\nDUP-1,1 TEST ST\nDUP-1,1 TEST ST\nBROKEN,\n"
    rejected = client.post(
        "/api/v1/properties/imports",
        headers=headers,
        files={"file": ("malformed.csv", malformed, "text/csv")},
        data={
            "provider_id": "fixture.sarasota.property_appraiser",
            "source_version": "fixture-property-2026-02",
            "idempotency_key": "property-import-malformed",
            "import_mode": "incremental",
        },
    )
    rejected.raise_for_status()
    assert rejected.json()["status"] == "imported_with_rejections"
    errors = client.get(
        f"/api/v1/properties/imports/{rejected.json()['property_import_id']}/errors",
        headers=headers,
    )
    errors.raise_for_status()
    assert {item["code"] for item in errors.json()} >= {
        "duplicate_parcel_id",
        "missing_required_value",
    }

    replacement = b"parcel_id,situs_address\nPARCEL-EX100,100 EXAMPLE AVE\n"
    full = client.post(
        "/api/v1/properties/imports",
        headers=headers,
        files={"file": ("replacement.csv", replacement, "text/csv")},
        data={
            "provider_id": "fixture.sarasota.property_appraiser",
            "source_version": "fixture-property-2026-03",
            "idempotency_key": "property-import-replacement",
            "import_mode": "full",
        },
    )
    full.raise_for_status()
    assert full.json()["removed_row_count"] >= 7
    parcel = client.get("/api/v1/properties/parcels/PARCEL-1001", headers=headers)
    parcel.raise_for_status()
    assert parcel.json()["is_active"] is False
    rollback = client.post(
        f"/api/v1/properties/imports/{full.json()['property_import_id']}/rollback", headers=headers
    )
    rollback.raise_for_status()
    assert rollback.json()["status"] == "rolled_back"
    restored = client.get("/api/v1/properties/parcels/PARCEL-1001", headers=headers)
    assert restored.json()["is_active"] is True
    assert restored.json()["current_import_id"] == imported["property_import_id"]
    assert restored.json()["provenance"]["source_row"]["source_parcel_id"] == "PARCEL-1001"
    assert restored.json()["provenance"]["import"]["parser_version"] == "sarasota.property.v1"


def test_property_match_exposes_evidence_and_preserves_human_decision(client: TestClient) -> None:
    headers = _auth(client)
    _import_properties(
        client,
        headers,
        key="property-match-import",
        effective_at="2026-01-15T14:22:00Z",
    )
    incident_id = _create_incident(client, headers, "100 Example Avenue", "match-exact")
    run = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    run.raise_for_status()
    run_data = run.json()
    assert run_data["status"] == "matched"
    assert run_data["candidates"][0]["classification"] == "exact"
    assert run_data["candidates"][0]["parcel"]["parcel_id"] == "PARCEL-EX100"
    assert run_data["candidates"][0]["explanation"]["matcher_version"] == "property-match.v1"

    candidate_id = run_data["candidates"][0]["id"]
    decision = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches/decisions",
        headers=headers,
        json={
            "decision": "confirmed",
            "candidate_id": candidate_id,
            "reason": "Reviewed source address.",
        },
    )
    decision.raise_for_status()
    assert decision.json()["parcel_id"] == run_data["candidates"][0]["parcel_id"]
    reprocessed = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches/reprocess",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    reprocessed.raise_for_status()
    assert reprocessed.json()["current_human_decision"]["decision"] == "confirmed"

    cleared = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches/decisions",
        headers=headers,
        json={"decision": "cleared", "reason": "Clear for fresh review."},
    )
    cleared.raise_for_status()
    assert cleared.json()["decision"] == "cleared"


def test_historical_property_import_cannot_be_used_for_a_new_match(client: TestClient) -> None:
    headers = _auth(client)
    first = _import_properties(client, headers, key="property-historical-1")
    replacement = client.post(
        "/api/v1/properties/imports",
        headers=headers,
        files={
            "file": (
                "replacement.csv",
                b"parcel_id,situs_address\nPARCEL-EX100,100 EXAMPLE AVE\n",
                "text/csv",
            )
        },
        data={
            "provider_id": "fixture.sarasota.property_appraiser",
            "source_version": "fixture-property-2026-02",
            "idempotency_key": "property-historical-2",
            "import_mode": "full",
            "authorized_snapshot": "false",
        },
    )
    replacement.raise_for_status()
    second = replacement.json()
    incident_id = _create_incident(client, headers, "100 Example Avenue", "match-historical")

    response = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches",
        headers=headers,
        json={
            "property_provider_id": "fixture.sarasota.property_appraiser",
            "property_import_id": first["property_import_id"],
        },
    )

    assert response.status_code == 422, response.text
    assert "historical property imports" in response.json()["detail"]
    assert second["property_import_id"] != first["property_import_id"]


def test_property_match_abstains_for_unit_ambiguity(client: TestClient) -> None:
    headers = _auth(client)
    _import_properties(client, headers, key="property-unit-import")
    incident_id = _create_incident(client, headers, "400 OAK AVE, Sarasota, FL 34237", "match-unit")
    run = client.post(
        f"/api/v1/incidents/{incident_id}/property-matches",
        headers=headers,
        json={"property_provider_id": "fixture.sarasota.property_appraiser"},
    )
    run.raise_for_status()
    data = run.json()
    assert data["status"] == "abstained"
    assert data["abstention_reason"] == "unit_ambiguity"
    assert any(item["is_abstained"] for item in data["candidates"])
