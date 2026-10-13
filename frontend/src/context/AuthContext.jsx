import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('user');
    try { return saved ? JSON.parse(saved) : null; } catch { localStorage.removeItem('user'); return null; }
  });

  useEffect(() => {
    if (!localStorage.getItem('access_token')) { setUser(null); return; }
    const controller = new AbortController();
    api.get('/auth/me', { signal: controller.signal }).then(({ data }) => {
      const actual = { id: data.SystemUserId, username: data.Username, role: data.Role, hostel_id: data.HostelId };
      localStorage.setItem('user', JSON.stringify(actual));
      setUser(actual);
    }).catch(err => { if (err.response?.status === 401 || err.response?.status === 403) logout(); });
    return () => controller.abort();
  }, []);

  const login = async (username, password) => {
    const response = await api.post('/auth/login', { username, password });
    const { access_token, user_id, role, hostel_id } = response.data;
    const userData = { id: user_id, username, role, hostel_id };

    localStorage.setItem('access_token', access_token);
    localStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
    return userData;
  };

  const logout = () => {
    const token = localStorage.getItem('access_token');
    if (token) api.post('/auth/logout', null, { headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
