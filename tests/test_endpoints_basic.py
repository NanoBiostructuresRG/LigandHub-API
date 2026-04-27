from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
