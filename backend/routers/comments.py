from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, DebugSession, Comment
from backend.schemas import StrictModel, UserProfile
from backend.dependencies import get_current_user

router = APIRouter(prefix="/comments", tags=["comments"])

class CommentCreate(StrictModel):
    content: str
    session_id: int

class CommentResponse(StrictModel):
    id: int
    content: str
    created_at: float
    author: UserProfile
    session_id: int

@router.post("/", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
def add_comment(
    comment_create: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = db.query(DebugSession).filter(DebugSession.id == comment_create.session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Debug session not found")
    
    is_owner = session.user_id == current_user.id
    is_team_member = False
    if session.team:
        is_team_member = current_user in session.team.members
    
    if not is_owner and not is_team_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to comment on this session")

    new_comment = Comment(
        content=comment_create.content,
        session_id=comment_create.session_id,
        user_id=current_user.id
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    return CommentResponse(
        id=new_comment.id,
        content=new_comment.content,
        created_at=new_comment.created_at,
        author=UserProfile(username=current_user.username, display_name=current_user.display_name),
        session_id=new_comment.session_id
    )

@router.get("/{session_id}", response_model=List[CommentResponse])
def get_comments_for_session(
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view comments for this session")

    comments = (
        db.query(Comment)
        .filter(Comment.session_id == session_id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    
    return [
        CommentResponse(
            id=comment.id,
            content=comment.content,
            created_at=comment.created_at,
            author=UserProfile(username=comment.author.username, display_name=comment.author.display_name),
            session_id=comment.session_id
        ) for comment in comments
    ]

@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this comment")
    
    db.delete(comment)
    db.commit()
    return 
