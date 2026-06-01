/**
 * Creates an authenticated fetch wrapper bound to a specific API base URL and token.
 * Calls onExpiry when a 401 is received so the caller can clear the session.
 */
export function createFetch(apiUrl, token, onExpiry) {
  return async function apiFetch(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
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
