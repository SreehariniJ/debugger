import React, { useState } from 'react'
import { motion as Motion, AnimatePresence } from 'framer-motion'
import { Zap, User, Lock, ArrowRight, UserPlus, LogIn } from 'lucide-react'
import { fetchJson } from './lib/api'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export default function LoginPage({ onLogin }) {
    const [isRegister, setIsRegister] = useState(false)
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [displayName, setDisplayName] = useState('')
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)
    const [shake, setShake] = useState(false)

    const triggerShake = () => {
        setShake(true)
        setTimeout(() => setShake(false), 500)
    }

    const handleSubmit = async (e) => {
        e.preventDefault()
        setError('')

        // Client-side validation
        if (isRegister) {
            if (username.length < 3) {
                setError('Username must be at least 3 characters.')
                triggerShake()
                return
            }
            if (!/^[a-zA-Z0-9_]+$/.test(username)) {
                setError('Username can only contain letters, numbers, and underscores.')
                triggerShake()
                return
            }
            if (password.length < 6) {
                setError('Password must be at least 6 characters.')
                triggerShake()
                return
            }
        }

        setLoading(true)

        try {
            const endpoint = isRegister ? '/auth/register' : '/auth/login'
            const body = isRegister
                ? { username, password, display_name: displayName || username }
                : { username, password }

            const data = await fetchJson(`${API}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })

            localStorage.setItem('auth_token', data.access_token)
            localStorage.setItem('auth_user', JSON.stringify(data.user))
            onLogin(data.user)
        } catch (err) {
            setError(err.message || 'Authentication failed.')
            triggerShake()
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="login-page">
            {/* Animated background particles */}
            <div className="login-particles">
                {[...Array(6)].map((_, i) => (
                    <div key={i} className={`login-particle particle-${i}`} />
                ))}
            </div>

            <Motion.div
                className="login-container"
                initial={{ opacity: 0, y: 30, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            >
                {/* Logo */}
                <div className="login-logo">
                    <div className="login-logo-icon">
                        <Zap size={32} color="white" fill="white" />
                    </div>
                    <div className="login-logo-text">
                        <span className="login-brand-top">OFFLINE</span>
                        <span className="login-brand-bottom">AI DEBUGGER</span>
                    </div>
                </div>

                <p className="login-subtitle">
                    {isRegister ? 'Create your account' : 'Sign in to continue'}
                </p>

                {/* Form */}
                <Motion.form
                    onSubmit={handleSubmit}
                    className={`login-form ${shake ? 'login-shake' : ''}`}
                >
                    <AnimatePresence mode="wait">
                        {isRegister && (
                            <Motion.div
                                key="displayName"
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                transition={{ duration: 0.3 }}
                            >
                                <div className="login-input-group">
                                    <User size={18} className="login-input-icon" />
                                    <input
                                        type="text"
                                        placeholder="Display Name"
                                        value={displayName}
                                        onChange={e => setDisplayName(e.target.value)}
                                        className="login-input"
                                        autoComplete="name"
                                    />
                                </div>
                            </Motion.div>
                        )}
                    </AnimatePresence>

                    <div className="login-input-group">
                        <User size={18} className="login-input-icon" />
                        <input
                            type="text"
                            placeholder="Username"
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                            className="login-input"
                            required
                            autoComplete="username"
                            autoFocus
                        />
                    </div>

                    <div className="login-input-group">
                        <Lock size={18} className="login-input-icon" />
                        <input
                            type="password"
                            placeholder="Password"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            className="login-input"
                            required
                            autoComplete={isRegister ? 'new-password' : 'current-password'}
                        />
                    </div>

                    <AnimatePresence>
                        {error && (
                            <Motion.div
                                className="login-error"
                                initial={{ opacity: 0, y: -5 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0 }}
                            >
                                {error}
                            </Motion.div>
                        )}
                    </AnimatePresence>

                    <button type="submit" className="login-submit" disabled={loading}>
                        {loading ? (
                            <Motion.div
                                className="login-spinner"
                                animate={{ rotate: 360 }}
                                transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                            />
                        ) : (
                            <>
                                {isRegister ? <UserPlus size={18} /> : <LogIn size={18} />}
                                {isRegister ? 'Create Account' : 'Sign In'}
                                <ArrowRight size={16} />
                            </>
                        )}
                    </button>
                </Motion.form>

                {/* Toggle */}
                <div className="login-toggle">
                    <span className="login-toggle-text">
                        {isRegister ? 'Already have an account?' : "Don't have an account?"}
                    </span>
                    <button
                        type="button"
                        className="login-toggle-btn"
                        onClick={() => { setIsRegister(!isRegister); setError('') }}
                    >
                        {isRegister ? 'Sign In' : 'Create Account'}
                    </button>
                </div>

                <div className="login-footer">
                    <span>100% Offline · Privacy-first · Local Authentication</span>
                </div>
            </Motion.div>
        </div>
    )
}
