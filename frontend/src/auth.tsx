import React, { createContext, useContext, useState, useCallback } from "react";
import { api, getToken, setToken } from "./api";

interface AuthContextValue {
  isAuthed: boolean;
  username: string | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthed, setIsAuthed] = useState<boolean>(!!getToken());
  const [username, setUsername] = useState<string | null>(localStorage.getItem("ff_username"));

  const login = useCallback(async (u: string, p: string) => {
    await api.login(u, p);
    localStorage.setItem("ff_username", u);
    setUsername(u);
    setIsAuthed(true);
  }, []);

  const register = useCallback(async (u: string, p: string) => {
    await api.register(u, p);
    await api.login(u, p);
    localStorage.setItem("ff_username", u);
    setUsername(u);
    setIsAuthed(true);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    localStorage.removeItem("ff_username");
    setUsername(null);
    setIsAuthed(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthed, username, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
