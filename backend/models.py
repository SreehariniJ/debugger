import time
from sqlalchemy import (Column, Integer, String, Float, ForeignKey, Table)
from sqlalchemy.orm import relationship

from .database import Base

user_team_association = Table('user_team_association', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('team_id', Integer, ForeignKey('teams.id'))
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String)
    hashed_password = Column(String, nullable=False)
    created_at = Column(Float, default=time.time)

    teams = relationship("Team", secondary=user_team_association, back_populates="members")
    sessions = relationship("DebugSession", back_populates="owner")
    comments = relationship("Comment", back_populates="author")

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    members = relationship("User", secondary=user_team_association, back_populates="teams")
    sessions = relationship("DebugSession", back_populates="team")


class DebugSession(Base):
    __tablename__ = "debug_sessions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(Float, default=time.time)
    title = Column(String, index=True)
    error = Column(String)
    analysis = Column(String, nullable=True)
    fixed_code = Column(String, nullable=True)
    source_path = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    pipeline_mode = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    owner = relationship("User", back_populates="sessions")

    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    team = relationship("Team", back_populates="sessions")

    comments = relationship("Comment", back_populates="session")


class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, nullable=False)
    created_at = Column(Float, default=time.time)

    session_id = Column(Integer, ForeignKey("debug_sessions.id"), index=True)
    session = relationship("DebugSession", back_populates="comments")

    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    author = relationship("User", back_populates="comments")
