import { cleanDisplayText } from '../services/displayText';
import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Building2, Plus, Edit, Trash2, CheckCircle, RefreshCw } from 'lucide-react';

const Hostels = () => {
  const { user } = useAuth();
  const { showSuccess, showError } = useToast();
  const [hostels, setHostels] = useState([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingHostel, setEditingHostel] = useState(null);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');

  const isEditor = user?.role === 'ADMIN' || user?.role === 'IT_ADMIN';

  const fetchHostels = async () => {
    setIsRefreshing(true);
    try {
      const res = await api.get('/hostels');
      setHostels(res.data);
    } catch (err) {
      showError('Unable to refresh data. Displayed information may be outdated.');
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchHostels();
  }, []);

  const openCreateModal = () => {
    setEditingHostel(null);
    setName('');
    setCode('');
    setShowModal(true);
  };

  const openEditModal = (h) => {
    setEditingHostel(h);
    setName(h.HostelName);
    setCode(h.HostelCode || '');
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      if (editingHostel) {
        await api.put(`/hostels/${editingHostel.HostelId}`, {
          HostelName: name,
          HostelCode: code,
          IsActive: editingHostel.IsActive
        });
        showSuccess(`Hostel '${name}' updated successfully!`);
      } else {
        await api.post('/hostels', {
          HostelName: name,
          HostelCode: code,
          IsActive: true
        });
        showSuccess(`Hostel '${name}' created successfully!`);
      }
      setShowModal(false);
      fetchHostels();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to save hostel');
    }
  };

  const handleToggleStatus = async (h) => {
    const actionText = h.IsActive ? 'deactivate' : 'activate';
    try {
      await api.put(`/hostels/${h.HostelId}/status`, { is_active: !h.IsActive });
      showSuccess(`Hostel '${cleanDisplayText(h.HostelName)}' ${h.IsActive ? 'deactivated' : 'activated'} successfully!`);
      fetchHostels();
    } catch (err) {
      showError(err.response?.data?.detail || `Failed to ${actionText} hostel`);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-black text-slate-900">Hostels Configuration</h1>
          <p className="text-sm font-semibold text-slate-600 mt-1">Manage Hostel Blocks & Buildings</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchHostels}
            disabled={isRefreshing}
            className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-sm font-bold px-3.5 py-2 rounded-lg transition disabled:opacity-50 border border-slate-300"
            title="Refresh Hostels List"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </button>
          {isEditor && (
            <button
              onClick={openCreateModal}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold px-4 py-2 rounded-lg transition shadow"
            >
              <Plus className="w-4 h-4" />
              Add New Hostel
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {hostels.map((h) => (
          <div key={h.HostelId} className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-indigo-50 text-indigo-700 rounded-lg">
                  <Building2 className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-extrabold text-slate-900 text-base">{cleanDisplayText(h.HostelName)}</h3>
                  <p className="text-xs text-slate-600 font-mono font-bold mt-0.5">Code: {h.HostelCode || 'N/A'}</p>
                </div>
              </div>
              <span className={`px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider ${h.IsActive ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' : 'bg-rose-100 text-rose-900 border border-rose-300'}`}>
                {h.IsActive ? 'ACTIVE' : 'INACTIVE'}
              </span>
            </div>

            {isEditor && (
              <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
                <button
                  onClick={() => openEditModal(h)}
                  className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition"
                  title="Edit Hostel Details"
                >
                  <Edit className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleToggleStatus(h)}
                  className={`p-2 rounded-lg transition ${
                    h.IsActive
                      ? 'bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200'
                      : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200'
                  }`}
                  title={h.IsActive ? 'Deactivate Hostel' : 'Reactivate Hostel'}
                >
                  {h.IsActive ? <Trash2 className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-5 border border-slate-200">
            <h3 className="font-black text-slate-900 text-lg">{editingHostel ? 'Edit Hostel' : 'Add New Hostel'}</h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Hostel Name *</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Hostel C - Senior Block"
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-sm text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Hostel Code *</label>
                <input
                  type="text"
                  required
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="e.g. HC-SENIOR"
                  className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-sm text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                />
              </div>
              <div className="flex justify-end gap-3 pt-3 border-t border-slate-200">
                <button type="button" onClick={() => setShowModal(false)} className="px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 text-sm font-bold rounded-lg transition">Cancel</button>
                <button type="submit" className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-lg shadow transition">
                  {editingHostel ? 'Update Hostel' : 'Save Hostel'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Hostels;
