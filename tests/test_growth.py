import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
import main
from storage import Store

TOKEN = "test_growth_token_at_least_24_characters"
HEADERS = {"Authorization": "Bearer " + TOKEN}

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", Store(str(tmp_path / "growth.sqlite3")))
    monkeypatch.setenv("JARVIS_ACCESS_TOKEN", TOKEN)
    return TestClient(main.app)

def test_growth_requires_auth(client):
    assert client.get("/api/growth").status_code == 401
    assert client.post("/api/growth/ideas", json={}).status_code == 401
    assert client.put("/api/growth/profile", json={"focus": "Video"}).status_code == 401

def test_daily_missions_and_profile_persist(client):
    first = client.get("/api/growth", headers=HEADERS)
    assert first.status_code == 200
    data = first.json()
    assert len(data["tasks"]) == 3
    assert {item["category"] for item in data["tasks"]} == {"impresa", "carriera", "visibilita"}
    task_id = data["tasks"][0]["id"]
    update = client.patch("/api/growth/tasks/" + task_id, headers=HEADERS, json={"done": True})
    assert update.status_code == 200
    assert update.json()["done_today"] == 1
    assert client.get("/api/growth", headers=HEADERS).json()["done_today"] == 1
    profile = {"focus": "Video verticali", "market": "Olanda", "starting_budget_eur": 0,
               "minutes_per_day": 60, "goal_90_days": "Primo cliente pagante"}
    assert client.put("/api/growth/profile", headers=HEADERS, json=profile).json()["profile"] == profile
    assert client.get("/api/growth", headers=HEADERS).json()["profile"] == profile

def test_idea_fallback_no_fake_market_research(client, monkeypatch):
    async def no_llm(*args, **kwargs):
        return None
    monkeypatch.setattr(main, "omnipotent_ask", no_llm)
    generated = client.post("/api/growth/ideas", headers=HEADERS, json={"topic": "UGC"})
    assert generated.status_code == 200
    idea = generated.json()
    assert idea["source"] == "modello_base"
    assert "first_test" in idea and "costs_and_risks" in idea
    assert len(client.get("/api/growth", headers=HEADERS).json()["ideas"]) == 1

def test_mentor_profile_and_fallback(client, monkeypatch):
    async def no_llm(*args, **kwargs):
        return None
    monkeypatch.setattr(main, "omnipotent_ask", no_llm)
    response = client.post("/api/growth/mentor", headers=HEADERS,
                           json={"question": "Come trovo il primo cliente per video?"})
    assert response.status_code == 200
    assert response.json()["mode"] == "guida_base"
    assert "cliente" in response.json()["answer"].lower()

def test_profile_and_task_validation(client):
    assert client.put("/api/growth/profile", headers=HEADERS,
                      json={"starting_budget_eur": -10}).status_code == 422
    assert client.patch("/api/growth/tasks/not-a-task", headers=HEADERS,
                        json={"done": True}).status_code == 422
    assert client.post("/api/growth/mentor", headers=HEADERS,
                       json={"question": "x"}).status_code == 422
