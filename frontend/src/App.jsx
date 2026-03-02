import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  Terminal, Shield,
  Lock,
  Zap,
  EyeOff,
  History, Settings, Activity, Clipboard, Share2,
  AlertCircle, CheckCircle2, Info, ChevronRight,
  Database, Layout, Moon, Sun, Upload
} from 'lucide-react'

const API = 'http://localhost:8000'

const SEVERITY_CONFIG = {
  CRITICAL: { color: '#f87171', bg: 'rgba(239,68,68,0.12)', icon: <AlertCircle size={16} />, label: 'Critical' },
  WARNING: { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)', icon: <AlertCircle size={16} />, label: 'Warning' },
  INFO: { color: '#60a5fa', bg: 'rgba(96,165,250,0.12)', icon: <Info size={16} />, label: 'Info' },
}

const GRADE_COLORS = { A: '#34d399', B: '#60a5fa', C: '#fbbf24', D: '#fb923c', F: '#f87171' }

function DiffLine({ line }) {
  let bg = 'transparent', color = 'var(--text-muted)'
  if (line.startsWith('+') && !line.startsWith('+++')) { bg = 'rgba(16,185,129,0.1)'; color = '#34d399' }
  if (line.startsWith('-') && !line.startsWith('---')) { bg = 'rgba(239,68,68,0.1)'; color = '#f87171' }
  if (line.startsWith('@@')) { bg = 'rgba(96,165,250,0.08)'; color = '#60a5fa' }
  return <div style={{ background: bg, color, fontFamily: 'monospace', fontSize: '0.82rem', padding: '0 0.75rem', lineHeight: '1.7', whiteSpace: 'pre' }}>{line}</div>
}

function StatCard({ label, value, icon: Icon, color }) {
  return (
    <div className="card glass" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
        <Icon size={14} /> {label}
      </div>
      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: color || 'var(--text-main)' }}>{value}</div>
    </div>
  )
}

