import { formatIndiaTime } from '../services/time';
import React from 'react';

export default function DataStatus({ pagination, status }) {
  const { skip, setSkip, limit, total } = pagination;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-white p-3 text-sm">
      <div aria-live="polite">
        {status.error ? <span role="alert" className="text-rose-700">{status.error} Previous results may be outdated.</span> :
          <span className="text-slate-600">{status.updated ? `Updated ${formatIndiaTime(status.updated)}` : 'Loading data…'}</span>}
      </div>
      <div className="flex items-center gap-3">
        <span>{total ? `${skip + 1}–${Math.min(skip + limit, total)} of ${total}` : '0 records'}</span>
        <button disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - limit))} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button>
        <button disabled={skip + limit >= total} onClick={() => setSkip(skip + limit)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}
