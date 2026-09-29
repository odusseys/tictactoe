import test from 'node:test';
import assert from 'node:assert/strict';
import { CELL_NAMES } from '../public/board-state.js';
import { GameSession } from '../public/game-session.js';
import { GameError } from '../public/errors.js';

const board = (marks = {}) => ({ cells: Object.fromEntries(CELL_NAMES.map((name) => [name, {
  value: marks[name] ?? 'empty', confidence: 1,
}])) });
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
function harness(overrides = {}) {
  const views = [];
  const waits = [];
  const camera = { open: async () => {}, stop() {}, async captureFrame() { return {}; } };
  const session = new GameSession({
    camera, cropFrame: async (frame) => frame, wait: async (ms) => { waits.push(ms); },
    onStateChange: (state) => views.push(structuredClone({ ...state, abortController: undefined })),
    ...overrides,
  });
  return { session, views, waits };
}

test('preview opens before Start, is reused, and stays live when a game ends', async () => {
  let opens = 0;
  let stops = 0;
  let reads = 0;
  const observations = [
    board({ top_left: 'O' }),
    board({ top_left: 'O', middle_left: 'X', top_middle: 'O' }),
    board({ top_left: 'O', middle_left: 'X', top_middle: 'O', middle_middle: 'X', top_right: 'O' }),
  ];
  let decisions = 0;
  const { session, views } = harness({
    camera: { open: async () => { opens++; }, stop: () => { stops++; }, captureFrame: async () => ({}) },
    detectBoard: async () => observations[reads++],
    selectAiMove: async () => ({ cell: ['middle_left', 'middle_middle'][decisions++] }),
  });
  await session.openPreview();
  assert.equal(reads, 0);
  assert.equal(views.at(-1).cameraReady, true);
  await session.start();
  assert.equal(opens, 1);
  assert.equal(reads, 3);
  assert.equal(decisions, 2);
  assert.equal(views.at(-1).status, 'finished');
  assert.equal(views.at(-1).game.result.winner, 'opponent');
  session.end();
  assert.equal(views.at(-1).game.step, 0);
  assert.equal(views.at(-1).cameraReady, true);
  assert.equal(stops, 0);
  session.dispose();
  assert.equal(stops, 1);
});

test('old boards at startup are ignored until an empty board or first O is visible', async () => {
  let reads = 0;
  let decisions = 0;
  const { session, views } = harness({
    detectBoard: async () => {
      reads++;
      if (reads < 8) return board({ top_left: 'X', bottom_right: 'O' });
      return reads === 8 ? board() : board({ top_left: 'O' });
    },
    selectAiMove: async (game) => {
      decisions++;
      assert.equal(game.step, 1);
      session.end();
      return { cell: 'middle_middle' };
    },
  });
  await session.start();
  assert.equal(reads, 9);
  assert.equal(decisions, 1);
  assert.equal(views.some((v) => v.status === 'paused'), false);
  assert.ok(views.some((v) => v.issue?.title === 'Waiting for a fresh board'));
});

test('unclear and incompatible readings keep accepted moves and recover without stopping', async () => {
  let reads = 0;
  let decisions = 0;
  const { session, views, waits } = harness({
    detectBoard: async () => {
      reads++;
      if (reads === 1) return board({ top_left: 'O' });
      if (reads < 8) return board(reads % 2 ? { top_left: 'unknown' } : {});
      return board({ top_left: 'O', middle_middle: 'X', bottom_right: 'O' });
    },
    selectAiMove: async (game) => {
      if (++decisions === 2) { assert.equal(game.step, 3); session.end(); }
      return { cell: decisions === 1 ? 'middle_middle' : 'top_right' };
    },
  });
  await session.start();
  assert.equal(decisions, 2);
  assert.equal(views.some((v) => v.status === 'paused'), false);
  assert.deepEqual(waits, []);
  assert.ok(views.filter((v) => v.issue).every((v) => v.game.cells.top_left.value === 'O'));
});

test('only consecutive uncertain readings show the warning, with no delay between captures', async () => {
  const lowConfidence = board();
  lowConfidence.cells.bottom_right.confidence = 0.79;
  const observations = [board({ top_left: 'unknown' }), board(),
    board({ top_left: 'unknown' }), lowConfidence, board({ middle_middle: 'unknown' }),
    board(), board({ bottom_left: 'unknown' })];
  const issues = [];
  let reads = 0;
  const { session, waits } = harness({
    detectBoard: async () => {
      issues.push(session.currentSession.issue?.title ?? null);
      if (reads === observations.length) { session.end(); return board(); }
      return observations[reads++];
    },
    selectAiMove: async () => assert.fail('No move is needed for these observations'),
  });
  await session.start();
  assert.deepEqual(issues, [null, null, null, null,
    'I can’t read the whole board', 'I can’t read the whole board', null, null]);
  assert.deepEqual(waits, []);
});

