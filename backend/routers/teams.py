from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import Field
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, Team
from backend.schemas import StrictModel, UserProfile
from backend.dependencies import get_current_user

router = APIRouter(prefix="/teams", tags=["teams"])

class TeamCreate(StrictModel):
    name: str

class MemberAction(StrictModel):
    username: str

class TeamResponse(StrictModel):
    id: int
    name: str
    members: List[UserProfile] = Field(default_factory=list)

@router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    team_create: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_team = db.query(Team).filter(Team.name == team_create.name).first()
    if db_team:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Team name already registered")
    
    new_team = Team(name=team_create.name)
    new_team.members.append(current_user)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    
    return TeamResponse(
        id=new_team.id,
        name=new_team.name,
        members=[UserProfile(username=member.username, display_name=member.display_name) for member in new_team.members]
    )

@router.get("/", response_model=List[TeamResponse])
def get_user_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    teams = current_user.teams
    return [
        TeamResponse(
            id=team.id,
            name=team.name,
            members=[UserProfile(username=member.username, display_name=member.display_name) for member in team.members]
        ) for team in teams
    ]

@router.get("/{team_id}", response_model=TeamResponse)
def get_team_by_id(
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    
    # Check if the current user is a member of the team
    if current_user not in team.members:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")
    
    
    
    return TeamResponse(
        id=team.id,
        name=team.name,
        members=[UserProfile(username=member.username, display_name=member.display_name) for member in team.members]
    )

@router.post("/{team_id}/add_member", response_model=TeamResponse)
def add_member_to_team(
    team_id: int,
    username: Optional[str] = None,
    body: Optional[MemberAction] = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_username = username or (body.username if body else None)
    if not target_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be provided via query param or body")
    
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    
    if current_user not in team.members:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")
    
    member_to_add = db.query(User).filter(User.username == target_username).first()
    if not member_to_add:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to add not found")
    
    if member_to_add in team.members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member of this team")
    
    team.members.append(member_to_add)
    db.commit()
    db.refresh(team)
    
    return TeamResponse(
        id=team.id,
        name=team.name,
        members=[UserProfile(username=member.username, display_name=member.display_name) for member in team.members]
    )

@router.post("/{team_id}/remove_member", response_model=TeamResponse)
def remove_member_from_team(
    team_id: int,
    username: Optional[str] = None,
    body: Optional[MemberAction] = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_username = username or (body.username if body else None)
    if not target_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be provided via query param or body")
    
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    
    if current_user not in team.members:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")

    member_to_remove = db.query(User).filter(User.username == target_username).first()
    if not member_to_remove:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to remove not found")
    
    if member_to_remove not in team.members:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a member of this team")
    
    if member_to_remove.id == current_user.id and len(team.members) == 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last member from a team")

    team.members.remove(member_to_remove)
    db.commit()
    db.refresh(team)
    
    return TeamResponse(
        id=team.id,
        name=team.name,
        members=[UserProfile(username=member.username, display_name=member.display_name) for member in team.members]
    )
