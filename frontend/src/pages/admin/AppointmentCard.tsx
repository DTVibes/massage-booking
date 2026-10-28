import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { SlotGrid } from "../../components/SlotGrid";
import { Button, Card, ErrorState, Field, Loading, Notice, Row, Screen, Sheet, StatusBadge, Toggle, errorText } from "../../components/ui";
import { api, qs } from "../../lib/api";
import { fmtDateTime, fmtDuration, fmtPrice, fmtRange, localDate, phoneHref, STATUS_LABEL, todayIn, zonedToIso } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import { haptic, openTelegramUser } from "../../lib/telegram";
import type { AdminAppointmentDetail, HistoryItem, Slot } from "../../lib/types";

const ACTIONS: Record<string, string> = {
  created: "Создана", cancelled: "Отменена", rescheduled: "Перенесена", status_changed: "Статус изменён", updated: "Изменена",
};

export default function AppointmentCard() {
  const { id } = useParams();
  const { info } = useSession();
  const tz = info.timezone;
  const navigate = useNavigate();
  const appt = useAsync(() => api.get<AdminAppointmentDetail>(`/admin/appointments/${id}`), [id]);
  const [sheet, setSheet] = useState<"cancel" | "move" | "comment" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [notify, setNotify] = useState(true);
  const [comment, setComment] = useState("");
  const [moveDate, setMoveDate] = useState(todayIn(tz));
  const [slot, setSlot] = useState<Slot | null>(null);
  const [manual, setManual] = useState(false);
  const [manualTime, setManualTime] = useState("10:00");
  const slots = useAsync(
    () => sheet === "move" && !manual ? api.get<Slot[]>(`/admin/availability/slots${qs({ date: moveDate, appointment_id: id })}`) : Promise.resolve([]),
    [sheet, moveDate, manual, id],
  );

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      appt.setData(await api.patch<AdminAppointmentDetail>(`/admin/appointments/${id}`, body));
      haptic.success();
      setSheet(null);
    } catch (e) {
      haptic.error();
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const a = appt.data;
  const now = new Date().toISOString();
  return (
    <Screen title="Запись" back={true}>
      {appt.loading && !a ? <Loading /> : appt.error ? <ErrorState error={appt.error} onRetry={appt.reload} /> : a && (
        <>
          <Card>
            <div className="flex items-start justify-between gap-2">
              <div className="text-lg font-semibold">{a.service_name}</div>
              <StatusBadge status={a.status} />
            </div>
            <div className="mt-1 text-[15px]">{fmtRange(a.starts_at, a.ends_at, tz)}</div>
            <div className="mt-2 border-t border-line pt-2">
              <Row label="Длительность" value={fmtDuration(a.duration_minutes)} />
              <Row label="Буфер после" value={`${a.buffer_minutes} мин`} />
              <Row label="Стоимость" value={fmtPrice(a.price_minor, a.currency)} />
              {a.comment && <Row label="Комментарий" value={a.comment} />}
            </div>
          </Card>
          <Card>
            <div className="flex items-center justify-between">
              <Link to={`/admin/clients/${a.client.id}`} className="font-semibold text-accent">{a.client.name} ›</Link>
              {(a.client.username || a.client.telegram_id) && (
                <button className="text-sm text-accent" onClick={() => openTelegramUser(a.client.username, a.client.telegram_id)}>Написать</button>
              )}
            </div>
            {a.client.phone && <a className="mt-1 block text-[15px] text-accent" href={phoneHref(a.client.phone)}>📞 {a.client.phone}</a>}
          </Card>

          {a.status === "booked" && (
            <div className="grid grid-cols-2 gap-2">
              <Button variant="secondary" onClick={() => { setError(null); setSlot(null); setMoveDate(localDate(a.starts_at, tz)); setSheet("move"); }}>Перенести</Button>
              <Button variant="danger" onClick={() => { setError(null); setReason(""); setSheet("cancel"); }}>Отменить</Button>
              {a.starts_at <= now && <Button variant="secondary" loading={busy} onClick={() => patch({ status: "completed" })}>Визит состоялся</Button>}
              {a.starts_at <= now && <Button variant="secondary" loading={busy} onClick={() => patch({ status: "no_show" })}>Неявка</Button>}
            </div>
          )}
          {(a.status === "completed" || a.status === "no_show") && (
            <Button variant="secondary" className="w-full" loading={busy}
              onClick={() => patch({ status: a.status === "completed" ? "no_show" : "completed" })}>
              Изменить на «{STATUS_LABEL[a.status === "completed" ? "no_show" : "completed"]}»
            </Button>
          )}
          <Button variant="ghost" className="w-full" onClick={() => { setComment(a.comment ?? ""); setError(null); setSheet("comment"); }}>
            {a.comment ? "Изменить комментарий" : "Добавить комментарий"}
          </Button>
          {error && !sheet && <Notice kind="error">{error}</Notice>}

          <div>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">История изменений</h2>
            <Card className="space-y-2">
              {a.history.map((h) => <HistoryLine key={h.id} h={h} tz={tz} />)}
            </Card>
          </div>

          <Sheet open={sheet === "cancel"} onClose={() => setSheet(null)} title="Отменить запись">
            <Field label="Причина (увидит клиент)">
              <input className="field" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
            </Field>
            <Toggle checked={notify} onChange={setNotify} label="Уведомить клиента" />
            {error && <Notice kind="error">{error}</Notice>}
            <Button variant="danger" className="w-full" loading={busy}
              onClick={() => patch({ status: "cancelled_by_admin", reason: reason || null, notify_client: notify })}>Отменить запись</Button>
          </Sheet>

          <Sheet open={sheet === "move"} onClose={() => setSheet(null)} title="Перенести запись">
            <Field label="Дата">
              <input type="date" className="field" value={moveDate} onChange={(e) => { setMoveDate(e.target.value); setSlot(null); }} />
            </Field>
            <Toggle checked={manual} onChange={setManual} label="Указать время вручную (вне графика)" />
            {manual ? (
              <Field label="Время начала"><input type="time" step={300} className="field" value={manualTime} onChange={(e) => setManualTime(e.target.value)} /></Field>
            ) : slots.loading ? <Loading /> : slots.error ? <ErrorState error={slots.error} /> : slots.data?.length ? (
              <SlotGrid slots={slots.data} value={slot?.starts_at ?? null} onChange={setSlot} />
            ) : <Notice kind="warn">На эту дату свободных слотов по графику нет.</Notice>}
            <Toggle checked={notify} onChange={setNotify} label="Уведомить клиента" />
            {error && <Notice kind="error">{error}</Notice>}
            <Button className="w-full" loading={busy} disabled={!manual && !slot}
              onClick={() => patch({
                starts_at: manual ? zonedToIso(moveDate, manualTime, tz) : slot!.starts_at,
                ignore_schedule: manual, notify_client: notify,
              })}>Перенести</Button>
          </Sheet>

          <Sheet open={sheet === "comment"} onClose={() => setSheet(null)} title="Комментарий">
            <textarea className="field min-h-[100px]" value={comment} maxLength={1000} onChange={(e) => setComment(e.target.value)} />
            {error && <Notice kind="error">{error}</Notice>}
            <Button className="w-full" loading={busy} onClick={() => patch({ comment })}>Сохранить</Button>
          </Sheet>
          <Button variant="ghost" className="w-full" onClick={() => navigate(`/admin?date=${localDate(a.starts_at, tz)}`)}>К расписанию дня</Button>
        </>
      )}
    </Screen>
  );
}

function HistoryLine({ h, tz }: { h: HistoryItem; tz: string }) {
  const who = h.actor_role === "admin" ? "массажист" : h.actor_role === "client" ? "клиент" : "система";
  let detail = "";
  if (h.action === "rescheduled" && h.old_starts_at && h.new_starts_at)
    detail = `${fmtDateTime(h.old_starts_at, tz)} → ${fmtDateTime(h.new_starts_at, tz)}`;
  else if (h.new_status && h.action !== "created") detail = STATUS_LABEL[h.new_status] ?? h.new_status;
  const reason = (h.details as { reason?: string } | null)?.reason;
  return (
    <div className="text-sm">
      <div><span className="font-medium">{ACTIONS[h.action] ?? h.action}</span> · {who}</div>
      {detail && <div className="text-muted">{detail}</div>}
      {reason && <div className="text-muted">Причина: {reason}</div>}
      <div className="text-xs text-muted">{fmtDateTime(h.created_at, tz)}</div>
    </div>
  );
}
