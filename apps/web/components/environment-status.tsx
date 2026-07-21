"use client";

import { useEffect, useState } from "react";

type State = "checking" | "ready" | "error";

export function EnvironmentStatus() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const controller = new AbortController();

    fetch("/api/v1/health/live", { cache: "no-store", signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("error");
      });

    return () => controller.abort();
  }, []);

  const text = {
    checking: "正在检查 API…",
    ready: "网页与 API 已连通",
    error: "网页已启动，API 尚未连通",
  }[state];

  return (
    <div className="status" data-state={state} role="status">
      <span className="status-dot" aria-hidden="true" />
      {text}
    </div>
  );
}
