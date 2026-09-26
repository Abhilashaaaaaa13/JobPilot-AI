import { useEffect, useState } from 'react';
import { api } from '../api';
import CompanyCard from '../components/CompanyCard';
import { useToast } from '../context/ToastContext';

export default function Outreach() {
  const [companies, setCompanies] = useState(null);
  const [scraping, setScraping] = useState(false);
  const [sourceFilter, setSourceFilter] = useState('all');
  const [hasContacts, setHasContacts] = useState(false);
  const toast = useToast();

  async function load() {
    const res = await api.getFeed();
    setCompanies(res.companies);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleFindMore() {
    setScraping(true);
    try {
      const res = await api.startScrape();
      if (res.already_running) {
        toast.info('Already scraping — hang tight.');
      }
      const id = setInterval(async () => {
        const status = await api.scrapeStatus();
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

      <div className="flex items-center gap-4 mb-6">
        <button onClick={handleFindMore} disabled={scraping} className="btn-primary">
          {scraping ? '🔍 Scraping (this can take a minute)…' : '🔍 Find More Startups'}
        </button>
        <span className="text-xs text-muted">{companies.length} companies in DB waiting for outreach</span>
      </div>

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
            <CompanyCard key={c.id} company={c} onSent={load} />
          ))}
        </div>
      )}
    </div>
  );
}
