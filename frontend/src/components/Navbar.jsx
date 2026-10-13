import React from 'react';
import { useAuth } from '../context/AuthContext';
import { LogOut, User as UserIcon } from 'lucide-react';

const Navbar = () => {
  const { user, logout } = useAuth();

  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3.5 flex items-center justify-between shadow-sm flex-shrink-0 z-20">
      <div className="flex items-center gap-3">
        <span className="text-lg font-black text-slate-900 tracking-tight">Hostel Tracker</span>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5 bg-slate-100 border border-slate-200 px-3.5 py-1.5 rounded-full text-sm font-semibold text-slate-800">
          <UserIcon className="w-4 h-4 text-indigo-600" />
          <span>{user?.username}</span>
          <span className="bg-indigo-600 text-white text-xs font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider shadow-sm">
            {user?.role}
          </span>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-2 text-sm text-rose-600 hover:text-rose-700 font-bold border border-rose-200 hover:bg-rose-50 px-3.5 py-1.5 rounded-lg transition"
        >
          <LogOut className="w-4 h-4" />
          Logout
        </button>
      </div>
    </header>
  );
};

export default Navbar;
