import test from 'node:test';
import assert from 'node:assert/strict';
import { GameSession } from '../public/game-session.js';
import { CELL_NAMES } from '../public/board-state.js';
import { GameError } from '../public/errors.js';

const observation = { cells: Object.fromEntries(CELL_NAMES.map((name) => [name, {
  value: name === 'top_left' ? 'O' : 'empty', confidence: 1,
}])) };

test('no paper uses the original frame for detection and move selection, then tries cropping again', async () => {
  const frames = [], crops = [], detections = [], views = [];
  let cropsRequested = 0;
  const session = new GameSession({
    camera: { open: async () => {}, stop() {}, captureFrame: async () => {
      const frame = { id: frames.length }; frames.push(frame); return frame;
    } },
    onStateChange: (state) => {
      views.push({ issue: state.issue, step: state.game.step, status: state.status });
    },
    cropFrame: async () => {
      cropsRequested++;
      if (cropsRequested === 1 || cropsRequested === 3) throw new GameError('no_paper', 'No paper', { retryable: false });
      const crop = { crop: true }; crops.push(crop); return crop;
    },
    detectBoard: async (frame) => {
      detections.push(frame);
      if (detections.length === 3) session.end();
      return observation;
    },
    selectAiMove: async (_, frame) => { assert.equal(frame, frames[0]); return { cell: 'middle_middle' }; },
    wait: async () => assert.fail('Recapturing should not wait'),
  });
  assert.equal(session.cropPaper, true);
  await session.start();
  assert.equal(frames.length, 3);
  assert.deepEqual(detections, [frames[0], crops[0], frames[2]]);
  assert.equal(session.cropPaper, true);
  assert.ok(views.some((view) => view.step === 1));
  assert.equal(views.some((view) => view.issue?.code === 'no_paper'), false);
  assert.equal(views.some((view) => view.status === 'paused'), false);
});

test('turning cropping off discards an in-flight crop and resumes with a full frame', async () => {
  let cropped = 0;
  let full;
  const session = new GameSession({
    camera: { open: async () => {}, stop() {}, captureFrame: async () => (full = {}) },
    onStateChange() {},
    cropFrame: async () => { cropped++; session.setCropPaper(false); return { oldCrop: true }; },
    detectBoard: async (frame) => { assert.equal(frame, full); return observation; },
    selectAiMove: async (_, frame) => { assert.equal(frame, full); session.end(); return { cell: 'middle_middle' }; },
    wait: async () => {},
  });
  session.setCropPaper(true);
  await session.start();
  assert.equal(cropped, 1);
  assert.equal(session.cropPaper, false);
});
