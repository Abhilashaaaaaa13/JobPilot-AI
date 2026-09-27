import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../context/ToastContext';

/**
 * Draft / edit / send / skip panel for one company's outreach email.
 * `autoDraft` triggers drafting immediately (e.g. from Home's "View Email"),
 * otherwise a "Draft Email" button gates it (avoids drafting-for-everyone-on-load).
 */
export default function EmailPanel({ company, autoDraft = false, onSent }) {
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(autoDraft);
  const [editing, setEditing] = useState(false);
  const [sending, setSending] = useState(false);
  const [skipped, setSkipped] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState(null);
  const [started, setStarted] = useState(autoDraft);
  const toast = useToast();

  async function loadDraft() {
    setStarted(true);
    setLoading(true);
    setError(null);
    try {
      const d = await api.draftEmail(company.id);
      setDraft(d);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (autoDraft) loadDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSend() {
    if (!draft.contact_email) return toast.error('Contact email is missing.');
    if (!draft.subject.trim()) return toast.error('Subject is empty.');
    if (!draft.body.trim()) return toast.error('Email body is empty.');
    setSending(true);
    try {
      await api.sendEmail(company.id, {
        contact_email: draft.contact_email, subject: draft.subject, body: draft.body,
        contact_name: draft.contact_name, contact_role: draft.contact_role,
        gap: draft.gap, proposal: draft.proposal,
      });
      setSent(true);
      toast.success(`✅ Sent to ${draft.contact_name || draft.contact_email}!`);
      onSent?.();
    } catch (err) {
      toast.error(`Send failed: ${err.message}`);
    } finally {
      setSending(false);
    }
  }

  async function handleSkip() {
    try {
      await api.skipCompany(company.id);
      setSkipped(true);
      onSent?.();
    } catch (err) {
      toast.error(err.message);
    }
  }

  if (sent) {
    return (
      <div className="rounded-lg bg-[#34d39910] border border-success/30 p-3 text-sm text-success">
        ✅ Email sent — check the Tracker for details.
      </div>
    );
  }

  if (skipped) return <p className="text-xs text-muted">⏭ Skipped</p>;

  if (!started) {
    return (
      <button onClick={loadDraft} className="btn-primary w-full">
        ✉️ Draft Email
      </button>
    );
  }

  if (loading) {
    return <p className="text-sm text-muted animate-pulse">Drafting email for {company.name}…</p>;
  }

  if (error) {
    return <p className="text-sm text-danger">❌ {error}</p>;
  }

  if (!draft) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-between text-sm">
        <span>
          <b>To:</b> {draft.contact_name} ({draft.contact_role})
        </span>
        <code className="text-xs text-muted">{draft.contact_email}</code>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        {draft.gap && (
          <div className="rounded bg-[#ea580c14] border-l-2 border-[#ea580c] p-2">
            <b className="text-[#ea580c] uppercase">Gap</b>
            <p className="mt-1 text-text/80 line-clamp-3">{draft.gap}</p>
          </div>
        )}
        {draft.proposal && (
          <div className="rounded bg-[#16a34a14] border-l-2 border-success p-2">
            <b className="text-success uppercase">Proposal</b>
            <p className="mt-1 text-text/80 line-clamp-3">{draft.proposal}</p>
          </div>
        )}
        {draft.why_fits && (
          <div className="rounded bg-[#58811214] border border-accent/25 p-2">
            <b className="text-accent uppercase">Why you</b>
            <p className="mt-1 text-text/80 line-clamp-3">{draft.why_fits}</p>
          </div>
        )}
      </div>

      {editing ? (
        <>
          <input
            className="input-field"
            value={draft.subject}
            onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
          />
          <textarea
            className="input-field"
            rows={8}
            value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })}
          />
        </>
      ) : (
        <>
          <input className="input-field opacity-70" value={draft.subject} disabled />
          <textarea className="input-field opacity-70" rows={7} value={draft.body} disabled />
        </>
      )}

      <div className="flex gap-2">
        <button onClick={handleSend} disabled={sending} className="btn-primary flex-[2]">
          {sending ? 'Sending…' : '🚀 Send Email'}
        </button>
        <button onClick={() => setEditing((e) => !e)} className="btn-secondary flex-1">
          {editing ? '💾 Save' : '✏️ Edit'}
        </button>
        <button onClick={handleSkip} className="btn-secondary flex-1">
          ❌ Skip
        </button>
      </div>
    </div>
  );
}
