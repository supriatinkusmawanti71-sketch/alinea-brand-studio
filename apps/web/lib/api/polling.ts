import { apiClient } from "./client";
import type { StageRunDetailResponse } from "./types";

type PollOptions = {
  intervalMs?: number;
  signal?: AbortSignal;
  onUpdate?: (run: StageRunDetailResponse) => void;
};

const TERMINAL_STATUSES = new Set(["SUCCEEDED", "FAILED", "WAITING_USER"]);

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason);
      return;
    }
    const timeout = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

export async function pollStageRun(
  stageRunId: string,
  { intervalMs = 1500, signal, onUpdate }: PollOptions = {},
) {
  while (true) {
    const run = await apiClient.getStageRun(stageRunId, { includeResult: false });
    onUpdate?.(run);

    if (TERMINAL_STATUSES.has(run.status)) {
      return run;
    }

    await wait(intervalMs, signal);
  }
}
