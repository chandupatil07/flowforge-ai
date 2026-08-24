import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from flowforge_ai.database import Base, get_db
from flowforge_ai.main import app
from flowforge_ai.models import User, Project, ProjectMember

# Create an in-memory SQLite database for fast unit testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_flowforge.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db():
    # Recreate the tables for every single test to ensure test isolation
    Base.metadata.create_all(bind=engine)
    db_session = TestingSessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_user_registration_and_login(client):
    # 1. Test register user
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "password123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert "id" in data

    # 2. Test register duplicate username fails
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "password456"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already taken"

    # 3. Test login with correct credentials
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "password123"}
    )
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 4. Test login with incorrect credentials
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"

def test_project_creation_and_isolation(client):
    # 1. Register User A and User B
    client.post("/api/v1/auth/register", json={"username": "usera", "password": "passworda"})
    client.post("/api/v1/auth/register", json={"username": "userb", "password": "passwordb"})

    # 2. Login User A
    login_a = client.post("/api/v1/auth/login", data={"username": "usera", "password": "passworda"}).json()
    token_a = login_a["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 3. Login User B
    login_b = client.post("/api/v1/auth/login", data={"username": "userb", "password": "passwordb"}).json()
    token_b = login_b["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 4. User A creates Project A
    res_proj = client.post("/api/v1/projects", json={"name": "Project A"}, headers=headers_a)
    assert res_proj.status_code == 201
    proj_a = res_proj.json()
    proj_id = proj_a["id"]

    # 5. User A accesses Project A (Authorized)
    res_access_a = client.get(f"/api/v1/projects/{proj_id}", headers=headers_a)
    assert res_access_a.status_code == 200
    assert res_access_a.json()["name"] == "Project A"

    # 6. User B accesses Project A (Unauthorized - 403 Forbidden)
    res_access_b = client.get(f"/api/v1/projects/{proj_id}", headers=headers_b)
    assert res_access_b.status_code == 403
    assert res_access_b.json()["detail"] == "Not a member of this project"