function WorkspacePanel({ files, onSelectFile }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <Layout size={20} color="var(--accent)" />
        <h3 style={{ fontSize: '1.25rem' }}>Workspace Explorer</h3>
      </div>
      <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
        <table className="elite-table">
          <thead>
            <tr>
              <th>File Name</th>
              <th>Path</th>
              <th>Size</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {files.map((file, idx) => (
              <tr key={idx}>
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
    </motion.div>
  )
}

function ComplexityPanel({ data }) {
  if (!data || (data.functions === 0 && data.classes === 0)) return null
  const grade = data.grade
  const gradeColor = GRADE_COLORS[grade] || '#a1a1aa'
  return (
    <motion.div
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
    </motion.div>
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
    <motion.div
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
            <Shield size={16} color="var(--accent)" /> ELITE SECURITY AUDIT — {data.engine || 'Agentic Core'}
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
    </motion.div>
  );
}
function ViperAnalytics({ result }) {
  if (!result || !result.metrics) return null
  return (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="card glass" style={{ border: '1px solid var(--accent)', background: 'rgba(168, 85, 247, 0.03)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', color: 'var(--accent)', fontWeight: 800 }}>
        <Zap size={18} /> VIPER CORE ANALYTICS
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        <div className="stat-box">
          <label style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>CONSENSUS PATH</label>
          <div style={{ fontSize: '0.75rem', fontWeight: 600 }}>{result.verification?.toUpperCase() || 'STANDARD'}</div>
        </div>
        <div className="stat-box">
          <label style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>AI CONFIDENCE</label>
          <div style={{ fontSize: '1rem', fontWeight: 800, color: result.confidence > 7 ? 'var(--success)' : 'var(--warning)' }}>{result.confidence}/10</div>
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
    </motion.div>
  )
}

function ViperEditor({ original, fixed, onEdit, onApply }) {
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

function App() {
  const [activeTab, setActiveTab] = useState('debug'); // debug, workspace, vault, terminal
  const [mode, setMode] = useState('paste'); // paste, upload
  const [filePath, setFilePath] = useState('test_logic.py')
  const [pasteCode, setPasteCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [result, setResult] = useState(null)
  const [diff, setDiff] = useState(null)
  const [showDiff, setShowDiff] = useState(false)
  const [health, setHealth] = useState({ online: false, model_loaded: false })
  const [status, setStatus] = useState('')
  const [history, setHistory] = useState([])
  const [workspaceFiles, setWorkspaceFiles] = useState([])
  const [preflightError, setPreflightError] = useState(null)
  const traceRef = useRef(null)

  const loadingMessages = [
    'Initializing Neural Pipeline...',
    'Performing Multi-Agent Consensus...',
    'Analyzing Security Surface...',
    'Synthesizing Optimal Fix...',
  ]

  useEffect(() => {
    let interval
    if (loading) {
      interval = setInterval(() => setLoadingStep(p => (p + 1) % loadingMessages.length), 800)
    } else {
      setLoadingStep(0)
    }
    return () => clearInterval(interval)
  }, [loading])

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
    fetchWorkspace();
    const int = setInterval(checkHealth, 5000);
    return () => clearInterval(int)
  }, [])

  const checkHealth = async () => {
    try {
      const resp = await fetch(`${API}/health`)
      const data = await resp.json()
      setHealth({ ...data, online: data.status === 'online' })
    } catch {
      setHealth({ online: false, model_loaded: false })
    }
  }

  const fetchWorkspace = async () => {
    try {
      const resp = await fetch(`${API}/scan_project`)
      const data = await resp.json()
      setWorkspaceFiles(data.files || [])
    } catch (e) {
      console.error("Workspace scan failed", e)
    }
  }

  const runDebug = async (fp, showLoader = true) => {
    if (showLoader) { setLoading(true); setResult(null); setDiff(null); setShowDiff(false) }
    setStatus('📡 MONITORING...')
    try {
      let resp
      if (mode === 'paste') {
        resp = await fetch(`${API}/debug_snippet`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: pasteCode })
        })
      } else {
        resp = await fetch(`${API}/debug`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_path: fp || filePath })
        })
      }
      const data = await resp.json()
      const isCached = data.metrics?.cache_status === 1.0

      if (data.success) {
        setStatus(isCached ? '⚡ CACHED: NO ERRORS' : '✅ SYSTEM STABLE')
        setHistory(prev => [{
          file: mode === 'paste' ? (pasteCode.split('\n')[0].slice(0, 30).trim() || 'Code Fragment') : (fp || filePath),
          status: 'clean', time: data.total_time || 0, id: Date.now(),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          full_content: mode === 'paste' ? pasteCode : null,
          id_path: fp || filePath
        }, ...prev].slice(0, 10))
      } else {
        setStatus(isCached ? '⚡ CACHED: BUG INTERCEPTED' : '⚠️ ANOMALY DETECTED')
        setHistory(prev => [{
          file: mode === 'paste' ? (pasteCode.split('\n')[0].slice(0, 30).trim() || 'Code Fragment') : (fp || filePath),
          status: 'fixed', time: data.total_time || 0, severity: data.severity, id: Date.now(),
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          full_content: mode === 'paste' ? pasteCode : null,
          id_path: fp || filePath
        }, ...prev].slice(0, 10))
      }
      setResult(data)
      if (data.fixed_code) setShowDiff(true) // Auto-show diff for elite feedback
      if (activeTab !== 'debug' && activeTab !== 'terminal') setActiveTab('debug')
    } catch {
      setStatus('❌ LINK SEVERED')
    } finally {
      if (showLoader) setLoading(false)
    }
  }

  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setLoading(true)
    setResult(null)
    setStatus('📤 UPLOADING...')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const resp = await fetch(`${API}/upload`, {
        method: 'POST',
        body: formData
      })
      const data = await resp.json()
      setResult(data)
      setFilePath(file.name)
      setStatus(data.success ? '✅ UPLOAD VERIFIED' : '⚠️ ANOMALIES FOUND')
      setActiveTab('debug')
    } catch {
      setStatus('❌ UPLOAD FAILED')
    } finally {
      setLoading(false)
    }
  }

  const handleApplyFix = async () => {
    if (!result?.fixed_code) return
    setStatus('🛠️ REPAIRING...')
    try {
      await fetch(`${API}/apply_fix`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath, fixed_code: result.fixed_code })
      })
      setStatus('✅ REPAIR COMPLETE')
      setTimeout(() => setStatus(''), 3000)
    } catch {
      setStatus('❌ REPAIR ABORTED')
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(result.fixed_code)
    setStatus('📋 COPIED')
    setTimeout(() => setStatus(''), 2000)
  }

  const handleShowDiff = async () => {
    if (showDiff) { setShowDiff(false); return }
    try {
      const resp = await fetch(`${API}/diff`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original: result.analysis || result.error || '', fixed: result.fixed_code })
      })
      const data = await resp.json()
      setDiff(data.diff)
      setShowDiff(true)
    } catch { setShowDiff(true) }
  }

  const sev = result?.severity ? SEVERITY_CONFIG[result.severity] : null

  return (
    <div className="app-layout">
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
            <span style={{ fontWeight: 800, fontSize: '1.3rem', letterSpacing: '-0.05em', lineHeight: 1 }}>DEBUGGER</span>
            <span style={{ fontWeight: 800, fontSize: '1.3rem', letterSpacing: '-0.05em', color: 'var(--accent)', lineHeight: 1 }}>ELITE PRO</span>
          </div>
        </div>

        <nav style={{ flex: 1 }}>
          <div style={{ color: 'var(--text-tertiary)', fontSize: '0.7rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: '1.5rem' }}>Session History</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {history.map((item) => (
              <motion.div
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
              </motion.div>
            ))}
            {history.length === 0 && <div style={{ color: 'var(--text-tertiary)', fontSize: '0.8rem', fontStyle: 'italic', padding: '1rem 0' }}>Empty Buffer</div>}
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
              {health.online ? 'ELITE QUANTUM LINK ACTIVE' : 'QUANTUM LINK SEVERED'}
            </div>
          </div>
        </div>
      </aside >

      {/* Main Content */}
      < main className="main-content" >
        <div className="main-scroll-area">
          <header>
            <motion.h1 initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>Viper Context Hub</motion.h1>
            <motion.p initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
              Secure, Offline-First Agentic Debugging & Security Orchestration.
            </motion.p>
          </header>

          <div className="tabs-container">
            <button className={`tab-btn ${activeTab === 'debug' ? 'active' : ''}`} onClick={() => setActiveTab('debug')}>Control Center</button>
            <button className={`tab-btn ${activeTab === 'workspace' ? 'active' : ''}`} onClick={() => setActiveTab('workspace')}>Workspace Scan</button>
            <button className={`tab-btn ${activeTab === 'security' ? 'active' : ''}`} onClick={() => setActiveTab('security')}>Quantum Vault</button>
            <button className={`tab-btn ${activeTab === 'terminal' ? 'active' : ''}`} onClick={() => setActiveTab('terminal')}>Execution Log</button>
          </div>

          <div className="grid" style={{ gridTemplateColumns: '1fr 320px', alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              <AnimatePresence mode="wait">
                {activeTab === 'debug' && (
                  <motion.div key="debug-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <div className="card">
                      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
                        <button className={`btn ${mode === 'paste' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('paste')}>
                          <Clipboard size={18} /> Paste Fragment
                        </button>
                        <button className={`btn ${mode === 'upload' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('upload')}>
                          <Upload size={18} /> Load File
                        </button>
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
                            <motion.div initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} style={{ color: 'var(--error)', fontSize: '0.75rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                              <AlertCircle size={14} /> {preflightError}
                            </motion.div>
                          )}
                          <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => runDebug(null)} disabled={loading || !pasteCode.trim()}>
                            {loading ? <div className="loader" /> : <Zap size={20} />}
                            {loading ? loadingMessages[loadingStep] : 'Begin Agentic Synthesis'}
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
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="status-indicator"
                          style={{
                            marginTop: '1.5rem',
                            color: status.includes('✅') || status.includes('⚡') ? 'var(--success)' : 'var(--error)',
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
                          {status.includes('⚡') ? <Zap size={14} fill="currentColor" /> : <Info size={14} />}
                          {status}
                          {result && !result.success && <span style={{ fontSize: '0.7rem', opacity: 0.6, marginLeft: '0.5rem' }}>(CLICK TO JUMP)</span>}
                        </motion.div>
                      )}
                    </div>

                    {result && !result.success && (
                      <div style={{ marginTop: '2rem', display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                        <div className="card" ref={traceRef}>
                          <h3 style={{ color: 'var(--error)', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '1.2rem', marginBottom: '1.5rem' }}>
                            <Terminal size={20} /> Traceback Intercepted
                          </h3>
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
                              <h3 style={{ color: 'var(--success)', fontSize: '1.2rem', marginBottom: '0.2rem' }}>Viper Live Workspace</h3>
                              <p style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>Dual-pane interactive patching engine</p>
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem' }}>
                              <button className="btn btn-secondary btn-sm" onClick={handleCopy}><Clipboard size={14} /> Copy</button>
                              <button className="btn btn-primary btn-sm" onClick={handleApplyFix}><Zap size={14} /> Commit Patch</button>
                            </div>
                          </div>

                          <ViperEditor
                            original={pasteCode || result.error || 'No context'}
                            fixed={result.fixed_code}
                            onEdit={(val) => setResult({ ...result, fixed_code: val })}
                          />
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}

                {activeTab === 'workspace' && (
                  <motion.div key="workspace-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <WorkspacePanel files={workspaceFiles} onSelectFile={(path) => { setFilePath(path); setMode('upload'); runDebug(path); }} />
                  </motion.div>
                )}

                {activeTab === 'security' && (
                  <motion.div key="security-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <div className="card">
                      <h3>Quantum Vault: Security Audit</h3>
                      <p style={{ color: 'var(--text-tertiary)', marginBottom: '2rem' }}>Comprehensive security scan of session logic using Bandit & Elite Heuristics.</p>
                      {result ? (
                        <SecurityPanel data={result.security_audit} />
                      ) : (
                        <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-tertiary)' }}>
                          <Shield size={48} style={{ opacity: 0.2, marginBottom: '1rem' }} />
                          <p>Initialize a debug session to view security audit data.</p>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}

                {activeTab === 'terminal' && (
                  <motion.div key="terminal-tab" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                    <TerminalPanel result={result} loading={loading} />
                  </motion.div>
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
