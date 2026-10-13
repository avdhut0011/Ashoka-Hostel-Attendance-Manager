import { cleanDisplayText } from '../services/displayText';
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Cpu, Plus, Edit, Trash2, CheckCircle, Building2, AlertTriangle, ArrowRight, RefreshCw } from 'lucide-react';

const Devices = () => {
  const { user } = useAuth();
  const { showSuccess, showError, showWarning } = useToast();
  const [devices, setDevices] = useState([]);
  const [hostels, setHostels] = useState([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingDevice, setEditingDevice] = useState(null);

  const [deviceId, setDeviceId] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [hostelId, setHostelId] = useState('');

  const isEditor = user?.role === 'ADMIN' || user?.role === 'IT_ADMIN';

  const fetchData = async () => {
    setIsRefreshing(true);
    try {
      const [dRes, hRes] = await Promise.all([
        api.get('/devices'),
        api.get('/hostels')
      ]);
      setDevices(dRes.data);
      setHostels(hRes.data.filter((h) => h.IsActive));
    } catch (err) {
      showError('Unable to refresh data. Displayed information may be outdated.');
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const openCreateModal = async () => {
    // Refresh hostels to get any newly created hostels immediately
    try {
      const hRes = await api.get('/hostels');
      setHostels(hRes.data.filter((h) => h.IsActive));
    } catch (e) {
      console.error(e);
    }
    setEditingDevice(null);
    setDeviceId('');
    setDeviceName('');
    setHostelId('');
    setShowModal(true);
  };

  const openEditModal = async (d) => {
    try {
      const hRes = await api.get('/hostels');
      setHostels(hRes.data.filter((h) => h.IsActive));
    } catch (e) {
      console.error(e);
    }
    setEditingDevice(d);
    setDeviceId(d.DeviceId.toString());
    setDeviceName(d.DeviceName);
    setHostelId(d.HostelId ? d.HostelId.toString() : '');
    setShowModal(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!hostelId) {
      showWarning('Assigned Hostel is mandatory. Please select a hostel from the list.');
      return;
    }

    try {
      if (editingDevice) {
        await api.put(`/devices/${editingDevice.DeviceId}`, {
          DeviceId: parseInt(deviceId),
          DeviceName: deviceName,
          HostelId: parseInt(hostelId),
          IsActive: editingDevice.IsActive
        });
        showSuccess(`Device ${deviceId} (${deviceName}) updated successfully!`);
      } else {
        await api.post('/devices', {
          DeviceId: parseInt(deviceId),
          DeviceName: deviceName,
          HostelId: parseInt(hostelId),
          IsActive: true
        });
        showSuccess(`Device ${deviceId} (${deviceName}) registered successfully!`);
      }
      setShowModal(false);
      fetchData();
    } catch (err) {
      showError(err.response?.data?.detail || 'Failed to save device');
    }
  };

  const handleToggleStatus = async (d) => {
    const actionText = d.IsActive ? 'deactivate' : 'activate';
    try {
      await api.put(`/devices/${d.DeviceId}/status`, { is_active: !d.IsActive });
      showSuccess(`Device ${d.DeviceId} ${d.IsActive ? 'deactivated' : 'activated'} successfully!`);
      fetchData();
    } catch (err) {
      showError(err.response?.data?.detail || `Failed to ${actionText} device`);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2">
            <Cpu className="w-6 h-6 text-indigo-600" />
            Biometric Devices
          </h1>
          <p className="text-sm font-semibold text-slate-600 mt-1">Manage Hardware Devices & Mandatory Hostel Mapping</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchData}
            disabled={isRefreshing}
            className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-sm font-bold px-3.5 py-2 rounded-lg transition disabled:opacity-50 border border-slate-300"
            title="Refresh Devices List"
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
              Add Device
            </button>
          )}
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-100/90 text-slate-800 uppercase text-xs font-extrabold tracking-wider border-b border-slate-200">
            <tr>
              <th className="p-3.5">Device ID</th>
              <th className="p-3.5">Device Name</th>
              <th className="p-3.5">Assigned Hostel</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 text-slate-900 font-medium">
            {devices.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-8 text-center text-slate-500 font-semibold text-sm">
                  No biometric devices configured yet. Click "Add Device" above to register a scanner.
                </td>
              </tr>
            ) : (
              devices.map((d) => {
                const assignedHostel = d.HostelName || hostels.find((h) => h.HostelId === d.HostelId)?.HostelName;
                return (
                  <tr key={d.DeviceId} className="hover:bg-slate-50 transition-colors">
                    <td className="p-3.5 font-mono font-extrabold text-indigo-700">{d.DeviceId}</td>
                    <td className="p-3.5 font-bold text-slate-900">{cleanDisplayText(d.DeviceName)}</td>
                    <td className="p-3.5 font-medium">
                      {assignedHostel ? (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-indigo-50 text-indigo-800 font-bold border border-indigo-200 text-xs">
                          <Building2 className="w-4 h-4 text-indigo-600" />
                          {cleanDisplayText(assignedHostel)}
                        </span>
                      ) : (
                        <span className="text-amber-800 font-bold bg-amber-50 px-2.5 py-1 rounded border border-amber-200 text-xs">Unassigned</span>
                      )}
                    </td>
                    <td className="p-3.5">
                      <span className={`px-2.5 py-1 rounded text-xs font-black uppercase tracking-wider ${d.IsActive ? 'bg-emerald-100 text-emerald-900 border border-emerald-300' : 'bg-rose-100 text-rose-900 border border-rose-300'}`}>
                        {d.IsActive ? 'ACTIVE' : 'DISABLED'}
                      </span>
                    </td>
                    <td className="p-3.5 text-right space-x-2">
                      {isEditor && (
                        <>
                          <button
                            onClick={() => openEditModal(d)}
                            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg transition"
                            title="Edit Device"
                          >
                            <Edit className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleToggleStatus(d)}
                            className={`p-2 rounded-lg transition ${
                              d.IsActive
                                ? 'bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200'
                                : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200'
                            }`}
                            title={d.IsActive ? 'Deactivate Device' : 'Reactivate Device'}
                          >
                            {d.IsActive ? <Trash2 className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-fadeIn">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-5 border border-slate-200">
            <div className="flex justify-between items-center border-b border-slate-200 pb-3">
              <h3 className="font-black text-slate-900 text-lg">
                {editingDevice ? `Edit Device ${editingDevice.DeviceId}` : 'Register Biometric Device'}
              </h3>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-700 text-2xl font-bold leading-none"
              >
                ×
              </button>
            </div>

            {/* If no hostels in database, show guidance banner */}
            {hostels.length === 0 ? (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl space-y-3">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-amber-100 text-amber-800 rounded-lg flex-shrink-0 mt-0.5">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="font-bold text-amber-900 text-sm">No Hostels Found in Database</h4>
                    <p className="text-xs text-slate-700 mt-1 leading-relaxed font-medium">
                      Every biometric device must be mapped to a specific hostel. Please create a hostel block first before adding devices.
                    </p>
                  </div>
                </div>

                <Link
                  to="/hostels"
                  className="flex items-center justify-center gap-2 w-full bg-amber-600 hover:bg-amber-700 text-white text-sm font-bold py-2.5 px-3 rounded-lg transition shadow-sm"
                >
                  <Building2 className="w-4 h-4" />
                  <span>Go to Hostels Configuration & Add Hostel</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4 text-sm">
                <div>
                  <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">
                    Hardware Device ID <span className="text-rose-600">*</span>
                  </label>
                  <input
                    type="number"
                    required
                    disabled={!!editingDevice}
                    value={deviceId}
                    onChange={(e) => setDeviceId(e.target.value)}
                    placeholder="e.g. 101, 102"
                    className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none disabled:bg-slate-100 font-mono font-bold text-slate-900"
                  />
                  <p className="text-xs text-slate-500 font-medium mt-1">Must match the Device ID configured in eSSL hardware</p>
                </div>

                <div>
                  <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">
                    Device Name / Location <span className="text-rose-600">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={deviceName}
                    onChange={(e) => setDeviceName(e.target.value)}
                    placeholder="e.g. Boys Hostel Main Gate Scanner"
                    className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-slate-900 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-800 uppercase text-xs tracking-wider mb-1.5">
                    Assigned Hostel <span className="text-rose-600">* (Mandatory)</span>
                  </label>
                  <select
                    required
                    value={hostelId}
                    onChange={(e) => setHostelId(e.target.value)}
                    className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none font-semibold text-slate-900 bg-white"
                  >
                    <option value="">-- Select Assigned Hostel (Mandatory) --</option>
                    {hostels.map((h) => (
                      <option key={h.HostelId} value={h.HostelId}>
                        {cleanDisplayText(h.HostelName)} {h.HostelCode ? `(${h.HostelCode})` : ''}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-slate-500 font-medium mt-1">Only active hostels from Hostels Configuration are listed</p>
                </div>

                <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
                  <button
                    type="button"
                    onClick={() => setShowModal(false)}
                    className="px-4 py-2.5 border border-slate-300 rounded-lg text-slate-700 font-bold hover:bg-slate-100 transition text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg shadow transition text-sm"
                  >
                    {editingDevice ? 'Update Device' : 'Save & Register Device'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Devices;
