import { type ButtonHTMLAttributes, type ReactNode, useEffect, useMemo } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { STATUS_LABEL } from "../lib/format";
import { useBackButton } from "../lib/hooks";
import { tg } from "../lib/telegram";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({ variant = "primary", loading, className = "", children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: "bg-accent text-on-accent",
    secondary: "bg-accent-soft text-accent",
    ghost: "bg-transparent text-accent",
    danger: "bg-danger/10 text-danger",
  };
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`flex min-h-[48px] items-center justify-center gap-2 rounded-xl px-4 text-[15px] font-semibold transition active:scale-[0.98] disabled:opacity-50 ${styles[variant]} ${className}`}
    >
      {loading && <Spinner small />}
      {children}
    </button>
  );
}

export function Card({ children, className = "", onClick }: { children: ReactNode; className?: string; onClick?: () => void }) {
  return (
    <div onClick={onClick} className={`rounded-2xl border border-line bg-card p-4 ${onClick ? "cursor-pointer active:bg-accent-soft/40" : ""} ${className}`}>
      {children}
    </div>
  );
}

export function Spinner({ small }: { small?: boolean }) {
  return (
    <span className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${small ? "h-4 w-4" : "h-7 w-7 text-accent"}`} />
  );
}

export function Loading({ text = "Загрузка…" }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-muted">
      <Spinner />
      <span className="text-sm">{text}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error | null; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-4 py-8 text-center">
      <div className="text-2xl">⚠️</div>
      <div className="text-[15px]">{error?.message || "Не удалось загрузить данные"}</div>
      {onRetry && <Button variant="secondary" onClick={onRetry}>Повторить</Button>}
    </div>
  );
}

export function Empty({ icon = "🌿", title, text, action }: { icon?: string; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
      <div className="text-3xl">{icon}</div>
      <div className="font-semibold">{title}</div>
      {text && <div className="max-w-xs text-sm text-muted">{text}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "error" | "warn" | "success"; children: ReactNode }) {
  const cls = {
    info: "bg-accent-soft text-ink",
    success: "bg-accent-soft text-accent",
    error: "bg-danger/10 text-danger",
    warn: "bg-warn/10 text-warn",
  }[kind];
  return <div className={`rounded-xl px-3.5 py-3 text-sm leading-relaxed ${cls}`}>{children}</div>;
}

export function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    booked: "bg-accent-soft text-accent",
    completed: "bg-line text-ink",
    no_show: "bg-warn/15 text-warn",
    cancelled_by_client: "bg-danger/10 text-danger",
    cancelled_by_admin: "bg-danger/10 text-danger",
  };
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls[status] ?? ""}`}>{STATUS_LABEL[status] ?? status}</span>;
}

/** Экран с заголовком; при наличии back — системная кнопка «Назад» Telegram и запасная в шапке. */
export function Screen({ title, back, children, actions }: { title?: string; back?: string | true | (() => void); children: ReactNode; actions?: ReactNode }) {
  const navigate = useNavigate();
  const onBack = useMemo(
    () => (back ? () => (typeof back === "function" ? back() : back === true ? navigate(-1) : navigate(back)) : undefined),
    [back, navigate],
  );
  useBackButton(onBack);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [title]);
  return (
    <div className="pb-safe mx-auto max-w-xl px-4 pt-4">
      {(title || actions) && (
        <div className="mb-4 flex min-h-[40px] items-center gap-2">
          {onBack && !tg?.initData && (
            <button onClick={onBack} className="-ml-1 rounded-lg px-2 py-1 text-2xl leading-none text-accent" aria-label="Назад">‹</button>
          )}
          <h1 className="flex-1 text-[22px] font-bold leading-tight">{title}</h1>
          {actions}
        </div>
      )}
      <div className="space-y-4">{children}</div>
    </div>
  );
}

export function BottomNav({ items }: { items: { to: string; label: string; icon: string; end?: boolean; also?: string[] }[] }) {
  const { pathname } = useLocation();
  const isActive = (it: (typeof items)[number]) =>
    [it.to, ...(it.also ?? [])].some((p) => (it.end ? pathname === p : pathname === p || pathname.startsWith(p + "/")));
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-card/95 backdrop-blur" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div className="mx-auto flex max-w-xl">
        {items.map((it) => (
          <Link key={it.to} to={it.to}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] ${isActive(it) ? "text-accent" : "text-muted"}`}>
            <span className="text-xl leading-none">{it.icon}</span>
            {it.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-t-2xl bg-bg p-4 sm:rounded-2xl"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)" }}>
        <div className="mb-4 flex items-center">
          <h2 className="flex-1 text-lg font-bold">{title}</h2>
          <button onClick={onClose} className="rounded-lg px-2 text-2xl leading-none text-muted" aria-label="Закрыть">×</button>
        </div>
        <div className="space-y-4">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 py-1">
      <span className="text-[15px]">{label}</span>
      <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        className={`relative h-7 w-12 shrink-0 rounded-full transition ${checked ? "bg-accent" : "bg-line"}`}>
        <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all ${checked ? "left-[22px]" : "left-0.5"}`} />
      </button>
    </label>
  );
}

export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-[15px]">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

export function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Что-то пошло не так. Попробуйте ещё раз.";
}
