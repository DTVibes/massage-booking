// Тонкая обёртка над официальным Telegram Mini Apps SDK (telegram-web-app.js).

type HapticStyle = "light" | "medium" | "heavy";

interface TelegramWebApp {
  initData: string;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  ready(): void;
  expand(): void;
  close(): void;
  openTelegramLink?(url: string): void;
  onEvent(event: string, cb: () => void): void;
  offEvent(event: string, cb: () => void): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: {
    impactOccurred(style: HapticStyle): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  disableVerticalSwipes?(): void;
  isVersionAtLeast?(v: string): boolean;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export const tg: TelegramWebApp | undefined = window.Telegram?.WebApp;

/** Исходная строка initData. Вне Telegram (только при разработке) — из ?initData= или VITE_DEV_INIT_DATA. */
export function getInitData(): string {
  if (tg?.initData) return tg.initData;
  if (import.meta.env.DEV) {
    const fromUrl = new URLSearchParams(window.location.search).get("initData");
    return fromUrl || (import.meta.env.VITE_DEV_INIT_DATA as string | undefined) || "";
  }
  return "";
}

function applyTheme() {
  const dark = tg?.colorScheme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const bg = dark ? "#1B1C19" : "#F6F3EE";
  try {
    tg?.setHeaderColor?.(bg);
    tg?.setBackgroundColor?.(bg);
  } catch {
    /* старые клиенты Telegram */
  }
}

export function initTelegram() {
  applyTheme();
  if (!tg) return;
  tg.ready();
  tg.expand();
  try {
    if (tg.isVersionAtLeast?.("7.7")) tg.disableVerticalSwipes?.();
  } catch {
    /* noop */
  }
  tg.onEvent("themeChanged", applyTheme);
}

export const haptic = {
  tap: () => tg?.HapticFeedback?.selectionChanged(),
  success: () => tg?.HapticFeedback?.notificationOccurred("success"),
  error: () => tg?.HapticFeedback?.notificationOccurred("error"),
};

export function openTelegramUser(username: string | null, telegramId: number | null) {
  const url = username ? `https://t.me/${username}` : telegramId ? `tg://user?id=${telegramId}` : null;
  if (!url) return;
  if (url.startsWith("https://") && tg?.openTelegramLink) tg.openTelegramLink(url);
  else window.location.href = url;
}
