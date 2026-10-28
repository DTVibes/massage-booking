import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, ErrorState, Field, Loading, Notice, Screen, Toggle, errorText } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtDateTime } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import type { AdminSettings, AuditItem, Page } from "../../lib/types";

const AUDIT_LABEL: Record<string, string> = {
  "settings.update": "Изменены настройки", "schedule.update": "Изменён график", "schedule.exception.create": "Добавлено исключение",
  "schedule.exception.delete": "Удалено исключение", "service.create": "Создана услуга", "service.update": "Изменена услуга",
  "client.create": "Добавлен клиент", "client.update": "Изменён клиент",
};

export default function Settings() {
  const { info, reloadInfo } = useSession();
  const navigate = useNavigate();
  const s = useAsync(() => api.get<AdminSettings>("/admin/settings"), []);
  const audit = useAsync(() => api.get<Page<AuditItem>>("/admin/audit?page_size=15"), []);
  const [form, setForm] = useState<Partial<AdminSettings>>({});
  const [reminders, setReminders] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  if (s.loading && !s.data) return <Screen title="Настройки"><Loading /></Screen>;
  if (s.error) return <Screen title="Настройки"><ErrorState error={s.error} onRetry={s.reload} /></Screen>;
  const v = { ...s.data!, ...form };
  const text = (k: keyof AdminSettings) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });
  const num = (k: keyof AdminSettings) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });
  const bool = (k: keyof AdminSettings) => (val: boolean) => setForm({ ...form, [k]: val });
  const dirty = Object.keys(form).length > 0 || reminders !== null;

  async function save() {
    setBusy(true);
    setMsg(null);
    const body: Partial<AdminSettings> = { ...form };
    if (reminders !== null) body.reminder_hours = reminders.split(/[,\s]+/).filter(Boolean).map(Number);
    if (body.currency) body.currency = body.currency.toUpperCase();
    try {
      s.setData(await api.patch<AdminSettings>("/admin/settings", body));
      setForm({});
      setReminders(null);
      await reloadInfo();
      audit.reload();
      setMsg({ kind: "success", text: "Настройки сохранены" });
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen title="Настройки">
      <Card className="space-y-3">
        <h2 className="font-semibold">Студия</h2>
        <Field label="Название"><input className="field" value={v.studio_name} onChange={text("studio_name")} /></Field>
        <Field label="Имя массажиста"><input className="field" value={v.master_name} onChange={text("master_name")} /></Field>
        <Field label="Приветствие на главном экране"><textarea className="field min-h-[70px]" value={v.welcome_text} onChange={text("welcome_text")} /></Field>
        <Field label="Адрес"><input className="field" value={v.address} onChange={text("address")} /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Телефон для связи"><input className="field" value={v.contact_phone} onChange={text("contact_phone")} /></Field>
          <Field label="Telegram для связи"><input className="field" value={v.contact_telegram} placeholder="@username" onChange={text("contact_telegram")} /></Field>
          <Field label="Часовой пояс"><input className="field" value={v.timezone} onChange={text("timezone")} /></Field>
          <Field label="Валюта"><input className="field uppercase" maxLength={3} value={v.currency} onChange={text("currency")} /></Field>
        </div>
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">Правила записи</h2>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Длительность по умолч., мин"><input type="number" className="field" value={v.default_duration_minutes} onChange={num("default_duration_minutes")} /></Field>
          <Field label="Шаг начала, мин"><input type="number" className="field" value={v.slot_step_minutes} onChange={num("slot_step_minutes")} /></Field>
          <Field label="Буфер после, мин"><input type="number" className="field" value={v.buffer_minutes} onChange={num("buffer_minutes")} /></Field>
          <Field label="Горизонт, дней"><input type="number" className="field" value={v.booking_horizon_days} onChange={num("booking_horizon_days")} /></Field>
          <Field label="Мин. до визита, мин"><input type="number" className="field" value={v.min_lead_minutes} onChange={num("min_lead_minutes")} /></Field>
          <Field label="Отмена клиентом за, ч"><input type="number" className="field" value={v.cancel_min_hours} onChange={num("cancel_min_hours")} /></Field>
          <Field label="Макс. активных записей"><input type="number" className="field" value={v.max_active_bookings_per_client} onChange={num("max_active_bookings_per_client")} /></Field>
        </div>
        <Toggle checked={v.allow_client_reschedule} onChange={bool("allow_client_reschedule")} label="Клиент может переносить запись" />
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">Уведомления</h2>
        <Field label="Напоминания клиенту, за сколько часов" hint="Через запятую, например: 24, 2">
          <input className="field" value={reminders ?? v.reminder_hours.join(", ")} onChange={(e) => setReminders(e.target.value)} />
        </Field>
        <Toggle checked={v.notify_admin_new} onChange={bool("notify_admin_new")} label="Мне: новая запись" />
        <Toggle checked={v.notify_admin_cancel} onChange={bool("notify_admin_cancel")} label="Мне: отмена клиентом" />
        <Toggle checked={v.notify_admin_reschedule} onChange={bool("notify_admin_reschedule")} label="Мне: перенос клиентом" />
      </Card>

      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {dirty && <Button className="sticky bottom-24 w-full shadow-lg" loading={busy} onClick={save}>Сохранить настройки</Button>}

      <Button variant="secondary" className="w-full" onClick={() => { sessionStorage.setItem("clientMode", "1"); navigate("/home"); }}>
        Открыть как клиент
      </Button>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Журнал изменений</h2>
        {audit.data?.items.length ? (
          <Card className="space-y-2">
            {audit.data.items.map((a) => (
              <div key={a.id} className="text-sm">
                <span className="font-medium">{AUDIT_LABEL[a.action] ?? a.action}</span>
                <span className="text-muted"> · {fmtDateTime(a.created_at, info.timezone)}</span>
              </div>
            ))}
          </Card>
        ) : <div className="text-sm text-muted">Пока пусто</div>}
      </div>
    </Screen>
  );
}
