const { test } = require('node:test');
const assert = require('node:assert/strict');
const { matchesFrom } = require('../../stacks/admin/homepage/custom.js');

const now = Date.parse('2026-10-10T12:00:00Z');
const event = (id, overrides = {}) => ({
  id, type: 'match', state: 'unstarted', startTime: '2026-10-15T16:00:00Z',
  league: { id: '98767975604431411', name: 'Worlds' },
  matchTeams: [{ code: 'TBD', name: 'TBD' }, { code: 'TBD', name: 'TBD' }],
  match: { strategy: { type: 'bestOf', count: 5 } },
  ...overrides,
});
const response = events => ({ data: { esports: { events } } });

test('shows live and earliest upcoming majors, excluding results, minor leagues and stale entries', () => {
  const data = response([
    event('late'), event('completed', { state: 'completed' }),
    event('minor', { league: { id: '100695891328981122', name: 'EMEA Masters' } }),
    event('live', { state: 'inProgress', startTime: '2026-10-10T06:00:00Z' }),
    event('early', { startTime: '2026-10-11T12:00:00Z' }),
    event('stale', { startTime: '2026-10-09T12:00:00Z' }),
    event('bad-date', { startTime: 'invalid' }), event('late'),
  ]);
  assert.deepEqual(matchesFrom(data, now).map(item => item.id), ['live', 'early', 'late']);
});

test('distinguishes an empty schedule from an upstream failure or schema change', () => {
  assert.deepEqual(matchesFrom(response([]), now), []);
  for (const payload of [{}, { error: 'Unavailable' }, { errors: [{ message: 'PersistedQueryNotFound' }] },
    { data: { esports: { events: null } } }]) {
    assert.throws(() => matchesFrom(payload, now), /unavailable/);
  }
});

test('bounds the compact panel to ten matches after sorting, even with a larger feed', () => {
  const events = Array.from({ length: 15 }, (_, i) => event(String(i), {
    startTime: new Date(now + (15 - i) * 3600000).toISOString(),
  }));
  const matches = matchesFrom(response(events), now);
  assert.equal(matches.length, 10);
  assert.equal(matches[0].id, '14');
  assert.equal(matches[9].id, '5');
});
