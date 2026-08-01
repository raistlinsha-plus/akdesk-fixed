export interface VisibilityPollingTarget {
  readonly visibilityState: DocumentVisibilityState;
  addEventListener(type: "visibilitychange", listener: EventListener): void;
  removeEventListener(type: "visibilitychange", listener: EventListener): void;
}

/**
 * Poll only while the page is visible. Returning to the page triggers one
 * immediate refresh before the regular interval resumes.
 */
export function startVisibilityPolling(
  callback: () => void,
  intervalMs: number,
  target: VisibilityPollingTarget = document,
): () => void {
  let timer: ReturnType<typeof setInterval> | null = null;

  function stopTimer() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function startTimer() {
    stopTimer();
    if (target.visibilityState !== "hidden") {
      timer = setInterval(callback, intervalMs);
    }
  }

  const handleVisibilityChange: EventListener = () => {
    stopTimer();
    if (target.visibilityState !== "hidden") {
      callback();
      startTimer();
    }
  };

  target.addEventListener("visibilitychange", handleVisibilityChange);
  startTimer();

  return () => {
    stopTimer();
    target.removeEventListener("visibilitychange", handleVisibilityChange);
  };
}
