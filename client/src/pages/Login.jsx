import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

export default function Login() {
  const [tab, setTab] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const { login, register } = useAuth();
  const toast = useToast();

  // Both login and register just set the user in AuthContext — App.jsx's
  // own redirect-when-authenticated logic on the /login route sends them
  // to "/" from there. Navigating manually here raced with that redirect
  // and lost, which is why an earlier version could land on the wrong page.
  async function handleLogin(e) {
    e.preventDefault();
    if (!email || !password) return toast.error('Please enter your email and password.');
    setBusy(true);
    try {
      await login(email, password);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    if (!email || !password) return toast.error('Please fill in all fields.');
    if (password !== confirm) return toast.error('Passwords do not match.');
    if (password.length < 6) return toast.error('Password must be at least 6 characters.');
    setBusy(true);
    try {
      await register(email, password);
      toast.success('Account created! Let\'s set up your profile.');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="font-mono text-3xl font-bold text-accent">⚡ OutreachAI</h1>
          <p className="text-muted text-sm mt-2">Cold outreach, automated.</p>
        </div>

        <div className="card p-6">
          <div className="flex gap-1 mb-6 border-b border-border">
            {['login', 'register'].map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 pb-3 text-sm font-mono uppercase tracking-wide border-b-2 transition-colors ${
                  tab === t ? 'text-accent border-accent' : 'text-muted border-transparent'
                }`}
              >
                {t === 'login' ? 'Login' : 'Register'}
              </button>
            ))}
          </div>

          {tab === 'login' ? (
            <form onSubmit={handleLogin} className="flex flex-col gap-4">
              <input
                type="email" placeholder="you@gmail.com" value={email}
                onChange={(e) => setEmail(e.target.value)} className="input-field"
              />
              <input
                type="password" placeholder="Password" value={password}
                onChange={(e) => setPassword(e.target.value)} className="input-field"
              />
              <button type="submit" disabled={busy} className="btn-primary w-full mt-2">
                {busy ? 'Logging in…' : 'Login'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegister} className="flex flex-col gap-4">
              <input
                type="email" placeholder="you@gmail.com" value={email}
                onChange={(e) => setEmail(e.target.value)} className="input-field"
              />
              <input
                type="password" placeholder="Password" value={password}
                onChange={(e) => setPassword(e.target.value)} className="input-field"
              />
              <input
                type="password" placeholder="Confirm Password" value={confirm}
                onChange={(e) => setConfirm(e.target.value)} className="input-field"
              />
              <button type="submit" disabled={busy} className="btn-primary w-full mt-2">
                {busy ? 'Creating…' : 'Create Account'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
