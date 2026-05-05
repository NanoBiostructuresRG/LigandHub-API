from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_health_endpoint_returns_ok_when_dependencies_are_available(monkeypatch):
    monkeypatch.setattr(
        "app.importlib.util.find_spec",
        lambda package_name: object(),
    )

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["dependencies"] == {
        "rdkit": True,
        "meeko": True,
        "molscrub": True,
    }
    assert payload["rdkit"] is True
    assert payload["meeko"] is True
    assert payload["molscrub"] is True


def test_health_endpoint_returns_degraded_when_critical_dependency_is_missing(monkeypatch):
    def find_spec(package_name):
        return None if package_name == "molscrub" else object()

    monkeypatch.setattr("app.importlib.util.find_spec", find_spec)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["dependencies"] == {
        "rdkit": True,
        "meeko": True,
        "molscrub": False,
    }


def test_limits_endpoint_returns_current_limit_contract():
    response = client.get("/limits")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_mode"] == "prototype"
    assert isinstance(payload["notes"], list)
    assert "limits" in payload

    limits = payload["limits"]
    assert limits["single_upload_max_bytes"] > 0
    assert limits["batch_upload_max_bytes"] > 0
    assert limits["batch_max_molecules"] > 0
    assert limits["batch_max_scrubbed_states_per_ligand"] > 0
    assert limits["batch_max_generated_pdbqt_files"] > 0
    assert limits["batch_max_total_pdbqt_bytes"] > 0


def test_validate_endpoint_accepts_valid_smiles_form_data():
    response = client.post("/validate", data={"smiles": "CCO"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["errors"] == []
    assert payload["smiles"] == "CCO"


def test_validate_endpoint_reports_invalid_smiles_with_current_contract():
    response = client.post("/validate", data={"smiles": "C1CC"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["errors"] == [
        {
            "type": "smiles_error",
            "message": "Invalid SMILES syntax - check parentheses, brackets, and ring closures",
        }
    ]
    assert payload["warnings"] == []
    assert payload["smiles"] == "C1CC"
