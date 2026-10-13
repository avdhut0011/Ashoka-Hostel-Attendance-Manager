import { cleanDisplayText } from '../services/displayText';
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import useListState from '../services/useListState';
import DataStatus from '../components/DataStatus';
import { getHostelsCached } from '../services/hostelCache';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { UserPlus, Sparkles, Building2, Clock, CheckCircle, Search, ShieldAlert, AlertTriangle, RotateCcw, RefreshCw } from 'lucide-react';

const StudentRegistration = () => {
  const { user } = useAuth();
  const { showSuccess, showError, showWarning } = useToast();
  const [pendingStudents, setPendingStudents] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Enrollment Modal state
  const [showModal, setShowModal] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [studentName, setStudentName] = useState('');
  const [hostelId, setHostelId] = useState('');
  const [roomNo, setRoomNo] = useState('');

  const isEditor = user?.role === 'ADMIN' || user?.role === 'IT_ADMIN' || user?.role === 'WARDEN';
  const isWarden = user?.role === 'WARDEN';

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(search);
    }, 300);
    return () => clearTimeout(handler);
  }, [search]);

  const loadHostels = async () => {
    try {
      const res = await api.get('/hostels');
      setHostels(res.data);
      return res.data;
    } catch (err) {
      console.error('Error fetching hostels:', err);
      return [];
    }
  };

  const pagination = useListState([debouncedSearch]);

  const fetchPending = async (showRefreshIndicator = true) => {
    const request = pagination.begin();
    if (showRefreshIndicator) setIsRefreshing(true);
    try {
      const res = await api.get('/students', {
        signal: request.signal,
        params: { skip: pagination.skip, limit: pagination.limit,
          pending_enrollment: true,
          search: debouncedSearch,
        },
      });
      if (request.success(res)) setPendingStudents(res.data);
    } catch (err) {
      request.fail(err);
      console.error('Error fetching pending student registrations:', err);
    } finally {
      if (!request.current()) return;
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    loadHostels();
  }, []);

  useEffect(() => {
    fetchPending(false);
  }, [pagination.skip, debouncedSearch]);

  const openEnrollModal = async (s) => {
    setSelectedStudent(s);
    setStudentName(s.StudentName || '');
    setRoomNo(s.RoomNo || '');

    // Refresh hostels directly from API to ensure always up to date
    const latestHostels = await loadHostels();

    if (isWarden && user?.hostel_id) {
      setHostelId(user.hostel_id.toString());
    } else if (s.HostelId) {
      setHostelId(s.HostelId.toString());
    } else if (latestHostels && latestHostels.length === 1) {
      setHostelId(latestHostels[0].HostelId.toString());
    } else {
      setHostelId('');
    }
    setShowModal(true);
  };

  const handleEnrollSubmit = async (e) => {
    e.preventDefault();
    const finalHostelId = (isWarden && user?.hostel_id) ? user.hostel_id : parseInt(hostelId);
    if (!studentName || !finalHostelId) {
      showWarning('Please fill in Student Name and select a Hostel');
      return;
    }

    try {
      await api.put(`/students/${selectedStudent.StudentId}/enroll`, {
        StudentName: studentName,
        HostelId: finalHostelId,
        RoomNo: roomNo,
      });

      showSuccess(`Student ${selectedStudent.UserId} (${studentName}) successfully registered and enrolled!`);
      setShowModal(false);
      fetchPending();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to complete student registration');
    }
  };

  return (
    <div className="p-6 space-y-6">
      <DataStatus pagination={pagination} status={pagination.status} />
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-amber-500" />
            New Student Registration
          </h1>
          <p className="text-sm font-semibold text-slate-600 mt-1">
            Review first-time biometric punches caught from hardware devices and complete student registration details.
          </p>
        </div>
        <button
          onClick={() => fetchPending(true)}
          disabled={isRefreshing}
          className="flex items-center gap-2 text-sm font-bold px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg border border-indigo-200 transition shadow-sm disabled:opacity-50"
          title="Refresh pending registration list"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Info Banner */}
      <div className="bg-gradient-to-r from-amber-50 to-indigo-50 border border-amber-200 p-5 rounded-xl flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-amber-100 text-amber-800 rounded-lg">
            <UserPlus className="w-6 h-6" />
          </div>
          <div>
            <h3 className="font-extrabold text-slate-900 text-base">Automated First-Punch Catch Engine</h3>
            <p className="text-sm font-medium text-slate-700 mt-0.5">
              When an unregistered student punches on any biometric device for the first time, their hardware UserId is caught automatically and their Hostel is auto-mapped from the device.
            </p>
          </div>
        </div>
        <div className="text-right flex-shrink-0 pl-4">
          <span className="text-3xl font-black text-amber-600">{pendingStudents.length}</span>
          <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">Pending Registrations</p>
        </div>
      </div>

      {/* Search Bar */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
          <input
            type="text"
            placeholder="Search by UserId..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-900 font-medium placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        {search && (
          <button
            onClick={() => {
              setSearch('');
              setDebouncedSearch('');
            }}
            className="flex items-center gap-1.5 text-sm font-bold px-3.5 py-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 transition shadow-sm"
          >
            <RotateCcw className="w-4 h-4" />
            Clear Search
          </button>
        )}
      </div>

      {/* Pending Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative">
        {/* Refreshing Progress Bar Indicator */}
        <div className={`h-1 w-full bg-indigo-600 transition-opacity duration-300 ${isRefreshing ? 'opacity-100 animate-pulse' : 'opacity-0'}`} />

        <table className="w-full text-left text-sm">
          <thead className="bg-slate-100/90 text-slate-800 uppercase text-xs font-extrabold tracking-wider border-b border-slate-200">
            <tr>
              <th className="p-3.5">Biometric UserId</th>
              <th className="p-3.5">First Punch Status</th>
              <th className="p-3.5">Auto-Mapped Hostel</th>
              <th className="p-3.5">Registration Status</th>
              <th className="p-3.5 text-right">Action</th>
            </tr>
          </thead>
          <tbody className={`divide-y divide-slate-200 text-slate-900 font-medium transition-opacity duration-200 ${isRefreshing ? 'opacity-50' : 'opacity-100'}`}>
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="p-3.5"><div className="h-4 w-20 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-5 w-36 bg-slate-200 rounded-full"></div></td>
                  <td className="p-3.5"><div className="h-5 w-28 bg-slate-200 rounded-full"></div></td>
                  <td className="p-3.5"><div className="h-4 w-32 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5 text-right"><div className="h-7 w-32 bg-slate-200 rounded inline-block"></div></td>
                </tr>
              ))
            ) : pendingStudents.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-8 text-center text-slate-500 font-semibold text-sm">
                  {search ? 'No pending student registrations match your search.' : 'No pending student registrations found. All first-time punches have been enrolled!'}
                </td>
              </tr>
            ) : (
              pendingStudents.map((s) => (
                <tr key={s.StudentId} className="hover:bg-slate-50 transition-colors">
                  <td className="p-3.5 font-mono font-extrabold text-indigo-700 text-sm">{s.UserId}</td>
                  <td className="p-3.5">
                    <span className="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-900 border border-amber-200 flex items-center gap-1.5 w-fit">
                      <Sparkles className="w-3.5 h-3.5 text-amber-600" /> Unregistered First-Time Punch
                    </span>
                  </td>
                  <td className="p-3.5">
                    {s.HostelName ? (
                      <span className="px-3 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-900 border border-blue-200 flex items-center gap-1.5 w-fit">
                        <Building2 className="w-3.5 h-3.5 text-blue-700" /> {cleanDisplayText(s.HostelName)}
                      </span>
                    ) : (
                      <span className="text-slate-400 text-sm italic font-medium">Unassigned</span>
                    )}
                  </td>
                  <td className="p-3.5 font-semibold text-slate-700">
                    Pending Name & Room Setup
                  </td>
                  <td className="p-3.5 text-right">
                    {isEditor ? (
                      <button
                        onClick={() => openEnrollModal(s)}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs px-3.5 py-2 rounded-lg transition shadow flex items-center gap-1.5 ml-auto"
                      >
                        <UserPlus className="w-4 h-4" />
                        Register & Enroll Student
                      </button>
                    ) : (
                      <span className="text-slate-500 text-xs font-semibold italic flex items-center gap-1 justify-end">
                        <ShieldAlert className="w-4 h-4" /> Read-Only (Admin/IT Admin Only)
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Enrollment Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <form onSubmit={handleEnrollSubmit} className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-5 border border-slate-200">
            <div className="flex justify-between items-center border-b border-slate-200 pb-3">
              <h3 className="font-black text-slate-900 text-lg flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-indigo-600" />
                Enroll Student (UserId: {selectedStudent?.UserId})
              </h3>
              <button type="button" onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700 text-2xl font-bold leading-none">×</button>
            </div>

            <div className="space-y-4 text-sm">
              <div>
                <label className="block font-bold text-slate-800 mb-1.5">Student Full Name *</label>
                <input
                  type="text"
                  required
                  value={studentName}
                  onChange={(e) => setStudentName(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg p-2.5 text-sm text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  placeholder="e.g. Amit Kumar"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 mb-1.5">
                  Assign Hostel Block * {selectedStudent?.HostelId && <span className="text-xs text-indigo-600 font-bold ml-1">(Auto-mapped from Device)</span>}
                </label>
                {hostels.length === 0 ? (
                  <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-lg text-amber-900 text-sm flex flex-col gap-2">
                    <div className="flex items-center gap-2 font-bold">
                      <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                      <span>No Hostels Found in Database</span>
                    </div>
                    <p className="text-xs text-slate-700 font-medium">
                      You must create at least one hostel before assigning students.
                    </p>
                    <Link
                      to="/hostels"
                      className="inline-flex items-center gap-1 text-xs font-bold text-indigo-700 hover:text-indigo-900 underline"
                    >
                      Go to Hostels Configuration &rarr;
                    </Link>
                  </div>
                ) : (
                  <select
                    required
                    value={hostelId}
                    onChange={(e) => setHostelId(e.target.value)}
                    className="w-full border border-slate-300 rounded-lg p-2.5 text-sm text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                  >
                    <option value="">-- Select Assigned Hostel --</option>
                    {hostels.map((h) => (
                      <option key={h.HostelId} value={h.HostelId.toString()}>
                        {cleanDisplayText(h.HostelName)} {h.HostelCode ? `(${h.HostelCode})` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block font-bold text-slate-800 mb-1.5">Room Number</label>
                <input
                  type="text"
                  value={roomNo}
                  onChange={(e) => setRoomNo(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg p-2.5 text-sm text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  placeholder="e.g. A-102"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="px-4 py-2.5 border border-slate-300 rounded-lg text-sm font-bold text-slate-700 hover:bg-slate-100 transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-bold shadow transition"
              >
                Complete Registration
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};

export default StudentRegistration;
