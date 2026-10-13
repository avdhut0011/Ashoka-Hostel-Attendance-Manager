import { formatIndiaDateTime } from '../services/time';
import React, { useEffect, useState } from 'react';
import api from '../services/api';
import useListState from '../services/useListState';
import useDebouncedValue from '../services/useDebouncedValue';
import DataStatus from '../components/DataStatus';
import { AlertTriangle, ShieldAlert, UserX, Search, RotateCcw, RefreshCw } from 'lucide-react';

const Punches = () => {
  const [activeTab, setActiveTab] = useState('duplicates'); // duplicates, invalid, inactive
  const [punches, setPunches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [search, setSearch] = useState('');

  const settledSearch = useDebouncedValue(search);
  const pagination = useListState([activeTab, settledSearch]);

  const fetchPunches = async (showRefreshIndicator = true) => {
    const request = pagination.begin();
    setPunches([]);
    setLoading(true);
    if (showRefreshIndicator) setIsRefreshing(true);
    try {
      let endpoint = '/punches/duplicates';
      if (activeTab === 'invalid') endpoint = '/punches/invalid-device';
      if (activeTab === 'inactive') endpoint = '/punches/inactive-students';

      const res = await api.get(endpoint, { params: { ...pagination.params, user_id: settledSearch || undefined }, signal: request.signal });
      if (request.success(res)) setPunches(res.data);
    } catch (err) {
      request.fail(err);
      console.error('Error fetching punches:', err);
    } finally {
      if (!request.current()) return;
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchPunches(false);
  }, [pagination.skip, activeTab, settledSearch]);

  const filteredPunches = punches;

  return (
    <div className="p-6 space-y-6">
      <DataStatus pagination={pagination} status={pagination.status} />
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-black text-slate-900">Punch Exception Reports</h1>
          <p className="text-sm font-semibold text-slate-600 mt-1">Audit Duplicates, Invalid Devices, and Inactive Student Punches</p>
        </div>
        <button
          onClick={() => fetchPunches(true)}
          disabled={isRefreshing}
          className="flex items-center gap-2 text-sm font-bold px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg border border-indigo-200 transition shadow-sm disabled:opacity-50"
          title="Refresh exception punches"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200 gap-6">
        <button
          onClick={() => setActiveTab('duplicates')}
          className={`pb-3 px-2 text-sm font-extrabold flex items-center gap-2 border-b-2 transition ${
            activeTab === 'duplicates' ? 'border-amber-600 text-amber-700' : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <AlertTriangle className="w-4 h-4 text-amber-600" />
          Duplicate Punches (&lt;45s)
        </button>

        <button
          onClick={() => setActiveTab('invalid')}
          className={`pb-3 px-2 text-sm font-extrabold flex items-center gap-2 border-b-2 transition ${
            activeTab === 'invalid' ? 'border-rose-600 text-rose-700' : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <ShieldAlert className="w-4 h-4 text-rose-600" />
          Invalid Device Punches
        </button>

        <button
          onClick={() => setActiveTab('inactive')}
          className={`pb-3 px-2 text-sm font-extrabold flex items-center gap-2 border-b-2 transition ${
            activeTab === 'inactive' ? 'border-purple-600 text-purple-700' : 'border-transparent text-slate-600 hover:text-slate-900'
          }`}
        >
          <UserX className="w-4 h-4 text-purple-600" />
          Inactive Student Punches
        </button>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
          <input
            type="text"
            placeholder="Search by UserId, DeviceId, or Reason..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-900 font-medium placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {search && (
          <button
            onClick={() => setSearch('')}
            className="flex items-center gap-1.5 text-sm font-bold px-3.5 py-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 transition shadow-sm"
            title="Clear search filter"
          >
            <RotateCcw className="w-4 h-4" />
            Clear Filter
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative">
        {/* Refreshing Progress Bar Indicator */}
        <div className={`h-1 w-full bg-indigo-600 transition-opacity duration-300 ${isRefreshing ? 'opacity-100 animate-pulse' : 'opacity-0'}`} />

        <table className="w-full text-left text-sm">
          <thead className="bg-slate-100/90 text-slate-800 uppercase text-xs font-extrabold tracking-wider border-b border-slate-200">
            <tr>
              <th className="p-3.5">Punch ID</th>
              <th className="p-3.5">User ID</th>
              <th className="p-3.5">Device ID</th>
              <th className="p-3.5">Timestamp</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5">Reason / Exception Detail</th>
            </tr>
          </thead>
          <tbody className={`divide-y divide-slate-200 text-slate-900 font-medium transition-opacity duration-200 ${isRefreshing ? 'opacity-50' : 'opacity-100'}`}>
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="p-3.5"><div className="h-4 w-12 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-20 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-16 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-28 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-5 w-24 bg-slate-200 rounded-full"></div></td>
                  <td className="p-3.5"><div className="h-4 w-40 bg-slate-200 rounded"></div></td>
                </tr>
              ))
            ) : filteredPunches.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-500 font-semibold text-sm">
                  {search ? 'No exception punches match your search filter.' : 'No exception punches recorded.'}
                </td>
              </tr>
            ) : (
              filteredPunches.map((p) => (
                <tr key={p.PunchId} className="hover:bg-slate-50 transition-colors">
                  <td className="p-3.5 font-mono font-bold text-slate-800">{p.PunchId}</td>
                  <td className="p-3.5 font-mono font-extrabold text-indigo-700">{p.UserId}</td>
                  <td className="p-3.5 font-bold text-slate-800">Device {p.DeviceId}</td>
                  <td className="p-3.5 text-slate-700 font-medium">{formatIndiaDateTime(p.LogDate)}</td>
                  <td className="p-3.5">
                    <span className="px-2.5 py-1 rounded text-xs font-black uppercase tracking-wide bg-rose-50 text-rose-700 border border-rose-200">
                      {p.ProcessingStatus}
                    </span>
                  </td>
                  <td className="p-3.5 text-slate-700 font-medium">{p.Reason}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Punches;
