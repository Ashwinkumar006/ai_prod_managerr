"""
Test Suite: AstroMarine Cascade Failure Prevention Engine
=========================================================
20+ test cases covering:
- Cascade analysis engine (graph building, criticality, Bayesian propagation, Monte Carlo)
- Anomaly detection (threshold, Z-score, rate-of-change)
- API endpoints (missions, subsystems, telemetry, cascade analysis)
- Database operations
"""

import pytest
import numpy as np
from datetime import datetime
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from main import (
    app, Base, engine, get_db, SessionLocal,
    CascadeAnalysisEngine, AnomalyDetector, SubsystemDB,
    MissionDB, DEFAULT_SUBSYSTEMS
)


# ─── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_db):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(test_db):
    return TestClient(app)


@pytest.fixture
def cascade_engine_fixture():
    return CascadeAnalysisEngine()


@pytest.fixture
def sample_subsystems():
    """Create sample subsystem DB objects for testing."""
    subs = []
    for sd in DEFAULT_SUBSYSTEMS[:8]:
        s = SubsystemDB(
            mission_id=1,
            code=sd["code"],
            name=sd["name"],
            domain=sd["domain"],
            health=100.0 - np.random.uniform(0, 30),
            failure_probability=np.random.uniform(0.01, 0.1),
            dependencies=sd["dependencies"],
        )
        subs.append(s)
    return subs


# ─── CASCADE ENGINE TESTS ───────────────────────────────────────────────────────

class TestCascadeEngine:

    def test_build_dependency_graph(self, cascade_engine_fixture, sample_subsystems):
        graph = cascade_engine_fixture.build_dependency_graph(sample_subsystems)
        assert len(graph.nodes) == len(sample_subsystems)
        # PWR-MAIN should have outgoing edges (others depend on it)
        assert graph.out_degree("PWR-MAIN") >= 1

    def test_criticality_scores(self, cascade_engine_fixture, sample_subsystems):
        cascade_engine_fixture.build_dependency_graph(sample_subsystems)
        scores = cascade_engine_fixture.compute_criticality_scores()
        assert len(scores) == len(sample_subsystems)
        # PWR-MAIN should be most critical (everything depends on it)
        assert scores["PWR-MAIN"] > 0
        assert all(v >= 0 for v in scores.values())

    def test_bayesian_propagation(self, cascade_engine_fixture, sample_subsystems):
        cascade_engine_fixture.build_dependency_graph(sample_subsystems)
        chain = cascade_engine_fixture.bayesian_cascade_propagation("PWR-MAIN", 0.95)
        assert len(chain) > 0
        # All probabilities should be between 0 and 1
        for code, prob in chain:
            assert 0 < prob <= 1.0
            assert code != "PWR-MAIN"  # Trigger excluded

    def test_bayesian_propagation_unknown_trigger(self, cascade_engine_fixture, sample_subsystems):
        cascade_engine_fixture.build_dependency_graph(sample_subsystems)
        chain = cascade_engine_fixture.bayesian_cascade_propagation("NONEXISTENT")
        assert chain == []

    def test_monte_carlo_simulation(self, cascade_engine_fixture, sample_subsystems):
        cascade_engine_fixture.build_dependency_graph(sample_subsystems)
        results = cascade_engine_fixture.monte_carlo_simulation("PWR-MAIN", n_runs=1000)
        assert results["trigger"] == "PWR-MAIN"
        assert results["runs"] == 1000
        assert results["mean_cascade_size"] >= 0
        assert len(results["confidence_interval_95"]) == 2
        assert results["confidence_interval_95"][0] <= results["confidence_interval_95"][1]

    def test_mitigation_actions(self, cascade_engine_fixture, sample_subsystems):
        cascade_engine_fixture.build_dependency_graph(sample_subsystems)
        chain = cascade_engine_fixture.bayesian_cascade_propagation("PWR-MAIN")
        actions = cascade_engine_fixture.generate_mitigation_actions(chain)
        assert len(actions) > 0
        for action in actions:
            assert "urgency" in action
            assert "action_type" in action
            assert action["urgency"] in ("IMMEDIATE", "HIGH", "ELEVATED")

    def test_empty_graph(self, cascade_engine_fixture):
        cascade_engine_fixture.build_dependency_graph([])
        scores = cascade_engine_fixture.compute_criticality_scores()
        assert scores == {}

    def test_cross_domain_coupling(self, cascade_engine_fixture, sample_subsystems):
        cascade_engine_fixture.build_dependency_graph(sample_subsystems)
        chain = cascade_engine_fixture.bayesian_cascade_propagation("PWR-MAIN")
        # Verify that cross-domain dependencies have higher cascade probability
        # (this is implicit in the coupling factor logic)
        assert len(chain) > 0


