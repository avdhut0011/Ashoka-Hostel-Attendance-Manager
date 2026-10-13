import { cleanDisplayText } from '../services/displayText';
import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { UserPlus, Edit, Trash2, ShieldCheck, CheckCircle, XCircle, RefreshCw, Search, Users as UsersIcon, ShieldAlert, Key, RotateCcw } from 'lucide-react';

const Users = () => {
  const { user } = useAuth();
  const { showSuccess, showError, showWarning } = useToast();
  const [users, setUsers] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  
  // Search & Filter
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');

  // Modal State
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  // Form states
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('WARDEN');
  const [hostelId, setHostelId] = useState('');

  const fetchUsers = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await api.get('/users');
      setUsers(res.data);
    } catch (err) {
      console.error('Error fetching users:', err);
      const msg = err.response?.data?.detail || 'Failed to load user accounts. Please check your credentials.';
      setErrorMsg(msg);
      showError(msg);
    } finally {
      setLoading(false);
    }
  };

  const fetchHostels = async () => {
    try {
      const res = await api.get('/hostels');
      setHostels(res.data);
    } catch (err) {
      console.error('Error fetching hostels:', err);
    }
  };

  useEffect(() => {
    fetchUsers();
    fetchHostels();
  }, []);

  const openCreateModal = () => {
    setEditingUser(null);
    setUsername('');
    setPassword('');
    setRole('WARDEN');
    setHostelId('');
    setShowModal(true);
  };

  const openEditModal = (u) => {
    setEditingUser(u);
    setUsername(u.Username);
    setPassword(''); // leave empty unless updating
    setRole(u.Role);
    setHostelId(u.HostelId ? u.HostelId.toString() : '');
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (role === 'WARDEN' && !hostelId) {
      showWarning('Select an assigned hostel for the warden account');
      return;
    }
    if ((!editingUser || password) && (password.length < 8 || new TextEncoder().encode(password).length > 72)) {
      showWarning('Password must contain at least 8 characters and no more than 72 UTF-8 bytes');
      return;
    }
    try {
      if (editingUser) {
        const updatePayload = {
          username,
          role,
          hostel_id: role === 'WARDEN' && hostelId ? parseInt(hostelId) : null,
        };
        if (password) updatePayload.password = password;

        await api.put(`/users/${editingUser.SystemUserId}`, updatePayload);
        showSuccess(`User account '${username}' updated successfully!`);
      } else {
        if (!password) {
          showWarning('Password is required when creating a new user account');
          return;
        }
        await api.post('/users', {
          username,
          password,
          role,
          hostel_id: role === 'WARDEN' && hostelId ? parseInt(hostelId) : null,
        });
        showSuccess(`User account '${username}' created successfully!`);
      }

      setShowModal(false);
      fetchUsers();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map(item => `${item.loc?.filter(part => part !== 'body').join('.') || 'Account'}: ${item.msg}`).join('; ')
        : typeof detail === 'string' ? detail : 'Failed to save user account';
      showError(message);
    }
  };

  const handleToggleStatus = async (u) => {
    const actionText = u.IsActive ? 'deactivate' : 'activate';
    try {
      await api.put(`/users/${u.SystemUserId}/status`, { is_active: !u.IsActive });
      showSuccess(`User account '${u.Username}' ${u.IsActive ? 'deactivated' : 'activated'} successfully!`);
      fetchUsers();
    } catch (err) {
      showError(err.response?.data?.detail || `Failed to ${actionText} user account`);
    }
  };

  // Filtered users
  const filteredUsers = users.filter((u) => {
    const matchesSearch = search ? u.Username.toLowerCase().includes(search.toLowerCase()) : true;
    const matchesRole = roleFilter ? u.Role === roleFilter : true;
    return matchesSearch && matchesRole;
  });

  const activeCount = users.filter((u) => u.IsActive).length;
  const wardenCount = users.filter((u) => u.Role === 'WARDEN' && u.IsActive).length;

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-indigo-600" />
            User Account Management
          </h1>
          <p className="text-sm font-semibold text-slate-600 mt-1">
            Manage System Accounts, Passwords, Role Privileges & Hostel Scopes
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchUsers}
            disabled={loading}
            className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-sm font-bold px-3.5 py-2 rounded-lg transition disabled:opacity-50 border border-slate-300"
            title="Refresh Users List"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
          {user?.role === 'ADMIN' && (
            <button
              onClick={openCreateModal}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold px-4 py-2 rounded-lg transition shadow"
            >
              <UserPlus className="w-4 h-4" />
              Create New User
            </button>
          )}
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">Total Accounts</p>
            <h3 className="text-2xl font-black text-slate-900 mt-1">{users.length}</h3>
          </div>
          <div className="p-3 bg-indigo-50 text-indigo-700 rounded-lg">
            <UsersIcon className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">Active Users</p>
            <h3 className="text-2xl font-black text-emerald-600 mt-1">{activeCount}</h3>
          </div>
          <div className="p-3 bg-emerald-50 text-emerald-700 rounded-lg">
            <CheckCircle className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">Active Wardens</p>
            <h3 className="text-2xl font-black text-amber-600 mt-1">{wardenCount}</h3>
          </div>
          <div className="p-3 bg-amber-50 text-amber-700 rounded-lg">
            <ShieldCheck className="w-6 h-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 flex items-center justify-between">
          <div>
            <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">Deactivated</p>
            <h3 className="text-2xl font-black text-rose-600 mt-1">{users.length - activeCount}</h3>
          </div>
          <div className="p-3 bg-rose-50 text-rose-700 rounded-lg">
            <XCircle className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {errorMsg && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl text-sm flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 text-rose-600 shrink-0" />
          <div>
            <p className="font-bold">Access Restricted / Error Loading Users</p>
            <p className="font-medium">{errorMsg}</p>
          </div>
        </div>
      )}

      {/* Search & Filter Bar */}
      <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
          <input
            type="text"
            placeholder="Search by Username..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-900 font-medium placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="border border-slate-300 rounded-lg text-sm text-slate-900 font-semibold py-2 px-3 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          <option value="">All Roles</option>
          <option value="ADMIN">ADMIN</option>
          <option value="WARDEN">WARDEN</option>
          <option value="IT_ADMIN">IT_ADMIN</option>
          <option value="MANAGEMENT">MANAGEMENT</option>
        </select>

        {(search || roleFilter) && (
          <button
            onClick={() => {
              setSearch('');
              setRoleFilter('');
            }}
            className="flex items-center gap-1.5 text-sm font-bold px-3.5 py-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 transition shadow-sm"
            title="Reset and clear all filters"
          >
            <RotateCcw className="w-4 h-4" />
            Clear Filters
          </button>
        )}
      </div>

      {/* Users Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-500 font-semibold text-sm flex flex-col items-center gap-2">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-600" />
            Loading system user accounts...
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-100/90 text-slate-800 uppercase text-xs font-extrabold tracking-wider border-b border-slate-200">
              <tr>
                <th className="p-3.5">User ID</th>
                <th className="p-3.5">Username</th>
                <th className="p-3.5">Assigned Role</th>
                <th className="p-3.5">Assigned Hostel Scope</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-slate-900 font-medium">
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500 font-semibold text-sm">
                    No user accounts found matching your search query.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((u) => (
                  <tr key={u.SystemUserId} className="hover:bg-slate-50 transition-colors">
                    <td className="p-3.5 font-mono font-bold text-slate-700">{u.SystemUserId}</td>
                    <td className="p-3.5 font-bold text-slate-900 flex items-center gap-2">
                      <Key className="w-4 h-4 text-slate-400" />
                      {u.Username}
                    </td>
                    <td className="p-3.5">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                        u.Role === 'ADMIN' ? 'bg-purple-100 text-purple-900 border border-purple-200' :
                        u.Role === 'IT_ADMIN' ? 'bg-blue-100 text-blue-900 border border-blue-200' :
                        u.Role === 'WARDEN' ? 'bg-amber-100 text-amber-900 border border-amber-200' : 'bg-emerald-100 text-emerald-900 border border-emerald-200'
                      }`}>
                        {u.Role}
                      </span>
                    </td>
                    <td className="p-3.5">
                      {u.Role === 'WARDEN' ? (
                        <span className="font-bold text-slate-800">{cleanDisplayText(u.HostelName) || `Hostel ${u.HostelId}`}</span>
                      ) : (
                        <span className="text-slate-500 font-medium italic">Global System Scope</span>
                      )}
                    </td>
                    <td className="p-3.5">
                      {u.IsActive ? (
                        <span className="inline-flex items-center gap-1.5 text-emerald-700 font-bold text-xs bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200">
                          <CheckCircle className="w-4 h-4" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-rose-700 font-bold text-xs bg-rose-50 px-2.5 py-1 rounded border border-rose-200">
                          <XCircle className="w-4 h-4" /> Deactivated
                        </span>
                      )}
                    </td>
                    <td className="p-3.5 text-right space-x-2">
                      {user?.role === 'ADMIN' ? (
                        <>
                          <button
                            onClick={() => openEditModal(u)}
                            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition"
                            title="Edit Credentials & Role"
                          >
                            <Edit className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleToggleStatus(u)}
                            className={`p-2 rounded-lg transition ${
                              u.IsActive
                                ? 'bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200'
                                : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200'
                            }`}
                            title={u.IsActive ? 'Deactivate User Account' : 'Reactivate User Account'}
                          >
                            {u.IsActive ? <Trash2 className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                          </button>
                        </>
                      ) : (
                        <span className="text-slate-400 text-xs italic font-medium">Read-Only</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal for Create / Edit User */}
      {showModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-5 border border-slate-200">
            <div className="flex justify-between items-center border-b border-slate-200 pb-3">
              <h3 className="font-black text-slate-900 text-lg">
                {editingUser ? `Edit Account: ${editingUser.Username}` : 'Create New User Account'}
              </h3>
              <button type="button" onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700 text-2xl font-bold leading-none">×</button>
            </div>

            <div className="space-y-4 text-sm">
              <div>
                <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">Username *</label>
                <input
                  type="text"
                  required
                  maxLength={100}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg p-2.5 text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  placeholder="e.g. warden_boys_a"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">
                  Password {editingUser && <span className="font-normal normal-case text-slate-500">(Leave blank to keep unchanged)</span>}
                </label>
                <input
                  type="password"
                  required={!editingUser}
                  minLength={8}
                  maxLength={72}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg p-2.5 text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  placeholder="Password"
                />
                <p className="mt-1 text-xs text-slate-500">At least 8 characters, up to 72 UTF-8 bytes.</p>
              </div>

              <div>
                <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">Select System Role</label>
                <select
                  value={role}
                  onChange={(e) => {
                    setRole(e.target.value);
                    if (e.target.value !== 'WARDEN') setHostelId('');
                  }}
                  className="w-full border border-slate-300 rounded-lg p-2.5 text-slate-900 font-semibold focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                >
                  <option value="ADMIN">ADMIN (Full Control)</option>
                  <option value="WARDEN">WARDEN (Assigned Hostel and Student Enrollment)</option>
                  <option value="IT_ADMIN">IT_ADMIN (Devices, Hostels & Student Registration)</option>
                  <option value="MANAGEMENT">MANAGEMENT (Global Read-Only Reports)</option>
                </select>
                {role !== 'WARDEN' && <p className="mt-2 text-xs text-slate-500">This role has access across hostels. No hostel assignment is required.</p>}
              </div>

              {role === 'WARDEN' && (
                <div>
                  <label htmlFor="user-hostel-scope" className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">Assigned Hostel (Required)</label>
                  <select
                    id="user-hostel-scope"
                    required={role === 'WARDEN'}
                    value={hostelId}
                    onChange={(e) => setHostelId(e.target.value)}
                    className="w-full border border-slate-300 rounded-lg p-2.5 text-slate-900 font-semibold focus:ring-2 focus:ring-indigo-500 focus:outline-none bg-white"
                  >
                    <option value="">Select Hostel...</option>
                    {hostels.filter((h) => h.IsActive).map((h) => (
                      <option key={h.HostelId} value={h.HostelId}>{cleanDisplayText(h.HostelName)}</option>
                    ))}
                  </select>
                </div>
              )}
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
                {editingUser ? 'Update Account' : 'Create Account'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};

export default Users;