test('transient move failure retries the exact accepted image and history', async () => {
  const frame = { id: 'accepted-frame' };
  let decisions = 0;
  let reads = 0;
  const { session, views, waits } = harness({
    camera: { open: async () => {}, stop() {}, captureFrame: async () => frame },
    detectBoard: async () => { if (++reads === 2) session.end(); return board({ top_left: 'O' }); },
    selectAiMove: async (game, image) => {
      assert.equal(image, frame);
      assert.equal(game.step, 1);
      if (++decisions === 1) throw new GameError('rate_limited', 'Busy', { retryAfterMs: 3000 });
      return { cell: 'middle_middle' };
    },
  });
  await session.start();
  assert.equal(decisions, 2);
  assert.deepEqual(waits, [3000]);
  assert.ok(views.some((v) => v.game.pendingDecision?.cell === 'middle_middle'));
  assert.ok(views.some((v) => v.issue?.code === 'rate_limited'));
});

test('exhausted retries pause; manual retry resumes the same move instead of rereading/resetting', async () => {
  let decisions = 0;
  let reads = 0;
  const frame = { id: 'saved-frame' };
  const { session, views, waits } = harness({
    camera: { open: async () => {}, stop() {}, captureFrame: async () => frame },
    detectBoard: async () => { if (++reads === 2) session.end(); return board({ top_left: 'O' }); },
    selectAiMove: async (game, image) => {
      assert.equal(game.step, 1);
      assert.equal(image, frame);
      if (++decisions <= 6) throw new GameError('network', 'Offline');
      return { cell: 'middle_middle' };
    },
  });
  await session.start();
  assert.equal(views.at(-1).status, 'paused');
  assert.equal(views.at(-1).game.step, 1);
  assert.deepEqual(waits, [1000, 2000, 4000, 8000, 15000]);
  assert.equal(reads, 1);
  await session.resume();
  assert.equal(decisions, 7);
  assert.ok(views.some((v) => v.game.pendingDecision?.cell === 'middle_middle'));
});

test('configuration failure pauses immediately without retrying or clearing history', async () => {
  let decisions = 0;
  const { session, views, waits } = harness({
    detectBoard: async () => board({ top_left: 'O' }),
    selectAiMove: async () => { decisions++; throw new GameError('quota_exhausted', 'Check billing', { retryable: false }); },
  });
  await session.start();
  assert.equal(decisions, 1);
  assert.deepEqual(waits, []);
  assert.equal(views.at(-1).status, 'paused');
  assert.equal(views.at(-1).game.step, 1);
  assert.equal(views.at(-1).issue.title, 'API quota exhausted');
});

test('camera permission failures can be retried before starting a game', async () => {
  let opens = 0;
  const { session, views } = harness({ camera: {
    open: async () => { if (++opens === 1) throw new GameError('camera_permission', 'Allow access', { retryable: false }); },
    stop() {},
  } });
  await session.openPreview();
  assert.equal(views.at(-1).issue.title, 'Allow camera access');
  assert.equal(views.at(-1).status, 'idle');
  await session.openPreview();
  assert.equal(views.at(-1).cameraReady, true);
  assert.equal(views.at(-1).issue, null);
});

test('ending during a pending observation ignores its late response', async () => {
  const pending = deferred();
  const entered = deferred();
  let decisions = 0;
  const { session, views } = harness({
    detectBoard: async () => { entered.resolve(); return pending.promise; },
    selectAiMove: async () => { decisions++; return { cell: 'middle_middle' }; },
  });
  const running = session.start();
  await entered.promise;
  session.end();
  pending.resolve(board({ top_left: 'O' }));
  await running;
  assert.equal(decisions, 0);
  assert.equal(views.at(-1).status, 'idle');
  assert.equal(views.at(-1).game.step, 0);
});

test('a stale decision cannot alter a replacement game', async () => {
  const pending = deferred();
  const entered = deferred();
  const newRead = deferred();
  let reads = 0;
  const { session, views } = harness({
    detectBoard: async () => ++reads === 1 ? board({ top_left: 'O' }) : newRead.promise,
    selectAiMove: async () => { entered.resolve(); return pending.promise; },
  });
  const oldRun = session.start();
  await entered.promise;
  session.end();
  const newRun = session.start();
  pending.resolve({ cell: 'middle_middle' });
  await oldRun;
  assert.equal(session.currentSession.game.step, 0);
  assert.equal(session.currentSession.game.pendingDecision, null);
  session.end();
  newRead.resolve(board());
  await newRun;
  assert.equal(views.at(-1).status, 'idle');
});
