import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import CompanyCard from '../components/CompanyCard';
import { useToast } from '../context/ToastContext';

export default function Dashboard() {
  const [companies, setCompanies] = useState(null);
  const [profile, setProfile] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const toast = useToast();

  async function load() {
    try {
      const [feed, prof] = await Promise.all([api.getFeed(), api.getProfile()]);
      setCompanies(feed.companies);
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
    try {
      const res = await api.startScrape();
      if (res.already_running) {
        toast.info('A refresh is already running…');
      } else {
        toast.info('Refreshing feed in the background — this can take a minute.');
        pollScrape();
      }
    } catch (err) {
      toast.error(err.message);
      setRefreshing(false);
    }
  }

  function pollScrape() {
    const id = setInterval(async () => {
      const status = await api.scrapeStatus();
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

      <div className="flex gap-3 mb-6">
        <Link to="/outreach" className="btn-primary">🚀 Start Outreach</Link>
        <button onClick={handleRefresh} disabled={refreshing} className="btn-secondary">
          {refreshing ? '🔄 Refreshing…' : '🔄 Refresh Feed'}
        </button>
      </div>

      {companies.length === 0 ? (
        <div className="card p-8 text-center text-muted">
          Feed is empty. Click "Refresh Feed" to find startups.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {companies.slice(0, 12).map((c) => (
            <CompanyCard key={c.id} company={c} onSent={load} />
          ))}
        </div>
      )}
    </div>
  );
}