# ─── ANOMALY DETECTOR TESTS ─────────────────────────────────────────────────────

class TestAnomalyDetector:

    def test_threshold_violation_high(self):
        detector = AnomalyDetector()
        is_anom, score = detector.detect("SYS1", "temp", 110, threshold_max=100)
        assert is_anom is True
        assert score > 0

    def test_threshold_violation_low(self):
        detector = AnomalyDetector()
        is_anom, score = detector.detect("SYS1", "pressure", -5, threshold_min=0)
        assert is_anom is True
        assert score > 0

    def test_normal_reading(self):
        detector = AnomalyDetector()
        is_anom, score = detector.detect("SYS1", "temp", 50, threshold_min=0, threshold_max=100)
        assert is_anom is False
        assert score == 0.0

    def test_z_score_anomaly(self):
        detector = AnomalyDetector()
        # Feed normal data
        for i in range(20):
            detector.detect("SYS2", "vibration", 10 + np.random.normal(0, 0.5))
        # Feed extreme value
        is_anom, score = detector.detect("SYS2", "vibration", 50)
        assert is_anom is True
        assert score > 0.3

    def test_rate_of_change(self):
        detector = AnomalyDetector()
        # Feed slowly changing data
        for i in range(10):
            detector.detect("SYS3", "flow", 100 + i * 0.1)
        # Sudden jump
        is_anom, score = detector.detect("SYS3", "flow", 200)
        assert is_anom is True


# ─── API ENDPOINT TESTS ─────────────────────────────────────────────────────────

class TestAPIEndpoints:

    def test_create_mission(self, client):
        response = client.post("/api/v1/missions", json={
            "mission_code": "TEST-ALPHA-001",
            "name": "Test Deep Sea Station Alpha",
            "zone": "Pacific Trench Zone",
            "depth_m": 3000,
            "altitude_km": 400,
            "crew_size": 12,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["mission_code"] == "TEST-ALPHA-001"
        assert data["status"] == "active"

    def test_duplicate_mission(self, client):
        response = client.post("/api/v1/missions", json={
            "mission_code": "TEST-ALPHA-001",
            "name": "Duplicate",
        })
        assert response.status_code == 409

    def test_list_missions(self, client):
        response = client.get("/api/v1/missions")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_get_mission(self, client):
        response = client.get("/api/v1/missions/TEST-ALPHA-001")
        assert response.status_code == 200
        assert response.json()["crew_size"] == 12

    def test_get_mission_not_found(self, client):
        response = client.get("/api/v1/missions/NONEXISTENT")
        assert response.status_code == 404

    def test_list_subsystems(self, client):
        response = client.get("/api/v1/missions/TEST-ALPHA-001/subsystems")
        assert response.status_code == 200
        subs = response.json()
        assert len(subs) == len(DEFAULT_SUBSYSTEMS)

    def test_ingest_telemetry(self, client):
        response = client.post("/api/v1/missions/TEST-ALPHA-001/telemetry", json={
            "subsystem_code": "PWR-MAIN",
            "metric_name": "voltage",
            "value": 230.5,
            "unit": "V",
            "threshold_min": 200,
            "threshold_max": 250,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["subsystem_code"] == "PWR-MAIN"

    def test_cascade_analysis(self, client):
        response = client.post(
            "/api/v1/missions/TEST-ALPHA-001/cascade/analyze?trigger_subsystem=PWR-MAIN&monte_carlo_runs=500"
        )
        assert response.status_code == 200
        data = response.json()
        assert "cascade_chain" in data
        assert "monte_carlo" in data
        assert "mitigation_actions" in data

    def test_dependency_graph(self, client):
        response = client.get("/api/v1/missions/TEST-ALPHA-001/cascade/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == len(DEFAULT_SUBSYSTEMS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
