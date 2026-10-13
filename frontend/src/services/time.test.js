import test from 'node:test';
import assert from 'node:assert/strict';
import { indiaToday, indiaDateTimeInput, formatIndiaTime } from './time.js';

test('India midnight selects the next date while UTC is still yesterday', () => {
  assert.equal(indiaToday(new Date('2026-10-09T18:30:00Z')), '2026-10-10');
  assert.equal(indiaToday(new Date('2026-10-09T18:29:59Z')), '2026-10-09');
});

test('biometric naive, India offset and UTC values describe the same time', () => {
  const expected = '2026-10-10T02:00:00';
  for (const value of ['2026-10-10T02:00:00', '2026-10-10T02:00:00+05:30', '2026-10-09T20:30:00Z']) {
    assert.equal(indiaDateTimeInput(value), expected);
    assert.equal(formatIndiaTime(value), formatIndiaTime('2026-10-09T20:30:00Z'));
  }
});
