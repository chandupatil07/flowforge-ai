from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from flowforge_ai.database import get_db
from flowforge_ai.models import User, Project, ProjectMember
from flowforge_ai.control_plane.auth.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    RoleChecker,
)

router = APIRouter(prefix="/api/v1")

# Pydantic schemas for request/response bodies
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)

class UserOut(BaseModel):
    id: str
    username: str

    class Config:
        from_attributes = True

class TokenOut(BaseModel):
    access_token: str
    token_type: str

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class ProjectOut(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True

@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    # Check if username exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    hashed = hash_password(user_data.password)
    user = User(username=user_data.username, password_hash=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/auth/login", response_model=TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = create_access_token(data={"sub": user.username, "user_id": user.id})
    return {"access_token": token, "token_type": "bearer"}

# Project Management & RBAC Verification routes
@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(project_data: ProjectCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = Project(name=project_data.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    
    # Automatically register creator as project OWNER
    member = ProjectMember(project_id=project.id, user_id=current_user.id, role="OWNER")
    db.add(member)
    db.commit()
    
    return project

@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    # Project isolation boundary verification: requires project membership role
    membership: ProjectMember = Depends(RoleChecker(["OWNER", "DEVELOPER", "OPERATOR"]))
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
