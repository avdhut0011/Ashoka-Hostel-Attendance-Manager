import { cleanDisplayText } from '../services/displayText';
import { formatIndiaDateTime, indiaToday } from '../services/time';
import React, { useEffect, useState } from 'react';
import api from '../services/api';
import useListState from '../services/useListState';
import DataStatus from '../components/DataStatus';
import { useToast } from '../context/ToastContext';

export default function StudentHistory() {
  const today = () => indiaToday();
  const [mode, setMode] = useState('single');
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [hostel, setHostel] = useState('');
  const [kind, setKind] = useState('');
  const [status, setStatus] = useState('');
  const [hostels, setHostels] = useState([]);
  const [rows, setRows] = useState([]);
  const [overrides, setOverrides] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const pagination = useListState([mode, start, end, debounced, hostel, kind, status]);
  const { showError, showSuccess } = useToast();
  const filters = { start_date: start || undefined, end_date: (mode === 'single' ? start : end) || undefined,
    user_id: debounced || undefined, hostel_id: hostel || undefined, punch_type: kind || undefined, status: status || undefined };
  useEffect(() => { const timer = setTimeout(() => setDebounced(search), 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    const controller = new AbortController();
    api.get('/hostels', { signal: controller.signal }).then(res => setHostels(res.data)).catch(() => {});
    return () => controller.abort();
  }, []);
  const fetchHistory = async () => {
    const request = pagination.begin();
    setLoading(true);
    try {
      const [res, manual] = await Promise.all([
        api.get('/attendance/history', { params: { ...filters, ...pagination.params }, signal: request.signal }),
        api.get('/attendance/overrides', { params: filters, signal: request.signal })
      ]);
      if (request.success(res)) { setRows(res.data); setOverrides(manual.data); }
    } catch (error) { request.fail(error); }
    finally { if (request.current()) setLoading(false); }
  };
  useEffect(() => { fetchHistory(); }, [pagination.skip, mode, start, end, debounced, hostel, kind, status]);
  const exportCsv = async () => {
    setExporting(true);
    try {
      const response = await api.get('/reports/export', { params: { ...filters, export_format: 'csv' }, responseType: 'blob', timeout: 120000 });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url; link.download = 'attendance_history.csv'; link.click(); URL.revokeObjectURL(url);
      showSuccess('Complete filtered history downloaded, including matching manual changes.');
    } catch { showError('Export failed. Please retry.'); }
    finally { setExporting(false); }
  };
  const reset = () => { setMode('single'); setStart(today()); setEnd(today()); setSearch(''); setHostel(''); setKind(''); setStatus(''); };
  const inputClass = 'w-full border border-slate-300 rounded-lg p-2 text-sm bg-white';
  return <div className="p-6 space-y-6">
    <div className="flex flex-wrap justify-between gap-3">
      <div><h1 className="text-2xl font-bold">Student IN/OUT Attendance History</h1><p className="text-sm text-slate-600">Dates use Indian Standard Time. Exports include all matching records.</p></div>
      <button disabled={exporting} onClick={exportCsv} className="rounded-lg bg-emerald-600 text-white px-4 py-2 disabled:opacity-50">{exporting ? 'Exporting...' : 'Export filtered CSV'}</button>
    </div>
    <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6 rounded-xl border bg-white p-4">
      <label className="text-sm font-semibold">Date selection<select className={inputClass} value={mode} onChange={e => setMode(e.target.value)}><option value="single">Particular date</option><option value="range">Date range</option></select></label>
      <label className="text-sm font-semibold">{mode === 'single' ? 'Date' : 'From date'}<input className={inputClass} type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
      {mode === 'range' && <label className="text-sm font-semibold">To date<input className={inputClass} type="date" value={end} onChange={e => setEnd(e.target.value)} /></label>}
      <label className="text-sm font-semibold">Student ID or name<input className={inputClass} value={search} onChange={e => setSearch(e.target.value)} placeholder="Search student" /></label>
      <label className="text-sm font-semibold">Hostel<select className={inputClass} value={hostel} onChange={e => setHostel(e.target.value)}><option value="">All permitted hostels</option>{hostels.map(h => <option key={h.HostelId} value={h.HostelId}>{cleanDisplayText(h.HostelName)}</option>)}</select></label>
      <label className="text-sm font-semibold">Punch type<select className={inputClass} value={kind} onChange={e => setKind(e.target.value)}><option value="">All types</option>{['IN','OUT','REGISTRATION'].map(k => <option key={k}>{k}</option>)}</select></label>
      <label className="text-sm font-semibold">Processing status<select className={inputClass} value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option>{['VALID','DUPLICATE','INVALID_DEVICE','INACTIVE_STUDENT','MANUAL_OVERRIDE'].map(k => <option key={k}>{k}</option>)}</select></label>
      <button onClick={reset} className="rounded border px-3 py-2">Reset filters</button>
      <button disabled={loading} onClick={fetchHistory} className="rounded border px-3 py-2 disabled:opacity-50">{loading ? 'Refreshing...' : 'Refresh'}</button>
    </div>
    <DataStatus pagination={pagination} status={pagination.status} />
    <p className="text-sm text-slate-600">This page: {rows.filter(r => r.PunchType === 'IN').length} IN, {rows.filter(r => r.PunchType === 'OUT').length} OUT.</p>
    <div className="rounded-xl border bg-white overflow-x-auto">
      <table className="w-full text-sm text-left"><thead className="bg-slate-100"><tr>{['Time','User ID','Student','Hostel / room','Device','Type','Status'].map(title => <th className="p-3" key={title}>{title}</th>)}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.PunchId} className="border-t">
          <td className="p-3">{formatIndiaDateTime(row.LogDate)}</td><td className="p-3">{row.UserId}</td><td className="p-3">{cleanDisplayText(row.StudentName) || 'Unregistered'}</td>
          <td className="p-3">{cleanDisplayText(row.HostelName) || 'Unassigned'} {row.RoomNo || ''}{!row.HistoricalAssignmentKnown && <p className="text-xs text-amber-700">Legacy assignment not verified</p>}</td>
          <td className="p-3">{row.DeviceId}</td><td className="p-3 font-semibold">{row.PunchType || '-'}</td><td className="p-3">{row.ProcessingStatus}<p className="text-xs text-slate-500">{row.Reason}</p></td>
        </tr>)}{!loading && rows.length === 0 && <tr><td colSpan={7} className="p-8 text-center">No matching biometric punches.</td></tr>}</tbody>
      </table>
    </div>
    <div className="rounded-xl border bg-white p-4 space-y-2">
      <h2 className="font-bold">Manual attendance changes</h2>
      <p className="text-xs text-slate-500">Latest 100 matching changes. The export includes all matching changes.</p>
      {overrides.map(o => <div key={o.OverrideId} className="border-t pt-2 text-sm">{o.UserId}: {o.PreviousStatus} to {o.CurrentStatus} | {formatIndiaDateTime(o.EffectiveAt)} | {o.CreatedBy} | {o.Reason}</div>)}
      {overrides.length === 0 && <p className="text-sm text-slate-500">No matching manual changes.</p>}
    </div>
  </div>;
}
