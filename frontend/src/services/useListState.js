import { useEffect, useRef, useState } from 'react';
import axios from 'axios';

export default function useListState(filters = []) {
  const [skip, setSkip] = useState(0);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState(null);
  const pending = useRef(null);
  const filterKey = JSON.stringify(filters);
  const cursors = useRef({ key: filterKey, pages: {} });
  if (cursors.current.key !== filterKey) cursors.current = { key: filterKey, pages: {} };
  useEffect(() => { setSkip(0); }, [filterKey]);
  useEffect(() => () => pending.current?.abort(), []);
  const begin = () => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setError('');
    return {
      signal: controller.signal,
      current: () => pending.current === controller && !controller.signal.aborted,
      success: (response) => {
        if (pending.current !== controller || controller.signal.aborted) return false;
        setTotal(Number(response.headers['x-total-count'] ?? response.data.length ?? 0));
        setUpdated(new Date());
        if (response.headers['x-next-cursor']) cursors.current.pages[skip + 100] = response.headers['x-next-cursor'];
        return true;
      },
      fail: (err) => {
        if (pending.current === controller && !axios.isCancel(err)) {
          setError(typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Unable to refresh data. Please retry.');
        }
      }
    };
  };
  return { skip, limit: 100, setSkip, total, params: { skip, limit: 100, ...(cursors.current.pages[skip] ? { cursor: cursors.current.pages[skip] } : {}) }, status: { error, updated }, begin };
}
