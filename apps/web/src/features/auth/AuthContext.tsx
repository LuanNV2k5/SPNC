import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as auth from "../../api/auth";
import { api, call, type Schemas } from "../../api/client";
import { getTraceStore } from "../practice/traceStore";

export type User = Schemas["UserResponse"];

interface AuthState {
  status: "loading" | "anonymous" | "authenticated";
  user: User | null;
  login(username: string, password: string): Promise<User>;
  /** Re-reads /auth/me (after a password change). */
  reload(): Promise<User | null>;
  /** Number of unsent trace events of this user (warned about before logout). */
  pendingTrace(): Promise<number>;
  logout(): Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

const fetchMe = () => call(api.GET("/api/v1/auth/me"));

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<User | null>(null);
  const queryClient = useQueryClient();

  const reload = useCallback(async () => {
    try {
      const me = await fetchMe();
      setUser(me);
      setStatus("authenticated");
      return me;
    } catch {
      setUser(null);
      setStatus("anonymous");
      return null;
    }
  }, []);

  useEffect(() => {
    // Reload of the page: the access token is gone, the refresh token may remain
    if (!auth.hasRefreshToken()) {
      setStatus("anonymous");
    } else {
      auth.refreshAccessToken().then(
        (ok) => {
          if (ok) void reload();
          else setStatus("anonymous");
        },
        () => setStatus("anonymous"),
      );
    }
    return auth.onAuthChange((loggedIn) => {
      if (!loggedIn) {
        setUser(null);
        setStatus("anonymous");
        queryClient.clear();
      }
    });
  }, [reload, queryClient]);

  const login = useCallback(async (username: string, password: string) => {
    await auth.login(username, password);
    const me = await fetchMe();
    setUser(me);
    setStatus("authenticated");
    return me;
  }, []);

  const pendingTrace = useCallback(async () => {
    if (!user) return 0;
    return (await getTraceStore()).pendingCountOf(user.id);
  }, [user]);

  const logout = useCallback(async () => {
    const id = user?.id;
    await auth.logout();
    // docs/46 §3.5.6: the user's drafts and events do not stay on a shared computer
    if (id) await (await getTraceStore()).clearUser(id);
    queryClient.clear();
  }, [user, queryClient]);

  const value = useMemo<AuthState>(() => ({ status, user, login, reload, pendingTrace, logout }), [status, user, login, reload, pendingTrace, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
