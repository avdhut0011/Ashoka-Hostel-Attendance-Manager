import React, { useEffect, useState } from 'react';
import { Download, RefreshCw, Search, Users } from 'lucide-react';
import api from '../services/api';
import useListState from '../services/useListState';
import useDebouncedValue from '../services/useDebouncedValue';
import DataStatus from '../components/DataStatus';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { cleanDisplayText } from '../services/displayText';
import { formatIndiaDateTime, indiaToday } from '../services/time';

const views = [
  { id: 'in', label: 'Currently IN' },
  { id: 'out', label: 'Currently OUT' },
  { id: 'frequent', label: '5 or more punches today' },
  { id: 'out_24h', label: 'OUT over 24 hours' },
];

export default function StudentDetails() {
  const { user } = useAuth();
  const { showSuccess, showError } = useToast();
  const isWarden = user?.role === 'WARDEN';
  const [view, setView] = useState('in');
  const [hostelId, setHostelId] = useState('');
  const [hostels, setHostels] = useState([]);
  const [search, setSearch] = useState('');
  const [direction, setDirection] = useState('either');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [hostelError, setHostelError] = useState('');
  const settledSearch = useDebouncedValue(search);
  const pagination = useListState([view, hostelId, settledSearch, direction]);
  const filters = { view, hostel_id: isWarden ? user.hostel_id : hostelId || undefined, search: settledSearch || undefined, direction };

  useEffect(() => {
    const controller = new AbortController();
    api.get('/hostels', { signal: controller.signal }).then(res => setHostels(res.data)).catch(error => {
      if (!controller.signal.aborted) setHostelError('Hostel options could not load. Refresh the page to retry.');
    });
    return () => controller.abort();
  }, []);

  const refresh = async () => {
    const request = pagination.begin();
    setLoading(true);
    setRows([]);
    try {
      const response = await api.get('/student-details', { params: { ...filters, skip: pagination.skip, limit: pagination.limit }, signal: request.signal });
      if (request.success(response)) setRows(response.data);
    } catch (error) {
      request.fail(error);
    } finally {
      if (request.current()) setLoading(false);
    }
  };
  useEffect(() => {
    refresh();
    const timer = setInterval(() => { if (!document.hidden) refresh(); }, 30000);
    return () => clearInterval(timer);
  }, [view, hostelId, settledSearch, direction, pagination.skip]);

  const download = async () => {
    if (search !== settledSearch) return;
    setExporting(true);
    try {
      const response = await api.get('/student-details/export', { params: filters, responseType: 'blob', timeout: 120000 });
      const url = window.URL.createObjectURL(response.data);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `student_list_${view}_${indiaToday()}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      showSuccess('Excel report downloaded with the selected filters.');
    } catch (error) {
      showError('Unable to download the Excel report. Please retry.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 flex items-center gap-2"><Users className="h-6 w-6 text-indigo-600" />Detailed Student Lists</h1>
          <p className="text-sm text-slate-600 mt-1">Active students by current attendance status and daily punch activity.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} disabled={loading} className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 text-indigo-700 px-4 py-2 text-sm font-semibold disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Refresh</button>
          <button onClick={download} disabled={exporting || loading || !!pagination.status.error} className="flex items-center gap-2 rounded-lg bg-indigo-600 text-white px-4 py-2 text-sm font-semibold disabled:opacity-50"><Download className="h-4 w-4" />{exporting ? 'Preparing Excel…' : 'Download Excel'}</button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Student list">
        {views.map(item => <button key={item.id} aria-pressed={view === item.id} onClick={() => setView(item.id)} className={`rounded-lg px-4 py-2 text-sm font-semibold border ${view === item.id ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-200 hover:bg-indigo-50'}`}>{item.label}</button>)}
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
        <div className="flex flex-wrap gap-3">
          <label className="relative flex-1 min-w-[220px]"><span className="sr-only">Search student name or user ID</span><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" /><input value={search} onChange={event => setSearch(event.target.value)} maxLength={150} placeholder="Search student name or user ID" className="w-full border border-slate-300 rounded-lg pl-9 pr-3 py-2 text-sm" /></label>
          <label><span className="sr-only">Hostel</span><select value={isWarden ? String(user.hostel_id ?? '') : hostelId} disabled={isWarden} onChange={event => setHostelId(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-600">
            {!isWarden && <option value="">All hostels</option>}
            {isWarden && !hostels.length && <option value={user.hostel_id ?? ''}>Assigned hostel</option>}
            {hostels.map(hostel => <option key={hostel.HostelId} value={hostel.HostelId}>{cleanDisplayText(hostel.HostelName)}</option>)}
          </select></label>
          {view === 'frequent' && <label><span className="sr-only">Punch direction</span><select value={direction} onChange={event => setDirection(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"><option value="either">5 or more IN or OUT</option><option value="in">5 or more IN</option><option value="out">5 or more OUT</option></select></label>}
          {(search || hostelId || direction !== 'either') && <button onClick={() => { setSearch(''); setHostelId(''); setDirection('either'); }} className="text-sm text-indigo-700 font-semibold">Clear filters</button>}
        </div>
        <p className="text-xs text-slate-500">Today's counts: {indiaToday()}, 12:00 am to the next 12:00 am (India time). Valid biometric IN and OUT punches are counted separately; duplicates and manual changes are excluded from these counts.</p>
        {view === 'out_24h' && <p className="text-xs text-slate-500">Duration starts at the latest valid OUT punch or manual change to OUT. Students with an unknown OUT time are excluded.</p>}
        {hostelError && <p role="alert" className="text-sm text-rose-700">{hostelError}</p>}
      </div>
      <DataStatus pagination={pagination} status={pagination.status} />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-slate-100 text-slate-700"><tr>{['User ID', 'Student', 'Hostel', 'Room', 'Status', 'IN today', 'OUT today', 'Last event', 'OUT since', 'Time OUT'].map(label => <th key={label} className="px-4 py-3 font-semibold">{label}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100 text-slate-800">
            {loading ? <tr><td colSpan={10} className="p-8 text-center text-slate-500">Loading students…</td></tr> : pagination.status.error ? <tr><td colSpan={10} className="p-8 text-center text-rose-700">Unable to load this list. Please refresh.</td></tr> : !rows.length ? <tr><td colSpan={10} className="p-8 text-center text-slate-500">No students match this list and its filters.</td></tr> : rows.map(row => <tr key={row.StudentId} className="hover:bg-slate-50">
              <td className="px-4 py-3">{cleanDisplayText(row.UserId)}</td><td className="px-4 py-3 font-semibold">{cleanDisplayText(row.StudentName) || 'Unnamed student'}</td><td className="px-4 py-3">{cleanDisplayText(row.HostelName) || 'Unassigned'}</td><td className="px-4 py-3">{cleanDisplayText(row.RoomNo) || '—'}</td>
              <td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${row.CurrentStatus === 'IN' ? 'bg-emerald-50 text-emerald-700' : row.CurrentStatus === 'OUT' ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>{row.CurrentStatus}</span></td>
              <td className="px-4 py-3 tabular-nums">{row.TodayInCount}</td><td className="px-4 py-3 tabular-nums">{row.TodayOutCount}</td><td className="px-4 py-3">{row.LastPunchTime ? formatIndiaDateTime(row.LastPunchTime) : '—'}</td><td className="px-4 py-3">{row.OutSince ? formatIndiaDateTime(row.OutSince) : '—'}</td><td className="px-4 py-3 tabular-nums">{row.OutHours !== null ? `${row.OutHours.toFixed(2)} hours` : '—'}</td>
            </tr>)}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">Excel includes every matching student across all pages. This list refreshes every 30 seconds while visible.</p>
    </div>
  );
}
