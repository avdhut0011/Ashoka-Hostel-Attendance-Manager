import React, { useState } from 'react';
import api from '../services/api';
import { useToast } from '../context/ToastContext';
import { Download, FileSpreadsheet, Calendar, RotateCcw } from 'lucide-react';

const Reports = () => {
  const { showSuccess, showError } = useToast();
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [exporting, setExporting] = useState(null);

  const handleExport = async (format) => {
    try {
      setExporting(format);
      showSuccess(`Generating ${format.toUpperCase()} attendance report...`);

      const res = await api.get('/reports/export', {
        params: {
          export_format: format,
          ...(startDate && { start_date: startDate }),
          ...(endDate && { end_date: endDate }),
        },
        responseType: 'blob',
        timeout: 120000,
      });

      const blob = new Blob([res.data]);
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      const fileExt = format === 'excel' ? 'xlsx' : 'csv';
      link.download = `attendance_report_${startDate || 'all'}_${endDate || 'all'}.${fileExt}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      showSuccess(`Attendance report (${format.toUpperCase()}) downloaded successfully!`);
    } catch (err) {
      console.error('Export error:', err);
      showError('Failed to generate attendance report. Please try again.');
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-black text-slate-900">Reports & Export Center</h1>
        <p className="text-sm font-semibold text-slate-600 mt-1">Generate and Export Attendance Reports in Excel / CSV formats</p>
      </div>

      <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-6 max-w-xl">
        <div className="flex items-center justify-between">
          <h3 className="font-extrabold text-sm text-slate-900 uppercase tracking-wider flex items-center gap-2">
            <Calendar className="w-4 h-4 text-indigo-600" />
            Filter Date Range
          </h3>
          {(startDate || endDate) && (
            <button
              onClick={() => {
                setStartDate('');
                setEndDate('');
              }}
              className="flex items-center gap-1.5 text-xs font-bold px-3 py-1 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-lg border border-rose-200 transition"
              title="Clear date range filters"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Clear Dates
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-sm text-slate-900 font-semibold focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full px-3.5 py-2.5 border border-slate-300 rounded-lg text-sm text-slate-900 font-semibold focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="pt-4 border-t border-slate-200 flex gap-4">
          <button
            onClick={() => handleExport('excel')}
            disabled={exporting !== null}
            className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold py-3 rounded-lg text-sm transition shadow"
          >
            <FileSpreadsheet className="w-5 h-5" />
            {exporting === 'excel' ? 'Exporting...' : 'Export Excel (.xlsx)'}
          </button>

          <button
            onClick={() => handleExport('csv')}
            disabled={exporting !== null}
            className="flex-1 flex items-center justify-center gap-2 bg-slate-900 hover:bg-black disabled:opacity-50 text-white font-bold py-3 rounded-lg text-sm transition shadow"
          >
            <Download className="w-5 h-5" />
            {exporting === 'csv' ? 'Exporting...' : 'Export CSV (.csv)'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Reports;
