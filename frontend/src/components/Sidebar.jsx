import React from 'react';
import { motion as Motion } from 'framer-motion';
import { Zap, CheckCircle2, AlertCircle, LogOut } from 'lucide-react';

const Sidebar = React.memo(({
    history,
    health,
    apiLatencyMs,
    onLogout,
    setFilePath,
    setMode,
    runDebug,
    setPasteCode
}) => {
    return (
        <aside className="sidebar">
            <div className="sidebar-brand">
                <div className="sidebar-brand-icon">
                    <Zap size={24} color="white" fill="white" />
                </div>
                <div className="sidebar-brand-text">
                    <span className="sidebar-brand-top">OFFLINE</span>
                    <span className="sidebar-brand-accent">AI DEBUGGER</span>
                </div>
            </div>

            <nav className="sidebar-nav">
                <div className="sidebar-section-label">Session History</div>
                <div className="sidebar-history-list">
                    {history.map((item) => (
                        <Motion.div
                            layout
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            key={item.id}
                            className="btn btn-secondary sidebar-history-btn"
                            onClick={() => {
                                const mode = item.type || (item.file.startsWith('/') || item.file.includes('.') ? 'upload' : 'paste');
                                setMode(mode);
                                if (mode === 'upload') {
                                    setFilePath(item.id_path || item.file);
                                    runDebug(item.id_path || item.file);
                                } else {
                                    setPasteCode(item.full_content || '');
                                    runDebug(null);
                                }
                            }}
                        >
                            <div className="sidebar-history-inner">
                                <div className="sidebar-history-row">
                                    {item.status === 'clean' ? <CheckCircle2 size={12} color="var(--success)" /> : <AlertCircle size={12} color="var(--error)" />}
                                    <span className="sidebar-history-name">{item.file}</span>
                                </div>
                                <span className="sidebar-history-time">{item.timestamp}</span>
                            </div>
                        </Motion.div>
                    ))}
                    {history.length === 0 && (
                        <div className="sidebar-empty">
                            No session history found.
                        </div>
                    )}
                </div>
            </nav>

            <div className="sidebar-footer">
                <div className="card glass sidebar-status-card">
                    <div className="sidebar-status-row" style={{ color: health.online ? 'var(--success)' : 'var(--error)' }}>
                        <div className={`sidebar-status-dot ${health.online ? 'online' : 'offline'}`} />
                        {health.online ? 'Backend Online' : 'Backend Offline'}
                    </div>
                    <div className="sidebar-meta-row">
                        <span>Model</span>
                        <span style={{ color: health.model_loaded ? 'var(--success)' : 'var(--warning)' }}>
                            {health.model_loaded ? 'Loaded' : 'Disabled'}
                        </span>
                    </div>
                    <div className="sidebar-meta-row">
                        <span>API Latency</span>
                        <span>{apiLatencyMs == null ? 'N/A' : `${apiLatencyMs} ms`}</span>
                    </div>
                </div>
                <button
                    className="btn btn-secondary sidebar-signout"
                    onClick={onLogout}
                >
                    <LogOut size={14} /> Sign Out
                </button>
            </div>
        </aside>
    );
});

Sidebar.displayName = 'Sidebar';

export default Sidebar;
