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


def join_as(client, owner, role, email):
    """Register another user and add them to `owner`'s organization with `role`.

    Returns a session dict scoped to `owner`'s organization.
    """
    other = register_and_login(client, email=email, org=f"{email} org")
    response = client.post("/members", json={"email": email, "role": role.value}, headers=headers(owner))
    assert response.status_code == 201, response.text
    return {**other, "org_id": owner["org_id"]}


def headers(session, access=None):
    return {
        "Authorization": f"Bearer {access or session['access']}",
        "X-Organization-Id": session["org_id"],
    }


def create_task(client, session, access=None, **body):
    return client.post("/tasks", json={"title": "t", **body}, headers=headers(session, access))
