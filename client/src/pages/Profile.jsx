import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from '../context/ToastContext';

const DOMAIN_OPTIONS = [
  ['ai_ml', '🤖 AI / ML'], ['data_science', '📊 Data Science'], ['software', '💻 Software Eng'],
  ['backend', '⚙️ Backend'], ['web_dev', '🌐 Web Dev'], ['full_stack', '🔄 Full Stack'], ['product', '📱 Product'],
];

export default function Profile() {
  const [profile, setProfile] = useState(null);
  const [oneLiner, setOneLiner] = useState('');
  const [preferredType, setPreferredType] = useState('job');
  const [domains, setDomains] = useState([]);
  const [rolesText, setRolesText] = useState('');
  const [skillsText, setSkillsText] = useState('');
  const [gmailAddress, setGmailAddress] = useState('');
  const [gmailPassword, setGmailPassword] = useState('');
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);
  const toast = useToast();

  async function load() {
    const p = await api.getProfile();
    setProfile(p);
    setOneLiner(p.one_liner);
    setPreferredType(p.preferred_type);
    setDomains(p.target_industries);
    setRolesText(p.target_roles.join(', '));
    setSkillsText(p.skills.join(', '));
    setGmailAddress(p.gmail_address);
  }

  useEffect(() => {
    load();
  }, []);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await api.uploadResume(file);
      toast.success(`Resume uploaded — ${(res.parsed?.skills || []).length} skills extracted`);
      await load();
      if (res.parsed?.skills?.length) setSkillsText(res.parsed.skills.join(', '));
      if (res.parsed?.target_roles?.length) setRolesText(res.parsed.target_roles.join(', '));
    } catch (err) {
      toast.error(err.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function handleRemoveResume() {
    try {
      await api.removeResume();
      toast.success('Resume removed.');
      await load();
    } catch (err) {
      toast.error(err.message);
    }
  }

  function toggleDomain(key) {
    setDomains((d) => (d.includes(key) ? d.filter((x) => x !== key) : [...d, key]));
  }

  async function handleSave() {
    if (!domains.length) return toast.error('Select at least one domain.');
    if (!rolesText.trim()) return toast.error('Add at least one target role.');
    if (!profile?.resume_uploaded) return toast.error('Upload a resume first (required).');

    setSaving(true);
    try {
      await api.updateProfile({
        one_liner: oneLiner,
        preferred_type: preferredType,
        target_industries: domains,
        target_roles: rolesText.split(',').map((s) => s.trim()).filter(Boolean),
        skills: skillsText.split(',').map((s) => s.trim()).filter(Boolean),
        gmail_address: gmailAddress || undefined,
        gmail_app_password: gmailPassword || undefined,
      });
      toast.success('Profile saved!');
      setGmailPassword('');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (!profile) return <p className="text-muted animate-pulse">Loading…</p>;

  return (
    <div className="max-w-2xl">
      <h1 className="font-mono text-2xl font-bold mb-6">👤 Profile Setup</h1>

      {/* Step 1 — Resume */}
      <section className="card p-5 mb-5">
        <p className="step-label">Step 1 — Resume</p>
        {profile.resume_uploaded ? (
          <div className="flex items-center justify-between">
            <span className="text-sm">
              <span className="text-success">✓ Uploaded</span>{' '}
              <span className="text-muted">{profile.resume_filename}</span>
            </span>
            <button onClick={handleRemoveResume} className="btn-secondary !py-1.5 !px-3 text-xs">
              🗑️ Remove
            </button>
          </div>
        ) : (
          <p className="text-sm text-muted mb-2">No resume uploaded yet — required to continue.</p>
        )}
        <input
          ref={fileRef} type="file" accept=".pdf" onChange={handleUpload} disabled={uploading}
          className="mt-3 text-sm text-muted file:btn-secondary file:!py-1.5 file:!px-3 file:mr-3 file:text-xs"
        />
        {uploading && <p className="text-xs text-accent mt-2 animate-pulse">Parsing resume…</p>}
      </section>

      {/* Step 2 — One liner */}
      <section className="card p-5 mb-5">
        <p className="step-label">Step 2 — Your One Liner</p>
        <input
          className="input-field" maxLength={150} value={oneLiner}
          placeholder="Final year CS student | built 3 RAG systems | LangChain expert"
          onChange={(e) => setOneLiner(e.target.value)}
        />
        <p className="text-xs text-muted mt-1">{oneLiner.length}/150</p>
      </section>

      {/* Step 3 — Preferences */}
      <section className="card p-5 mb-5">
        <p className="step-label">Step 3 — Preferences</p>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <select className="input-field" value={preferredType} onChange={(e) => setPreferredType(e.target.value)}>
            <option value="job">Only Job</option>
            <option value="internship">Only Internship</option>
            <option value="both">Internship + Job</option>
          </select>
        </div>

        <p className="text-sm mb-2">Domains</p>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {DOMAIN_OPTIONS.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={domains.includes(key)} onChange={() => toggleDomain(key)} />
              {label}
            </label>
          ))}
        </div>

        <p className="text-sm mb-1">Target Roles (comma separated)</p>
        <textarea className="input-field mb-4" rows={2} value={rolesText} onChange={(e) => setRolesText(e.target.value)} />

        <p className="text-sm mb-1">Skills (comma separated)</p>
        <textarea className="input-field" rows={2} value={skillsText} onChange={(e) => setSkillsText(e.target.value)} />
      </section>

      {/* Step 4 — Gmail */}
      <section className="card p-5 mb-6">
        <p className="step-label">Step 4 — Gmail (for sending emails)</p>
        {profile.gmail_connected && (
          <p className="text-xs text-success mb-2">✓ Gmail connected: {profile.gmail_address}</p>
        )}
        <p className="text-xs text-muted mb-3">
          Outreach emails send from your Gmail.{' '}
          <a href="https://support.google.com/accounts/answer/185833" target="_blank" rel="noreferrer" className="text-accent underline">
            App Password guide ↗
          </a>
        </p>
        <div className="grid grid-cols-2 gap-3">
          <input
            className="input-field" placeholder="yourname@gmail.com" value={gmailAddress}
            onChange={(e) => setGmailAddress(e.target.value)}
          />
          <input
            className="input-field" type="password" placeholder="App Password" value={gmailPassword}
            onChange={(e) => setGmailPassword(e.target.value)}
          />
        </div>
      </section>

      <button onClick={handleSave} disabled={saving} className="btn-primary w-full">
        {saving ? 'Saving…' : '💾 Save Profile →'}
      </button>
    </div>
  );
}
