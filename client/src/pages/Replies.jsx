import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../context/ToastContext';

export default function Replies() {
  const [tab, setTab] = useState('notifications');
  const [notifications, setNotifications] = useState(null);
  const [drafts, setDrafts] = useState(null);
  const [checking, setChecking] = useState(false);
  const toast = useToast();

  async function loadAll() {
    const [n, d] = await Promise.all([api.getNotifications(), api.getDrafts()]);
    setNotifications(n.notifications);
    setDrafts(d.drafts);
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleCheckNow() {
    setChecking(true);
    try {
      const res = await api.checkReplies();
      if (res.error) toast.error(res.error);
      else toast.success(`${res.new} new reply(ies) found`);
      loadAll();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setChecking(false);
    }
  }

  async function markRead(id) {
    await api.markNotifRead(id);
    loadAll();
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-mono text-2xl font-bold">📬 Replies & Drafts</h1>
          <p className="text-muted text-sm">Auto-detected replies from cold outreach emails.</p>
        </div>
        <button onClick={handleCheckNow} disabled={checking} className="btn-primary">
          {checking ? 'Checking…' : '🔄 Check Now'}
        </button>
      </div>

      <div className="flex gap-1 mb-6 border-b border-border">
        {[
          ['notifications', `🔔 New Replies${notifications?.length ? ` (${notifications.length})` : ''}`],
          ['drafts', `✏️ Draft Approvals${drafts?.length ? ` (${drafts.length})` : ''}`],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`pb-3 px-1 mr-6 text-sm font-mono border-b-2 transition-colors ${
              tab === key ? 'text-accent border-accent' : 'text-muted border-transparent'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'notifications' && (
        <div className="flex flex-col gap-3">
          {!notifications ? (
            <p className="text-muted animate-pulse">Loading…</p>
          ) : notifications.length === 0 ? (
            <p className="text-muted">✨ No new replies yet. Keep outreaching!</p>
          ) : (
            notifications.map((n) => (
              <div key={n.id} className="card p-4">
                <p className="font-medium">{n.title}</p>
                <p className="text-sm mt-1"><b>From:</b> {n.data?.from}</p>
                <p className="text-sm"><b>Company:</b> {n.data?.company || 'N/A'}</p>
                <p className="text-sm"><b>Subject:</b> {n.data?.subject}</p>
                {n.data?.body_preview && (
                  <p className="text-xs text-muted mt-2 border-t border-border pt-2">{n.data.body_preview}</p>
                )}
                <button onClick={() => markRead(n.id)} className="btn-secondary !py-1 !px-3 text-xs mt-3">
                  ✅ Mark as read
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {tab === 'drafts' && (
        <DraftsTab drafts={drafts} onChange={loadAll} />
      )}
    </div>
  );
}

function DraftsTab({ drafts, onChange }) {
  const toast = useToast();
  const [edits, setEdits] = useState({});

  function getEdit(d) {
    return edits[d.id] || {
      subject: d.auto_draft?.subject || `Re: ${d.original_subject}`,
      body: d.auto_draft?.body || '',
    };
  }

  function setEdit(d, patch) {
    setEdits((e) => ({ ...e, [d.id]: { ...getEdit(d), ...patch } }));
  }

  async function approve(d) {
    const e = getEdit(d);
    try {
      await api.approveDraft(d.id, e);
      toast.success(`Reply sent to ${d.from}`);
      onChange();
    } catch (err) {
      toast.error(err.message);
    }
  }

  async function reject(d) {
    await api.rejectDraft(d.id);
    toast.info('Marked for manual reply');
    onChange();
  }

  if (!drafts) return <p className="text-muted animate-pulse">Loading…</p>;
  if (drafts.length === 0) return <p className="text-muted">✨ No drafts pending review.</p>;

  return (
    <div className="flex flex-col gap-4">
      {drafts.map((d) => {
        const e = getEdit(d);
        return (
          <div key={d.id} className="card p-4">
            <p className="font-mono font-semibold">📧 {d.company || d.from}</p>
            <p className="text-xs text-muted mb-3">Reply from {d.from} · {(d.reply_at || '').slice(0, 10)}</p>
            <details className="text-xs mb-3">
              <summary className="cursor-pointer text-muted">View original context</summary>
              <p className="mt-2"><b>Original subject:</b> {d.original_subject}</p>
              <p className="mt-1 text-muted">{d.reply_body_preview}</p>
            </details>
            <input
              className="input-field mb-2" value={e.subject}
              onChange={(ev) => setEdit(d, { subject: ev.target.value })}
            />
            <textarea
              className="input-field" rows={5} value={e.body}
              onChange={(ev) => setEdit(d, { body: ev.target.value })}
            />
            <div className="flex gap-2 mt-3">
              <button onClick={() => approve(d)} className="btn-primary flex-1">✅ Send Reply</button>
              <button onClick={() => reject(d)} className="btn-secondary flex-1">❌ Reject</button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
