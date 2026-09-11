def test_register_creates_user_organization_and_owner_membership(client):
    response = client.post("/auth/register", json={
        "email": "owner@example.com",
        "password": "senha123",
        "organization_name": "Empresa Teste",
    })

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "owner@example.com"
    assert data["organization"]["name"] == "Empresa Teste"
    assert "user_id" in data
    assert "id" in data["organization"]


def test_register_rejects_duplicate_email(client):
    client.post("/auth/register", json={
        "email": "duplicado@example.com",
        "password": "senha123",
        "organization_name": "Org 1",
    })

    response = client.post("/auth/register", json={
        "email": "duplicado@example.com",
        "password": "outrasenha",
        "organization_name": "Org 2",
    })

    assert response.status_code == 400


def test_register_rejects_blank_organization_name(client):
    response = client.post("/auth/register", json={
        "email": "teste@example.com",
        "password": "senha123",
        "organization_name": "   ",
    })

    assert response.status_code == 422


def test_login_after_register_succeeds(client):
    client.post("/auth/register", json={
        "email": "login@example.com",
        "password": "senha123",
        "organization_name": "Org Login",
    })

    response = client.post("/auth/login", json={
        "email": "login@example.com",
        "password": "senha123",
    })

    assert response.status_code == 200
    assert "access_token" in response.json()
