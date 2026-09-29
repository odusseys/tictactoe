import { GameError } from './errors.js';

const CAMERA_ERRORS = {
  NotAllowedError: ['camera_permission', 'Allow camera access in your browser’s site settings, then retry.', false],
  NotFoundError: ['camera_missing', 'Connect a webcam, then retry.', false],
  NotReadableError: ['camera_busy', 'Close other apps using the camera.', true],
  OverconstrainedError: ['camera_missing', 'Connect a camera that supports video capture, then retry.', false],
  SecurityError: ['camera_blocked', 'Your browser has blocked camera access for this page.', false],
};

export class Camera {
  #stream = null;

  constructor(video, onDisconnected) {
    Object.assign(this, { video, onDisconnected });
  }

  async open(signal) {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      throw new GameError('camera_blocked', 'Open this app using localhost or HTTPS to allow camera access.', { retryable: false });
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 960 }, facingMode: 'environment' }, audio: false,
      });
      signal.throwIfAborted();
      this.#stream = stream;
      this.video.srcObject = stream;
      stream.getVideoTracks()[0].addEventListener('ended', () => {
        if (this.#stream === stream) {
          this.stop();
          this.onDisconnected();
        }
      }, { once: true });
      await this.video.play();
      signal.throwIfAborted();
      if (!stream.active) throw new GameError('camera_disconnected', 'Reconnect your camera to continue.');
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      if (stream && this.video.srcObject === stream) this.video.srcObject = null;
      if (this.#stream === stream) this.#stream = null;
      signal.throwIfAborted();
      if (error instanceof GameError) throw error;
      const [code, message, retryable] = CAMERA_ERRORS[error.name]
        || ['camera_busy', 'The camera could not start. Check the camera connection.', true];
      throw new GameError(code, message, { retryable });
    }
  }

  stop() {
    this.#stream?.getTracks().forEach((track) => track.stop());
    if (this.video.srcObject === this.#stream) this.video.srcObject = null;
    this.#stream = null;
  }

  async captureFrame() {
    const width = this.video.videoWidth;
    const height = this.video.videoHeight;
    if (!this.#stream?.active || !width || !height || this.video.readyState < 2 || this.#stream.getVideoTracks()[0].muted) {
      throw new GameError('camera_frame', 'The camera is not supplying a frame yet. Keep it connected.');
    }
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) throw new GameError('camera_frame', 'Your browser could not capture this frame.');
    context.drawImage(this.video, 0, 0, width, height);
    const image = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
    if (!image) throw new GameError('camera_frame', 'Your browser could not encode this frame.');
    return image;
  }
}
