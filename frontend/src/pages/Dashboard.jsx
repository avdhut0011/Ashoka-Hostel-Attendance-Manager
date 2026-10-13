import { cleanDisplayText } from '../services/displayText';
import { formatIndiaTime } from '../services/time';
import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { connectDashboardLive } from '../services/dashboardLive';
import { useAuth } from '../context/AuthContext';
import { Users, LogIn, LogOut, Clock, AlertCircle, Building2, RefreshCw, Activity, CheckCircle, ShieldAlert, UserPlus, ArrowRight, AlertTriangle } from 'lucide-react';

const Dashboard = () => {
  const { user } = useAuth();
  const [loadError, setLoadError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [summary, setSummary] = useState(null);
  const [hostels, setHostels] = useState([]);
  const [recentPunches, setRecentPunches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [liveConnected, setLiveConnected] = useState(false);
  const live = useRef(false);
  const queuedRefresh = useRef(false);

  const isWarden = user?.role === 'WARDEN';
  const request = useRef(null);
  const mounted = useRef(true);

  const fetchDashboardData = async (isBackground = false) => {
    if (request.current) { queuedRefresh.current = true; return; }
    const controller = new AbortController();
    request.current = controller;
    if (!isBackground) setIsRefreshing(true);
    try {
      const [sumRes, hosRes, pRes] = await Promise.allSettled([
        api.get('/dashboard/summary', { signal: controller.signal }),
        api.get('/dashboard/hostels', { signal: controller.signal }),
        api.get('/punches/processed?limit=10', { signal: controller.signal })
      ]);
      if (!mounted.current || controller.signal.aborted) return;

      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
      const complete = [sumRes, hosRes, pRes].every(result => result.status === 'fulfilled');
      setLoadError(complete ? '' : 'Some dashboard data could not refresh. Displayed values may be outdated.');
      if (complete) setLastUpdated(new Date());
      if (hosRes.status === 'fulfilled') setHostels(hosRes.value.data);
      if (pRes.status === 'fulfilled') setRecentPunches(pRes.value.data);
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
    } finally {
      if (request.current === controller) request.current = null;
      if (mounted.current && !controller.signal.aborted) {
        setLoading(false);
        setIsRefreshing(false);
        if (queuedRefresh.current) {
          queuedRefresh.current = false;
          fetchDashboardData(true);
        }
      }
    }
  };

  useEffect(() => {
    mounted.current = true;
    fetchDashboardData();
    const disconnect = connectDashboardLive(() => fetchDashboardData(true), connected => {
      live.current = connected;
      if (mounted.current) setLiveConnected(connected);
    });
    // Ten-second fallback only while push is disconnected.
    const interval = setInterval(() => { if (!live.current) fetchDashboardData(true); }, 10000);
    return () => {
      mounted.current = false;
      disconnect();
      clearInterval(interval);
      request.current?.abort();
      request.current = null;
    };
  }, []);

  const pendingCount = summary?.pending_enrollments ?? 0;

  return (
    <div className="p-6 space-y-6">
      {loadError && <div role="alert" className="rounded border border-rose-300 bg-rose-50 p-3 text-rose-700">{loadError}</div>}
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Attendance Overview</h1>
          <p className="text-sm font-medium text-slate-600 mt-1">Real-time Biometric Punch & Student Status Monitoring</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:gap-4 xl:justify-end">
          <div className="space-y-1">
            <p className={`flex items-center gap-2 text-xs font-semibold ${liveConnected ? 'text-emerald-700' : 'text-amber-700'}`}>
              <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${liveConnected ? 'bg-emerald-500' : 'bg-amber-500'}`} />
              {liveConnected ? 'Live updates connected' : 'Live updates disconnected'}
            </p>
            <p className="text-xs text-slate-500 tabular-nums">
              {lastUpdated ? `Last updated ${formatIndiaTime(lastUpdated)}` : 'Waiting for first update'}
            </p>
            {!liveConnected && <p className="text-xs text-slate-500">Refreshing every 10 seconds</p>}
          </div>
          <button
          onClick={() => fetchDashboardData(false)}
          className="flex shrink-0 items-center gap-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-sm font-bold px-4 py-2 rounded-lg transition border border-indigo-200 shadow-sm"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh Data'}
          </button>
        </div>
      </div>

      {/* Action Required Banner for Pending Enrollments */}
      {pendingCount > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm animate-fade-in">
          <div className="flex items-center gap-3.5">
            <div className="p-3 bg-amber-500 text-white rounded-xl shadow-sm flex-shrink-0">
              <UserPlus className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-amber-950 flex items-center gap-2">
                Action Required: {pendingCount} Student{pendingCount > 1 ? 's' : ''} Awaiting Formal Enrollment
                <span className="bg-amber-200 text-amber-900 text-xs font-bold px-2.5 py-0.5 rounded-full border border-amber-300">New Catch</span>
              </h3>
              <p className="text-sm font-medium text-amber-800 mt-0.5">
                First-time biometric punches have been logged. Please assign their official name and room to activate them on the live headcount dashboard.
              </p>
            </div>
          </div>
          <Link
            to="/student-registration"
            className="flex items-center gap-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-bold px-4 py-2.5 rounded-lg transition shadow-md whitespace-nowrap"
          >
            Complete Registration
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      )}

      {/* Top Stat Cards */}
      <div className={`grid grid-cols-1 md:grid-cols-2 ${isWarden ? 'lg:grid-cols-5' : 'lg:grid-cols-6'} gap-4`}>
        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
          <div className="p-3 bg-blue-50 text-blue-600 rounded-xl border border-blue-100">
            <Users className="w-7 h-7" />
          </div>
          <div>
            <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">Enrolled Students</p>
            <h3 className="text-3xl font-black text-slate-900 mt-0.5">
              {loading && !summary ? <span className="animate-pulse text-slate-300">...</span> : (summary?.total_students ?? 0)}
            </h3>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
          <div className="p-3 bg-emerald-50 text-emerald-600 rounded-xl border border-emerald-100">
            <LogIn className="w-7 h-7" />
          </div>
          <div>
            <p className="text-xs font-bold text-emerald-800 uppercase tracking-wider">Currently IN</p>
            <h3 className="text-3xl font-black text-emerald-600 mt-0.5">
              {loading && !summary ? <span className="animate-pulse text-slate-300">...</span> : (summary?.currently_in ?? 0)}
            </h3>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
          <div className="p-3 bg-amber-50 text-amber-600 rounded-xl border border-amber-100">
            <LogOut className="w-7 h-7" />
          </div>
          <div>
            <p className="text-xs font-bold text-amber-800 uppercase tracking-wider">Currently OUT</p>
            <h3 className="text-3xl font-black text-amber-600 mt-0.5">
              {loading && !summary ? <span className="animate-pulse text-slate-300">...</span> : (summary?.currently_out ?? 0)}
            </h3>
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
          <div className="p-3 bg-purple-50 text-purple-600 rounded-xl border border-purple-100">
            <Clock className="w-7 h-7" />
          </div>
          <div>
            <p className="text-xs font-bold text-purple-800 uppercase tracking-wider">Not Started</p>
            <h3 className="text-3xl font-black text-purple-600 mt-0.5">
              {loading && !summary ? <span className="animate-pulse text-slate-300">...</span> : (summary?.not_started ?? 0)}
            </h3>
          </div>
        </div>

        {/* Pending Enrollment Card */}
        <Link
          to="/student-registration"
          className={`bg-white p-5 rounded-xl shadow-sm border transition flex items-center gap-4 ${
            pendingCount > 0
              ? 'border-amber-400 hover:border-amber-500 bg-amber-50/40 shadow-amber-100'
              : 'border-slate-200 hover:border-slate-300'
          }`}
        >
          <div className={`p-3 rounded-xl border ${pendingCount > 0 ? 'bg-amber-100 text-amber-700 border-amber-200' : 'bg-slate-100 text-slate-500 border-slate-200'}`}>
            <UserPlus className="w-7 h-7" />
          </div>
          <div>
            <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">Pending</p>
            <h3 className={`text-3xl font-black mt-0.5 ${pendingCount > 0 ? 'text-amber-600' : 'text-slate-700'}`}>
              {loading && !summary ? <span className="animate-pulse text-slate-300">...</span> : pendingCount}
            </h3>
          </div>
        </Link>

        {!isWarden && (
          <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
            <div className="p-3 bg-rose-50 text-rose-600 rounded-xl border border-rose-100">
              <AlertCircle className="w-7 h-7" />
            </div>
            <div>
              <p className="text-xs font-bold text-rose-800 uppercase tracking-wider">Inactive</p>
              <h3 className="text-3xl font-black text-rose-600 mt-0.5">
                {loading && !summary ? <span className="animate-pulse text-slate-300">...</span> : (summary?.inactive_students ?? 0)}
              </h3>
            </div>
          </div>
        )}
      </div>

      {/* Today's Activity Summary & Hostel Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Hostel Summary Breakdown Cards */}
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
          <h2 className="text-base font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-2.5">
            <Building2 className="w-5 h-5 text-indigo-600" />
            Hostel-wise Status Summary
          </h2>

          {loading && hostels.length === 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2].map((i) => (
                <div key={i} className="bg-slate-50 p-4 rounded-xl border border-slate-200 h-28 animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {hostels.map((h) => (
                <div key={h.HostelId} className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-3 shadow-sm">
                  <div className="flex items-center justify-between border-b border-slate-200 pb-2.5">
                    <span className="font-extrabold text-slate-900 text-base">{cleanDisplayText(h.HostelName)}</span>
                    <div className="flex items-center gap-2">
                      {h.pending_enrollments > 0 && (
                        <span className="text-xs font-bold bg-amber-100 text-amber-900 px-2.5 py-0.5 rounded-full border border-amber-300">
                          {h.pending_enrollments} Pending
                        </span>
                      )}
                      <span className="text-sm font-mono font-extrabold text-slate-700 bg-white border border-slate-200 px-2 py-0.5 rounded-md">{h.total_students} Active</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="bg-emerald-100/70 border border-emerald-200/80 p-2.5 rounded-lg">
                      <p className="text-xs text-emerald-800 font-extrabold uppercase">IN</p>
                      <p className="font-black text-emerald-900 text-base mt-0.5">{h.currently_in}</p>
                    </div>
                    <div className="bg-amber-100/70 border border-amber-200/80 p-2.5 rounded-lg">
                      <p className="text-xs text-amber-800 font-extrabold uppercase">OUT</p>
                      <p className="font-black text-amber-900 text-base mt-0.5">{h.currently_out}</p>
                    </div>
                    <div className="bg-purple-100/70 border border-purple-200/80 p-2.5 rounded-lg">
                      <p className="text-xs text-purple-800 font-extrabold uppercase">Unstarted</p>
                      <p className="font-black text-purple-900 text-base mt-0.5">{h.not_started}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Live Punches Stream Feed */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
          <h2 className="text-base font-extrabold text-slate-900 uppercase tracking-wider flex items-center justify-between">
            <span className="flex items-center gap-2.5">
              <Activity className="w-5 h-5 text-indigo-600" />
              Live Biometric Punches
            </span>
            <span className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 bg-emerald-100/80 border border-emerald-200 px-2.5 py-1 rounded-full">
              <span className={`w-2 h-2 rounded-full ${liveConnected ? 'bg-emerald-500 animate-ping' : 'bg-amber-500'}`} /> {liveConnected ? 'Live' : 'Polling'}
            </span>
          </h2>

          <div className="space-y-2.5 max-h-[360px] overflow-y-auto pr-1">
            {recentPunches.length === 0 ? (
              <p className="text-sm font-semibold text-slate-400 text-center py-8">No biometric punches logged today.</p>
            ) : (
              recentPunches.map((p) => {
                const isDuplicate = p.ProcessingStatus === 'DUPLICATE';
                const isInvalid = p.ProcessingStatus === 'INVALID_DEVICE' || p.ProcessingStatus === 'INACTIVE_STUDENT';
                const punchLabel = isDuplicate ? 'DUPLICATE' : (isInvalid ? p.ProcessingStatus : (p.PunchType || p.ProcessingStatus));

                const badgeClass = isDuplicate
                  ? 'bg-slate-200 text-slate-800 border border-slate-300'
                  : isInvalid
                  ? 'bg-rose-100 text-rose-900 border border-rose-300'
                  : p.PunchType === 'IN'
                  ? 'bg-emerald-100 text-emerald-900 border border-emerald-300'
                  : p.PunchType === 'OUT'
                  ? 'bg-amber-100 text-amber-900 border border-amber-300'
                  : 'bg-indigo-100 text-indigo-900 border border-indigo-300';

                return (
                  <div key={p.PunchId} className="flex items-center justify-between p-3 bg-slate-50 hover:bg-slate-100 rounded-xl border border-slate-200 transition shadow-sm">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-900 text-sm">
                          {cleanDisplayText(p.StudentName) || <span className="text-amber-800 font-bold">Unregistered Card</span>}
                        </span>
                        <span className="font-mono text-xs text-indigo-700 bg-indigo-50 border border-indigo-200 px-1.5 py-0.5 rounded font-bold">
                          {p.UserId}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-slate-600">
                        <span>{cleanDisplayText(p.DeviceName) || `Device ${p.DeviceId}`}</span>
                        <time dateTime={p.LogDate} className="tabular-nums text-slate-500">{formatIndiaTime(p.LogDate, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>
                      </div>
                    </div>
                    <span className={`px-3 py-1 rounded-md text-xs font-black uppercase tracking-wider shrink-0 ${badgeClass}`}>
                      {punchLabel}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
