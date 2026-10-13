import { cleanDisplayText } from '../services/displayText';
import { formatIndiaDateTime } from '../services/time';
import React, { useEffect, useState } from 'react';
import api from '../services/api';
import useListState from '../services/useListState';
import DataStatus from '../components/DataStatus';
import { useAuth } from '../context/AuthContext';
import { Clock, Search, RotateCcw, RefreshCw } from 'lucide-react';

const Attendance = () => {
  const { user } = useAuth();
  const isWarden = user?.role === 'WARDEN';
  const [punches, setPunches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [search, setSearch] = useState('');
  const [punchType, setPunchType] = useState('');

  const pagination = useListState([search, punchType]);

  const fetchTodayAttendance = async (showRefreshIndicator = true) => {
    const request = pagination.begin();
    if (showRefreshIndicator) setIsRefreshing(true);
    try {
      const res = await api.get('/attendance/today', { params: { skip: pagination.skip, limit: pagination.limit, user_id: search || undefined, punch_type: punchType || undefined }, signal: request.signal });
      if (request.success(res)) setPunches(res.data);
    } catch (err) {
      request.fail(err);
      console.error('Error loading today attendance:', err);
    } finally {
      if (!request.current()) return;
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchTodayAttendance(false);
  }, [pagination.skip, search, punchType]);

  const filteredPunches = punches;

  return (
    <div className="p-6 space-y-6">
      <DataStatus pagination={pagination} status={pagination.status} />
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Today's Valid Attendance Logs</h1>
          <p className="text-sm font-medium text-slate-600 mt-1">Processed Valid IN, OUT & REGISTRATION Events</p>
        </div>
        <button
          onClick={() => fetchTodayAttendance(true)}
          disabled={isRefreshing}
          className="flex items-center gap-2 text-sm font-bold px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg border border-indigo-200 transition shadow-sm disabled:opacity-50"
          title="Refresh today's attendance logs"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Filter Bar */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
          <input
            type="text"
            placeholder="Search by Student Name or User ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-900 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <select
          value={punchType}
          onChange={(e) => setPunchType(e.target.value)}
          className="border border-slate-300 rounded-lg text-sm font-semibold text-slate-800 py-2 px-3.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          <option value="">All Event Types</option>
          <option value="IN">IN (Entry)</option>
          <option value="OUT">OUT (Exit)</option>
          <option value="REGISTRATION">REGISTRATION</option>
        </select>

        {(search || punchType) && (
          <button
            onClick={() => {
              setSearch('');
              setPunchType('');
            }}
            className="flex items-center gap-1.5 text-sm font-bold px-3.5 py-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 transition shadow-sm"
            title="Reset and clear all filters"
          >
            <RotateCcw className="w-4 h-4" />
            Clear Filters
          </button>
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative">
        {/* Refreshing Progress Bar Indicator */}
        <div className={`h-1 w-full bg-indigo-500 transition-opacity duration-300 ${isRefreshing ? 'opacity-100 animate-pulse' : 'opacity-0'}`} />

        <table className="w-full text-left text-sm">
          <thead className="bg-slate-100/90 text-slate-800 uppercase text-xs font-extrabold border-b border-slate-200 tracking-wider">
            <tr>
              <th className="p-3.5">Punch ID</th>
              <th className="p-3.5">User ID</th>
              <th className="p-3.5">Student Name</th>
              {!isWarden && <th className="p-3.5">Device & Hostel</th>}
              <th className="p-3.5">Log Time</th>
              <th className="p-3.5">Event Type</th>
              <th className="p-3.5">First Valid Today?</th>
            </tr>
          </thead>
          <tbody className={`divide-y divide-slate-100 text-slate-900 transition-opacity duration-200 ${isRefreshing ? 'opacity-50' : 'opacity-100'}`}>
            {loading ? (
              Array.from({ length: 6 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="p-3.5"><div className="h-4 w-12 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-16 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-28 bg-slate-200 rounded"></div></td>
                  {!isWarden && <td className="p-3.5"><div className="h-4 w-24 bg-slate-200 rounded"></div></td>}
                  <td className="p-3.5"><div className="h-4 w-28 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-5 w-16 bg-slate-200 rounded-full"></div></td>
                  <td className="p-3.5"><div className="h-4 w-16 bg-slate-200 rounded"></div></td>
                </tr>
              ))
            ) : filteredPunches.length === 0 ? (
              <tr>
                <td colSpan={isWarden ? 6 : 7} className="p-8 text-center text-slate-500 font-semibold text-base">
                  {search || punchType ? 'No attendance records match your filter.' : 'No attendance logs recorded today.'}
                </td>
              </tr>
            ) : (
              filteredPunches.map((p) => (
                <tr key={p.PunchId} className="hover:bg-slate-50/80 transition">
                  <td className="p-3.5 font-mono text-slate-600 font-semibold">{p.PunchId}</td>
                  <td className="p-3.5 font-mono font-extrabold text-indigo-700">{p.UserId}</td>
                  <td className="p-3.5 font-bold text-slate-900">
                    {cleanDisplayText(p.StudentName) || (
                      <span className="text-amber-900 font-bold text-xs bg-amber-100 border border-amber-300 px-2.5 py-0.5 rounded-full">
                        Unregistered Card
                      </span>
                    )}
                  </td>
                  {!isWarden && (
                    <td className="p-3.5 text-slate-700 font-semibold">
                      {cleanDisplayText(p.DeviceName) || `Device ${p.DeviceId}`} {p.HostelName ? `(${cleanDisplayText(p.HostelName)})` : ''}
                    </td>
                  )}
                  <td className="p-3.5 text-slate-800 font-medium">
                    {formatIndiaDateTime(p.LogDate, { dateStyle: 'medium', timeStyle: 'short' })}
                  </td>
                  <td className="p-3.5">
                    <span className={`px-3 py-1 rounded-md text-xs font-black uppercase tracking-wider ${
                      p.PunchType === 'IN' ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' :
                      p.PunchType === 'OUT' ? 'bg-amber-100 text-amber-900 border border-amber-300' : 'bg-indigo-100 text-indigo-900 border border-indigo-300'
                    }`}>
                      {p.PunchType}
                    </span>
                  </td>
                  <td className="p-3.5">
                    {p.IsFirstValidPunchOfDay ? (
                      <span className="text-emerald-700 font-bold text-xs bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">Yes (First)</span>
                    ) : (
                      <span className="text-slate-400 font-semibold text-xs">No</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Attendance;
