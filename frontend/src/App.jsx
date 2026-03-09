import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { motion as Motion, AnimatePresence } from 'framer-motion'
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import jsx from 'react-syntax-highlighter/dist/esm/languages/prism/jsx'
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python'
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

SyntaxHighlighter.registerLanguage('jsx', jsx)
SyntaxHighlighter.registerLanguage('python', python)
SyntaxHighlighter.registerLanguage('json', json)
import {
  Terminal, Shield,
  Zap,
  EyeOff,
  Activity, Clipboard,
  AlertCircle, CheckCircle2, Info,
  Layout, Upload,
  BarChart3, RefreshCcw, Clock3, ListChecks,
  LogOut
} from 'lucide-react'
import { fetchJson, fetchJsonWithMeta } from './lib/api'
import LoginPage from './LoginPage'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
const HISTORY_STORAGE_KEY = 'offline_debugger_history_v1'
const MODE_STORAGE_KEY = 'offline_debugger_mode_v1'

const SEVERITY_CONFIG = {
  CRITICAL: { color: '#f87171', bg: 'rgba(239,68,68,0.12)', icon: <AlertCircle size={16} />, label: 'Critical' },
  WARNING: { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)', icon: <AlertCircle size={16} />, label: 'Warning' },
  INFO: { color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', icon: <Info size={16} />, label: 'Info' },
}

const GRADE_COLORS = { A: '#34d399', B: '#60a5fa', C: '#fbbf24', D: '#fb923c', F: '#f87171' }
const LOADING_MESSAGES = [
  'Initializing Neural Pipeline...',
  'Performing Multi-Agent Consensus...',
  'Analyzing Security Surface...',
  'Synthesizing Optimal Fix...',
]

function formatRelativeAge(epochSeconds) {
  if (!epochSeconds) return 'N/A'
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds))
  if (delta < 60) return `${delta}s ago`
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`
  return `${Math.floor(delta / 86400)}d ago`
}

function DiffLine({ line }) {
  let bg = 'transparent', color = 'var(--text-muted)'
  if (line.startsWith('+') && !line.startsWith('+++')) { bg = 'rgba(16,185,129,0.1)'; color = '#34d399' }
  if (line.startsWith('-') && !line.startsWith('---')) { bg = 'rgba(239,68,68,0.1)'; color = '#f87171' }
  if (line.startsWith('@@')) { bg = 'rgba(96,165,250,0.08)'; color = '#60a5fa' }
  return <div style={{ background: bg, color, fontFamily: 'monospace', fontSize: '0.82rem', padding: '0 0.75rem', lineHeight: '1.7', whiteSpace: 'pre' }}>{line}</div>
}

function StatCard({ label, value, icon, color }) {
  const StatIcon = icon
  return (
    <div className="card glass" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
        <StatIcon size={14} /> {label}
      </div>
      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: color || 'var(--text-main)' }}>{value}</div>
    </div>
  )
}

function WorkspacePanel({
  files,
  onSelectFile,
  selectedPaths,
  onTogglePath,
  onBatchDebug,
  onClearSelection,
  batchLoading,
  workspaceRoot,
  onUpdateRoot,
  onPickProject,
  onUploadProject,
  projectUploadLoading
}) {
  const [newRoot, setNewRoot] = React.useState(workspaceRoot)
  const projectUploadInputRef = React.useRef(null)

  React.useEffect(() => {
    setNewRoot(workspaceRoot)
  }, [workspaceRoot])

  const handleFolderUpload = async (event) => {
    const selectedFiles = Array.from(event.target.files || [])
    if (selectedFiles.length === 0) return
    const uploadedPath = await onUploadProject(selectedFiles)
    if (uploadedPath) {
      setNewRoot(uploadedPath)
    }
    event.target.value = ''
  }

  const handlePickProject = async () => {
    const selectedPath = await onPickProject()
    if (selectedPath === '__upload_fallback__') {
      const input = projectUploadInputRef.current
      if (input) {
        input.setAttribute('webkitdirectory', '')
        input.setAttribute('directory', '')
        input.setAttribute('mozdirectory', '')
        input.click()
      }
      return
    }
    if (selectedPath) {
      setNewRoot(selectedPath)
    }
  }

  return (
    <Motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card">
      <div style={{ marginBottom: '2rem', padding: '1.25rem', background: 'rgba(255,255,255,0.02)', borderRadius: '1rem', border: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Active Workspace Root</div>
          <div>
            <button
              className="btn btn-secondary btn-sm"
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.7rem' }}
              onClick={handlePickProject}
              disabled={projectUploadLoading}
              type="button"
            >
              <Upload size={14} /> {projectUploadLoading ? 'Working...' : 'Select Folder'}
            </button>
            <input
              ref={projectUploadInputRef}
              type="file"
              hidden
              multiple
              onChange={handleFolderUpload}
            />
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <input
            className="input-field"
            style={{ minHeight: 'unset', padding: '0.6rem 1rem', fontSize: '0.85rem', flex: 1 }}
            value={newRoot}
            onChange={(e) => setNewRoot(e.target.value)}
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
                  <button className="btn btn-secondary btn-sm" onClick={() => onSelectFile(file.path)}>
                    <EyeOff size={14} /> Debug
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Motion.div>
  )
}

function ComplexityPanel({ data }) {
  if (!data || (data.functions === 0 && data.classes === 0)) return null
  const grade = data.grade
  const gradeColor = GRADE_COLORS[grade] || '#a1a1aa'
  return (
    <Motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card glass"
      style={{ marginTop: '1rem' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={14} /> CODE COMPLEXITY
        </span>
        <span style={{ fontWeight: 800, fontSize: '1rem', color: gradeColor }}>Grade {grade}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
        {[
          ['Functions', data.functions],
          ['Classes', data.classes],
          ['Loops', data.loops],
          ['Conditions', data.conditions],
          ['Lines (LOC)', data.loc],
          ['MI Score', data.mi_score || 'N/A']
        ].map(([k, v]) => (
          <div key={k} style={{ display: 'flex', flexDirection: 'column', fontSize: '0.8rem', padding: '0.5rem', background: 'rgba(255,255,255,0.02)', borderRadius: '0.5rem' }}>
            <span style={{ color: 'var(--text-tertiary)', fontSize: '0.7rem' }}>{k}</span>
            <span style={{ fontFamily: 'monospace', color: 'var(--text-primary)', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis' }}>{v}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: '1rem', fontSize: '0.75rem', color: 'var(--text-tertiary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Cyclomatic Intensity</span>
        <span style={{ color: gradeColor, fontWeight: 800 }}>{data.complexity_score}</span>
      </div>
    </Motion.div>
  )
}

const RadarChart = ({ score }) => {
  const radius = 30;
  const cx = 40;
  const cy = 40;
  const points = [];
  for (let i = 0; i < 5; i++) {
    const angle = (i * 72 - 90) * (Math.PI / 180);
    const r = score > i * 2 ? radius : radius * 0.4;
    points.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`);
  }
  return (
    <svg width="80" height="80" viewBox="0 0 80 80" style={{ filter: 'drop-shadow(0 0 8px var(--accent))' }}>
      <polygon points="40,10 68,31 58,64 22,64 12,31" fill="none" stroke="rgba(168, 85, 247, 0.2)" strokeWidth="1" />
      <polygon points={points.join(' ')} fill="rgba(168, 85, 247, 0.3)" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      {[0, 72, 144, 216, 288].map(a => (
        <line key={a} x1={cx} y1={cy} x2={cx + radius * Math.cos((a - 90) * Math.PI / 180)} y2={cy + radius * Math.sin((a - 90) * Math.PI / 180)} stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
      ))}
    </svg>
  );
};

