from fastapi.testclient import TestClient


def test_register_login_and_me(client: TestClient) -> None:
    register_response = client.post(
        "/auth/register",
        json={
            "email": "Ada@example.com",
            "password": "correct-horse-battery",
            "full_name": "Ada Lovelace",
        },
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "ada@example.com"
    assert "hashed_password" not in register_response.json()

    login_response = client.post(
        "/auth/login",
        data={"username": "ada@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["full_name"] == "Ada Lovelace"


def test_duplicate_registration_is_rejected(client: TestClient) -> None:
    payload = {"email": "dupe@example.com", "password": "correct-horse-battery"}
    assert client.post("/auth/register", json=payload).status_code == 201
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 409


def test_me_requires_valid_token(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
