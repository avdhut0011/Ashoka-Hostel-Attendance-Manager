import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Users, UserPlus, Building2, Cpu, Clock, History, AlertTriangle, FileText, Activity, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Sidebar = () => {
  const { user } = useAuth();
  const isWarden = user?.role === 'WARDEN';

  const navItems = [
    { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { label: 'Students', path: '/students', icon: Users },
    { label: 'Detailed Student Lists', path: '/student-details', icon: FileText },
    { label: 'New Registration', path: '/student-registration', icon: UserPlus },
    { label: 'IN/OUT History', path: '/student-history', icon: History },
    ...(!isWarden ? [
      { label: 'Hostels', path: '/hostels', icon: Building2 },
      { label: 'Devices', path: '/devices', icon: Cpu },
    ] : []),
    { label: 'Attendance', path: '/attendance', icon: Clock },
    { label: 'Punches & Exceptions', path: '/punches', icon: AlertTriangle },
    { label: 'Reports & Export', path: '/reports', icon: FileText },
    ...(['ADMIN', 'IT_ADMIN'].includes(user?.role) ? [
      { label: 'System & Sync', path: '/system', icon: Activity },
      { label: 'Skipped Punch Review', path: '/recovery', icon: History },
    ] : []),
  ];

  if (user?.role === 'ADMIN') {
    navItems.push({ label: 'User Management', path: '/users', icon: ShieldCheck });
  }

  return (
    <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col h-screen border-r border-slate-800 flex-shrink-0 select-none z-30">
      <div className="p-4 border-b border-slate-800 flex items-center gap-3.5 flex-shrink-0">
        <img
          src="/logo.jpg"
          alt="Ashoka Group of Schools Logo"
          className="w-11 h-11 rounded-lg object-contain bg-white p-1 shadow-sm flex-shrink-0"
        />
        <div className="min-w-0">
          <h1 className="font-black text-[15px] leading-snug text-white tracking-tight">
            Ashoka Group of Schools
          </h1>
        </div>
      </div>
      <nav className="flex-1 p-3 space-y-1.5 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[15px] font-semibold transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white font-bold shadow-md shadow-indigo-950/40'
                    : 'text-slate-200 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="p-3 border-t border-slate-800 bg-slate-950/80 flex-shrink-0">
        <div className="bg-gradient-to-br from-indigo-950/90 via-slate-900 to-indigo-900/60 border border-indigo-500/40 rounded-xl p-3 text-center shadow-lg shadow-indigo-950/50">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 text-[11px] font-bold tracking-wide mb-1.5 border border-indigo-500/30">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]"></span>
            Hostel Tracker v1.0.0
          </div>
          <div className="text-xs text-slate-300 font-medium">
            Developed by{' '}
            <span className="text-slate-400 font-normal">
              Avadhut Jagtap
            </span>
          </div>
          <div className="mt-1 text-sm font-bold text-amber-300">System Creation Team</div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
