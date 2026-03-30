import re
import traceback

try:
    with open(r'c:\Users\Sreeharini\offline_debugger\frontend\src\App.jsx', 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace App Definition
    app_pat = r'function App\(\) \{.*?(?=function MainApp)'
    app_new = """export const globalToastManager = {
  addToast: (message, type) => console.log("Toast miss:", message)
};

function App() {
  const [authUser, setAuthUser] = useState(() => {
    try {
      const token = localStorage.getItem('auth_token')
      const user = localStorage.getItem('auth_user')
      if (token && user) return JSON.parse(user)
      return null
    } catch { return null }
  })
  
  const [toasts, setToasts] = useState([])
  const [isVerifyingSession, setIsVerifyingSession] = useState(!!authUser)

  globalToastManager.addToast = useCallback((message, type = 'info') => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, message, type }])
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  useEffect(() => {
    const handleExpired = (e) => {
      setAuthUser(null)
      if (e && e.detail && typeof e.detail === 'string') {
         globalToastManager.addToast(e.detail, 'error')
      }
    }
    window.addEventListener('auth_expired', handleExpired)
    return () => window.removeEventListener('auth_expired', handleExpired)
  }, [])

  useEffect(() => {
    if (authUser) {
      setIsVerifyingSession(true)
      fetchJson(`${API}/auth/me`)
        .then(() => setIsVerifyingSession(false))
        .catch(() => setIsVerifyingSession(false))
    } else {
      setIsVerifyingSession(false)
    }
  }, [authUser])

  const handleLogin = (user) => setAuthUser(user)

  const handleLogout = () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    setAuthUser(null)
  }

  return (
    <>
      {isVerifyingSession ? (
         <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-main)' }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.5rem', color: 'var(--text-secondary)', fontWeight: 800 }}>
                <RefreshCcw size={28} className="spin" color="var(--accent)" />
                VERIFYING SESSION...
            </div>
         </div>
      ) : !authUser ? (
         <LoginPage onLogin={handleLogin} />
      ) : (
         <MainApp authUser={authUser} onLogout={handleLogout} />
      )}

      {/* Global Toast Container */}
      <div style={{ position: 'fixed', bottom: '2rem', right: '2rem', zIndex: 9999, pointerEvents: 'none', display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
        <AnimatePresence>
          {toasts.map(t => (
            <Toast key={t.id} message={t.message} type={t.type} onClose={() => removeToast(t.id)} />
          ))}
        </AnimatePresence>
      </div>
    </>
  )
}

"""
    content = re.sub(app_pat, app_new, content, flags=re.DOTALL)

    # MainApp Toasts removal
    mainapp_pat = r'(function MainApp\(\{[^}]+\}\) \{.*?)(  const \[toasts.*?)(?=  const \[mode, setMode)'
    
    def mainapp_sub(m):
        return m.group(1) + '  const addToast = globalToastManager.addToast;\n'
        
    content = re.sub(mainapp_pat, mainapp_sub, content, flags=re.DOTALL)

    # End Toast removal
    toast_end_pat = r'      \{\/\* Toast Notification Container \*\/.*?<\/div >\n    <\/div >'
    toast_end_sub = '    </div >\n    </div >'
    content = re.sub(toast_end_pat, toast_end_sub, content, flags=re.DOTALL)

    with open(r'c:\Users\Sreeharini\offline_debugger\frontend\src\App.jsx', 'w', encoding='utf-8') as f:
        f.write(content)

    print('SUCCESS')
except Exception as e:
    traceback.print_exc()
