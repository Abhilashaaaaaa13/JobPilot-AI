import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../context/ToastContext';

const STATUS_STYLE = {
  replied: 'text-success border-success/30 bg-success/10',
  followup_sent: 'text-warning border-warning/30 bg-warning/10',
  awaiting: 'text-muted border-border bg-white/5',
};
const STATUS_LABEL = { replied: '📩 Replied', followup_sent: '🔄 Follow Up', awaiting: '⏳ Awaiting' };

export default function Tracker() {
  const [emails, setEmails] = useState(null);
  const [filter, setFilter] = useState('all');
  const [checking, setChecking] = useState(false);
  const [sendingFollowups, setSendingFollowups] = useState(false);
  const toast = useToast();

  async function load() {
    const res = await api.getSentEmails();
    setEmails(res.emails);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCheckReplies() {
    setChecking(true);
    try {
      const res = await api.checkReplies();
      if (res.error) toast.error(res.error);
      else toast.success(`${res.checked} replies checked · ${res.new} new`);
      load();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setChecking(false);
    }
  }

  async function handleSendFollowups() {
    setSendingFollowups(true);
    try {
      const res = await api.sendFollowups();
      toast.success(`✅ ${res.followups_sent ?? 0} follow ups sent`);
      load();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSendingFollowups(false);
    }
  }

  if (!emails) return <p className="text-muted animate-pulse">Loading…</p>;

  const total = emails.length;
  const replied = emails.filter((e) => e.replied).length;
  const followups = emails.filter((e) => e.followup_sent).length;
  const replyPct = total ? Math.round((replied / total) * 100) : 0;

  const sorted = [...emails].sort((a, b) => (b.sent_at || '').localeCompare(a.sent_at || ''));
  const filtered = filter === 'all' ? sorted : sorted.filter((e) => (e.status || 'awaiting') === filter);

  return (
    <div className="max-w-4xl">
      <h1 className="font-mono text-2xl font-bold mb-1">📊 Tracker</h1>
      <p className="text-muted text-sm mb-6">Sent emails, replies, follow ups — everything in one place.</p>

      <div className="grid grid-cols-5 gap-3 mb-6">
        {[
          ['Total Sent', total], ['Replied', replied], ['Awaiting', total - replied],
          ['Follow Ups', followups], ['Reply Rate', `${replyPct}%`],
        ].map(([label, value]) => (
          <div key={label} className="card p-3 text-center">
            <p className="text-[10px] uppercase text-muted tracking-wide">{label}</p>
            <p className="font-mono text-xl text-accent mt-1">{value}</p>
          </div>
        ))}
      </div>

      <div className="flex gap-3 mb-6">
        <button onClick={handleCheckReplies} disabled={checking} className="btn-primary">
          {checking ? 'Checking…' : '🔄 Check Replies Now'}
        </button>
        <button onClick={handleSendFollowups} disabled={sendingFollowups} className="btn-secondary">
          {sendingFollowups ? 'Sending…' : '📤 Force Send Follow Ups'}
        </button>
      </div>

      <div className="flex items-center justify-between mb-3">
        <h2 className="font-mono text-sm text-muted uppercase">Sent Emails</h2>
        <select className="input-field !w-auto" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="awaiting">⏳ Awaiting</option>
          <option value="replied">📩 Replied</option>
          <option value="followup_sent">🔄 Follow Up Sent</option>
        </select>
      </div>

      {filtered.length === 0 ? (
        <div className="card p-8 text-center text-muted">No emails sent yet.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((e, i) => {
            const status = e.status || 'awaiting';
            return (
              <details key={i} className="card p-4">
                <summary className="cursor-pointer text-sm flex items-center justify-between">
                  <span><b>{e.company || e.to}</b> · {e.to} · {(e.sent_at || '').slice(0, 10)}</span>
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${STATUS_STYLE[status]}`}>
                    {STATUS_LABEL[status]}
                  </span>
                </summary>
                <div className="mt-3 text-sm space-y-1 text-text/80">
                  <p><b>Subject:</b> {e.subject || '—'}</p>
                  {e.replied && e.reply_body && <p className="text-xs text-muted">Preview: {e.reply_body.slice(0, 200)}</p>}
                  {e.gap && <p className="text-xs"><b>Gap:</b> {e.gap.slice(0, 120)}</p>}
                  {e.proposal && <p className="text-xs"><b>Proposal:</b> {e.proposal.slice(0, 120)}</p>}
                </div>
              </details>
            );
          })}
        </div>
      )}
    </div>
  );
}
