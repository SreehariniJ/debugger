from __future__ import annotations


def _register_user(client, username: str) -> str:
    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": "secret123",
            "display_name": username.title(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_create_list_and_get_team(client):
    created = client.post("/teams/", json={"name": "Core Team"})
    assert created.status_code == 201
    team = created.json()
    assert team["name"] == "Core Team"
    assert team["members"][0]["username"] == "admin"

    listed = client.get("/teams/")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = client.get(f"/teams/{team['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == team["id"]


def test_add_and_remove_team_member(client):
    alice_token = _register_user(client, "alice")
    created = client.post("/teams/", json={"name": "Shared Team"})
    team_id = created.json()["id"]

    added = client.post(f"/teams/{team_id}/add_member?username=alice")
    assert added.status_code == 200
    assert {member["username"] for member in added.json()["members"]} == {"admin", "alice"}

    removed = client.post(f"/teams/{team_id}/remove_member?username=alice")
    assert removed.status_code == 200
    assert {member["username"] for member in removed.json()["members"]} == {"admin"}

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {alice_token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_team_session_visible_to_added_member(client):
    bob_token = _register_user(client, "bob")
    team = client.post("/teams/", json={"name": "Review Team"}).json()
    team_id = team["id"]

    add_member = client.post(f"/teams/{team_id}/add_member?username=bob")
    assert add_member.status_code == 200

    created = client.post(
        "/sessions/",
        json={
            "title": "ZeroDivision Failure",
            "error": "ZeroDivisionError: division by zero",
            "team_id": team_id,
            "analysis": "Guard the denominator before division.",
            "fixed_code": "if denom != 0:\n    print(num / denom)\nelse:\n    print(0)\n",
            "source_path": str(client.workspace_root / "bug.py"),
            "severity": "CRITICAL",
            "pipeline_mode": "fast",
        },
    )
    assert created.status_code == 201
    session = created.json()
    assert session["analysis"]
    assert session["fixed_code"]

    member_headers = {"Authorization": f"Bearer {bob_token}"}
    listed = client.get("/sessions/", headers=member_headers)
    assert listed.status_code == 200
    session_ids = {item["id"] for item in listed.json()}
    assert session["id"] in session_ids

    fetched = client.get(f"/sessions/{session['id']}", headers=member_headers)
    assert fetched.status_code == 200
    fetched_payload = fetched.json()
    assert fetched_payload["analysis"] == session["analysis"]
    assert fetched_payload["fixed_code"] == session["fixed_code"]
    assert fetched_payload["team"]["name"] == "Review Team"


def test_comments_round_trip_for_shared_session(client):
    alice_token = _register_user(client, "alice")
    team_id = client.post("/teams/", json={"name": "Comments Team"}).json()["id"]
    assert client.post(f"/teams/{team_id}/add_member?username=alice").status_code == 200

    session = client.post(
        "/sessions/",
        json={
            "title": "Shared Failure",
            "error": "NameError: missing variable",
            "team_id": team_id,
        },
    ).json()

    alice_headers = {"Authorization": f"Bearer {alice_token}"}
    created_comment = client.post(
        "/comments/",
        json={"content": "I can reproduce this bug.", "session_id": session["id"]},
        headers=alice_headers,
    )
    assert created_comment.status_code == 201
    comment_id = created_comment.json()["id"]

    listed = client.get(f"/comments/{session['id']}")
    assert listed.status_code == 200
    comments = listed.json()
    assert len(comments) == 1
    assert comments[0]["content"] == "I can reproduce this bug."
    assert comments[0]["author"]["username"] == "alice"

    deleted = client.delete(f"/comments/{comment_id}", headers=alice_headers)
    assert deleted.status_code == 204

    listed_again = client.get(f"/comments/{session['id']}")
    assert listed_again.status_code == 200
    assert listed_again.json() == []
