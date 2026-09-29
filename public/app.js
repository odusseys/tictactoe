import { Camera } from './camera.js';
import { GameSession } from './game-session.js';
import { renderGameSession } from './game-view.js';

const camera = new Camera(document.querySelector('#camera-video'), () => gameSession.cameraDisconnected());
const gameSession = new GameSession({ camera, onStateChange: renderGameSession });

document.querySelector('#start-game').addEventListener('click', () => { void gameSession.start(); });
document.querySelector('#end-game').addEventListener('click', () => gameSession.end());
document.querySelector('#retry-game').addEventListener('click', () => { void gameSession.resume(); });
document.querySelector('#retry-camera').addEventListener('click', () => { void gameSession.openPreview(); });
document.querySelector('#crop-paper').addEventListener('change', (event) => gameSession.setCropPaper(event.target.checked));
window.addEventListener('pagehide', () => gameSession.dispose());
window.addEventListener('pageshow', (event) => { if (event.persisted) location.reload(); });
renderGameSession({ ...gameSession.currentSession, cropPaper: gameSession.cropPaper });

const howToPlay = document.querySelector('#how-to-play');
// Both the button and Escape close the dialog. Neither requests camera access
// until the explainer is dismissed, and background controls stay inert.
howToPlay.addEventListener('close', () => { void gameSession.openPreview(); }, { once: true });
howToPlay.showModal();
