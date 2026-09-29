import { requestBoardObservation, requestAiMove, requestPaperCrop } from './api.js';
import { createEmptyGame, applyBoardObservation, setPendingAiMove } from './game-state.js';
import { GameError, describeError } from './errors.js';
import { retryOperation, waitWithAbort } from './retry.js';

export function createIdleSessionState() {
  return { status: 'idle', game: createEmptyGame(), operation: null, issue: null, decisionFrame: null };
}

function describeDetectionIssue(transition) {
  if (transition.kind === 'waiting-start') return { title: 'Waiting for a fresh board', message: transition.reason };
  if (transition.kind === 'incompatible') return { title: 'The board doesn’t match', message: `${transition.reason} Keep the accepted marks as shown below.` };
  return { title: 'I can’t read the whole board', message: 'Keep all nine cells well lit and visible, and move your hand away.' };
}

// The preview belongs to the page. A game owns only its requests and accepted
// moves, so ending or recovering a game never requires reopening a healthy camera.
export class GameSession {
  constructor({ camera, onStateChange, detectBoard = requestBoardObservation, selectAiMove = requestAiMove,
    cropFrame = requestPaperCrop, wait = waitWithAbort }) {
    Object.assign(this, { camera, onStateChange, detectBoard, selectAiMove, cropFrame, wait });
    this.cropPaper = true;
    this.currentSession = createIdleSessionState();
    this.previewController = new AbortController();
    this.cameraReady = false;
    this.cameraOpening = false;
    this.cameraIssue = null;
    this.cameraPromise = null;
  }

