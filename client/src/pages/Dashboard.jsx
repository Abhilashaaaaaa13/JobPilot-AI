import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import CompanyCard from '../components/CompanyCard';
import { useToast } from '../context/ToastContext';

export default function Dashboard() {
  const [companies, setCompanies] = useState(null);
  const [newIds, setNewIds] = useState([]);
  const [profile, setProfile] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [sourceProgress, setSourceProgress] = useState(null);
  const toast = useToast();

  async function load() {
    try {
      const [feed, prof] = await Promise.all([api.getFeed(), api.getProfile()]);
      setCompanies(feed.companies);
      setNewIds(feed.new_ids || []);
      setProfile(prof);
    } catch (err) {
      toast.error(err.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (profile && !profile.resume_uploaded) {
    return (
      <div className="max-w-lg">
        <h1 className="font-mono text-2xl font-bold mb-3">⚡ Dashboard</h1>
        <div className="card p-6">
          <p className="text-warning mb-4">⚠️ Profile setup incomplete — please upload your resume.</p>
          <Link to="/profile" className="btn-primary inline-block">Complete Profile Setup</Link>
        </div>
      </div>
    );
  }

  async function handleRefresh() {
    setRefreshing(true);
    setSourceProgress(null);
    try {
      const res = await api.startScrape();
      if (res.already_running) {
        toast.info('A refresh is already running…');
      }
      pollScrape();
    } catch (err) {
      toast.error(err.message);
      setRefreshing(false);
    }
  }

  function pollScrape() {
    const id = setInterval(async () => {
      const status = await api.scrapeStatus();
      setSourceProgress(status.sources || null);
      if (status.done) {
        clearInterval(id);
        setRefreshing(false);
        if (status.error) toast.error(`Refresh failed: ${status.error}`);
        else toast.success(`${status.new} new companies added`);
        load();
      }
    }, 2000);
  }

  if (!companies) {
    return <p className="text-muted animate-pulse">Loading dashboard…</p>;
  }

  return (
    <div className="max-w-4xl">
      <h1 className="font-mono text-2xl font-bold mb-1">⚡ Dashboard</h1>
      <p className="text-muted text-sm mb-6">
        {companies.length} companies waiting for outreach.
      </p>

      <div className="flex gap-3 mb-3">
        <Link to="/outreach" className="btn-primary">🚀 Start Outreach</Link>
        <button onClick={handleRefresh} disabled={refreshing} className="btn-secondary">
          {refreshing ? '🔄 Refreshing…' : '🔄 Refresh Feed'}
        </button>
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

      {companies.length === 0 ? (
        <div className="card p-8 text-center text-muted">
          Feed is empty. Click "Refresh Feed" to find startups.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {companies.slice(0, 12).map((c) => (
            <CompanyCard key={c.id} company={c} isNew={newIds.includes(c.id)} onSent={load} />
          ))}
        </div>
      )}
    </div>
  );
}
