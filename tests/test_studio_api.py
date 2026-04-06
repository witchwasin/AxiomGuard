"""
Tests for Axiom Studio v2 API.

Tests the FastAPI backend endpoints without browser.
"""

import pytest

try:
    from fastapi.testclient import TestClient
    from axiomguard.studio.api import create_app

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:

    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "Z3" in data["engine"]


class TestVerifyEndpoint:

    def test_verify_passing_claim(self, client):
        yaml_rules = """
axiomguard: "0.7"
domain: test
rules:
  - name: max_age
    type: range
    entity: person
    relation: age
    value_type: int
    max: 120
    severity: error
    message: "Age must be <= 120."
"""
        r = client.post("/api/verify", json={
            "yaml_rules": yaml_rules,
            "subject": "person",
            "relation": "age",
            "value": "30",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_hallucinating"] is False

    def test_verify_failing_claim(self, client):
        yaml_rules = """
axiomguard: "0.7"
domain: test
rules:
  - name: max_age
    type: range
    entity: person
    relation: age
    value_type: int
    max: 120
    severity: error
    message: "Age must be <= 120."
"""
        r = client.post("/api/verify", json={
            "yaml_rules": yaml_rules,
            "subject": "person",
            "relation": "age",
            "value": "999",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["is_hallucinating"] is True


class TestValidateEndpoint:

    def test_validate_valid_yaml(self, client):
        yaml_str = """
axiomguard: "0.7"
domain: test
rules:
  - name: r1
    type: unique
    entity: x
    relation: y
    severity: error
    message: "Unique."
"""
        r = client.post("/api/validate", json={"yaml_str": yaml_str})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert len(data["rules"]) == 1

    def test_validate_invalid_yaml(self, client):
        r = client.post("/api/validate", json={"yaml_str": "invalid: [["})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False


class TestBuildYamlEndpoint:

    def test_build_yaml(self, client):
        r = client.post("/api/build-yaml", json={
            "domain": "test",
            "rules": [{
                "name": "r1",
                "type": "unique",
                "entity": "x",
                "relation": "y",
                "severity": "error",
                "message": "Unique."
            }],
        })
        assert r.status_code == 200
        data = r.json()
        assert "axiomguard" in data["yaml"]
        assert "r1" in data["yaml"]


class TestGenerateEndpoint:

    def test_generate_without_llm(self, client):
        """Without LLM backend, should return error gracefully."""
        r = client.post("/api/generate", json={
            "text": "Some policy document",
            "domain": "test",
        })
        assert r.status_code == 200
        data = r.json()
        # Should return error (no LLM) but not crash
        assert "error" in data
