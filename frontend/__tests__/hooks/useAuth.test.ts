import { act, renderHook } from "@testing-library/react";
import { useAuth } from "../../hooks/useAuth";
import type { AuthSession } from "../../types/api";

const API_URL = "http://localhost:8000";

const mockSession: AuthSession = {
  token: "test-token-abc",
  user: {
    user_id: "user-123",
    email: "test@example.com",
    display_name: "Test User",
    created_at: "2024-01-01T00:00:00Z",
    is_admin: false,
    email_verified: true,
  },
};

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
});

describe("useAuth — initial state", () => {
  it("starts with no session", () => {
    const { result } = renderHook(() => useAuth(API_URL));
    expect(result.current.session).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.activeUserId).toBe("default");
    expect(result.current.authMode).toBe("login");
  });

  it("restores session from localStorage on mount", () => {
    localStorage.setItem("signalscope_session", JSON.stringify(mockSession));
    const { result } = renderHook(() => useAuth(API_URL));
    expect(result.current.session).toEqual(mockSession);
    expect(result.current.token).toBe("test-token-abc");
    expect(result.current.activeUserId).toBe("user-123");
  });

  it("clears corrupt localStorage session gracefully", () => {
    localStorage.setItem("signalscope_session", "not-valid-json{{{");
    const { result } = renderHook(() => useAuth(API_URL));
    expect(result.current.session).toBeNull();
    expect(localStorage.getItem("signalscope_session")).toBeNull();
  });
});

describe("useAuth — authMode", () => {
  it("can toggle between login and register", () => {
    const { result } = renderHook(() => useAuth(API_URL));
    act(() => { result.current.setAuthMode("register"); });
    expect(result.current.authMode).toBe("register");
    act(() => { result.current.setAuthMode("login"); });
    expect(result.current.authMode).toBe("login");
  });
});

describe("useAuth — form state", () => {
  it("updates email field", () => {
    const { result } = renderHook(() => useAuth(API_URL));
    act(() => { result.current.setAuthForm((p) => ({ ...p, email: "new@example.com" })); });
    expect(result.current.authForm.email).toBe("new@example.com");
  });

  it("updates password field", () => {
    const { result } = renderHook(() => useAuth(API_URL));
    act(() => { result.current.setAuthForm((p) => ({ ...p, password: "Newpass1" })); });
    expect(result.current.authForm.password).toBe("Newpass1");
  });
});

describe("useAuth — logout", () => {
  it("clears session state and localStorage", async () => {
    localStorage.setItem("signalscope_session", JSON.stringify(mockSession));
    const { result } = renderHook(() => useAuth(API_URL));

    // Session restored
    expect(result.current.session).toEqual(mockSession);

    // Mock the logout endpoint
    global.fetch = jest.fn().mockResolvedValueOnce({ ok: true, json: async () => ({}) } as Response);

    await act(async () => { await result.current.logout(); });

    expect(result.current.session).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem("signalscope_session")).toBeNull();
  });

  it("clears session even if logout API call fails", async () => {
    localStorage.setItem("signalscope_session", JSON.stringify(mockSession));
    const { result } = renderHook(() => useAuth(API_URL));

    global.fetch = jest.fn().mockRejectedValueOnce(new Error("Network error"));

    await act(async () => { await result.current.logout(); });

    expect(result.current.session).toBeNull();
  });
});

describe("useAuth — onExpiry callback", () => {
  it("clears session when apiFetch receives 401", async () => {
    localStorage.setItem("signalscope_session", JSON.stringify(mockSession));
    const onError = jest.fn();
    const { result } = renderHook(() => useAuth(API_URL, { onError }));

    global.fetch = jest.fn().mockResolvedValueOnce({ status: 401, ok: false } as Response);

    await act(async () => {
      try { await result.current.apiFetch("/me/profile"); } catch { /* expected */ }
    });

    expect(result.current.session).toBeNull();
    expect(onError).toHaveBeenCalledWith("Your session expired. Please sign in again.");
  });
});
