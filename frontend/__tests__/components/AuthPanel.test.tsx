import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import AuthPanel from "../../components/AuthPanel";
import type { AuthFormState, AuthSession } from "../../types/api";

const noop = () => {};
const noopDispatch = () => {};

const defaultForm: AuthFormState = { email: "", password: "", display_name: "" };

const mockSession: AuthSession = {
  token: "tok-abc",
  user: {
    user_id: "u1",
    email: "user@example.com",
    display_name: "Alice",
    created_at: "2024-01-01T00:00:00Z",
    is_admin: false,
    email_verified: true,
  },
};

function renderPanel(overrides: Partial<React.ComponentProps<typeof AuthPanel>> = {}) {
  const props = {
    session: null,
    authMode: "login" as const,
    setAuthMode: noop,
    authForm: defaultForm,
    setAuthForm: noopDispatch,
    resetEmail: "",
    setResetEmail: noop,
    resetToken: "",
    setResetToken: noop,
    resetPassword: "",
    setResetPassword: noop,
    verificationPreview: null,
    resetPreview: null,
    submitAuth: noop,
    logout: noop,
    requestVerification: noop,
    verifyEmailFromPreview: noop,
    requestPasswordReset: noop,
    confirmPasswordReset: noop,
    ...overrides,
  };
  return render(<AuthPanel {...props} />);
}

// ── Logged-out view ──────────────────────────────────────────────────────────

describe("AuthPanel — logged out", () => {
  it("renders login/register toggle chips", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: /login/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /register/i })).toBeInTheDocument();
  });

  it("renders email and password inputs", () => {
    renderPanel();
    expect(screen.getByPlaceholderText("Email")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
  });

  it("does NOT show display_name input in login mode", () => {
    renderPanel({ authMode: "login" });
    expect(screen.queryByPlaceholderText("Display name")).not.toBeInTheDocument();
  });

  it("shows display_name input in register mode", () => {
    renderPanel({ authMode: "register" });
    expect(screen.getByPlaceholderText("Display name")).toBeInTheDocument();
  });

  it("shows 'Sign in' CTA in login mode", () => {
    renderPanel({ authMode: "login" });
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("shows 'Create account' CTA in register mode", () => {
    renderPanel({ authMode: "register" });
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("calls setAuthMode when Register chip is clicked", () => {
    const setAuthMode = jest.fn();
    renderPanel({ setAuthMode });
    fireEvent.click(screen.getByRole("button", { name: /register/i }));
    expect(setAuthMode).toHaveBeenCalledWith("register");
  });

  it("calls submitAuth when Sign in is clicked", () => {
    const submitAuth = jest.fn();
    renderPanel({ submitAuth });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(submitAuth).toHaveBeenCalledTimes(1);
  });

  it("renders password reset email input", () => {
    renderPanel();
    expect(screen.getByPlaceholderText("name@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /request reset/i })).toBeInTheDocument();
  });

  it("calls requestPasswordReset when Request reset is clicked", () => {
    const requestPasswordReset = jest.fn();
    renderPanel({ requestPasswordReset });
    fireEvent.click(screen.getByRole("button", { name: /request reset/i }));
    expect(requestPasswordReset).toHaveBeenCalledTimes(1);
  });

  it("shows reset token inputs when resetPreview has a token", () => {
    renderPanel({ resetPreview: { ok: true, message: "", token_preview: "tok123", email_sent: false, delivery_mode: "preview", recipient: "" } });
    expect(screen.getByPlaceholderText(/paste reset token/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm reset/i })).toBeInTheDocument();
  });
});

// ── Logged-in view ───────────────────────────────────────────────────────────

describe("AuthPanel — logged in", () => {
  it("shows user display name", () => {
    renderPanel({ session: mockSession });
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("shows user email", () => {
    renderPanel({ session: mockSession });
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
  });

  it("shows 'member' role for non-admin", () => {
    renderPanel({ session: mockSession });
    expect(screen.getByText(/member/i)).toBeInTheDocument();
  });

  it("shows 'admin' role for admin users", () => {
    const adminSession = { ...mockSession, user: { ...mockSession.user, is_admin: true } };
    renderPanel({ session: adminSession });
    expect(screen.getByText(/admin/i)).toBeInTheDocument();
  });

  it("shows Sign out button", () => {
    renderPanel({ session: mockSession });
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("calls logout when Sign out is clicked", () => {
    const logout = jest.fn();
    renderPanel({ session: mockSession, logout });
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("shows Verify email button when email is unverified", () => {
    const unverifiedSession = { ...mockSession, user: { ...mockSession.user, email_verified: false } };
    renderPanel({ session: unverifiedSession });
    expect(screen.getByRole("button", { name: /verify email/i })).toBeInTheDocument();
  });

  it("does NOT show Verify email button when already verified", () => {
    renderPanel({ session: mockSession }); // email_verified: true
    expect(screen.queryByRole("button", { name: /verify email/i })).not.toBeInTheDocument();
  });

  it("calls requestVerification when Verify email is clicked", () => {
    const requestVerification = jest.fn();
    const unverifiedSession = { ...mockSession, user: { ...mockSession.user, email_verified: false } };
    renderPanel({ session: unverifiedSession, requestVerification });
    fireEvent.click(screen.getByRole("button", { name: /verify email/i }));
    expect(requestVerification).toHaveBeenCalledTimes(1);
  });

  it("shows verification preview token when present", () => {
    renderPanel({
      session: { ...mockSession, user: { ...mockSession.user, email_verified: false } },
      verificationPreview: { ok: true, message: "", token_preview: "ver-tok-abc", email_sent: false, delivery_mode: "preview", recipient: "" },
    });
    expect(screen.getByText("ver-tok-abc")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /use preview token/i })).toBeInTheDocument();
  });

  it("does NOT render login/register form when logged in", () => {
    renderPanel({ session: mockSession });
    expect(screen.queryByPlaceholderText("Password")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign in/i })).not.toBeInTheDocument();
  });
});
