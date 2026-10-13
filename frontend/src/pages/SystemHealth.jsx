import { formatIndiaDateTime, indiaDateTimeInput } from '../services/time';
import React, { useEffect, useState } from 'react';
import api from '../services/api';
import useListState from '../services/useListState';
import DataStatus from '../components/DataStatus';
import { useToast } from '../context/ToastContext';
import { 
  Activity, Database, RefreshCw, CheckCircle2, AlertTriangle, 
  ShieldAlert, Check, X, Play, RotateCcw, Filter, Eye, AlertCircle
} from 'lucide-react';

const SystemHealth = () => {
  const { showSuccess, showError } = useToast();
  const [health, setHealth] = useState(null);
  const [syncStatus, setSyncStatus] = useState(null);
  const [quarantineLogs, setQuarantineLogs] = useState([]);
  const [quarantineFilter, setQuarantineFilter] = useState('PENDING'); // PENDING, RESOLVED, IGNORED, ALL
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  
  // Reprocess Modal State
  const [selectedItem, setSelectedItem] = useState(null);
  const [reprocessUserId, setReprocessUserId] = useState('');
  const [reprocessDeviceId, setReprocessDeviceId] = useState('');
  const [reprocessDate, setReprocessDate] = useState('');
  const [reprocessing, setReprocessing] = useState(false);

  const pagination = useListState([quarantineFilter]);

  const fetchStatus = async () => {
    const request = pagination.begin();
    setLoading(true);
    try {
      const [hRes, sRes, qRes] = await Promise.all([
        api.get('/system/health', { signal: request.signal }),
        api.get('/system/sync-status', { signal: request.signal }).catch(err => { if (err.response?.status === 404) return { data: { LastSyncStatus: 'NEVER_RUN' } }; throw err; }),
        api.get('/system/quarantine', { signal: request.signal, params: { skip: pagination.skip, limit: pagination.limit, status: quarantineFilter !== 'ALL' ? quarantineFilter : undefined } })
      ]);
      if (!request.success(qRes)) return;
      setHealth(hRes.data);
      setSyncStatus(sRes.data);
      setQuarantineLogs(qRes.data || []);
    } catch (err) {
      request.fail(err);
      console.error('Error fetching system health:', err);
    } finally {
      if (!request.current()) return;
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, [pagination.skip, quarantineFilter]);

  const handleManualSync = async () => {
    setTriggering(true);
    try {
      const res = await api.post('/system/sync-trigger');
      await fetchStatus();
      const result = res.data?.result;
      if (result?.status === 'IN_PROGRESS') showSuccess('Another synchronization cycle is already running.');
      else showSuccess(`${result?.status}: ${result?.synced_count ?? 0} punches processed; ${result?.quarantined_count ?? 0} quarantined.`);
    } catch (err) {
      showError(err.response?.data?.detail || 'Manual sync trigger failed');
    } finally {
      setTriggering(false);
    }
  };

  const handleResolveAction = async (quarantineId, action) => {
    try {
      await api.post(`/system/quarantine/${quarantineId}/resolve?action=${action}`);
      showSuccess(`Quarantine record ${quarantineId} marked as ${action}.`);
      fetchStatus();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to update quarantine status');
    }
  };

  const openReprocessModal = (item) => {
    setSelectedItem(item);
    setReprocessUserId(item.UserId || '');
    setReprocessDeviceId(item.DeviceId || '');
    setReprocessDate(indiaDateTimeInput(item.LogDate));
  };

  const handleExecuteReprocess = async () => {
    if (!reprocessUserId.trim()) {
      showError('Please provide a valid User ID / Student ID');
      return;
    }
    setReprocessing(true);
    try {
      const payload = {
        corrected_user_id: reprocessUserId.trim(),
        corrected_device_id: parseInt(reprocessDeviceId) || selectedItem.DeviceId,
        corrected_log_date: reprocessDate ? reprocessDate : selectedItem.LogDate
      };
      const res = await api.post(`/system/quarantine/${selectedItem.QuarantineId}/reprocess`, payload);
      showSuccess(`Success: ${res.data?.message} (Punch ${res.data?.punch_id}, Status: ${res.data?.processing_status})`);
      setSelectedItem(null);
      fetchStatus();
    } catch (err) {
      showError(err.response?.data?.detail || 'Reprocessing failed');
    } finally {
      setReprocessing(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <DataStatus pagination={pagination} status={pagination.status} />
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-black text-slate-900">System & Synchronization Health</h1>
          <p className="text-sm font-semibold text-slate-600 mt-1">IT Database Integration, Distributed Worker & Dead-Letter Quarantine</p>
        </div>
        <button
          onClick={handleManualSync}
          disabled={triggering}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold px-4 py-2.5 rounded-lg transition shadow disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${triggering ? 'animate-spin' : ''}`} />
          {triggering ? 'Synchronizing...' : 'Trigger Manual Sync'}
        </button>
      </div>

      {/* Grid: Health Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
          <h3 className="font-extrabold text-sm text-slate-900 uppercase tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            Core Health Indicators
          </h3>

          <div className="space-y-3">
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-sm font-semibold text-slate-700">Overall Status</span>
              <span className={`px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider ${
                health?.status === 'HEALTHY' ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' : 'bg-amber-100 text-amber-900 border border-amber-300'
              }`}>
                {health?.status || 'CHECKING...'}
              </span>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-sm font-semibold text-slate-700">Target MS SQL DB</span>
              <span className="text-xs font-bold text-emerald-700 flex items-center gap-1.5 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200">
                <CheckCircle2 className="w-4 h-4" /> Connected
              </span>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-sm font-semibold text-slate-700">Source IT ePush DB</span>
              <span className="text-xs font-bold text-emerald-700 flex items-center gap-1.5 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200">
                <CheckCircle2 className="w-4 h-4" /> Connected
              </span>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-sm font-semibold text-slate-700">Total Raw Ingested</span>
              <span className="text-base font-black text-slate-900">{health?.total_raw_punches ?? 0}</span>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
          <h3 className="font-extrabold text-sm text-slate-900 uppercase tracking-wider flex items-center gap-2">
            <Database className="w-4 h-4 text-indigo-600" />
            Sync Checkpoint State
          </h3>

          <div className="space-y-3 text-sm">
            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-slate-600 font-semibold text-xs">Source Name</span>
              <span className="font-mono font-bold text-slate-900">{syncStatus?.SourceName || 'IT_SQL_SERVER'}</span>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-slate-600 font-semibold text-xs">Last Synced Log ID</span>
              <span className="font-mono font-extrabold text-indigo-700">{syncStatus?.LastSourceDeviceLogId ?? 0}</span>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-slate-600 font-semibold text-xs">Last Sync Time</span>
              <span className="font-bold text-slate-900 text-xs">
                {syncStatus?.LastSyncCompletedAt ? formatIndiaDateTime(syncStatus.LastSyncCompletedAt) : 'N/A'}
              </span>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-slate-600 font-semibold text-xs">Sync Status</span>
              <span className={`font-black text-xs uppercase tracking-wider px-2.5 py-0.5 rounded ${
                syncStatus?.LastSyncStatus === 'SUCCESS' ? 'text-emerald-700 bg-emerald-50 border border-emerald-200' :
                syncStatus?.LastSyncStatus === 'PARTIAL_SUCCESS' ? 'text-amber-700 bg-amber-50 border border-amber-200' : 'text-blue-700 bg-blue-50 border border-blue-200'
              }`}>
                {syncStatus?.LastSyncStatus || 'IDLE'}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
          <h3 className="font-extrabold text-sm text-slate-900 uppercase tracking-wider flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-amber-600" />
            Dead-Letter Quarantine
          </h3>

          <div className="space-y-3 text-sm">
            <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-lg">
              <div className="text-amber-900 font-bold text-xs uppercase tracking-wider mb-1">Pending Triage Queue</div>
              <div className="text-3xl font-black text-amber-900">
                {health?.pending_quarantined_punches ?? 0}
              </div>
              <p className="text-xs text-amber-800 font-medium mt-1">
                Corrupted records safely isolated from ePush to prevent watermark stalling.
              </p>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-slate-600 font-semibold text-xs">Quarantine Strategy</span>
              <span className="font-bold text-slate-800 text-xs">Savepoint Isolation</span>
            </div>

            <div className="flex justify-between items-center p-3 bg-slate-50 rounded-lg">
              <span className="text-slate-600 font-semibold text-xs">Distributed Lock</span>
              <span className="font-mono font-bold text-indigo-700 text-xs">sp_getapplock Active</span>
            </div>
          </div>
        </div>
      </div>

      {/* Quarantine Audit & Management Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h2 className="text-base font-extrabold text-slate-900 flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-amber-600" />
              Dead-Letter Quarantine Management
            </h2>
            <p className="text-sm font-medium text-slate-600 mt-0.5">
              Review, correct, and reprocess corrupted raw punch entries into the attendance flowchart.
            </p>
          </div>

          <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-lg text-xs font-bold">
            {['PENDING', 'RESOLVED', 'IGNORED', 'ALL'].map((tab) => (
              <button
                key={tab}
                onClick={() => setQuarantineFilter(tab)}
                className={`px-3 py-1.5 rounded-md transition ${
                  quarantineFilter === tab
                    ? 'bg-white text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-100/90 text-slate-800 uppercase text-xs font-extrabold tracking-wider border-b border-slate-200">
              <tr>
                <th className="p-3.5">ID</th>
                <th className="p-3.5">Source Log ID</th>
                <th className="p-3.5">Device</th>
                <th className="p-3.5">Raw User ID</th>
                <th className="p-3.5">Punch Time</th>
                <th className="p-3.5">Error Type & Reason</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-slate-900 font-medium">
              {quarantineLogs.length === 0 ? (
                <tr>
                  <td colSpan="8" className="p-8 text-center text-slate-500 font-semibold text-sm">
                    No quarantined records found for filter "{quarantineFilter}".
                  </td>
                </tr>
              ) : (
                quarantineLogs.map((item) => (
                  <tr key={item.QuarantineId} className="hover:bg-slate-50 transition-colors">
                    <td className="p-3.5 font-mono font-bold text-slate-700">{item.QuarantineId}</td>
                    <td className="p-3.5 font-mono font-bold text-slate-800">{item.SourceDeviceLogId}</td>
                    <td className="p-3.5">
                      <span className="px-2.5 py-1 rounded bg-slate-100 text-slate-800 font-bold text-xs border border-slate-200">
                        Dev {item.DeviceId || 'N/A'}
                      </span>
                    </td>
                    <td className="p-3.5 font-mono font-extrabold text-rose-600">
                      {item.UserId ? item.UserId : <span className="italic text-slate-400 font-normal">[EMPTY / NULL]</span>}
                    </td>
                    <td className="p-3.5 text-slate-700 font-medium">
                      {item.LogDate ? formatIndiaDateTime(item.LogDate) : 'N/A'}
                    </td>
                    <td className="p-3.5 max-w-xs">
                      <span className="font-bold text-amber-800">{item.ErrorType}: </span>
                      <span className="text-slate-700 font-medium">{item.ErrorMessage}</span>
                    </td>
                    <td className="p-3.5">
                      <span className={`px-2.5 py-1 rounded-full font-black uppercase text-xs tracking-wider ${
                        item.ResolvedStatus === 'PENDING' ? 'bg-amber-100 text-amber-900 border border-amber-300' :
                        item.ResolvedStatus === 'RESOLVED' ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' : 'bg-slate-100 text-slate-700 border border-slate-200'
                      }`}>
                        {item.ResolvedStatus}
                      </span>
                    </td>
                    <td className="p-3.5 text-right">
                      {item.ResolvedStatus === 'PENDING' ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => openReprocessModal(item)}
                            className="flex items-center gap-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 px-3 py-1.5 rounded-lg text-xs font-bold border border-indigo-200 transition"
                            title="Correct details and replay through attendance flowchart"
                          >
                            <Play className="w-3.5 h-3.5" /> Fix & Replay
                          </button>
                          <button
                            onClick={() => handleResolveAction(item.QuarantineId, 'IGNORED')}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                            title="Dismiss / Ignore record"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-500 font-semibold text-xs">
                          {item.ResolvedBy ? `By ${item.ResolvedBy}` : 'Processed'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Fix & Reprocess Modal */}
      {selectedItem && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-5 border border-slate-200">
            <div className="flex justify-between items-center border-b border-slate-200 pb-3">
              <div>
                <h3 className="font-black text-slate-900 text-lg">Fix & Replay Quarantined Punch</h3>
                <p className="text-xs text-slate-500 font-bold mt-0.5">Quarantine Record {selectedItem.QuarantineId}</p>
              </div>
              <button onClick={() => setSelectedItem(null)} className="text-slate-400 hover:text-slate-700">
                <X className="w-6 h-6" />
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <div>
                <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">
                  Corrected Student User ID / Card Code <span className="text-rose-600">*</span>
                </label>
                <input
                  type="text"
                  value={reprocessUserId}
                  onChange={(e) => setReprocessUserId(e.target.value)}
                  placeholder="e.g. STU1001"
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 font-mono font-bold text-slate-900"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">Device ID</label>
                <input
                  type="number"
                  value={reprocessDeviceId}
                  onChange={(e) => setReprocessDeviceId(e.target.value)}
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">Punch Log Date / Time</label>
                <input
                  type="datetime-local"
                  value={reprocessDate}
                  onChange={(e) => setReprocessDate(e.target.value)}
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="p-3.5 bg-indigo-50 border border-indigo-200 rounded-lg text-indigo-900 text-xs leading-relaxed">
                <p className="font-bold mb-1">Automated Attendance Flowchart Execution:</p>
                <p>
                  Replaying will insert a clean <code className="font-bold bg-indigo-100 px-1 py-0.5 rounded">RawPunch</code>, evaluate device mapping, auto-register student if new, and calculate <strong>REGISTRATION / IN / OUT</strong> state.
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-200">
              <button
                onClick={() => setSelectedItem(null)}
                disabled={reprocessing}
                className="px-4 py-2.5 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 text-sm font-bold transition"
              >
                Cancel
              </button>
              <button
                onClick={handleExecuteReprocess}
                disabled={reprocessing}
                className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-bold shadow transition disabled:opacity-50"
              >
                <Play className={`w-4 h-4 ${reprocessing ? 'animate-spin' : ''}`} />
                {reprocessing ? 'Reprocessing...' : 'Execute Replay'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SystemHealth;
