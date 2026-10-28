import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import { tg } from "./telegram";

export interface AsyncState<T> {
  data: T | undefined;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (d: T) => void;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => id === seq.current && setData(d))
      .catch((e) => id === seq.current && setError(e instanceof ApiError ? e : new ApiError(0, "unknown", String(e))))
      .finally(() => id === seq.current && setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}

/** Показывает системную кнопку «Назад» Telegram (или ничего вне Telegram). */
export function useBackButton(onBack: (() => void) | undefined) {
  useEffect(() => {
    if (!tg || !onBack) return;
    tg.BackButton.show();
    tg.BackButton.onClick(onBack);
    return () => {
      tg!.BackButton.offClick(onBack);
      tg!.BackButton.hide();
    };
  }, [onBack]);
}
