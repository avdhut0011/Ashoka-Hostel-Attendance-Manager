export const ATTENDANCE_TIMEZONE = 'Asia/Kolkata';

function timestamp(value) {
  if (value instanceof Date) return value;
  if (!value) return null;
  // Legacy biometric API values without offsets are India wall-clock time.
  const text = String(value).replace(' ', 'T');
  return new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(text) ? text : `${text}+05:30`);
}

export function formatIndiaDateTime(value, options = {}) {
  const date = timestamp(value);
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleString('en-IN', { timeZone: ATTENDANCE_TIMEZONE, ...options }) : 'N/A';
}

export function formatIndiaTime(value, options = {}) {
  const date = timestamp(value);
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleTimeString('en-IN', { timeZone: ATTENDANCE_TIMEZONE, ...options }) : 'N/A';
}

export function indiaToday(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: ATTENDANCE_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function indiaDateTimeInput(value) {
  const date = timestamp(value);
  if (!date || Number.isNaN(date.getTime())) return '';
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: ATTENDANCE_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}:${values.second}`;
}
