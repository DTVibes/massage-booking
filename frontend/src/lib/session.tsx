import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, authenticate } from "./api";
import type { Info, User } from "./types";

interface Session {
  user: User;
  info: Info;
  setUser: (u: User) => void;
  reloadInfo: () => Promise<void>;
}

const Ctx = createContext<Session | null>(null);

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("SessionProvider missing");
  return s;
}

export function SessionProvider({ children, fallback }: { children: ReactNode; fallback: (state: { error: ApiError | null; retry: () => void }) => ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setError(null);
    Promise.all([authenticate(), api.get<Info>("/info")])
      .then(([u, i]) => { setUser(u); setInfo(i); })
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, "unknown", String(e))));
  }, [attempt]);

  const reloadInfo = useCallback(async () => setInfo(await api.get<Info>("/info")), []);

  if (!user || !info) return <>{fallback({ error, retry: () => setAttempt((a) => a + 1) })}</>;
  return <Ctx.Provider value={{ user, info, setUser, reloadInfo }}>{children}</Ctx.Provider>;
}
