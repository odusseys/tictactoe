// Keep requests sequential and bounded; a paused game can resume the same step.
export async function retryOperation(operation, { signal, wait = waitWithAbort, onRetry, maxRetries = 5 }) {
  for (let failures = 0; ; failures += 1) {
    signal.throwIfAborted();
    try {
      const result = await operation();
      signal.throwIfAborted();
      return result;
    } catch (error) {
      signal.throwIfAborted();
      if (!error.retryable || failures >= maxRetries) throw error;
      const delayMs = Math.max(Math.min(1000 * 2 ** failures, 15000), error.retryAfterMs || 0);
      onRetry(error, delayMs);
      await wait(delayMs, signal);
    }
  }
}

export function waitWithAbort(durationMs, signal) {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, durationMs);
    signal.addEventListener('abort', abort, { once: true });
  });
}
