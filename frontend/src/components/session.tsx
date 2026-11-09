"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

const SessionContext = createContext<User | null>(null);

export function useUser(): User {
  const user = useContext(SessionContext);
  if (!user) throw new Error("useUser must be used inside <SessionProvider> after sign-in");
  return user;
}

/** Loads the signed-in user once; unauthenticated visitors are redirected to /login by api(). */
export function SessionProvider({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    api<User>("/api/auth/me").then(setUser).catch(() => undefined);
  }, []);
  if (!user) return <>{fallback}</>;
  return <SessionContext.Provider value={user}>{children}</SessionContext.Provider>;
}
