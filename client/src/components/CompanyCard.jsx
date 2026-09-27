import { useState } from 'react';
import EmailPanel from './EmailPanel';

const SOURCE_ICONS = {
  yc_api: '🟠 YC', betalist: '🟣 BL', product_hunt: '🔴 PH',
  indie_hackers: '🟢 IH', github_trending: '⚫ GH', hn_hiring: '🟡 HN',
};

function shortUrl(url) {
  if (!url) return '';
  return url.replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/$/, '').split('/')[0];
}

export default function CompanyCard({ company, defaultOpen = false, autoDraft = false, onSent }) {
  const [open, setOpen] = useState(defaultOpen);
  const contacts = company.contacts || [];
  const bestEmail = contacts.find((c) => c.email && c.verified) || contacts.find((c) => c.email);
  const src = SOURCE_ICONS[company.source] || '⚪';

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left p-4 flex items-center justify-between gap-3 hover:bg-[#ffffff05] transition-colors"
      >
        <div className="min-w-0">
          <p className="font-medium truncate">
            {src} <span className="font-mono">{company.name}</span>{' '}
            <span className="text-muted text-xs">· {company.funding || '?'}</span>
            {company.github_stars ? <span className="text-xs text-muted"> · ⭐ {company.github_stars}</span> : null}
          </p>
          {company.one_liner && <p className="text-xs text-muted truncate mt-0.5">{company.one_liner}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0 text-xs">
          {bestEmail ? (
            <span className="text-success">✅ {bestEmail.email}</span>
          ) : (
            <span className="text-muted">⚠️ no email</span>
          )}
          <span className="text-muted">{open ? '▲' : '▼'}</span>
        </div>
      </button>

      {open && (
        <div className="border-t border-border p-4 flex flex-col gap-4">
          {company.description && company.description !== company.one_liner && (
            <div className="rounded bg-[#a3e63608] border-l-2 border-accent/30 p-3 text-sm text-text/80">
              📋 {company.description.slice(0, 300)}
            </div>
          )}

          <div className="flex gap-4 text-xs text-muted">
            {company.website && (
              <a href={company.website} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                🔗 {shortUrl(company.website)}
              </a>
            )}
            {company.github_url && (
              <a href={company.github_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                🐙 GitHub
              </a>
            )}
          </div>

          {(company.recent_highlight || company.ai_hook || (company.tech_stack || []).length > 0) && (
            <div className="rounded bg-surface-2 border border-border p-3 text-xs space-y-2">
              <p className="font-semibold">🔬 Research Insights</p>
              {company.recent_highlight && company.recent_highlight !== 'N/A' && (
                <p><span className="text-muted uppercase">Recent: </span>{company.recent_highlight}</p>
              )}
              {company.ai_hook && company.ai_hook !== 'N/A' && (
                <p><span className="text-muted uppercase">AI Angle: </span>{company.ai_hook}</p>
              )}
              {(company.tech_stack || []).length > 0 && (
                <p><span className="text-muted uppercase">Stack: </span>{company.tech_stack.slice(0, 6).join(', ')}</p>
              )}
            </div>
          )}

          {contacts.length > 0 ? (
            <div className="text-sm space-y-1">
              <p className="font-semibold text-xs text-muted uppercase">Contacts</p>
              {contacts.map((c, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span>{c.name} · {c.role}</span>
                  <code className="text-muted">{c.email || '(no email)'}</code>
                  <span>{c.verified ? '✅' : '⚠️'}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-danger">No contacts found — cannot send email.</p>
          )}

          {contacts.length > 0 && (
            <EmailPanel company={company} autoDraft={autoDraft} onSent={onSent} />
          )}
        </div>
      )}
    </div>
  );
}
