/** Connection health tracking and debounce rules.
 *
 *  A single failed poll should not show a blocking alert to the user.
 *  Background polling occurs every 8 seconds, so a failure threshold of 3
 *  gives approximately 24 seconds of tolerance for brief hiccups (service restarts,
 *  sleep/wake cycles, network switches).
 *
 *  When consecutive failures reach the threshold, a quiet, non-blocking notice
 *  is displayed to inform the user that reconnection is underway. Any single
 *  successful poll immediately clears the notice and resets the failure counter.
 */

export const CONNECTION_FAILURE_THRESHOLD = 3;

export interface ConnectionHealth {
  consecutiveFailures: number;
  showNotice: boolean;
}

export function initialConnectionHealth(): ConnectionHealth {
  return {
    consecutiveFailures: 0,
    showNotice: false,
  };
}

export function recordConnectionSuccess(): ConnectionHealth {
  return {
    consecutiveFailures: 0,
    showNotice: false,
  };
}

export function recordConnectionFailure(
  current: ConnectionHealth,
  threshold = CONNECTION_FAILURE_THRESHOLD,
): ConnectionHealth {
  const nextCount = current.consecutiveFailures + 1;
  return {
    consecutiveFailures: nextCount,
    showNotice: nextCount >= threshold,
  };
}

export type ActiveBanner = "error" | "connection" | "none";

/** Determines which banner should be active at the top of the workspace.
 *
 *  Precedence rule:
 *  Explicit user action failure (`actionError`) ALWAYS takes precedence over
 *  background connection notice. If the user encountered a send failure,
 *  navigation block, or command error, it must remain prominent as an alert.
 *
 *  Only when there is no action error and consecutive connection poll failures
 *  have reached the failure threshold, the quiet `.connection-banner` is shown.
 */
export function resolveActiveBanner(
  actionError: string,
  connectionHealth: ConnectionHealth,
): ActiveBanner {
  if (actionError) return "error";
  if (connectionHealth.showNotice) return "connection";
  return "none";
}