  #notifyView(session = this.currentSession) {
    if (this.currentSession !== session || this.previewController.signal.aborted) return;
    this.onStateChange({ ...session, cameraReady: this.cameraReady, cameraOpening: this.cameraOpening, cropPaper: this.cropPaper,
      issue: session.issue || this.cameraIssue });
  }

  setCropPaper(enabled) {
    this.cropPaper = Boolean(enabled);
    this.#notifyView();
  }

  async #openCamera() {
    try {
      await this.camera.open(this.previewController.signal);
      this.previewController.signal.throwIfAborted();
      this.cameraReady = true;
      this.cameraIssue = null;
    } catch (error) {
      this.cameraReady = false;
      this.cameraIssue = describeError(error);
      throw error;
    } finally {
      this.cameraOpening = false;
      this.cameraPromise = null;
      this.#notifyView();
    }
  }

  #ensureCamera() {
    if (this.cameraReady) return Promise.resolve();
    if (this.cameraPromise) return this.cameraPromise;
    this.cameraOpening = true;
    this.cameraIssue = null;
    this.#notifyView();
    this.cameraPromise = this.#openCamera();
    return this.cameraPromise;
  }

  async openPreview() {
    try { await this.#ensureCamera(); } catch { /* Camera issues already appear in the panel. */ }
  }

  cameraDisconnected() {
    this.cameraReady = false;
    this.cameraIssue = describeError(new GameError('camera_disconnected', 'Reconnect your camera. Your game is saved.'));
    this.#notifyView();
  }

  end() {
    this.currentSession.abortController?.abort();
    this.currentSession = createIdleSessionState();
    this.#notifyView();
  }

  dispose() {
    this.currentSession.abortController?.abort();
    this.previewController.abort();
    this.camera.stop();
  }

  start() {
    this.end();
    return this.#beginRun(this.currentSession);
  }

  resume() {
    if (this.currentSession.status !== 'paused') return Promise.resolve();
    return this.#beginRun(this.currentSession);
  }

  #beginRun(session) {
    Object.assign(session, { status: 'running', issue: null, abortController: new AbortController() });
    this.#notifyView(session);
    return this.#run(session);
  }

  async #withRetries(session, operation) {
    return retryOperation(operation, {
      signal: session.abortController.signal, wait: this.wait,
      onRetry: (error, delayMs) => {
        session.operation = null;
        session.issue = { ...describeError(error), retrySeconds: Math.ceil(delayMs / 1000) };
        this.#notifyView(session);
      },
    });
  }

  async #captureFrame(session) {
    const { signal } = session.abortController;
    await this.#ensureCamera();
    signal.throwIfAborted();
    const cropPaper = this.cropPaper;
    const original = await this.camera.captureFrame();
    signal.throwIfAborted();
    if (!cropPaper) return { frame: original, cropPaper };
    session.operation = 'cropping';
    this.#notifyView(session);
    try {
      const frame = await this.cropFrame(original, signal);
      signal.throwIfAborted();
      return { frame, cropPaper };
    } catch (error) {
      signal.throwIfAborted();
      if (cropPaper !== this.cropPaper) return { transition: { kind: 'retry-capture' } };
      if (error.code !== 'no_paper') throw error;
      // A missing paper mask should not prevent the board reader from trying
      // the original image. Keep this same frame for any resulting AI decision.
      return { frame: original, cropPaper };
    }
  }

  async #readBoard(session) {
    const { signal } = session.abortController;
    return this.#withRetries(session, async () => {
      session.operation = 'detecting';
      if (session.issue) delete session.issue.retrySeconds;
      this.#notifyView(session);
      const capture = await this.#captureFrame(session);
      if (capture.transition) return capture;
      const { frame, cropPaper } = capture;
      if (cropPaper !== this.cropPaper) return { transition: { kind: 'retry-capture' } };
      session.operation = 'detecting';
      this.#notifyView(session);
      const observation = await this.detectBoard(frame, session.game, signal);
      signal.throwIfAborted();
      if (cropPaper !== this.cropPaper) return { transition: { kind: 'retry-capture' } };
      return { frame, transition: applyBoardObservation(session.game, observation.cells) };
    });
  }

  async #chooseMove(session) {
    const { signal } = session.abortController;
    // Keep this frame through retries and manual resume: it belongs to the
    // accepted O, and the chosen X has not entered the physical board yet.
    const nextGame = await this.#withRetries(session, async () => {
      session.operation = 'deciding';
      if (session.issue) delete session.issue.retrySeconds;
      this.#notifyView(session);
      const { cell } = await this.selectAiMove(session.game, session.decisionFrame, signal);
      signal.throwIfAborted();
      return setPendingAiMove(session.game, cell);
    });
    signal.throwIfAborted();
    Object.assign(session, { game: nextGame, decisionFrame: null, issue: null, operation: null });
    this.#notifyView(session);
  }

  async #run(session) {
    const { signal } = session.abortController;
    let uncertainReadings = 0;
    try {
      while (!signal.aborted) {
        if (session.game.phase === 'self') {
          await this.#chooseMove(session);
          continue;
        }
        const { frame, transition } = await this.#readBoard(session);
        signal.throwIfAborted();
        session.operation = null;
        uncertainReadings = transition.kind === 'uncertain' ? uncertainReadings + 1 : 0;
        if (transition.kind === 'retry-capture') continue;
        if (['uncertain', 'incompatible', 'waiting-start'].includes(transition.kind)) {
          session.issue = transition.kind === 'uncertain' && uncertainReadings < 2
            ? null : describeDetectionIssue(transition);
          this.#notifyView(session);
          continue;
        }
        Object.assign(session, { game: transition.game, issue: null });
        if (session.game.result) {
          session.status = 'finished';
          this.#notifyView(session);
          return;
        }
        if (session.game.phase === 'self') session.decisionFrame = frame;
        this.#notifyView(session);
      }
    } catch (error) {
      if (signal.aborted) return;
      // Pausing preserves both the board and a pending move request. Only End
      // game or a deliberate new Start resets history.
      Object.assign(session, { status: 'paused', operation: null, issue: describeError(error) });
      this.#notifyView(session);
    }
  }
}
