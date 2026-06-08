type OnExpiry = () => void;

/**
 * Compute the API base URL from the environment variable, falling back to the
 * appropriate local dev address. Import this instead of copy-pasting the logic
 * into every page component.
 *
 * @param versioned - whether to append the `/v1` path segment (default true).
 *   Pass `false` for unversioned endpoints like `/metrics/summary`.
 */
export function getApiBase(versioned = true): string {
  const base =
    process.env.NEXT_PUBLIC_API_URL ||
    (typeof window !== "undefined" &&
    !["localhost", "127.0.0.1"].includes(window.location.hostname)
      ? "/api"
      : "http://127.0.0.1:8000");
  return versioned ? `${base}/v1` : base;
}

export function createFetch(apiUrl: string, token: string | null, onExpiry?: OnExpiry) {
  return async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const response = await fetch(`${apiUrl}${path}`, { ...options, headers });
    if (response.status === 401 && onExpiry) {
      onExpiry();
      throw new Error("Your session expired. Please sign in again.");
    }
    return response;
  };
}
