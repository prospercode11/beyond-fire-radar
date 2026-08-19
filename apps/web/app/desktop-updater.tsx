"use client";

import { useEffect, useState } from "react";

type UpdateState =
  | "unsupported"
  | "idle"
  | "checking"
  | "current"
  | "available"
  | "downloading"
  | "downloaded"
  | "installing"
  | "error";

type UpdateStatus = {
  state: UpdateState;
  message: string;
  currentVersion: string;
  availableVersion?: string;
  percent?: number;
};

type RuntimeInfo = {
  version: string;
  dataDirectory: string;
  startsAtLogin: boolean;
};

type DesktopUpdaterBridge = {
  getRuntimeInfo: () => Promise<RuntimeInfo>;
  getStatus: () => Promise<UpdateStatus>;
  check: () => Promise<UpdateStatus>;
  download: () => Promise<UpdateStatus>;
  install: () => Promise<UpdateStatus>;
  onStatus: (callback: (status: UpdateStatus) => void) => () => void;
};

declare global {
  interface Window {
    desktopUpdater?: DesktopUpdaterBridge;
  }
}

const DEFAULT_STATUS: UpdateStatus = {
  state: "unsupported",
  message: "Open the installed Windows app to check for updates.",
  currentVersion: "web",
};

export function DesktopUpdater() {
  const [status, setStatus] = useState<UpdateStatus>(DEFAULT_STATUS);
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);

  useEffect(() => {
    const updater = window.desktopUpdater;
    if (!updater) return;
    void Promise.all([updater.getStatus(), updater.getRuntimeInfo()]).then(
      ([nextStatus, nextRuntime]) => {
        setStatus(nextStatus);
        setRuntime(nextRuntime);
      },
    );
    return updater.onStatus(setStatus);
  }, []);

  const updater = typeof window === "undefined" ? undefined : window.desktopUpdater;
  const busy = ["checking", "downloading", "installing"].includes(status.state);
  const action =
    status.state === "available"
      ? { label: "Download update", run: () => updater?.download() }
      : status.state === "downloaded"
        ? { label: "Restart and update", run: () => updater?.install() }
        : { label: "Check for updates", run: () => updater?.check() };

  return (
    <div className="setting-row">
      <div>
        <strong>Desktop app updates</strong>
        <small>
          {status.message}
          {runtime
            ? ` Version ${runtime.version} · starts at Windows sign-in ${runtime.startsAtLogin ? "on" : "off"}.`
            : ""}
        </small>
      </div>
      {updater ? (
        <button
          className="button button-light"
          disabled={busy}
          onClick={() => void action.run()?.catch((error: unknown) => setStatus({
            ...status,
            state: "error",
            message: error instanceof Error ? error.message : "Update action failed.",
          }))}
          type="button"
        >
          {action.label}
        </button>
      ) : (
        <span className="setting-value">Windows app only</span>
      )}
    </div>
  );
}
