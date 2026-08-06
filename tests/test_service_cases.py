from core.service_cases import STATUSES, create_case, get_case, get_timeline, init_service_cases, list_cases, update_status


def test_create_case_generates_number_and_timeline(tmp_path, monkeypatch):
    import core.service_cases as sc
    monkeypatch.setattr(sc, "DB_PATH", tmp_path / "cases.db")
    init_service_cases()

    case = create_case(
        "Budi",
        "No power",
        customer_phone="0123456789",
        device_serial="SERIAL-1",
        imei="123456789012345",
        model="Example X",
        technician="Tech 1",
    )

    assert case.case_number.startswith("NS-")
    assert case.status == "Received"
    assert get_case(case.id).customer_name == "Budi"
    assert get_timeline(case.id)[0]["event_type"] == "created"


def test_status_changes_are_recorded(tmp_path, monkeypatch):
    import core.service_cases as sc
    monkeypatch.setattr(sc, "DB_PATH", tmp_path / "cases.db")
    case = create_case("Budi", "Screen broken")

    updated = update_status(case.id, "Diagnosing", "Initial inspection")
    assert updated.status == "Diagnosing"
    timeline = get_timeline(case.id)
    assert any(e["old_value"] == "Received" and e["new_value"] == "Diagnosing" for e in timeline)


def test_list_filter_and_validation(tmp_path, monkeypatch):
    import core.service_cases as sc
    monkeypatch.setattr(sc, "DB_PATH", tmp_path / "cases.db")
    create_case("Budi", "Battery issue", model="Model A")
    create_case("Sari", "Camera issue", model="Model B")

    assert len(list_cases(search="Model A")) == 1
    assert len(list_cases(status="Received")) == 2

    try:
        update_status(1, "Unknown")
        assert False, "invalid status should fail"
    except ValueError:
        pass

    assert "Completed" in STATUSES
