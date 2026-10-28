import { useState } from "react";
import { Button, Card, Empty, ErrorState, Field, Loading, Notice, Screen, Sheet, Toggle, errorText } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtDuration, fmtPrice } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import type { AdminService } from "../../lib/types";

interface Form { name: string; description: string; duration_minutes: number; price: string; currency: string; is_active: boolean; sort_order: number }

export default function Services() {
  const { info } = useSession();
  const list = useAsync(() => api.get<AdminService[]>("/admin/services"), []);
  const [editing, setEditing] = useState<AdminService | "new" | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function open(s: AdminService | "new") {
    setError(null);
    setEditing(s);
    setForm(s === "new"
      ? { name: "", description: "", duration_minutes: 60, price: "", currency: info.currency, is_active: true, sort_order: 0 }
      : { name: s.name, description: s.description, duration_minutes: s.duration_minutes, price: s.price_minor ? String(s.price_minor / 100) : "",
          currency: s.currency, is_active: s.is_active, sort_order: s.sort_order });
  }

  async function save() {
    if (!form) return;
    setBusy(true);
    setError(null);
    const body = {
      name: form.name.trim(), description: form.description.trim(), duration_minutes: form.duration_minutes,
      price_minor: Math.round(Number(form.price.replace(",", ".") || 0) * 100), currency: form.currency.toUpperCase(),
      is_active: form.is_active, sort_order: form.sort_order,
    };
    try {
      if (editing === "new") await api.post("/admin/services", body);
      else await api.patch(`/admin/services/${(editing as AdminService).id}`, body);
      setEditing(null);
      list.reload();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen title="Услуги" actions={<Button className="!min-h-[40px] !px-3 text-sm" onClick={() => open("new")}>+ Услуга</Button>}>
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : !list.data!.length ? (
        <Empty icon="💆" title="Услуг пока нет" text="Пока нет активных услуг, клиенты не смогут записаться." />
      ) : (
        <>
          {!list.data!.some((s) => s.is_active) && <Notice kind="warn">Нет активных услуг — онлайн-запись недоступна клиентам.</Notice>}
          {list.data!.map((s) => (
            <Card key={s.id} onClick={() => open(s)} className={s.is_active ? "" : "opacity-60"}>
              <div className="flex items-start justify-between gap-2">
                <div className="font-semibold">{s.name}</div>
                <div className="whitespace-nowrap font-semibold text-accent">{fmtPrice(s.price_minor, s.currency)}</div>
              </div>
              {s.description && <div className="mt-1 text-sm text-muted">{s.description}</div>}
              <div className="mt-1 text-sm text-muted">⏱ {fmtDuration(s.duration_minutes)} · {s.is_active ? "активна" : "скрыта"}</div>
            </Card>
          ))}
          <p className="text-xs text-muted">Изменение услуги не влияет на уже созданные записи: в них сохраняются название, длительность и цена на момент записи.</p>
        </>
      )}
      <Sheet open={!!editing && !!form} onClose={() => setEditing(null)} title={editing === "new" ? "Новая услуга" : "Редактирование услуги"}>
        {form && (
          <>
            <Field label="Название"><input className="field" value={form.name} maxLength={200} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Описание"><textarea className="field min-h-[72px]" value={form.description} maxLength={2000} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Длительность, мин"><input type="number" min={5} step={5} className="field" value={form.duration_minutes} onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) })} /></Field>
              <Field label="Стоимость"><input inputMode="decimal" className="field" placeholder="0 — по договорённости" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></Field>
              <Field label="Валюта"><input className="field uppercase" maxLength={3} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} /></Field>
              <Field label="Порядок"><input type="number" className="field" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })} /></Field>
            </div>
            <Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} label="Доступна для записи" />
            {error && <Notice kind="error">{error}</Notice>}
            <Button className="w-full" loading={busy} disabled={!form.name.trim()} onClick={save}>Сохранить</Button>
          </>
        )}
      </Sheet>
    </Screen>
  );
}
