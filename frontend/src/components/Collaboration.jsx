import React, { useState, useEffect } from 'react';
import { motion as Motion, AnimatePresence } from 'framer-motion';
import { Users, Plus, UserPlus, Trash2, MessageSquare, Clock, Code2, Zap } from 'lucide-react';
import { fetchJson } from '../lib/api';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const API = import.meta.env.VITE_API_URL || (window.location.port.startsWith('517') ? 'http://127.0.0.1:8001' : '')

export const CollaborationTab = () => {
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateTeam, setShowCreateTeam] = useState(false);
  const [newTeamName, setNewTeamName] = useState('');
  const [error, setError] = useState(null);

  const fetchTeams = async () => {
    try {
      setLoading(true);
      const data = await fetchJson(`${API}/teams/`);
      if (Array.isArray(data)) {
        setTeams(data);
      } else {
        setTeams([]);
        throw new Error("Teams data endpoint unavailable or invalid format.");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeams();
  }, []);

  const handleCreateTeam = async (e) => {
    e.preventDefault();
    if (!newTeamName.trim()) return;
    try {
      await fetchJson(`${API}/teams/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newTeamName })
      });
      setNewTeamName('');
      setShowCreateTeam(false);
      fetchTeams();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="collaboration-tab">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Users size={24} color="var(--accent)" />
          <div>
            <h2 style={{ margin: 0 }}>Teams</h2>
            <p style={{ margin: '0.2rem 0 0', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Create teams and invite people to review shared debugging sessions.
            </p>
          </div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setShowCreateTeam(true)}>
          <Plus size={18} /> Create Team
        </button>
      </div>

      <AnimatePresence>
        {showCreateTeam && (
          <Motion.div 
            initial={{ opacity: 0, height: 0 }} 
            animate={{ opacity: 1, height: 'auto' }} 
            exit={{ opacity: 0, height: 0 }}
            className="card glass" 
            style={{ marginBottom: '1.5rem', overflow: 'hidden' }}
          >
            <form onSubmit={handleCreateTeam} style={{ display: 'flex', gap: '1rem' }}>
              <input 
                autoFocus
                className="input-field" 
                placeholder="Enter team name..." 
                value={newTeamName}
                onChange={e => setNewTeamName(e.target.value)}
              />
              <button className="btn btn-primary" type="submit">Create</button>
              <button className="btn btn-secondary" type="button" onClick={() => setShowCreateTeam(false)}>Cancel</button>
            </form>
          </Motion.div>
        )}
      </AnimatePresence>

      {error && (
        <div className="card glass border-error" style={{ marginBottom: '1.5rem', color: 'var(--error)' }}>
          {error}
        </div>
      )}

      {loading ? (
        <div className="loader-container"><div className="loader" /></div>
      ) : (
        <div className="teams-grid">
          {teams.length === 0 ? (
            <div className="card glass" style={{ textAlign: 'center', padding: '3rem' }}>
              <h3 style={{ marginBottom: '0.5rem' }}>Create your first team</h3>
              <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>Create a team to collaborate on debugging sessions.</p>
              <button className="btn btn-primary btn-sm" type="button" onClick={() => setShowCreateTeam(true)}>
                <Plus size={16} /> Create Team
              </button>
            </div>
          ) : (
            teams.map(team => (
              <TeamCard key={team.id} team={team} onRefresh={fetchTeams} />
            ))
          )}
        </div>
      )}
    </div>
  );
};

const TeamCard = ({ team, onRefresh }) => {
  const [showAddMember, setShowAddMember] = useState(false);
  const [newMemberUsername, setNewMemberUsername] = useState('');
  const [error, setError] = useState(null);

  const handleAddMember = async (e) => {
    e.preventDefault();
    try {
      await fetchJson(`${API}/teams/${team.id}/add_member?username=${newMemberUsername}`, {
        method: 'POST'
      });
      setNewMemberUsername('');
      setShowAddMember(false);
      onRefresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRemoveMember = async (username) => {
    if (!confirm(`Are you sure you want to remove ${username} from the team?`)) return;
    try {
      await fetchJson(`${API}/teams/${team.id}/remove_member?username=${username}`, {
        method: 'POST'
      });
      onRefresh();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="card glass team-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
        <h3 style={{ margin: 0, color: 'var(--accent)' }}>{team.name}</h3>
        <button className="btn btn-secondary btn-sm" type="button" onClick={() => setShowAddMember(!showAddMember)}>
          <UserPlus size={14} /> {showAddMember ? 'Close' : 'Add Member'}
        </button>
      </div>

      <AnimatePresence>
        {showAddMember && (
          <Motion.div 
            initial={{ opacity: 0, y: -10 }} 
            animate={{ opacity: 1, y: 0 }} 
            exit={{ opacity: 0, y: -10 }}
            style={{ marginBottom: '1rem' }}
          >
            <form onSubmit={handleAddMember} style={{ display: 'flex', gap: '0.5rem' }}>
              <input 
                className="input-field input-sm" 
                placeholder="Username" 
                value={newMemberUsername}
                onChange={e => setNewMemberUsername(e.target.value)}
              />
              <button className="btn btn-primary btn-sm" type="submit">Add</button>
            </form>
            {error && <p style={{ color: 'var(--error)', fontSize: '0.7rem', marginTop: '0.5rem' }}>{error}</p>}
          </Motion.div>
        )}
      </AnimatePresence>

      <div className="members-list">
        <label style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: '0.5rem', display: 'block' }}>Members</label>
        {team.members.map(member => (
          <div key={member.username} className="member-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div className="avatar-sm">{member.display_name[0]}</div>
              <span style={{ fontSize: '0.85rem' }}>{member.display_name}</span>
            </div>
            <button className="btn-icon text-error" onClick={() => handleRemoveMember(member.username)}>
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export const SharedSessionList = ({ onSelectSession, onOpenDebug }) => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchSessions = async () => {
    try {
      const data = await fetchJson(`${API}/sessions/`);
      if (Array.isArray(data)) {
        setSessions(data);
      } else {
        setSessions([]);
        console.error("Sessions data endpoint unavailable or invalid format.");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  return (
    <div className="shared-sessions">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <Clock size={24} color="var(--accent)" />
          <div>
            <h2 style={{ margin: 0 }}>Shared Sessions</h2>
            <p style={{ margin: '0.2rem 0 0', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Recent debugging sessions shared across your teams.
            </p>
          </div>
      </div>

      {loading ? <div className="loader" /> : (
        <div className="sessions-list">
          {sessions.length === 0 ? (
            <div className="card glass" style={{ textAlign: 'center', padding: '3rem' }}>
              <h3 style={{ marginBottom: '0.5rem' }}>No shared sessions yet</h3>
              <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>Run a debug session and share it with your team.</p>
              {onOpenDebug && (
                <button className="btn btn-primary btn-sm" type="button" onClick={onOpenDebug}>
                  <Zap size={16} /> Open Debug
                </button>
              )}
            </div>
          ) : sessions.map(session => (
            <div key={session.id} className="card glass session-item" onClick={() => onSelectSession(session)}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <h4 style={{ margin: 0 }}>{session.title}</h4>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>{new Date(session.created_at * 1000).toLocaleString()}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>by {session.owner.display_name}</span>
                {session.team && <span className="team-badge">{session.team.name}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const SessionCollaboration = ({ session }) => {
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchComments = async () => {
    try {
      const data = await fetchJson(`${API}/comments/${session.id}`);
      if (Array.isArray(data)) {
        setComments(data);
      } else {
        setComments([]);
        console.error("Comments endpoint unavailable or invalid format.");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchComments();
  }, [session.id]);

  const handleAddComment = async (e) => {
    e.preventDefault();
    if (!newComment.trim()) return;
    try {
      await fetchJson(`${API}/comments/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newComment, session_id: session.id })
      });
      setNewComment('');
      fetchComments();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="session-collaboration card glass">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.75rem' }}>
        <MessageSquare size={18} color="var(--accent)" />
        <div>
          <h4 style={{ margin: 0 }}>Session Discussion</h4>
          <p style={{ margin: '0.2rem 0 0', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
            Review the latest error, analysis, and suggested fix with your team.
          </p>
        </div>
      </div>

      <div className="session-data" style={{ marginBottom: '2rem' }}>
        <h3 style={{ color: 'var(--text-primary)', marginBottom: '0.5rem' }}>{session.title}</h3>
        {session.error && <p style={{ color: 'var(--error)', fontSize: '0.85rem', marginBottom: '1.5rem', background: 'rgba(244, 63, 94, 0.05)', padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid rgba(244, 63, 94, 0.2)' }}>{session.error}</p>}
        
        {session.analysis ? (
          <div className="markdown-body" style={{ background: 'rgba(16, 16, 24, 0.6)', padding: '1.5rem', borderRadius: '0.75rem', border: '1px solid var(--border)', marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
              <Zap size={16} color="var(--accent)" />
              <span style={{ fontWeight: 800, textTransform: 'uppercase', fontSize: '0.75rem', letterSpacing: '0.1em', color: 'var(--text-secondary)' }}>AI Analysis</span>
            </div>
            <ReactMarkdown>{session.analysis}</ReactMarkdown>
          </div>
        ) : (
          <div className="card glass" style={{ marginBottom: '1.5rem', color: 'var(--text-secondary)' }}>
            No AI analysis was saved for this session.
          </div>
        )}

        {session.fixed_code ? (
          <div className="card glass editor-frame" style={{ marginBottom: '1.5rem' }}>
            <div className="editor-header" style={{ padding: '0.75rem 1rem', background: 'rgba(0,0,0,0.2)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Code2 size={16} color="var(--accent)" />
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Suggested Fix</span>
            </div>
            <div className="code-display" style={{ padding: '0.5rem', maxHeight: '400px', overflowY: 'auto' }}>
              <SyntaxHighlighter language="python" style={vscDarkPlus} showLineNumbers>
                {session.fixed_code}
              </SyntaxHighlighter>
            </div>
          </div>
        ) : (
          <div className="card glass" style={{ marginBottom: '1.5rem', color: 'var(--text-secondary)' }}>
            No suggested fix was attached to this session.
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <h4 style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Team Comments</h4>
      </div>

      <div className="comments-area" style={{ maxHeight: '300px', overflowY: 'auto', marginBottom: '1rem' }}>
        {loading ? <div className="loader" /> : comments.length === 0 ? (
          <div className="card glass" style={{ padding: '1.25rem', color: 'var(--text-secondary)' }}>
            No comments yet. Start the discussion.
          </div>
        ) : comments.map(comment => (
          <div key={comment.id} className="comment-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
              <span style={{ fontWeight: 800, fontSize: '0.75rem', color: 'var(--accent)' }}>{comment.author.display_name}</span>
              <span style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>{new Date(comment.created_at * 1000).toLocaleTimeString()}</span>
            </div>
            <p style={{ margin: 0, fontSize: '0.85rem' }}>{comment.content}</p>
          </div>
        ))}
      </div>

      <form onSubmit={handleAddComment}>
        <textarea 
          className="input-field" 
          placeholder="Add context, notes, or review feedback..." 
          value={newComment}
          onChange={e => setNewComment(e.target.value)}
          style={{ minHeight: '60px', marginBottom: '0.5rem' }}
        />
        <button className="btn btn-primary btn-sm" type="submit">Post Comment</button>
      </form>
    </div>
  );
};
