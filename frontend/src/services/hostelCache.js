import api from './api';

let cachedHostels = null;

export const getHostelsCached = async (forceRefresh = false) => {
  if (cachedHostels && !forceRefresh) {
    return cachedHostels;
  }
  try {
    const res = await api.get('/hostels');
    cachedHostels = res.data;
    return cachedHostels;
  } catch (err) {
    console.error('Error fetching hostels:', err);
    return cachedHostels || [];
  }
};

export const clearHostelsCache = () => {
  cachedHostels = null;
};
