import test from 'node:test';
import assert from 'node:assert/strict';
import { requestBoardObservation } from '../public/api.js';
import { createEmptyGame } from '../public/game-state.js';

const request = (signal = new AbortController().signal) => requestBoardObservation(
  new Blob(['frame'], { type: 'image/jpeg' }), createEmptyGame(), signal,
);

test('non-JSON HTTP errors retain their status and retry policy', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>Unavailable</html>', { status: 503 }));
  await assert.rejects(request(), (error) => error.code === 'service_unavailable' && error.status === 503 && error.retryable);
});

test('null successful responses are classified as unreadable, not network failures', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('null'));
  await assert.rejects(request(), (error) => error.code === 'invalid_response' && error.retryable);
});

test('rate limits preserve retry delay while quota failures require user action', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    error: 'Busy', code: 'rate_limited', retryable: true,
  }), { status: 429, headers: { 'Retry-After': '7' } }));
  await assert.rejects(request(), (error) => error.code === 'rate_limited' && error.retryAfterMs === 7000);
  fetch.mock.mockImplementation(async () => new Response(JSON.stringify({
    error: 'Check billing', code: 'quota_exhausted', retryable: false,
  }), { status: 503 }));
  await assert.rejects(request(), (error) => error.code === 'quota_exhausted' && !error.retryable);
});

test('network failures are retryable but user cancellation stays cancellation', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch'); });
  await assert.rejects(request(), (error) => error.code === 'network' && error.retryable);
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(request(controller.signal), (error) => error.name === 'AbortError');
});
