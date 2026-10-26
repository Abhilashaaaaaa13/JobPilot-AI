import { useEffect, useState } from 'react';
import { api } from '../api';
import CompanyCard from '../components/CompanyCard';
import { useToast } from '../context/ToastContext';

export default function Outreach() {
  const [companies, setCompanies] = useState(null);
  const [newIds, setNewIds] = useState([]);
  const [scraping, setScraping] = useState(false);
  const [sourceProgress, setSourceProgress] = useState(null);
  const [sourceFilter, setSourceFilter] = useState('all');
  const [hasContacts, setHasContacts] = useState(false);
  const toast = useToast();

  async function load() {
    const res = await api.getFeed();
    setCompanies(res.companies);
    setNewIds(res.new_ids || []);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleFindMore() {
    setScraping(true);
    setSourceProgress(null);
    try {
      const res = await api.startScrape();
      if (res.already_running) {
        toast.info('Already scraping — hang tight.');
      }
      const id = setInterval(async () => {
        const status = await api.scrapeStatus();
        setSourceProgress(status.sources || null);
        if (status.done) {
          clearInterval(id);
          setScraping(false);
          if (status.error) toast.error(`Scrape failed: ${status.error}`);
          else toast.success(`✅ ${status.new} new companies added to DB`);
          load();
        }
      }, 2000);
    } catch (err) {
      toast.error(err.message);
      setScraping(false);
    }
  }

  if (!companies) return <p className="text-muted animate-pulse">Loading…</p>;

  const sources = [...new Set(companies.map((c) => c.source || '?'))].sort();
  let filtered = companies;
  if (sourceFilter !== 'all') filtered = filtered.filter((c) => c.source === sourceFilter);
  if (hasContacts) filtered = filtered.filter((c) => (c.contacts || []).length > 0);

  return (
    <div className="max-w-4xl">
      <h1 className="font-mono text-2xl font-bold mb-1">🚀 Cold Outreach</h1>
      <p className="text-muted text-sm mb-6">Find startups, generate personalized emails, and reach out.</p>

      <div className="flex items-center gap-4 mb-3">
        <button onClick={handleFindMore} disabled={scraping} className="btn-primary">
          {scraping ? '🔍 Scraping…' : '🔍 Find More Startups'}
        </button>
        <span className="text-xs text-muted">{companies.length} companies in DB waiting for outreach</span>
      </div>

      {sourceProgress && (
        <div className="flex flex-wrap gap-2 mb-6 text-xs font-mono">
          {Object.entries(sourceProgress).map(([label, value]) => (
            <span
              key={label}
              className={`px-2 py-1 rounded border ${
                value === 'pending'
                  ? 'border-border text-muted'
                  : value === 'error'
                  ? 'border-danger/40 text-danger'
                  : 'border-success/40 text-success'
              }`}
            >
              {label}: {value === 'pending' ? 'searching…' : value === 'error' ? 'failed' : `${value} found`}
            </span>
          ))}
        </div>
      )}
      {!sourceProgress && <div className="mb-6" />}

      <div className="flex gap-3 mb-6">
        <select className="input-field !w-auto" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
          <option value="all">All sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={hasContacts} onChange={(e) => setHasContacts(e.target.checked)} />
          Has Contacts
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className="card p-8 text-center text-muted">
          🎉 No companies match — click "Find More Startups" to get more.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((c) => (
            <CompanyCard key={c.id} company={c} isNew={newIds.includes(c.id)} onSent={load} />
          ))}
        </div>
      )}
    </div>
  );
}
