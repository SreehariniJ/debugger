from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, Team, DebugSession
from backend.schemas import StrictModel, UserProfile
from backend.dependencies import get_current_user

router = APIRouter(prefix="/sessions", tags=["sessions"])

class TeamResponse(StrictModel): # Defined here to avoid circular import with backend.routers.teams
    id: int
    name: str

class DebugSessionCreate(StrictModel):
    title: str
    error: str
    team_id: Optional[int] = None
    analysis: Optional[str] = None
    fixed_code: Optional[str] = None
    source_path: Optional[str] = None
    severity: Optional[str] = None
    pipeline_mode: Optional[str] = None

class DebugSessionResponse(StrictModel):
    id: int
    created_at: float
    title: str
    error: str
    owner: UserProfile
    team: Optional[TeamResponse] = None
    analysis: Optional[str] = None
    fixed_code: Optional[str] = None
    source_path: Optional[str] = None
    severity: Optional[str] = None
    pipeline_mode: Optional[str] = None


def _serialize_session(session: DebugSession) -> DebugSessionResponse:
    team_response = None
    if session.team:
        team_response = TeamResponse(id=session.team.id, name=session.team.name)

    return DebugSessionResponse(
        id=session.id,
        created_at=session.created_at,
        title=session.title,
        error=session.error,
        owner=UserProfile(
            username=session.owner.username,
            display_name=session.owner.display_name,
        ),
        team=team_response,
        analysis=session.analysis,
        fixed_code=session.fixed_code,
        source_path=session.source_path,
        severity=session.severity,
        pipeline_mode=session.pipeline_mode,
    )

@router.post("/", response_model=DebugSessionResponse, status_code=status.HTTP_201_CREATED)
def create_debug_session(
    session_create: DebugSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    team = None
    if session_create.team_id:
        team = db.query(Team).filter(Team.id == session_create.team_id).first()
        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        if current_user not in team.members:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this team")

    new_session = DebugSession(
        title=session_create.title,
        error=session_create.error,
        user_id=current_user.id,
        team_id=session_create.team_id,
        analysis=session_create.analysis,
        fixed_code=session_create.fixed_code,
        source_path=session_create.source_path,
        severity=session_create.severity,
        pipeline_mode=session_create.pipeline_mode,
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return _serialize_session(new_session)

@router.get("", response_model=List[DebugSessionResponse])
@router.get("/", response_model=List[DebugSessionResponse])
def get_debug_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_sessions = (
        db.query(DebugSession)
        .filter(DebugSession.user_id == current_user.id)
        .order_by(DebugSession.created_at.desc())
        .all()
    )
    team_sessions = []
    for team in current_user.teams:
        team_sessions.extend(
            db.query(DebugSession)
            .filter(DebugSession.team_id == team.id)
            .order_by(DebugSession.created_at.desc())
            .all()
        )
    
    # Deduplicate: a session owned by the user AND on their team should appear only once
    seen_ids = set()
    all_sessions = []
    for session in user_sessions + team_sessions:
        if session.id not in seen_ids:
            seen_ids.add(session.id)
            all_sessions.append(session)
    
    all_sessions.sort(key=lambda item: item.created_at, reverse=True)
    return [_serialize_session(session) for session in all_sessions]

@router.get("/{session_id}", response_model=DebugSessionResponse)
def get_debug_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = db.query(DebugSession).filter(DebugSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debug session not found")
    
    is_owner = session.user_id == current_user.id
    is_team_member = False
    if session.team:
        is_team_member = current_user in session.team.members
    
    if not is_owner and not is_team_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this session")
    
    return _serialize_session(session)
