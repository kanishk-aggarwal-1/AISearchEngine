type OnExpiry = () => void;

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