function SecurityPanel({ data }) {
  if (!data) return null;
  const issues = data.issues || [];
  return (
    <Motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card"
      style={{
        borderLeft: '4px solid var(--accent)',
        background: 'linear-gradient(145deg, rgba(168, 85, 247, 0.05), rgba(0, 0, 0, 0.2))',
        padding: '1.5rem',
        marginTop: '1.5rem'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: 'var(--accent)', fontWeight: 800, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '1rem' }}>
            <Shield size={16} color="var(--accent)" /> ELITE SECURITY AUDIT - {data.engine || 'Agentic Core'}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {issues.map((issue, idx) => (
              <div key={idx} style={{ padding: '0.75rem', borderRadius: '0.75rem', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span style={{ fontSize: '0.65rem', fontWeight: 900, padding: '0.15rem 0.5rem', borderRadius: '4px', background: issue.risk === 'CRITICAL' || issue.risk === 'HIGH' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(251, 191, 36, 0.2)', color: issue.risk === 'CRITICAL' || issue.risk === 'HIGH' ? '#f87171' : '#fbbf24' }}>
                    {issue.risk}
                  </span>
                  <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>{issue.type}</span>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.4, marginBottom: '0.5rem' }}>{issue.desc}</div>
                {issue.line && (
                  <div style={{ fontSize: '0.7rem', color: 'var(--accent)', fontWeight: 600 }}>LOC: Line {issue.line}</div>
                )}
              </div>
            ))}
            {issues.length === 0 && (
              <div style={{ color: 'var(--success)', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
                <CheckCircle2 size={16} /> Zero Vulnerabilities Detected by Bandit Engine
              </div>
            )}
          </div>
        </div>
        <div style={{ marginLeft: '1rem', textAlign: 'center' }}>
          <RadarChart score={issues.length > 0 ? (issues.length > 5 ? 10 : 7) : 2} />
          <div style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)', marginTop: '0.5rem', fontWeight: 700 }}>SURFACE AREA</div>
        </div>
      </div>
    </Motion.div>
  );
}
function ViperAnalytics({ result }) {
  if (!result || !result.metrics) return null
  return (
    <Motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="card glass" style={{ border: '1px solid var(--accent)', background: 'rgba(168, 85, 247, 0.03)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', color: 'var(--accent)', fontWeight: 800 }}>
        <Zap size={18} /> VIPER CORE ANALYTICS
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: '1rem' }}>
        <div className="stat-box">
          <label style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>CONSENSUS PATH</label>
          <div style={{ fontSize: '0.75rem', fontWeight: 600 }}>{result.verification?.toUpperCase() || 'STANDARD'}</div>
        </div>
        <div className="stat-box">
          <label style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>AI CONFIDENCE</label>
          <div style={{ fontSize: '1rem', fontWeight: 800, color: result.confidence > 7 ? 'var(--success)' : 'var(--warning)' }}>{result.confidence}/10</div>
        </div>
        <div className="stat-box">
          <label style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>PIPELINE MODE</label>
          <div style={{ fontSize: '0.75rem', fontWeight: 700 }}>
            {result.metrics.fast_mode === 1 ? 'FAST' : 'FULL'}
          </div>
        </div>
      </div>
      <div style={{ marginTop: '1rem', padding: '0.75rem', background: 'rgba(0,0,0,0.2)', borderRadius: '0.5rem', fontSize: '0.75rem' }}>
        <div style={{ color: 'var(--text-tertiary)', marginBottom: '0.5rem' }}>INTERNAL PROCESSING (MS)</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', opacity: 0.8 }}>
          <span>Research Phase</span>
          <span>{((result.metrics.scan_rag || result.metrics.viper_orchestration / 2) * 1000).toFixed(0)}ms</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', opacity: 0.8 }}>
          <span>Synthesis Phase</span>
          <span>{(result.metrics.final_synthesis * 1000).toFixed(0)}ms</span>
        </div>
      </div>
    </Motion.div>
  )
}

function ViperEditor({ original, fixed = '', onEdit }) {
  return (
    <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1px', background: 'var(--border)', borderRadius: '1rem', overflow: 'hidden', border: '1px solid var(--border)' }}>
      <div style={{ background: 'var(--bg-main)', padding: '1rem' }}>
        <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--text-muted)', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <EyeOff size={12} /> ORIGINAL BUFFER
        </div>
        <SyntaxHighlighter language="python" style={vscDarkPlus} showLineNumbers={true} customStyle={{ margin: 0, padding: 0, fontSize: '0.8rem', background: 'transparent', height: '100%', minHeight: '300px' }}>
          {original}
        </SyntaxHighlighter>
      </div>
      <div style={{ background: 'rgba(16,185,129,0.03)', padding: '1rem' }}>
        <div style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--success)', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}><CheckCircle2 size={12} /> VIPER PATCH (EDITABLE)</div>
          {fixed.length > 500 && <span style={{ opacity: 0.5 }}>SYNTHESIZED</span>}
        </div>
        <textarea
          style={{ width: '100%', height: 'calc(100% - 20px)', minHeight: '300px', background: 'transparent', border: 'none', color: '#e4e4e7', fontFamily: 'monospace', fontSize: '0.8rem', resize: 'none', outline: 'none', lineHeight: '1.5' }}
          value={fixed}
          onChange={(e) => onEdit(e.target.value)}
        />
      </div>
    </div>
  )
}

function TerminalPanel({ result, loading }) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Terminal size={20} /> Execution Log
      </h3>
      <div style={{ borderRadius: '0.75rem', border: '1px solid var(--border)', overflow: 'hidden', background: 'rgba(0,0,0,0.3)' }}>
        <SyntaxHighlighter
          language="text"
          style={vscDarkPlus}
          showLineNumbers={true}
          customStyle={{ margin: 0, padding: '1rem', fontSize: '0.8rem', background: 'transparent', minHeight: '280px' }}
        >
          {loading
            ? 'Running debug pipeline...'
            : result
              ? JSON.stringify(result, null, 2)
              : 'No session output yet.'}
        </SyntaxHighlighter>
      </div>
    </div>
  )
}

function FixValidationPanel({ validation, loading }) {
  if (loading) {
    return (
      <div className="fix-validation-panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <RefreshCcw size={14} className="spin" />
          Validating patch quality...
        </div>
      </div>
    )
  }

  if (!validation) return null
  const ok = Boolean(validation.ready_to_apply)
  return (
    <div className={`fix-validation-panel ${ok ? 'ok' : 'warn'}`}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.65rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700 }}>
          <ListChecks size={14} />
          Patch Quality Check
        </div>
        <div className={`validation-chip ${ok ? 'ok' : 'warn'}`}>
          {ok ? 'Ready to apply' : 'Needs review'}
        </div>
      </div>

      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.55rem' }}>
        Quality score: <strong style={{ color: 'var(--text-primary)' }}>{validation.quality_score}/100</strong>
      </div>

      {validation.issues?.length > 0 ? (
        <ul className="validation-issues">
          {validation.issues.map((issue, idx) => (
            <li key={idx}>{issue}</li>
          ))}
        </ul>
      ) : (
        <div style={{ fontSize: '0.78rem', color: 'var(--success)', fontWeight: 600 }}>
          No regression risks detected by static validation.
        </div>
      )}
    </div>
  )
}

