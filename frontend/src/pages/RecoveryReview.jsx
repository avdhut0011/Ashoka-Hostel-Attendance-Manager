import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { formatIndiaDateTime, indiaToday } from '../services/time';
import useListState from '../services/useListState';
import DataStatus from '../components/DataStatus';

export default function RecoveryReview() {
  const [start, setStart] = useState(indiaToday());
  const [end, setEnd] = useState(indiaToday());
  const [status, setStatus] = useState('PENDING');
  const [rows, setRows] = useState([]);
  const [scans, setScans] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const page = useListState([status]);
  const scanPage = useListState([]);
  useEffect(() => {
    const load = page.begin();
    api.get('/recovery/punches', { params: { status: status || undefined, skip: page.skip, limit: page.limit }, signal: load.signal })
      .then(response => { if (load.success(response)) setRows(response.data); }).catch(load.fail);
  }, [status, page.skip, version]);
  useEffect(() => {
    const load = scanPage.begin();
    api.get('/recovery/scans', { params: { skip: scanPage.skip, limit: scanPage.limit }, signal: load.signal })
      .then(response => { if (load.success(response)) setScans(response.data); }).catch(load.fail);
  }, [scanPage.skip, version]);
  const run = async (scanId) => {
    setBusy(true); setError('');
    try {
      let id = scanId;
      if (!id) id = (await api.post('/recovery/scans', { start_date: start, end_date: end })).data.ScanId;
      await api.post(`/recovery/scans/${id}/continue`, null, { timeout: 45000 });
      setVersion(value => value + 1);
    } catch (err) { setError(err.response?.data?.detail || 'Scan could not complete. Resume it below.'); }
    finally { setBusy(false); }
  };
  const review = async (row, decision) => {
    const note = window.prompt(`Reason for marking this punch ${decision.toLowerCase()}:`);
    if (!note?.trim()) return;
    try {
      await api.put(`/recovery/punches/${row.RecoveryId}/review`, { status: decision, note });
      setVersion(value => value + 1);
    } catch (err) { setError(err.response?.data?.detail || 'Review could not be saved.'); }
  };
  return <div className="p-6 space-y-4">
    <h1 className="text-2xl font-bold">Skipped Punch Review</h1>
    <p className="text-sm text-slate-600">Scans read matching active devices and save missing punches for existing students here. Punches before the device's latest activation are excluded. Reviewing a punch does not import it or change attendance.</p>
    {error && <div role="alert" className="text-red-700">{error}</div>}
    <form className="flex gap-3 items-end" onSubmit={event => { event.preventDefault(); run(); }}>
      <label>From (India time)<input type="date" required value={start} onChange={event => setStart(event.target.value)} className="block border p-2" /></label>
      <label>To<input type="date" required min={start} value={end} onChange={event => setEnd(event.target.value)} className="block border p-2" /></label>
      <button disabled={busy} className="rounded bg-indigo-600 p-2 text-white">{busy ? 'Scanning…' : 'Scan for missing punches'}</button>
    </form>
    <DataStatus pagination={scanPage} status={scanPage.status} />
    <div className="space-y-2">{scans.map(scan => <div key={scan.ScanId} className="text-sm border p-2">
      {scan.StartDate} – {scan.EndDate}: {scan.Status}; {scan.ScannedCount} scanned, {scan.CandidateCount} candidates, {scan.UnknownStudentCount} unknown students excluded
      {scan.Status !== 'COMPLETE' && <button disabled={busy} onClick={() => run(scan.ScanId)} className="ml-3 text-indigo-700">Resume scan</button>}
    </div>)}</div>
    <select value={status} onChange={event => setStatus(event.target.value)} className="border p-2"><option value="">All reviews</option><option>PENDING</option><option>REVIEWED</option><option>IGNORED</option></select>
    <DataStatus pagination={page} status={page.status} />
    <table className="w-full bg-white text-sm"><thead><tr>{['Source ID', 'Student', 'Device', 'Time (India)', 'Status / reason', 'Review'].map(label => <th key={label} className="p-2 text-left">{label}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.RecoveryId} className="border-t">
        <td className="p-2">{row.SourceDeviceLogId}</td><td>{row.UserId}</td><td>{row.DeviceId}</td><td>{formatIndiaDateTime(row.LogDate)}</td>
        <td className="p-2">{row.ReviewStatus}<p>{row.Reason}</p><p>{row.ReviewNote}</p></td>
        <td><button onClick={() => review(row, 'REVIEWED')} className="text-indigo-700 mr-3">Mark reviewed</button><button onClick={() => review(row, 'IGNORED')}>Ignore</button></td>
      </tr>)}</tbody></table>
  </div>;
}
