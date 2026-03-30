import React from 'react';
import { motion as Motion } from 'framer-motion';
import { Layout, Zap, EyeOff, Folder } from 'lucide-react';

const WorkspaceExplorer = React.memo(({
    files,
    onTogglePath,
    selectedPaths,
    onClearSelection,
    onBatchDebug,
    batchLoading,
    onUpdateRoot,
    workspaceRoot,
    onSelectFile,
    workspaceQuery,
    setWorkspaceQuery
}) => {
    const [newRoot, setNewRoot] = React.useState(workspaceRoot);

    React.useEffect(() => {
        setNewRoot(workspaceRoot);
    }, [workspaceRoot]);

    return (
        <Motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card glass">
            <div style={{ marginBottom: '1.5rem', background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '1rem', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                    <Folder size={18} color="var(--accent)" />
                    <span style={{ fontSize: '0.8rem', fontWeight: 800, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Project Root</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <input
                        className="input-field"
                        style={{ padding: '0.6rem 1rem', fontSize: '0.85rem' }}
                        value={newRoot}
                        onChange={e => setNewRoot(e.target.value)}
                        placeholder="Absolute path to your project folder..."
                    />
                    <button
                        className="btn btn-primary btn-sm"
                        onClick={() => onUpdateRoot(newRoot)}
                        disabled={!newRoot || newRoot === workspaceRoot}
                    >
                        Switch Root
                    </button>
                </div>
                <div style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)', marginTop: '0.5rem' }}>
                    Indexing: <strong style={{ color: 'var(--accent)' }}>{files.length}</strong> Python files detected in this scope.
                </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <Layout size={20} color="var(--accent)" />
                    <h3 style={{ fontSize: '1.25rem' }}>Workspace Explorer</h3>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                        className="btn btn-secondary btn-sm"
                        type="button"
                        onClick={onClearSelection}
                        disabled={selectedPaths.length === 0 || batchLoading}
                    >
                        Clear
                    </button>
                    <button
                        className="btn btn-primary btn-sm"
                        type="button"
                        onClick={onBatchDebug}
                        disabled={selectedPaths.length === 0 || batchLoading}
                    >
                        <Zap size={14} /> {batchLoading ? 'Running...' : `Debug Selected (${selectedPaths.length})`}
                    </button>
                </div>
            </div>

            <div style={{ marginBottom: '1rem' }}>
                <input
                    className="input-field"
                    placeholder="Filter files..."
                    value={workspaceQuery}
                    onChange={(e) => setWorkspaceQuery(e.target.value)}
                    style={{ padding: '0.6rem 1rem', fontSize: '0.85rem', borderRadius: '0.75rem' }}
                />
            </div>

            <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
                <table className="elite-table">
                    <thead>
                        <tr>
                            <th style={{ width: '42px' }}>Pick</th>
                            <th>File Name</th>
                            <th>Path</th>
                            <th>Size</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {files.map((file, idx) => (
                            <tr key={idx}>
                                <td>
                                    <input
                                        type="checkbox"
                                        checked={selectedPaths.includes(file.path)}
                                        onChange={() => onTogglePath(file.path)}
                                        aria-label={`Select ${file.rel_path}`}
                                    />
                                </td>
                                <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{file.name}</td>
                                <td style={{ color: 'var(--text-tertiary)', fontSize: '0.8rem' }}>{file.rel_path}</td>
                                <td style={{ color: 'var(--text-secondary)' }}>{(file.size / 1024).toFixed(1)} KB</td>
                                <td>
                                    <div style={{ display: 'flex', gap: '0.25rem' }}>
                                        <button
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => {
                                                if (selectedPaths.includes(file.path)) {
                                                    onTogglePath(file.path)
                                                }
                                            }}
                                            disabled={!selectedPaths.includes(file.path)}
                                            title="Clear selection for this file"
                                        >
                                            Clear
                                        </button>
                                        <button
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => {
                                                onClearSelection()
                                                onSelectFile(file.path)
                                            }}
                                            title="Debug this file"
                                        >
                                            <EyeOff size={14} /> Debug
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {files.length === 0 && (
                            <tr>
                                <td colSpan="5" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-tertiary)' }}>
                                    No files found in this workspace.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </Motion.div>
    );
});

WorkspaceExplorer.displayName = 'WorkspaceExplorer';

export default WorkspaceExplorer;