function InsightsPanel({ insights, loading, error, onRefresh }) {
  if (loading) {
    return (
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', color: 'var(--text-secondary)' }}>
          <RefreshCcw size={14} className="spin" />
          Building workspace analytics...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <div style={{ color: 'var(--error)', marginBottom: '0.75rem' }}>{error}</div>
        <button className="btn btn-secondary btn-sm" type="button" onClick={() => onRefresh(true)}>
          <RefreshCcw size={14} /> Retry
        </button>
      </div>
    )
  }

  if (!insights) return null
  const grades = insights.grade_distribution || {}
  const generatedAge = formatRelativeAge(insights.generated_at)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div className="card glass">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', fontWeight: 800 }}>
            <BarChart3 size={16} color="var(--accent)" />
            Workspace Intelligence
          </div>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => onRefresh(true)}>
            <RefreshCcw size={14} /> Refresh
          </button>
        </div>

        <div className="insights-kpi-grid">
          <div className="insights-kpi-card">
            <div className="kpi-label">Python Files</div>
            <div className="kpi-value">{insights.total_files}</div>
          </div>
          <div className="insights-kpi-card">
            <div className="kpi-label">Total LOC</div>
            <div className="kpi-value">{insights.total_loc}</div>
          </div>
          <div className="insights-kpi-card">
            <div className="kpi-label">Avg LOC / File</div>
            <div className="kpi-value">{insights.avg_loc_per_file}</div>
          </div>
          <div className="insights-kpi-card">
            <div className="kpi-label">Avg Size</div>
            <div className="kpi-value">{insights.average_size_kb} KB</div>
          </div>
        </div>

        <div style={{ marginTop: '1rem', fontSize: '0.75rem', color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Clock3 size={12} />
          Generated {generatedAge} from {insights.inspected_files} files (sample limit {insights.analysis_sample_limit}).
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: '0.75rem', fontSize: '0.95rem' }}>Complexity Grade Distribution</h3>
        <div className="grade-grid">
          {Object.entries(grades).map(([grade, count]) => (
            <div className="grade-pill" key={grade}>
              <span style={{ color: GRADE_COLORS[grade] || 'var(--text-primary)', fontWeight: 800 }}>{grade}</span>
              <span>{count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
        <div className="card">
          <h3 style={{ marginBottom: '0.8rem', fontSize: '0.95rem' }}>Complexity Hotspots</h3>
          <div className="insights-list">
            {(insights.hotspots || []).map((file, idx) => (
              <div className="insights-row" key={`${file.rel_path}-${idx}`}>
                <div style={{ minWidth: 0 }}>
                  <div className="insights-title">{file.rel_path}</div>
                  <div className="insights-sub">Grade {file.grade} | LOC {file.loc}</div>
                </div>
                <div className="insights-score">{file.complexity_score}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginBottom: '0.8rem', fontSize: '0.95rem' }}>Largest Files</h3>
          <div className="insights-list">
            {(insights.largest_files || []).map((file, idx) => (
              <div className="insights-row" key={`${file.rel_path}-${idx}`}>
                <div style={{ minWidth: 0 }}>
                  <div className="insights-title">{file.rel_path}</div>
                  <div className="insights-sub">{(file.size / 1024).toFixed(1)} KB</div>
                </div>
                <div className="insights-score">{file.loc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricsPanel({ metrics, loading, error, onRefresh }) {
  if (loading) {
    return (
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', color: 'var(--text-secondary)' }}>
          <RefreshCcw size={14} className="spin" />
          Fetching backend metrics...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <div style={{ color: 'var(--error)', marginBottom: '0.75rem' }}>{error}</div>
        <button className="btn btn-secondary btn-sm" type="button" onClick={onRefresh}>
          <RefreshCcw size={14} /> Retry
        </button>
      </div>
    )
  }

  if (!metrics) return null
  return (
    <div style={{ display: 'grid', gap: '1rem' }}>
      <div className="card glass">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
          <div style={{ fontWeight: 800 }}>Backend Observability</div>
          <button className="btn btn-secondary btn-sm" type="button" onClick={onRefresh}>
            <RefreshCcw size={14} /> Refresh
          </button>
        </div>
        <div className="insights-kpi-grid">
          <div className="insights-kpi-card">
            <div className="kpi-label">Uptime</div>
            <div className="kpi-value">{metrics.uptime_seconds}s</div>
          </div>
          <div className="insights-kpi-card">
            <div className="kpi-label">Workers</div>
            <div className="kpi-value">{metrics.thread_pool_workers}</div>
          </div>
          <div className="insights-kpi-card">
            <div className="kpi-label">Pipeline Slots</div>
            <div className="kpi-value">{metrics.available_pipeline_slots}</div>
          </div>
          <div className="insights-kpi-card">
            <div className="kpi-label">Rate Limit</div>
            <div className="kpi-value">{metrics.rate_limiter?.limit_per_minute || 'N/A'}</div>
          </div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
        {[
          ['Debug Cache', metrics.cache?.debug],
          ['Analysis Cache', metrics.cache?.analysis],
          ['Insights Cache', metrics.cache?.workspace_insights]
        ].map(([label, cache]) => (
          <div className="card" key={label}>
            <h3 style={{ fontSize: '0.9rem', marginBottom: '0.75rem' }}>{label}</h3>
            <div style={{ display: 'grid', gap: '0.35rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              <div>Entries: <strong style={{ color: 'var(--text-primary)' }}>{cache?.entries ?? 'N/A'}</strong></div>
              <div>Capacity: <strong style={{ color: 'var(--text-primary)' }}>{cache?.max_entries ?? 'N/A'}</strong></div>
              <div>TTL: <strong style={{ color: 'var(--text-primary)' }}>{cache?.ttl_seconds ?? 'N/A'}s</strong></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function App() {
  const [authUser, setAuthUser] = useState(() => {
    try {
      const token = localStorage.getItem('auth_token')
      const user = localStorage.getItem('auth_user')
      if (token && user) return JSON.parse(user)
      return null
    } catch { return null }
  })

  useEffect(() => {
    const handleExpired = () => setAuthUser(null)
    window.addEventListener('auth_expired', handleExpired)
    return () => window.removeEventListener('auth_expired', handleExpired)
  }, [])

  const handleLogin = (user) => setAuthUser(user)

  const handleLogout = () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    setAuthUser(null)
  }

  if (!authUser) {
    return <LoginPage onLogin={handleLogin} />
  }

  return <MainApp authUser={authUser} onLogout={handleLogout} />
}

function MainApp({ authUser, onLogout }) {

  const [activeTab, setActiveTab] = useState('debug'); // debug, workspace, insights, security, metrics, terminal
  const [mode, setMode] = useState('paste'); // paste, upload
  const [filePath, setFilePath] = useState('test_logic.py')
  const [pasteCode, setPasteCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [result, setResult] = useState(null)
  const [diff, setDiff] = useState(null)
  const [showDiff, setShowDiff] = useState(false)
  const [health, setHealth] = useState({ online: false, model_loaded: false })
  const [apiLatencyMs, setApiLatencyMs] = useState(null)
  const [status, setStatus] = useState('')
  const [history, setHistory] = useState(() => {
    try {
      const raw = localStorage.getItem(HISTORY_STORAGE_KEY)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })
  const [workspaceFiles, setWorkspaceFiles] = useState([])
  const [workspaceCount, setWorkspaceCount] = useState(0)
  const [workspaceQuery, setWorkspaceQuery] = useState('')
  const [selectedWorkspacePaths, setSelectedWorkspacePaths] = useState([])
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchSummary, setBatchSummary] = useState(null)
  const [workspaceRoot, setWorkspaceRoot] = useState('')
  const [projectUploadLoading, setProjectUploadLoading] = useState(false)
  const [debugMode, setDebugMode] = useState(() => {
    try {
      const saved = localStorage.getItem(MODE_STORAGE_KEY)
      return saved === 'fast' ? 'fast' : 'full'
    } catch {
      return 'full'
    }
  })
  const [preflightError, setPreflightError] = useState(null)
  const [fixValidation, setFixValidation] = useState(null)
  const [validatingFix, setValidatingFix] = useState(false)
  const [insights, setInsights] = useState(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError] = useState('')
  const [metrics, setMetrics] = useState(null)
  const [metricsLoading, setMetricsLoading] = useState(false)
  const [metricsError, setMetricsError] = useState('')
  const [showCommandPalette, setShowCommandPalette] = useState(false)
  const [paletteQuery, setPaletteQuery] = useState('')
  const traceRef = useRef(null)
  const modeInitializedRef = useRef(false)
  const requestControllerRef = useRef(null)
  const insightsEtagRef = useRef('')

  useEffect(() => {
    let interval
    if (loading) {
      interval = setInterval(() => setLoadingStep(p => (p + 1) % LOADING_MESSAGES.length), 800)
    } else {
      setLoadingStep(0)
    }
    return () => clearInterval(interval)
  }, [loading])

  useEffect(() => {
    const handleCmdPalette = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setShowCommandPalette(prev => !prev)
        setPaletteQuery('')
      }
      if (e.key === 'Escape') {
        setShowCommandPalette(false)
      }
    }
    window.addEventListener('keydown', handleCmdPalette)
    return () => window.removeEventListener('keydown', handleCmdPalette)
  }, [])

  useEffect(() => {
    if (mode === 'paste' && pasteCode.trim()) {
      const timeout = setTimeout(() => {
        // Simple heuristic for real-time feedback
        const code = pasteCode.trim()
        if (code.includes('def ') && !code.includes(':')) setPreflightError('Missing colon in function definition?')
        else if (code.includes('if ') && !code.includes(':')) setPreflightError('Missing colon in if statement?')
        else if ((code.match(/\(/g) || []).length !== (code.match(/\)/g) || []).length) setPreflightError('Unbalanced parentheses detected.')
        else setPreflightError(null)
      }, 500)
      return () => clearTimeout(timeout)
    } else {
      setPreflightError(null)
    }
  }, [pasteCode, mode])

  useEffect(() => {
    checkHealth();
    fetchWorkspaceRoot();
    fetchWorkspace('');
    fetchInsights()
    fetchMetrics()
    const int = setInterval(checkHealth, 5000);
    return () => clearInterval(int)
  }, [])

  useEffect(() => {
    return () => {
      if (requestControllerRef.current) {
        requestControllerRef.current.abort()
      }
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(MODE_STORAGE_KEY, debugMode)
    } catch {
      // no-op for restricted browser contexts
    }
  }, [debugMode])

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history.slice(0, 10)))
    } catch {
      // no-op for restricted browser contexts
    }
  }, [history])

  useEffect(() => {
    const timeout = setTimeout(() => {
      fetchWorkspace(workspaceQuery)
    }, 250)
    return () => clearTimeout(timeout)
  }, [workspaceQuery])

  useEffect(() => {
    setSelectedWorkspacePaths(prev => prev.filter(path => workspaceFiles.some(file => file.path === path)))
  }, [workspaceFiles])

  const checkHealth = async () => {
    try {
      const { payload: data, durationMs } = await fetchJsonWithMeta(`${API}/health`)
      setHealth({ ...data, online: data.status === 'online' })
      setApiLatencyMs(durationMs)
      if (!modeInitializedRef.current) {
        const hasSavedMode = (() => {
          try {
            return Boolean(localStorage.getItem(MODE_STORAGE_KEY))
          } catch {
            return false
          }
        })()
        if (!hasSavedMode) {
          setDebugMode(data.fast_mode_default ? 'fast' : 'full')
        }
        modeInitializedRef.current = true
      }
    } catch {
      setHealth({ online: false, model_loaded: false })
      setApiLatencyMs(null)
    }
  }

  const fetchWorkspace = async (queryValue = '') => {
    try {
      const params = new URLSearchParams({
        query: queryValue,
        limit: '800',
        offset: '0'
      })
      const data = await fetchJson(`${API}/scan_project?${params.toString()}`)
      setWorkspaceFiles(data.files || [])
      setWorkspaceCount(data.count || 0)
    } catch (e) {
      console.error("Workspace scan failed", e)
    }
  }

  const fetchWorkspaceRoot = async () => {
    try {
      const data = await fetchJson(`${API}/workspace/root`)
      setWorkspaceRoot(data.path || '')
    } catch (e) {
      console.error("Failed to fetch workspace root", e)
    }
  }

  const handleUpdateWorkspaceRoot = async (newPath) => {
    setStatus('Updating workspace root...')
    try {
      const data = await fetchJson(`${API}/workspace/root`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: newPath })
      })
      setWorkspaceRoot(data.path)
      setStatus('Workspace root updated')
      fetchWorkspace()
      fetchInsights(true)
      setTimeout(() => setStatus(''), 3000)
      return data.path || null
    } catch (e) {
      setStatus(`Failed to update workspace root: ${e.message}`)
      return null
    }
  }

  const handleWorkspaceProjectUpload = async (selectedFiles) => {
    if (!selectedFiles || selectedFiles.length === 0) return null
    setProjectUploadLoading(true)
    setStatus('Uploading folder...')
    try {
      const formData = new FormData()
      selectedFiles.forEach((file) => {
        formData.append('files', file)
        formData.append('relative_paths', file.webkitRelativePath || file.name)
      })
      const data = await fetchJson(`${API}/workspace/upload`, {
        method: 'POST',
        body: formData
      })

      const uploadedPath = data.path || ''
      if (uploadedPath) {
        setWorkspaceRoot(uploadedPath)
      }
      setWorkspaceQuery('')
      setSelectedWorkspacePaths([])
      setBatchSummary(null)
      await fetchWorkspace('')
      fetchInsights(true)
      const pythonCount = data.python_files ?? 0
      setStatus(`Folder uploaded. ${pythonCount} Python file${pythonCount === 1 ? '' : 's'} detected.`)
      setTimeout(() => setStatus(''), 3000)
      return uploadedPath || null
    } catch (error) {
      setStatus(`Folder upload failed: ${error.message}`)
      return null
    } finally {
      setProjectUploadLoading(false)
    }
  }

  const handlePickWorkspaceProject = async () => {
    setProjectUploadLoading(true)
    setStatus('Opening folder picker...')
    try {
      const data = await fetchJson(`${API}/workspace/browse`, { method: 'POST' })
      const selectedPath = data.path || ''
      if (!selectedPath) {
        setStatus('')
        return null
      }
      setWorkspaceQuery('')
      setSelectedWorkspacePaths([])
      setBatchSummary(null)
      return await handleUpdateWorkspaceRoot(selectedPath)
    } catch (error) {
      const message = error?.message || ''
      if (
        message.includes('Desktop App mode')
        || message.includes('Could not open native folder picker')
      ) {
        setStatus('Native picker unavailable. Choose a folder to upload...')
        return '__upload_fallback__'
      }
      setStatus(`Folder selection failed: ${error.message}`)
      return null
    } finally {
      setProjectUploadLoading(false)
    }
  }

  const fetchInsights = async (forceRefresh = false) => {
    setInsightsLoading(true)
    setInsightsError('')
    try {
      const endpoint = forceRefresh ? `${API}/workspace_insights?refresh=${Date.now()}` : `${API}/workspace_insights`
      const headers = {}
      if (!forceRefresh && insightsEtagRef.current) {
        headers['If-None-Match'] = insightsEtagRef.current
      }
      const response = await fetch(endpoint, { headers })
      if (response.status === 304) {
        return
      }

      let data = {}
      try {
        data = await response.json()
      } catch {
        data = {}
      }

      if (!response.ok) {
        const message = data?.detail || `Request failed (${response.status})`
        throw new Error(message)
      }

      const etag = response.headers.get('etag')
      if (etag) {
        insightsEtagRef.current = etag
      }
      setInsights(data)
    } catch (error) {
      setInsightsError(`Insights unavailable: ${error.message}`)
    } finally {
      setInsightsLoading(false)
    }
  }

  const fetchMetrics = async () => {
    setMetricsLoading(true)
    setMetricsError('')
    try {
      const data = await fetchJson(`${API}/metrics`)
      setMetrics(data)
    } catch (error) {
      setMetricsError(`Metrics unavailable: ${error.message}`)
    } finally {
      setMetricsLoading(false)
    }
  }

  const runDebug = useCallback(async (fp, showLoader = true) => {
    if (showLoader) {
      setLoading(true)
      setResult(null)
      setDiff(null)
      setShowDiff(false)
      setFixValidation(null)
    }
    setStatus(`Monitoring (${debugMode.toUpperCase()})...`)
    if (requestControllerRef.current) {
      requestControllerRef.current.abort()
    }
    const controller = new AbortController()
    requestControllerRef.current = controller
    try {
      let data
      if (mode === 'paste') {
        data = await fetchJson(`${API}/debug_snippet`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: pasteCode, mode: debugMode }),
          signal: controller.signal
        })
      } else {
        data = await fetchJson(`${API}/debug`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_path: fp || filePath, mode: debugMode }),
          signal: controller.signal
        })
      }
      const isCached = data.metrics?.cache_status === 1.0
      const resolvedPath = data.source_path || fp || filePath
      setFilePath(resolvedPath)

      if (data.success) {
        setStatus(isCached ? 'Cached: no errors' : 'System stable')
        setHistory(prev => [{
          file: mode === 'paste' ? (pasteCode.split('\n')[0].slice(0, 30).trim() || 'Code Fragment') : (fp || filePath),
          status: 'clean',
          time: data.total_time || 0,
          id: Date.now(),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          full_content: mode === 'paste' ? pasteCode : null,
          id_path: resolvedPath
        }, ...prev].slice(0, 10))
      } else {
        setStatus(isCached ? 'Cached: anomaly detected' : 'Anomaly detected')
        setHistory(prev => [{
          file: mode === 'paste' ? (pasteCode.split('\n')[0].slice(0, 30).trim() || 'Code Fragment') : (fp || filePath),
          status: 'fixed',
          time: data.total_time || 0,
          severity: data.severity,
          id: Date.now(),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          full_content: mode === 'paste' ? pasteCode : null,
          id_path: resolvedPath
        }, ...prev].slice(0, 10))
      }
      setResult(data)
      if (data.pipeline_mode) {
        setDebugMode(data.pipeline_mode)
      }
      if (activeTab !== 'debug' && activeTab !== 'terminal') setActiveTab('debug')
    } catch (error) {
      if (error?.name === 'AbortError') {
        return
      }
      setStatus(`Link error: ${error.message}`)
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null
      }
      if (showLoader) setLoading(false)
    }
  }, [activeTab, debugMode, filePath, mode, pasteCode])

  useEffect(() => {
    if (activeTab === 'insights' && !insights && !insightsLoading) {
      fetchInsights()
    }
    if (activeTab === 'metrics' && !metrics && !metricsLoading) {
      fetchMetrics()
    }
  }, [activeTab, insights, insightsLoading, metrics, metricsLoading])

  useEffect(() => {
    const onKeyDown = (event) => {
      if (!(event.ctrlKey || event.metaKey) || event.key !== 'Enter' || loading || activeTab !== 'debug') {
        return
      }
      event.preventDefault()
      if (mode === 'paste' && pasteCode.trim()) {
        runDebug(null)
      } else if (mode === 'upload' && filePath.trim()) {
        runDebug(filePath)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeTab, loading, mode, pasteCode, filePath, debugMode, runDebug])

  const toggleWorkspaceSelection = (path) => {
    setSelectedWorkspacePaths(prev => (
      prev.includes(path)
        ? prev.filter(item => item !== path)
        : [...prev, path]
    ))
  }

  const clearWorkspaceSelection = () => {
    setSelectedWorkspacePaths([])
  }

  const handleBatchApplyFixes = async () => {
    if (!batchSummary || !batchSummary.items) return;
    setStatus('Applying batch auto-fixes...');
    let appliedCount = 0;
    for (const item of batchSummary.items) {
      if (item.ok && item.result?.fixed_code && item.result?.success === false) {
        try {
          await fetchJson(`${API}/apply_fix`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: item.file_path, fixed_code: item.result.fixed_code })
          });
          appliedCount++;
        } catch (error) {
          console.error(`Failed to apply to ${item.file_path}:`, error);
        }
      }
    }
    setStatus(`Batch auto-fix applied to ${appliedCount} files.`);
    fetchWorkspace();
    setBatchSummary(null);
    clearWorkspaceSelection();
  };

  const handleBatchDebug = async () => {
    if (selectedWorkspacePaths.length === 0) return
    setBatchLoading(true)
    setBatchSummary(null)
    setStatus(`Batch debugging ${selectedWorkspacePaths.length} files...`)
    try {
      const payload = await fetchJson(`${API}/debug_batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_paths: selectedWorkspacePaths,
          mode: debugMode,
          max_concurrency: Math.min(4, selectedWorkspacePaths.length)
        })
      })

      setBatchSummary(payload)
      setStatus(`Batch complete: ${payload.succeeded} succeeded, ${payload.failed} failed`)

      const firstAnomaly = (payload.items || []).find(item => item.ok && item.result && item.result.success === false)
      if (firstAnomaly?.result) {
        setResult(firstAnomaly.result)
        setFilePath(firstAnomaly.result.source_path || firstAnomaly.file_path)
        setActiveTab('debug')
      }
    } catch (error) {
      setStatus(`Batch debug failed: ${error.message}`)
    } finally {
      setBatchLoading(false)
    }
  }

  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setLoading(true)
    setResult(null)
    setDiff(null)
    setShowDiff(false)
    setFixValidation(null)
    setStatus('Uploading...')

    const formData = new FormData()
    formData.append('file', file)

    if (requestControllerRef.current) {
      requestControllerRef.current.abort()
    }
    const controller = new AbortController()
    requestControllerRef.current = controller

    try {
      const data = await fetchJson(`${API}/upload?mode=${debugMode}`, {
        method: 'POST',
        body: formData,
        signal: controller.signal
      })
      setResult(data)
      setFilePath(data.source_path || file.name)
      setStatus(data.success ? 'Upload verified' : 'Anomalies found')
      fetchWorkspace()
      fetchInsights(true)
      setActiveTab('debug')
      if (data.pipeline_mode) {
        setDebugMode(data.pipeline_mode)
      }
    } catch (error) {
      if (error?.name === 'AbortError') {
        return
      }
      setStatus(`Upload failed: ${error.message}`)
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null
      }
      setLoading(false)
    }
  }

  const handleValidatePatch = async () => {
    if (!result?.fixed_code) return
    const originalText = result?.source_code || pasteCode || ''
    if (!originalText.trim()) {
      setStatus('Source context missing for patch validation')
      return
    }

    setValidatingFix(true)
    setStatus('Validating patch quality...')
    try {
      const payload = await fetchJson(`${API}/validate_fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          original: originalText,
          fixed: result.fixed_code,
          include_security: debugMode === 'full'
        })
      })
      setFixValidation(payload)
      setStatus(payload.ready_to_apply ? 'Patch validation passed' : 'Patch requires review')
    } catch (error) {
      setStatus(`Validation failed: ${error.message}`)
    } finally {
      setValidatingFix(false)
    }
  }

  const handleApplyFix = async () => {
    if (!result?.fixed_code) return
    if (fixValidation && !fixValidation.ready_to_apply) {
      setStatus('Patch validation flagged risks. Resolve before commit.')
      return
    }
    setStatus('Applying fix...')
    try {
      const targetPath = result?.source_path || filePath
      const payload = await fetchJson(`${API}/apply_fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: targetPath, fixed_code: result.fixed_code })
      })
      setStatus(payload?.message || 'Repair complete')
      fetchWorkspace()
      fetchInsights(true)
      setTimeout(() => setStatus(''), 3000)
    } catch (error) {
      setStatus(`Repair failed: ${error.message}`)
    }
  }

  const handleCopy = async () => {
    if (!result?.fixed_code) return
    try {
      await navigator.clipboard.writeText(result.fixed_code)
      setStatus('Copied')
      setTimeout(() => setStatus(''), 2000)
    } catch {
      setStatus('Clipboard unavailable')
    }
  }

  const handleShowDiff = async () => {
    if (!result?.fixed_code) return
    if (showDiff) {
      setShowDiff(false)
      return
    }

    try {
      const originalText = result?.source_code || pasteCode || ''
      const data = await fetchJson(`${API}/diff`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original: originalText, fixed: result.fixed_code })
      })
      setDiff(data.diff || '')
      setShowDiff(true)
    } catch (error) {
      setStatus(`Diff failed: ${error.message}`)
    }
  }

  const severityInfo = result?.severity ? SEVERITY_CONFIG[result.severity] : null
  const successStatus = /stable|verified|copied|complete|cached: no errors|passed|ready/i.test(status)
  const filteredWorkspaceFiles = useMemo(() => {
    const query = workspaceQuery.trim().toLowerCase()
    if (!query) return workspaceFiles
    return workspaceFiles.filter(file => (
      file.name.toLowerCase().includes(query) || file.rel_path.toLowerCase().includes(query)
    ))
  }, [workspaceFiles, workspaceQuery])

  const filteredPaletteFiles = useMemo(() => {
    const query = paletteQuery.trim().toLowerCase()
    if (!query) return []
    return workspaceFiles.filter(file => (
      file.name.toLowerCase().includes(query) || file.rel_path.toLowerCase().includes(query)
    )).slice(0, 10)
  }, [workspaceFiles, paletteQuery])

  return (
    <div className="app-layout">
      {/* Command Palette Overlay */}
      <AnimatePresence>
        {showCommandPalette && (
          <Motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              inset: 0,
              backgroundColor: 'rgba(0,0,0,0.6)',
              backdropFilter: 'blur(8px)',
              zIndex: 9999,
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'center',
              paddingTop: '15vh'
            }}
            onClick={() => setShowCommandPalette(false)}
          >
            <Motion.div
              initial={{ opacity: 0, scale: 0.95, y: -20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -20 }}
              className="card glass"
              style={{ width: '90%', maxWidth: '600px', padding: '1.5rem' }}
              onClick={e => e.stopPropagation()}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                <Zap size={20} color="var(--accent)" />
                <h3 style={{ margin: 0 }}>Command Palette</h3>
              </div>
              <input
                autoFocus
                className="input-field"
                placeholder="Search workspace files or commands..."
                value={paletteQuery}
                onChange={e => setPaletteQuery(e.target.value)}
                style={{ padding: '1rem', fontSize: '1.1rem' }}
              />
              {paletteQuery && (
                <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {filteredPaletteFiles.map(file => (
                    <div
                      key={file.path}
                      className="btn btn-secondary"
                      style={{ justifyContent: 'flex-start', padding: '0.75rem 1rem' }}
                      onClick={() => {
                        setFilePath(file.path);
                        setMode('upload');
                        setActiveTab('debug');
                        runDebug(file.path);
                        setShowCommandPalette(false);
                      }}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                        <span style={{ fontWeight: 600 }}>{file.name}</span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>{file.rel_path}</span>
                      </div>
                    </div>
                  ))}
                  {filteredPaletteFiles.length === 0 && (
                    <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-tertiary)' }}>
                      No files found.
                    </div>
                  )}
                </div>
              )}
            </Motion.div>
          </Motion.div>
        )}
      </AnimatePresence>
      {/* Sidebar */}
      <aside className="sidebar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '3.5rem' }}>
          <div style={{
            background: 'var(--elite-gradient)',
            borderRadius: '1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '44px',
            height: '44px',
            boxShadow: '0 8px 24px -6px rgba(168, 85, 247, 0.5)'
          }}>
            <Zap size={24} color="white" fill="white" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontWeight: 800, fontSize: '1.2rem', letterSpacing: '-0.02em', lineHeight: 1 }}>OFFLINE</span>
            <span style={{ fontWeight: 800, fontSize: '1.2rem', letterSpacing: '-0.02em', color: 'var(--accent)', lineHeight: 1 }}>AI DEBUGGER</span>
          </div>
        </div>

        <nav style={{ flex: 1 }}>
          <div style={{ color: 'var(--text-tertiary)', fontSize: '0.7rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: '1.5rem' }}>Session History</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {history.map((item) => (
              <Motion.div
                layout
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                key={item.id}
                className="btn btn-secondary"
                style={{ justifyContent: 'flex-start', fontSize: '0.8rem', padding: '0.75rem 1rem', width: '100%', border: '1px solid transparent' }}
                onClick={() => {
                  if (item.file !== '<snippet>') {
                    setFilePath(item.id_path || item.file);
                    setMode(item.file.startsWith('/') || item.file.includes('.') ? 'upload' : 'paste');
                    if (item.file.startsWith('/') || item.file.includes('.')) {
                      runDebug(item.id_path || item.file);
                    } else {
                      setPasteCode(item.full_content || '');
                      runDebug(null);
                    }
                  }
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem', overflow: 'hidden' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {item.status === 'clean' ? <CheckCircle2 size={12} color="var(--success)" /> : <AlertCircle size={12} color="var(--error)" />}
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600 }}>{item.file}</span>
                  </div>
                  <span style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)', opacity: 0.7 }}>{item.timestamp}</span>
                </div>
              </Motion.div>
            ))}
            {history.length === 0 && <div size={12} />}
          </div>
        </nav>

        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="card glass" style={{ padding: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.75rem', color: health.online ? 'var(--success)' : 'var(--error)', fontWeight: 800 }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%',
                background: health.online ? 'var(--success)' : 'var(--error)',
                boxShadow: `0 0 12px ${health.online ? 'var(--success)' : 'var(--error)'}`,
                animation: health.online ? 'pulse 2s infinite' : 'none'
              }} />
              {health.online ? 'Backend Online' : 'Backend Offline'}
            </div>
            <div style={{ marginTop: '0.55rem', fontSize: '0.72rem', color: 'var(--text-tertiary)', display: 'flex', justifyContent: 'space-between' }}>
              <span>Model</span>
              <span style={{ color: health.model_loaded ? 'var(--success)' : 'var(--warning)' }}>
                {health.model_loaded ? 'Loaded' : 'Disabled'}
              </span>
            </div>
            <div style={{ marginTop: '0.25rem', fontSize: '0.72rem', color: 'var(--text-tertiary)', display: 'flex', justifyContent: 'space-between' }}>
              <span>API Latency</span>
              <span>{apiLatencyMs == null ? 'N/A' : `${apiLatencyMs} ms`}</span>
            </div>
          </div>
          <button
            className="btn btn-secondary"
            style={{ fontSize: '0.78rem', gap: '0.5rem', padding: '0.6rem 1rem', width: '100%', justifyContent: 'center', marginTop: '0.75rem' }}
            onClick={onLogout}
          >
            <LogOut size={14} /> Sign Out
          </button>
        </div>
      </aside >

      {/* Main Content */}
      < main className="main-content" >
        <div className="main-scroll-area">
          <header>
            <Motion.h1 initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} style={{ fontSize: '2rem' }}>Offline AI-Powered Code Debugger - V2</Motion.h1>
            <Motion.p initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
              using RAG and Multi-Agent Architecture for automation, validation, and security insights.
            </Motion.p>
          </header>

          <div className="tabs-container">
            <button className={`tab-btn ${activeTab === 'debug' ? 'active' : ''}`} onClick={() => setActiveTab('debug')}>Debug</button>
            <button className={`tab-btn ${activeTab === 'workspace' ? 'active' : ''}`} onClick={() => setActiveTab('workspace')}>Workspace</button>
            <button className={`tab-btn ${activeTab === 'insights' ? 'active' : ''}`} onClick={() => setActiveTab('insights')}>Insights</button>
            <button className={`tab-btn ${activeTab === 'security' ? 'active' : ''}`} onClick={() => setActiveTab('security')}>Security</button>
            <button className={`tab-btn ${activeTab === 'metrics' ? 'active' : ''}`} onClick={() => setActiveTab('metrics')}>Metrics</button>
            <button className={`tab-btn ${activeTab === 'terminal' ? 'active' : ''}`} onClick={() => setActiveTab('terminal')}>Execution Log</button>
          </div>

          <div className="grid" style={{ gridTemplateColumns: '1fr 320px', alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              <AnimatePresence mode="wait">
                {activeTab === 'debug' && (
                  <Motion.div key="debug-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <div className="card">
                      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
                        <button className={`btn ${mode === 'paste' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('paste')}>
                          <Clipboard size={18} /> Paste Fragment
                        </button>
                        <button className={`btn ${mode === 'upload' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('upload')}>
                          <Upload size={18} /> Load File
                        </button>
                      </div>

                      <div className="mode-toolbar">
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
                          Pipeline Mode
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className={`mode-chip ${debugMode === 'fast' ? 'active' : ''}`} onClick={() => setDebugMode('fast')} type="button">
                            Fast
                          </button>
                          <button className={`mode-chip ${debugMode === 'full' ? 'active' : ''}`} onClick={() => setDebugMode('full')} type="button">
                            Full
                          </button>
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                          {debugMode === 'fast'
                            ? 'Fast mode prioritizes latency by skipping deep orchestration and heavy security scan.'
                            : 'Full mode runs full orchestration and complete security audit.'}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>
                          Shortcut: Ctrl/Cmd + Enter to run debug.
                        </div>
                      </div>

                      {mode === 'paste' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                          <textarea
                            className="input-field"
                            value={pasteCode}
                            onChange={e => setPasteCode(e.target.value)}
                            placeholder="# Enter buggy Python logic..."
                            style={{ minHeight: '280px', border: preflightError ? '1px solid var(--error)' : '1px solid var(--border)' }}
                          />
                          {preflightError && (
                            <Motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} style={{ color: 'var(--error)', fontSize: '0.75rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                              <AlertCircle size={14} /> {preflightError}
                            </Motion.div>
                          )}
                          <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => runDebug(null)} disabled={loading || !pasteCode.trim()}>
                            {loading ? <div className="loader" /> : <Zap size={20} />}
                            {loading ? LOADING_MESSAGES[loadingStep] : 'Run Debug Pipeline'}
                          </button>
                        </div>
                      ) : (
                        <div
                          style={{
                            border: '2px dashed var(--border)',
                            borderRadius: '1.5rem',
                            padding: '4rem 2rem',
                            textAlign: 'center',
                            background: 'rgba(255,255,255,0.01)',
                            transition: 'all 0.3s'
                          }}
                          onDragOver={(e) => { e.preventDefault(); e.target.style.borderColor = 'var(--accent)' }}
                          onDragLeave={(e) => { e.preventDefault(); e.target.style.borderColor = 'var(--border)' }}
                          onDrop={(e) => {
                            e.preventDefault()
                            const file = e.dataTransfer.files[0]
                            if (file) handleUpload({ target: { files: [file] } })
                          }}
                        >
                          <Upload size={48} color="var(--text-tertiary)" style={{ marginBottom: '1.5rem' }} />
                          <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>Drop Python target into Quantum Field or</p>
                          <label className="btn btn-secondary" style={{ display: 'inline-flex' }}>
                            Initialize Uplink
                            <input type="file" hidden onChange={handleUpload} accept=".py" />
                          </label>
                        </div>
                      )}

                      {status && (
                        <Motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="status-indicator"
                          style={{
                            marginTop: '1.5rem',
                            color: successStatus ? 'var(--success)' : 'var(--error)',
                            cursor: result && !result.success ? 'pointer' : 'default',
                            padding: '0.75rem',
                            borderRadius: '0.75rem',
                            background: result && !result.success ? 'rgba(239, 68, 68, 0.05)' : 'transparent'
                          }}
                          onClick={() => {
                            if (result && !result.success) {
                              traceRef.current?.scrollIntoView({ behavior: 'smooth' })
                            }
                          }}
                        >
                          {successStatus ? <CheckCircle2 size={14} /> : <Info size={14} />}
                          {status}
                          {result && !result.success && <span style={{ fontSize: '0.7rem', opacity: 0.6, marginLeft: '0.5rem' }}>(CLICK TO JUMP)</span>}
                        </Motion.div>
                      )}
                    </div>

                    {result && !result.success && (
                      <div style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                        <div className="card" ref={traceRef}>
                          <h3 style={{ color: 'var(--error)', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '1.2rem', marginBottom: '1.5rem' }}>
                            <Terminal size={20} /> Traceback Intercepted
                          </h3>
                          {severityInfo && (
                            <div style={{ marginBottom: '1rem', display: 'inline-flex', alignItems: 'center', gap: '0.45rem', padding: '0.35rem 0.65rem', borderRadius: '999px', background: severityInfo.bg, color: severityInfo.color, fontSize: '0.72rem', fontWeight: 700 }}>
                              {severityInfo.icon} {severityInfo.label}
                            </div>
                          )}
                          <div style={{ borderRadius: '1rem', overflow: 'hidden', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border)' }}>
                            <SyntaxHighlighter language="text" style={vscDarkPlus} showLineNumbers={true} customStyle={{ margin: 0, padding: '1.5rem', fontSize: '0.85rem', background: 'transparent' }}>
                              {result.error}
                            </SyntaxHighlighter>
                          </div>
                          {result.analysis && (
                            <div style={{ marginTop: '2rem' }}>
                              <h4 style={{ marginBottom: '1rem', fontSize: '0.75rem', color: 'var(--accent)', fontWeight: 800, textTransform: 'uppercase' }}>VIPER AGENT ADVISORY</h4>
                              <div style={{ padding: '1.25rem', background: 'rgba(168, 85, 247, 0.05)', borderRadius: '1rem', border: '1px solid rgba(168, 85, 247, 0.1)', lineHeight: 1.8, fontSize: '0.9rem' }}>
                                {result.analysis}
                              </div>
                            </div>
                          )}
                        </div>

                        <div className="card" style={{ borderTop: '4px solid var(--success)', padding: '0' }}>
                          <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <h3 style={{ color: 'var(--success)', fontSize: '1.2rem', marginBottom: '0.2rem' }}>Patch Workspace</h3>
                              <p style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>Review, validate, and apply generated patch changes</p>
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem' }}>
                              <button className="btn btn-secondary btn-sm" onClick={handleShowDiff} disabled={!result?.fixed_code}>
                                <Info size={14} /> {showDiff ? 'Hide Diff' : 'Show Diff'}
                              </button>
                              <button className="btn btn-secondary btn-sm" onClick={handleCopy} disabled={!result?.fixed_code}>
                                <Clipboard size={14} /> Copy
                              </button>
                              <button className="btn btn-secondary btn-sm" onClick={handleValidatePatch} disabled={!result?.fixed_code || validatingFix}>
                                <ListChecks size={14} /> {validatingFix ? 'Validating...' : 'Validate Patch'}
                              </button>
                              <button
                                className="btn btn-primary btn-sm"
                                onClick={handleApplyFix}
                                disabled={!result?.fixed_code || validatingFix || (fixValidation && !fixValidation.ready_to_apply)}
                              >
                                <Zap size={14} /> Commit Patch
                              </button>
                            </div>
                          </div>

                          <ViperEditor
                            original={result.source_code || pasteCode || result.error || 'No context'}
                            fixed={result.fixed_code}
                            onEdit={(val) => {
                              setResult({ ...result, fixed_code: val })
                              setFixValidation(null)
                            }}
                          />

                          {(fixValidation || validatingFix) && (
                            <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid var(--border)' }}>
                              <FixValidationPanel validation={fixValidation} loading={validatingFix} />
                            </div>
                          )}

                          {showDiff && (
                            <div style={{ padding: '1.25rem', borderTop: '1px solid var(--border)' }}>
                              <h4 style={{ marginBottom: '0.75rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                Unified Diff
                              </h4>
                              <div style={{ border: '1px solid var(--border)', borderRadius: '0.75rem', overflow: 'hidden', maxHeight: '320px', overflowY: 'auto' }}>
                                {(diff || '').split('\n').map((line, idx) => (
                                  <DiffLine line={line} key={idx} />
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </Motion.div>
                )}

                {activeTab === 'workspace' && (
                  <Motion.div key="workspace-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <div className="card glass" style={{ marginBottom: '1rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                      <input
                        className="input-field"
                        style={{ minHeight: 'unset', padding: '0.75rem 1rem' }}
                        value={workspaceQuery}
                        onChange={(e) => setWorkspaceQuery(e.target.value)}
                        placeholder="Filter files by name or path..."
                      />
                      <div style={{ minWidth: '120px', fontSize: '0.78rem', color: 'var(--text-secondary)', textAlign: 'right' }}>
                        {filteredWorkspaceFiles.length} / {workspaceCount}
                      </div>
                    </div>
                    {batchSummary && (
                      <div className="card" style={{ marginBottom: '1rem', borderLeft: '3px solid var(--accent-secondary)' }}>
                        <div style={{ fontSize: '0.82rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span>Batch run complete</span>
                          <span style={{ color: 'var(--text-secondary)' }}>{batchSummary.duration_seconds}s</span>
                        </div>
                        <div style={{ marginTop: '0.55rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                          Requested: {batchSummary.requested} | Success: {batchSummary.succeeded} | Failed: {batchSummary.failed}
                        </div>
                        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                          <button className="btn btn-primary btn-sm" onClick={handleBatchApplyFixes}>
                            <Zap size={14} /> Auto-Apply Fixes
                          </button>
                        </div>
                      </div>
                    )}
                    <WorkspacePanel
                      files={filteredWorkspaceFiles}
                      selectedPaths={selectedWorkspacePaths}
                      onTogglePath={toggleWorkspaceSelection}
                      onBatchDebug={handleBatchDebug}
                      onClearSelection={clearWorkspaceSelection}
                      batchLoading={batchLoading}
                      onSelectFile={(path) => { setFilePath(path); setMode('upload'); runDebug(path); }}
                      workspaceRoot={workspaceRoot}
                      onUpdateRoot={handleUpdateWorkspaceRoot}
                      onPickProject={handlePickWorkspaceProject}
                      onUploadProject={handleWorkspaceProjectUpload}
                      projectUploadLoading={projectUploadLoading}
                    />
                  </Motion.div>
                )}

                {activeTab === 'insights' && (
                  <Motion.div key="insights-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <InsightsPanel
                      insights={insights}
                      loading={insightsLoading}
                      error={insightsError}
                      onRefresh={fetchInsights}
                    />
                  </Motion.div>
                )}

                {activeTab === 'security' && (
                  <Motion.div key="security-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <div className="card">
                      <h3>Security Audit</h3>
                      <p style={{ color: 'var(--text-tertiary)', marginBottom: '2rem' }}>Static security findings from heuristics and Bandit (when available).</p>
                      {result ? (
                        <SecurityPanel data={result.security_audit} />
                      ) : (
                        <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-tertiary)' }}>
                          <Shield size={48} style={{ opacity: 0.2, marginBottom: '1rem' }} />
                          <p>Initialize a debug session to view security audit data.</p>
                        </div>
                      )}
                    </div>
                  </Motion.div>
                )}

                {activeTab === 'metrics' && (
                  <Motion.div key="metrics-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <MetricsPanel
                      metrics={metrics}
                      loading={metricsLoading}
                      error={metricsError}
                      onRefresh={fetchMetrics}
                    />
                  </Motion.div>
                )}

                {activeTab === 'terminal' && (
                  <Motion.div key="terminal-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <TerminalPanel result={result} loading={loading} />
                  </Motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Right Sidebar stats */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', position: 'sticky', top: '0' }}>
              <div className="card glass" style={{ padding: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
                  <Zap size={18} color="var(--accent)" />
                  <span style={{ fontWeight: 800, fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Kernel Metrics</span>
                </div>
                <StatCard label="Pipeline State" value={health.model_loaded ? 'Optimal' : 'Cold Start'} icon={Shield} color={health.model_loaded ? 'var(--success)' : 'var(--warning)'} />
                <StatCard label="Active Mode" value={debugMode === 'fast' ? 'Fast' : 'Full'} icon={Zap} color={debugMode === 'fast' ? 'var(--warning)' : 'var(--accent)'} />
                {insights && <StatCard label="Workspace Files" value={insights.total_files} icon={Layout} color="var(--accent-secondary)" />}
                {result && result.total_time && <StatCard label="Latent Response" value={`${result.total_time}s`} icon={Activity} color="var(--accent)" />}
              </div>
              <ComplexityPanel data={result?.complexity} />
              <ViperAnalytics result={result} />
            </div>
          </div>
        </div>
      </main >
    </div >
  )
}

export default App
