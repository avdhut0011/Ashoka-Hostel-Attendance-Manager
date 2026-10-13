import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';

import Sidebar from './components/Sidebar';
import Navbar from './components/Navbar';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Students from './pages/Students';
import Hostels from './pages/Hostels';
import Devices from './pages/Devices';
import Attendance from './pages/Attendance';
import Punches from './pages/Punches';
import Reports from './pages/Reports';
import SystemHealth from './pages/SystemHealth';
import Users from './pages/Users';
import StudentRegistration from './pages/StudentRegistration';
import StudentHistory from './pages/StudentHistory';
import RecoveryReview from './pages/RecoveryReview';
import StudentDetails from './pages/StudentDetails';

const RoleRoute = ({ allowedRoles, children }) => {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
};

const ProtectedLayout = ({ children }) => {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <Navbar />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
};

function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <ProtectedLayout>
                  <Routes>
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/students" element={<Students />} />
                    <Route path="/student-details" element={<StudentDetails />} />
                    <Route path="/student-registration" element={<StudentRegistration />} />
                    <Route path="/student-history" element={<StudentHistory />} />
                    <Route
                      path="/hostels"
                      element={
                        <RoleRoute allowedRoles={['ADMIN', 'IT_ADMIN', 'MANAGEMENT']}>
                          <Hostels />
                        </RoleRoute>
                      }
                    />
                    <Route
                      path="/devices"
                      element={
                        <RoleRoute allowedRoles={['ADMIN', 'IT_ADMIN', 'MANAGEMENT']}>
                          <Devices />
                        </RoleRoute>
                      }
                    />
                    <Route path="/attendance" element={<Attendance />} />
                    <Route path="/punches" element={<Punches />} />
                    <Route path="/reports" element={<Reports />} />
                    <Route path="/recovery" element={<RoleRoute allowedRoles={['ADMIN', 'IT_ADMIN']}><RecoveryReview /></RoleRoute>} />
                    <Route
                      path="/system"
                      element={
                        <RoleRoute allowedRoles={['ADMIN', 'IT_ADMIN']}>
                          <SystemHealth />
                        </RoleRoute>
                      }
                    />
                    <Route
                      path="/users"
                      element={
                        <RoleRoute allowedRoles={['ADMIN']}>
                          <Users />
                        </RoleRoute>
                      }
                    />
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                  </Routes>
                </ProtectedLayout>
              }
            />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ToastProvider>
  );
}

export default App;
