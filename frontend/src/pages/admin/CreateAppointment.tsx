import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { SlotGrid } from "../../components/SlotGrid";
import { Button, Card, ErrorState, Field, Loading, Notice, Screen, Toggle, errorText } from "../../components/ui";
import { api, qs } from "../../lib/api";
import { todayIn, zonedToIso } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import { haptic } from "../../lib/telegram";
import type { AdminAppointmentDetail, AdminClient, AdminService, Page, Slot } from "../../lib/types";

export default function CreateAppointment() {
  const { info } = useSession();
  const tz = info.timezone;
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"existing" | "new">(params.get("client") ? "existing" : "new");
  const [query, setQuery] = useState("");
  const [client, setClient] = useState<AdminClient | null>(null);
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [serviceId, setServiceId] = useState<string>("");
  const [date, setDate] = useState(params.get("date") || todayIn(tz));
  const [slot, setSlot] = useState<Slot | null>(null);
  const [manual, setManual] = useState(false);
  const [manualTime, setManualTime] = useState("10:00");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const services = useAsync(async () => {
    const list = await api.get<AdminService[]>("/admin/services");
    const active = list.filter((s) => s.is_active);
    if (!serviceId && active[0]) setServiceId(active[0].id);
    return active;
  }, []);
  const preset = useAsync(async () => {
    const id = params.get("client");
    if (!id) return null;
    const c = await api.get<AdminClient>(`/admin/clients/${id}`);
    setClient(c);
    return c;
  }, []);
  const found = useAsync(
    () => (mode === "existing" && query.trim().length >= 2 ? api.get<Page<AdminClient>>(`/admin/clients${qs({ q: query, page_size: 8 })}`) : Promise.resolve(null)),
    [mode, query],
  );
  const slots = useAsync(
    () => (serviceId && !manual ? api.get<Slot[]>(`/admin/availability/slots${qs({ date, service_id: serviceId })}`) : Promise.resolve([])),
    [serviceId, date, manual],
  );

  const ready = (mode === "existing" ? !!client : newName.trim() && newPhone.trim()) && serviceId && (manual || slot);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const a = await api.post<AdminAppointmentDetail>("/admin/appointments", {
        client_id: mode === "existing" ? client!.id : null,
        new_client: mode === "new" ? { name: newName.trim(), phone: newPhone } : null,
        service_id: serviceId,
        starts_at: manual ? zonedToIso(date, manualTime, tz) : slot!.starts_at,
        ignore_schedule: manual,
        comment: comment.trim() || null,
      });
      haptic.success();
      navigate(`/admin/appointments/${a.id}`, { replace: true });
    } catch (e) {
      haptic.error();
      setError(errorText(e));
      slots.reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen title="Новая запись" back={true}>
      <Card className="space-y-3">
        <div className="flex rounded-xl bg-line/60 p-1">
          {([["existing", "Клиент из базы"], ["new", "Новый клиент"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setMode(k)} className={`flex-1 rounded-lg py-2 text-sm font-medium ${mode === k ? "bg-card shadow-sm" : "text-muted"}`}>{label}</button>
          ))}
        </div>
        {mode === "existing" ? (
          client ? (
            <div className="flex items-center justify-between rounded-xl bg-accent-soft px-3 py-2.5">
              <div><div className="font-semibold">{client.name}</div><div className="text-sm text-muted">{client.phone ?? "без телефона"}</div></div>
              <button className="text-sm text-accent" onClick={() => setClient(null)}>Изменить</button>
            </div>
          ) : (
            <>
              <input className="field" placeholder="Имя, телефон или Telegram" value={query} onChange={(e) => setQuery(e.target.value)} />
              {preset.loading && params.get("client") ? <Loading /> : found.data?.items.map((c) => (
                <button key={c.id} className="block w-full rounded-xl border border-line bg-card px-3 py-2 text-left" onClick={() => setClient(c)}>
                  <div className="font-medium">{c.name}</div><div className="text-sm text-muted">{c.phone ?? "без телефона"}</div>
                </button>
              ))}
              {found.data && !found.data.items.length && <div className="text-sm text-muted">Никого не нашли</div>}
            </>
          )
        ) : (
          <>
            <Field label="Имя"><input className="field" value={newName} onChange={(e) => setNewName(e.target.value)} /></Field>
            <Field label="Телефон"><input className="field" type="tel" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} placeholder="+7 900 000-00-00" /></Field>
          </>
        )}
      </Card>

      <Card className="space-y-3">
        {services.loading ? <Loading /> : services.error ? <ErrorState error={services.error} /> : (
          <Field label="Услуга">
            <select className="field" value={serviceId} onChange={(e) => { setServiceId(e.target.value); setSlot(null); }}>
              {services.data!.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.duration_minutes} мин</option>)}
            </select>
          </Field>
        )}
        <Field label="Дата"><input type="date" className="field" value={date} onChange={(e) => { setDate(e.target.value); setSlot(null); }} /></Field>
        <Toggle checked={manual} onChange={setManual} label="Время вручную (вне графика)" />
        {manual ? (
          <Field label="Время начала" hint="Пересечения с другими записями всё равно запрещены.">
            <input type="time" step={300} className="field" value={manualTime} onChange={(e) => setManualTime(e.target.value)} />
          </Field>
        ) : slots.loading ? <Loading /> : slots.error ? <ErrorState error={slots.error} /> : slots.data?.length ? (
          <SlotGrid slots={slots.data} value={slot?.starts_at ?? null} onChange={setSlot} />
        ) : <Notice kind="warn">Свободных слотов по графику нет. Можно указать время вручную.</Notice>}
        <Field label="Комментарий"><input className="field" value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
      </Card>
      {error && <Notice kind="error">{error}</Notice>}
      <Button className="w-full" disabled={!ready} loading={busy} onClick={submit}>Создать запись</Button>
    </Screen>
  );
}
