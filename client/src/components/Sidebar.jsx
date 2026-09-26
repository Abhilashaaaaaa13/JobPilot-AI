import { NavLink } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

const NAV = [
  { to: '/', label: '⚡  Home', end: true },
  { to: '/profile', label: '👤  Profile Setup' },
  { to: '/outreach', label: '🚀  Cold Outreach' },
  { to: '/tracker', label: '📊  Tracker' },
  { to: '/replies', label: '📬  Replies & Drafts' },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const [replyCount, setReplyCount] = useState(0);
  const [sentStats, setSentStats] = useState(null);
  const [schedRunning, setSchedRunning] = useState(false);
  const [schedBusy, setSchedBusy] = useState(false);

  async function refresh() {
    try {
      const [notifs, sent, sched] = await Promise.all([
        api.getNotifications(),
        api.getSentEmails(),
        api.getSchedulerStatus(),
      ]);
      setReplyCount(notifs.notifications.length);
      const emails = sent.emails || [];
      setSentStats({ sent: emails.length, replied: emails.filter((e) => e.replied).length });
      setSchedRunning(sched.running);
    } catch {
      /* sidebar stats are best-effort */
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, []);

  async function toggleScheduler() {
    setSchedBusy(true);
    try {
      if (schedRunning) await api.stopScheduler();
      else await api.startScheduler();
      const sched = await api.getSchedulerStatus();
      setSchedRunning(sched.running);
    } finally {
      setSchedBusy(false);
    }
  }

  return (
    <aside className="w-64 shrink-0 bg-surface border-r border-border flex flex-col h-screen sticky top-0">
      <div className="p-5">
        <p className="font-mono text-lg font-bold text-accent leading-none">⚡ OutreachAI</p>
        <p className="text-xs text-muted mt-1 truncate">{user?.email}</p>
      </div>
      <div className="border-t border-border" />

      <nav className="flex flex-col gap-1 p-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive ? 'bg-[#e8ff4715] text-accent' : 'text-text hover:bg-[#ffffff08]'
              }`
            }
          >
            {item.label}
            {item.to === '/replies' && replyCount > 0 && (
              <span className="ml-2 text-danger">🔴 {replyCount}</span>
            )}
          </NavLink>
        ))}
      </nav>

      {sentStats && (
        <div className="px-5 py-2 text-xs text-muted font-mono">
          📤 {sentStats.sent} sent · 📩 {sentStats.replied} replied
        </div>
      )}

      <div className="border-t border-border mx-3 my-2" />

      <div className="px-5 py-2 flex items-center justify-between">
        <span className={`text-xs font-mono ${schedRunning ? 'text-success' : 'text-muted'}`}>
          {schedRunning ? '🟢 Scheduler on' : '⚪ Scheduler off'}
        </span>
        <button
          onClick={toggleScheduler}
          disabled={schedBusy}
          className={schedRunning ? 'btn-secondary !py-1 !px-3 text-xs' : 'btn-primary !py-1 !px-3 text-xs'}
        >
          {schedRunning ? 'Stop' : 'Start'}
        </button>
      </div>

      <div className="border-t border-border mx-3 my-2" />

      <div className="mt-auto p-3">
        <button onClick={logout} className="btn-secondary w-full">
          Logout
        </button>
      </div>
    </aside>
  );
}
