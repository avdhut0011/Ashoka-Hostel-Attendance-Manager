import { cleanDisplayText } from '../services/displayText';
import { formatIndiaDateTime } from '../services/time';
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import useListState from '../services/useListState';
import DataStatus from '../components/DataStatus';
import { getHostelsCached } from '../services/hostelCache';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Search, UserCheck, UserX, History, Edit, Filter, ShieldAlert, UserPlus, Sparkles, ArrowLeftRight, LogIn, LogOut, AlertTriangle, RotateCcw, RefreshCw } from 'lucide-react';

const Students = () => {
  const { user } = useAuth();
  const { showSuccess, showError, showWarning } = useToast();
  const [students, setStudents] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedHostel, setSelectedHostel] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [pendingOnly, setPendingOnly] = useState(false);

  const clearFilters = () => {
    setSearch('');
    setDebouncedSearch('');
    setSelectedHostel('');
    setSelectedStatus('');
    setPendingOnly(false);
  };

  const hasActiveFilters = search || selectedHostel || selectedStatus || pendingOnly;

  // Modals
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [historyPunches, setHistoryPunches] = useState([]);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [assignmentHistory, setAssignmentHistory] = useState(null);
  const [assignmentError, setAssignmentError] = useState('');
  useEffect(() => {
    if (!showHistoryModal || !selectedStudent) return;
    const controller = new AbortController();
    setAssignmentHistory(null); setAssignmentError('');
    api.get(`/students/${selectedStudent.StudentId}/assignment-history`, { signal: controller.signal })
      .then(response => { if (!controller.signal.aborted) setAssignmentHistory(response.data); })
      .catch(error => { if (!controller.signal.aborted) setAssignmentError('Assignment history could not load.'); });
    return () => controller.abort();
  }, [showHistoryModal, selectedStudent?.StudentId]);
  const historyPage = useListState([selectedStudent?.StudentId]);
  useEffect(() => {
    if (!showHistoryModal || !selectedStudent) return;
    const load = historyPage.begin();
    api.get(`/students/${selectedStudent.StudentId}/history`, {
      params: { skip: historyPage.skip, limit: historyPage.limit }, signal: load.signal
    }).then(res => { if (load.success(res)) setHistoryPunches(res.data); }).catch(load.fail);
  }, [showHistoryModal, selectedStudent?.StudentId, historyPage.skip]);

  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [enrollStudentObj, setEnrollStudentObj] = useState(null);
  const [studentName, setStudentName] = useState('');
  const [studentHostelId, setStudentHostelId] = useState('');
  const [studentRoomNo, setStudentRoomNo] = useState('');

  // Attendance Status Override Modal (Admin Only)
  const [showAttendanceModal, setShowAttendanceModal] = useState(false);
  const [targetStudentForAttendance, setTargetStudentForAttendance] = useState(null);
  const [newAttendanceStatus, setNewAttendanceStatus] = useState('IN');
  const [overrideReason, setOverrideReason] = useState('');
  const [savingStatus, setSavingStatus] = useState(false);

  // Deactivate Student Modal (Admin Only)
  const [showDeactivateModal, setShowDeactivateModal] = useState(false);
  const [studentToDeactivate, setStudentToDeactivate] = useState(null);
  const [deactivationReason, setDeactivationReason] = useState('');
  const [isDeactivating, setIsDeactivating] = useState(false);

  // Reactivate Student Modal (Admin Only)
  const [showActivateModal, setShowActivateModal] = useState(false);
  const [studentToActivate, setStudentToActivate] = useState(null);
  const [isActivating, setIsActivating] = useState(false);

  const isEditor = user?.role === 'ADMIN' || user?.role === 'IT_ADMIN' || user?.role === 'WARDEN';
  const isWarden = user?.role === 'WARDEN';

  // 300ms Search Debouncing
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

  const pagination = useListState([debouncedSearch, selectedHostel, selectedStatus, pendingOnly]);

  const fetchStudents = async (showRefreshIndicator = true) => {
    const request = pagination.begin();
    if (showRefreshIndicator) setIsRefreshing(true);
    try {
      const params = { skip: pagination.skip, limit: pagination.limit };
      if (debouncedSearch) params.search = debouncedSearch;
      if (selectedHostel) params.hostel_id = selectedHostel;
      if (selectedStatus) params.status = selectedStatus;
      if (pendingOnly) params.pending_enrollment = true;

      const res = await api.get('/students', { params, signal: request.signal });
      if (request.success(res)) setStudents(res.data);
    } catch (err) {
      request.fail(err);
      console.error('Error fetching students:', err);
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
    fetchStudents(false);
  }, [pagination.skip, debouncedSearch, selectedHostel, selectedStatus, pendingOnly]);

  const openEnrollModal = async (student) => {
    setEnrollStudentObj(student);
    setStudentName(student.StudentName || '');
    setStudentRoomNo(student.RoomNo || '');

    const latestHostels = await loadHostels();
    if (isWarden && user?.hostel_id) {
      setStudentHostelId(user.hostel_id.toString());
    } else if (student.HostelId) {
      setStudentHostelId(student.HostelId.toString());
    } else if (latestHostels && latestHostels.length === 1) {
      setStudentHostelId(latestHostels[0].HostelId.toString());
    } else {
      setStudentHostelId('');
    }
    setShowEnrollModal(true);
  };

  const handleSaveEnrollment = async (e) => {
    e.preventDefault();
    const finalHostelId = (isWarden && user?.hostel_id) ? user.hostel_id : parseInt(studentHostelId);
    if (!studentName || !finalHostelId) {
      showWarning('Please fill in Student Name and select a Hostel');
      return;
    }
    try {
      const requiresEnrollment = enrollStudentObj.RegistrationStatus === 'PENDING_ENROLLMENT' || !enrollStudentObj.StudentName;
      await api.put(`/students/${enrollStudentObj.StudentId}${requiresEnrollment ? '/enroll' : ''}`, {
        StudentName: studentName,
        HostelId: finalHostelId,
        RoomNo: studentRoomNo,
      });
      showSuccess(`Student ${enrollStudentObj.UserId} details saved successfully!`);
      setShowEnrollModal(false);
      fetchStudents();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to enroll student');
    }
  };

  const handleToggleStatus = (student) => {
    if (user?.role !== 'ADMIN') return;
    if (student.RegistrationStatus === 'ACTIVE') {
      setStudentToDeactivate(student);
      setDeactivationReason('');
      setShowDeactivateModal(true);
    } else {
      setStudentToActivate(student);
      setShowActivateModal(true);
    }
  };

  const confirmDeactivation = async (e) => {
    e.preventDefault();
    if (!studentToDeactivate) return;
    if (!deactivationReason.trim()) {
      showWarning('Please provide a valid reason for deactivating this student');
      return;
    }
    setIsDeactivating(true);
    try {
      await api.put(`/students/${studentToDeactivate.StudentId}/status`, {
        RegistrationStatus: 'INACTIVE',
        DeactivationReason: deactivationReason.trim()
      });
      showSuccess(`Student ${studentToDeactivate.UserId} deactivated successfully!`);
      setShowDeactivateModal(false);
      fetchStudents();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to deactivate student');
    } finally {
      setIsDeactivating(false);
    }
  };

  const confirmActivation = async () => {
    if (!studentToActivate) return;
    setIsActivating(true);
    try {
      await api.put(`/students/${studentToActivate.StudentId}/status`, {
        RegistrationStatus: 'ACTIVE',
        DeactivationReason: null
      });
      showSuccess(`Student ${studentToActivate.UserId} reactivated successfully!`);
      setShowActivateModal(false);
      fetchStudents();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to reactivate student');
    } finally {
      setIsActivating(false);
    }
  };

  const openAttendanceModal = (student) => {
    setTargetStudentForAttendance(student);
    setNewAttendanceStatus(student.CurrentStatus === 'IN' ? 'OUT' : 'IN');
    setOverrideReason('');
    setShowAttendanceModal(true);
  };

  const handleSaveAttendanceStatus = async (e) => {
    e.preventDefault();
    if (!targetStudentForAttendance) return;
    setSavingStatus(true);
    try {
      await api.put(`/students/${targetStudentForAttendance.StudentId}/attendance-status`, {
        CurrentStatus: newAttendanceStatus,
        Reason: overrideReason || 'Manual status override by Admin'
      });
      showSuccess(`Student ${targetStudentForAttendance.UserId} status updated to ${newAttendanceStatus}!`);
      setShowAttendanceModal(false);
      fetchStudents();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to update attendance status');
    } finally {
      setSavingStatus(false);
    }
  };

  const handleViewHistory = async (student) => {
    setHistoryPunches([]);
    historyPage.setSkip(0);
    setSelectedStudent(student);
    setShowHistoryModal(true);
  };

  return (
    <div className="p-6 space-y-6">
      <DataStatus pagination={pagination} status={pagination.status} />
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Student Directory & Enrollment</h1>
          <p className="text-xs text-gray-500 mt-1">Manage Profiles, First-Time Punch Registrations & Hostel Assignments</p>
        </div>
        <button
          onClick={() => fetchStudents(true)}
          disabled={isRefreshing}
          className="flex items-center gap-1.5 text-xs font-semibold px-3.5 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg border border-indigo-200 transition shadow-sm disabled:opacity-50"
          title="Refresh student directory"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          {isRefreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Search & Filter Bar */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
          <input
            type="text"
            placeholder="Search by UserId or Student Name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-900 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <select
          value={selectedHostel}
          onChange={(e) => setSelectedHostel(e.target.value)}
          className="border border-slate-300 rounded-lg text-sm font-semibold text-slate-800 py-2 px-3.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          <option value="">All Hostels</option>
          {hostels.map((h) => (
            <option key={h.HostelId} value={h.HostelId}>{cleanDisplayText(h.HostelName)}</option>
          ))}
        </select>

        <select
          value={selectedStatus}
          onChange={(e) => setSelectedStatus(e.target.value)}
          className="border border-slate-300 rounded-lg text-sm font-semibold text-slate-800 py-2 px-3.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          <option value="">All Registration Statuses</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="INACTIVE">INACTIVE</option>
        </select>

        <button
          onClick={() => setPendingOnly(!pendingOnly)}
          className={`flex items-center gap-2 text-sm font-bold px-3.5 py-2 rounded-lg border transition ${
            pendingOnly ? 'bg-amber-100 border-amber-300 text-amber-900 shadow-sm' : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'
          }`}
        >
          <Sparkles className="w-4 h-4 text-amber-500" />
          {pendingOnly ? 'Showing First-Time Punches' : 'Filter First-Time Punches'}
        </button>

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1.5 text-sm font-bold px-3.5 py-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 transition shadow-sm"
            title="Reset and clear all filters"
          >
            <RotateCcw className="w-4 h-4" />
            Clear Filters
          </button>
        )}
      </div>

      {/* Student Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative">
        {/* Refreshing Progress Bar Indicator */}
        <div className={`h-1 w-full bg-indigo-500 transition-opacity duration-300 ${isRefreshing ? 'opacity-100 animate-pulse' : 'opacity-0'}`} />

        <table className="w-full text-left text-sm">
          <thead className="bg-slate-100/90 text-slate-800 uppercase text-xs font-extrabold border-b border-slate-200 tracking-wider">
            <tr>
              <th className="p-3.5">User ID</th>
              <th className="p-3.5">Student Name</th>
              <th className="p-3.5">Hostel & Room</th>
              <th className="p-3.5">Registration Status</th>
              <th className="p-3.5">Current Location</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className={`divide-y divide-slate-100 text-slate-900 transition-opacity duration-200 ${isRefreshing ? 'opacity-50' : 'opacity-100'}`}>
            {loading ? (
              Array.from({ length: 6 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  <td className="p-3.5"><div className="h-4 w-16 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-32 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-28 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-4 w-16 bg-slate-200 rounded"></div></td>
                  <td className="p-3.5"><div className="h-5 w-20 bg-slate-200 rounded-full"></div></td>
                  <td className="p-3.5 text-right"><div className="h-6 w-20 bg-slate-200 rounded inline-block"></div></td>
                </tr>
              ))
            ) : students.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-500 font-semibold text-base">
                  {hasActiveFilters ? 'No students match your selected filters.' : 'No students found in the database.'}
                </td>
              </tr>
            ) : (
              students.map((s) => {
              const needsEnrollment = s.RegistrationStatus === 'PENDING_ENROLLMENT' || !s.StudentName;
              return (
                <tr key={s.StudentId} className="hover:bg-slate-50/80 transition">
                  <td className="p-3.5 font-mono font-extrabold text-indigo-700">{s.UserId}</td>
                  <td className="p-3.5">
                    {s.StudentName ? (
                      <span className="font-bold text-slate-900">{cleanDisplayText(s.StudentName)}</span>
                    ) : (
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1 w-fit">
                        <Sparkles className="w-3.5 h-3.5 text-amber-600" /> First-Time Punched (Unregistered)
                      </span>
                    )}
                  </td>
                  <td className="p-3.5 font-semibold text-slate-800">
                    {s.HostelId ? `Hostel ${s.HostelId}` : <span className="text-slate-400 italic">Unassigned Hostel</span>} {s.RoomNo ? `(Room ${s.RoomNo})` : ''}
                  </td>
                  <td className="p-3.5">
                    <span className={`px-2.5 py-0.5 rounded text-xs font-bold ${
                      s.RegistrationStatus === 'ACTIVE' ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' :
                      s.RegistrationStatus === 'PENDING_ENROLLMENT' ? 'bg-amber-100 text-amber-900 border border-amber-300' :
                      'bg-rose-100 text-rose-900 border border-rose-300'
                    }`}>
                      {s.RegistrationStatus === 'PENDING_ENROLLMENT' ? 'PENDING ENROLLMENT' : s.RegistrationStatus}
                    </span>
                  </td>
                  <td className="p-3.5">
                    {s.RegistrationStatus === 'PENDING_ENROLLMENT' ? (
                      <span className="px-3 py-1 rounded-md text-xs font-black bg-amber-100 text-amber-900 border border-amber-300 uppercase tracking-wide">
                        PENDING ENROLLMENT
                      </span>
                    ) : s.RegistrationStatus === 'INACTIVE' ? (
                      <span className="px-3 py-1 rounded-md text-xs font-black bg-slate-200 text-slate-700 border border-slate-300 uppercase tracking-wide">
                        INACTIVE
                      </span>
                    ) : user?.role === 'ADMIN' ? (
                      <button
                        onClick={() => openAttendanceModal(s)}
                        className={`group px-3 py-1 rounded-md text-xs font-black flex items-center gap-1.5 shadow-sm transition hover:ring-2 hover:ring-offset-1 cursor-pointer uppercase tracking-wider ${
                          s.CurrentStatus === 'IN' ? 'bg-emerald-600 text-white hover:ring-emerald-400' :
                          s.CurrentStatus === 'OUT' ? 'bg-amber-600 text-white hover:ring-amber-400' :
                          'bg-indigo-600 text-white hover:ring-indigo-400'
                        }`}
                        title="Admin: Click to edit attendance status"
                      >
                        <span>{s.CurrentStatus || 'REGISTRATION'}</span>
                        <Edit className="w-3 h-3 opacity-75 group-hover:opacity-100" />
                      </button>
                    ) : (
                      <span className={`px-3 py-1 rounded-md text-xs font-black uppercase tracking-wider ${
                        s.CurrentStatus === 'IN' ? 'bg-emerald-600 text-white' :
                        s.CurrentStatus === 'OUT' ? 'bg-amber-600 text-white' :
                        'bg-indigo-600 text-white'
                      }`}>
                        {s.CurrentStatus || 'REGISTRATION'}
                      </span>
                    )}
                  </td>
                  <td className="p-3.5 text-right space-x-2">
                    {/* 1. History Option (Always Available) */}
                    <button
                      onClick={() => handleViewHistory(s)}
                      className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition border border-slate-200 shadow-sm"
                      title="View Punch History"
                    >
                      <History className="w-4 h-4" />
                    </button>

                    {/* Active-only options: Edit Attendance Status & Enroll / Edit Student Details */}
                    {s.RegistrationStatus === 'ACTIVE' && (
                      <>
                        {user?.role === 'ADMIN' && (
                          <button
                            onClick={() => openAttendanceModal(s)}
                            className="p-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg transition border border-indigo-200 shadow-sm"
                            title="Admin: Edit Attendance Status (IN/OUT)"
                          >
                            <ArrowLeftRight className="w-4 h-4" />
                          </button>
                        )}

                        {isEditor && (
                          <button
                            onClick={() => openEnrollModal(s)}
                            className={`p-2 rounded-lg transition border shadow-sm ${
                              needsEnrollment ? 'bg-indigo-600 text-white hover:bg-indigo-700 font-bold px-3 flex items-center gap-1.5 inline-flex' : 'bg-slate-100 hover:bg-slate-200 text-slate-800 border-slate-200'
                            }`}
                            title={needsEnrollment ? 'Enroll Student Details' : 'Edit Student Details'}
                          >
                            {needsEnrollment ? (
                              <>
                                <UserPlus className="w-4 h-4" />
                                <span>Enroll</span>
                              </>
                            ) : (
                              <Edit className="w-4 h-4" />
                            )}
                          </button>
                        )}
                      </>
                    )}

                    {/* 2. Activate / Deactivate Option */}
                    {user?.role === 'ADMIN' && (
                      <button
                        onClick={() => handleToggleStatus(s)}
                        className={`p-2 rounded-lg transition border shadow-sm ${
                          s.RegistrationStatus === 'ACTIVE'
                            ? 'bg-rose-50 text-rose-600 hover:bg-rose-100 border-rose-200'
                            : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100 border-emerald-200'
                        }`}
                        title={s.RegistrationStatus === 'ACTIVE' ? 'Deactivate Student (Admin Only)' : 'Activate Student (Admin Only)'}
                      >
                        {s.RegistrationStatus === 'ACTIVE' ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
        </table>
      </div>

      {/* Enroll / Edit Modal */}
      {showEnrollModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <form onSubmit={handleSaveEnrollment} className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex justify-between items-center border-b pb-3">
              <h3 className="font-bold text-gray-800 text-base">
                Enroll Student: User {enrollStudentObj?.UserId}
              </h3>
              <button type="button" onClick={() => setShowEnrollModal(false)} className="text-gray-400 hover:text-gray-600 text-lg font-bold">×</button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-gray-700 mb-1">Student Full Name</label>
                <input
                  type="text"
                  required
                  value={studentName}
                  onChange={(e) => setStudentName(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  placeholder="e.g. Rahul Sharma"
                />
              </div>

              <div>
                <label className="block font-semibold text-gray-700 mb-1">
                  Assign Hostel {enrollStudentObj?.HostelId && <span className="text-[10px] text-blue-600 font-normal">(Auto-mapped from Device)</span>}
                </label>
                {hostels.length === 0 ? (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-xs flex flex-col gap-2">
                    <div className="flex items-center gap-1.5 font-bold">
                      <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                      <span>No Hostels Found in Database</span>
                    </div>
                    <p className="text-[11px] text-gray-600">
                      You must create at least one hostel before assigning students.
                    </p>
                    <Link
                      to="/hostels"
                      className="inline-flex items-center gap-1 text-xs font-bold text-indigo-600 hover:text-indigo-800 underline"
                    >
                      Go to Hostels Configuration &rarr;
                    </Link>
                  </div>
                ) : (
                  <select
                    required
                    value={studentHostelId}
                    onChange={(e) => setStudentHostelId(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white text-gray-800"
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
                <label className="block font-semibold text-gray-700 mb-1">Room Number</label>
                <input
                  type="text"
                  value={studentRoomNo}
                  onChange={(e) => setStudentRoomNo(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  placeholder="e.g. B-204"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t pt-4">
              <button
                type="button"
                onClick={() => setShowEnrollModal(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow"
              >
                Save & Complete Enrollment
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Punch History Modal */}
      {showHistoryModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-6 space-y-4 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center border-b pb-3">
              <h3 className="font-bold text-gray-800 text-base">Punch History: {selectedStudent?.UserId} ({cleanDisplayText(selectedStudent?.StudentName) || 'Unregistered'})</h3>
              <button onClick={() => setShowHistoryModal(false)} className="text-gray-400 hover:text-gray-600 text-lg font-bold">×</button>
            </div>
            <DataStatus pagination={historyPage} status={historyPage.status} />
            {assignmentError && <p role="alert" className="text-sm text-red-700">{assignmentError}</p>}
            {assignmentHistory?.verified_room_changes.map((change, index) => <p key={index} className="text-sm rounded bg-indigo-50 p-2">
              Confirmed room change: {change.OldRoomNo} → {change.NewRoomNo} on {change.ChangeDate}.
              {' '}{change.EffectiveAt ? formatIndiaDateTime(change.EffectiveAt) : 'Exact time unknown; punches on this date keep an unknown room unless a snapshot exists.'}
            </p>)}
            <table className="w-full text-left text-xs">
              <thead className="bg-gray-50 text-gray-500 uppercase">
                <tr>
                  <th className="p-2">Timestamp</th>
                  <th className="p-2">Device</th>
                  <th className="p-2">Historical room</th>
                  <th className="p-2">Type</th>
                  <th className="p-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {historyPunches.map((p) => (
                  <tr key={p.PunchId}>
                    <td className="p-2">{formatIndiaDateTime(p.LogDate)}</td>
                    <td className="p-2">Device {p.DeviceId}</td>
                    <td className="p-2">{p.HistoricalRoomNo ?? 'Unknown'}</td>
                    <td className="p-2"><span className="font-bold">{p.PunchType || '-'}</span></td>
                    <td className="p-2"><span className="px-2 py-0.5 rounded text-[10px] bg-gray-100 font-bold">{p.ProcessingStatus}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Attendance Status Override Modal (Admin Only) */}
      {showAttendanceModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <form onSubmit={handleSaveAttendanceStatus} className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-4">
            <div className="flex justify-between items-center border-b pb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                  <ArrowLeftRight className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-gray-800 text-base">Override Attendance Status</h3>
                  <p className="text-xs text-gray-500 font-medium">Admin Privilege Status Edit</p>
                </div>
              </div>
              <button type="button" onClick={() => setShowAttendanceModal(false)} className="text-gray-400 hover:text-gray-600 text-lg font-bold">×</button>
            </div>

            <div className="bg-slate-50 p-3 rounded-lg text-xs space-y-1 border border-slate-200">
              <p className="font-semibold text-gray-800">
                Student: <span className="text-indigo-600 font-mono font-bold">{targetStudentForAttendance?.UserId}</span> - {cleanDisplayText(targetStudentForAttendance?.StudentName) || 'Unnamed'}
              </p>
              <p className="text-gray-600">
                Current Location: <span className="font-bold text-gray-800">{targetStudentForAttendance?.CurrentStatus}</span>
              </p>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-gray-700 mb-1.5">Select New Attendance Status</label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setNewAttendanceStatus('IN')}
                    className={`py-2 px-3 rounded-lg font-bold flex items-center justify-center gap-1.5 border text-xs transition ${
                      newAttendanceStatus === 'IN'
                        ? 'bg-emerald-600 text-white border-emerald-600 shadow'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-emerald-50'
                    }`}
                  >
                    <LogIn className="w-3.5 h-3.5" />
                    <span>Set IN 🟢</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setNewAttendanceStatus('OUT')}
                    className={`py-2 px-3 rounded-lg font-bold flex items-center justify-center gap-1.5 border text-xs transition ${
                      newAttendanceStatus === 'OUT'
                        ? 'bg-amber-600 text-white border-amber-600 shadow'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-amber-50'
                    }`}
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Set OUT 🔴</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setNewAttendanceStatus('REGISTRATION')}
                    className={`py-2 px-3 rounded-lg font-bold flex items-center justify-center gap-1.5 border text-xs transition ${
                      newAttendanceStatus === 'REGISTRATION'
                        ? 'bg-indigo-600 text-white border-indigo-600 shadow'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-indigo-50'
                    }`}
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>REGISTRATION 🔵</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="block font-semibold text-gray-700 mb-1">Reason for Status Change (Audit Log)</label>
                <textarea
                  rows={2}
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none text-xs"
                  placeholder="e.g. Special gate pass, biometric scanner missed, medical appointment..."
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t pt-4">
              <button
                type="button"
                onClick={() => setShowAttendanceModal(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={savingStatus}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow disabled:opacity-50"
              >
                {savingStatus ? 'Updating...' : 'Save & Update Status'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Deactivate Student Modal */}
      {showDeactivateModal && studentToDeactivate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50 animate-fadeIn">
          <form onSubmit={confirmDeactivation} className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4 border border-rose-100">
            <div className="flex items-start gap-3">
              <div className="p-3 bg-rose-100 text-rose-600 rounded-xl flex-shrink-0">
                <ShieldAlert className="w-6 h-6" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-gray-900 text-base">Deactivate Student Profile</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Deactivating will immediately prevent this student from logging valid attendance punches.
                </p>
              </div>
            </div>

            <div className="bg-slate-50 p-3 rounded-xl border border-slate-100 space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">Student User ID:</span>
                <span className="font-mono font-bold text-indigo-600">{studentToDeactivate.UserId}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Student Name:</span>
                <span className="font-semibold text-gray-800">{cleanDisplayText(studentToDeactivate.StudentName) || 'Unregistered / Pending'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Hostel & Room:</span>
                <span className="text-gray-700">Hostel {studentToDeactivate.HostelId || 'N/A'} {studentToDeactivate.RoomNo ? `(Room ${studentToDeactivate.RoomNo})` : ''}</span>
              </div>
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1.5 text-xs">
                Reason for Deactivation <span className="text-rose-500">*</span>
              </label>
              <textarea
                required
                rows={3}
                value={deactivationReason}
                onChange={(e) => setDeactivationReason(e.target.value)}
                placeholder="e.g. Course completed / Graduated, Left hostel accommodation, Transferred to other campus, Disciplinary suspension..."
                className="w-full border border-gray-300 rounded-lg p-2.5 text-xs focus:ring-2 focus:ring-rose-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 border-t pt-4">
              <button
                type="button"
                onClick={() => setShowDeactivateModal(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isDeactivating}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold shadow disabled:opacity-50 flex items-center gap-1.5"
              >
                <UserX className="w-4 h-4" />
                {isDeactivating ? 'Deactivating...' : 'Confirm Deactivation'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Reactivate Student Modal */}
      {showActivateModal && studentToActivate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4 border border-emerald-100">
            <div className="flex items-start gap-3">
              <div className="p-3 bg-emerald-100 text-emerald-600 rounded-xl flex-shrink-0">
                <UserCheck className="w-6 h-6" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-gray-900 text-base">Reactivate Student Profile</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Are you sure you want to reactivate student <span className="font-bold text-gray-800 font-mono">{studentToActivate.UserId}</span> ({cleanDisplayText(studentToActivate.StudentName) || 'Unnamed'})?
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 bg-emerald-50/70 p-3 rounded-xl border border-emerald-100">
              Reactivating will restore this student's active status and enable automatic biometric attendance tracking.
            </p>

            <div className="flex justify-end gap-2 border-t pt-4">
              <button
                type="button"
                onClick={() => setShowActivateModal(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-xs font-semibold text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmActivation}
                disabled={isActivating}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow disabled:opacity-50 flex items-center gap-1.5"
              >
                <UserCheck className="w-4 h-4" />
                {isActivating ? 'Reactivating...' : 'Confirm Activation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Students;
