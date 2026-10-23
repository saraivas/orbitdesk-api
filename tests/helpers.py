def register_and_login(client, email="owner@example.com", password="senha123", org="Org"):
    """Register a user (with an organization) and log in. Returns the tokens and ids."""
    registered = client.post("/auth/register", json={
        "email": email, "password": password, "organization_name": org,
    }).json()
    tokens = client.post("/auth/login", json={"email": email, "password": password}).json()
    return {
        "user_id": registered["user_id"],
        "org_id": registered["organization"]["id"],
        "access": tokens["access_token"],
        "refresh": tokens["refresh_token"],
    }


def headers(session, access=None):
    return {
        "Authorization": f"Bearer {access or session['access']}",
        "X-Organization-Id": session["org_id"],
    }


def create_task(client, session, access=None):
    return client.post("/tasks", json={"title": "t"}, headers=headers(session, access))
