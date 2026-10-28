import { useState } from "react";
import { Button, Card, ErrorState, Field, Loading, Notice, Screen, Sheet, Toggle, errorText } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { fmtDateTime, fmtTime, localDate, todayIn, WEEKDAYS_FULL, zonedToIso, addDays } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import { haptic } from "../../lib/telegram";
import type { AdminSettings, Conflict, DaySchedule, ExceptionType, Schedule } from "../../lib/types";
import { ConflictList } from "./ConflictList";

const hhmm = (t: string) => t.slice(0, 5);
const EX_LABEL: Record<ExceptionType, string> = { closed: "Закрыто", break: "Перерыв", open: "Доп. рабочее время" };
type ExKind = "dayoff" | "closed" | "break" | "open";

export default function WorkHours() {
  const { info } = useSession();
  const tz = info.timezone;
  const sched = useAsync(async () => {
    const s = await api.get<Schedule>("/admin/schedule");
    setDays(s.days.map((d) => ({ ...d, intervals: d.intervals.map((i) => ({ start: hhmm(i.start), end: hhmm(i.end) })) })));
    return s;
  }, []);
  const [days, setDays] = useState<DaySchedule[]>([]);
  const [conflicts, setConflicts] = useState<{ list: Conflict[]; saved: boolean; retry?: () => void } | null>(null);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [exOpen, setExOpen] = useState(false);

  function updateDay(wd: number, patch: Partial<DaySchedule>) {
    setDays((ds) => ds.map((d) => (d.weekday === wd ? { ...d, ...patch } : d)));
  }

  async function saveWeek(force = false) {
    setBusy(true);
    setMsg(null);
    setConflicts(null);
    try {
      const s = await api.put<Schedule>("/admin/schedule", { days, force });
      sched.setData(s);
      haptic.success();
      setMsg({ kind: "success", text: "График сохранён" });
      if (s.conflicts.length) setConflicts({ list: s.conflicts, saved: true });
    } catch (e) {
      if (e instanceof ApiError && e.code === "schedule_conflicts") {
        setConflicts({ list: e.details as Conflict[], saved: false, retry: () => saveWeek(true) });
      } else setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  async function deleteException(id: number, force = false) {
    setConflicts(null);
    try {
      await api.del(`/admin/schedule/exceptions/${id}${force ? "?force=true" : ""}`);
      sched.reload();
    } catch (e) {
      if (e instanceof ApiError && e.code === "schedule_conflicts")
        setConflicts({ list: e.details as Conflict[], saved: false, retry: () => deleteException(id, true) });
      else setMsg({ kind: "error", text: errorText(e) });
    }
  }

  return (
    <Screen title="Рабочий график">
      {sched.loading && !sched.data ? <Loading /> : sched.error ? <ErrorState error={sched.error} onRetry={sched.reload} /> : (
        <>
          <p className="text-sm text-muted">Часовой пояс: {tz}. Несколько интервалов в день = перерыв между ними.</p>
          {days.map((d) => (
            <Card key={d.weekday} className="!p-3">
              <Toggle checked={d.is_working_day} label={<span className="font-semibold">{WEEKDAYS_FULL[d.weekday]}</span>}
                onChange={(v) => updateDay(d.weekday, { is_working_day: v, intervals: v && !d.intervals.length ? [{ start: "10:00", end: "19:00" }] : d.intervals })} />
              {d.is_working_day ? (
                <div className="mt-2 space-y-2">
                  {d.intervals.map((iv, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input type="time" className="field !py-2" value={iv.start}
                        onChange={(e) => updateDay(d.weekday, { intervals: d.intervals.map((x, j) => (j === i ? { ...x, start: e.target.value } : x)) })} />
                      <span className="text-muted">—</span>
                      <input type="time" className="field !py-2" value={iv.end}
                        onChange={(e) => updateDay(d.weekday, { intervals: d.intervals.map((x, j) => (j === i ? { ...x, end: e.target.value } : x)) })} />
                      {d.intervals.length > 1 && (
                        <button className="px-2 text-xl text-danger" aria-label="Удалить интервал"
                          onClick={() => updateDay(d.weekday, { intervals: d.intervals.filter((_, j) => j !== i) })}>×</button>
                      )}
                    </div>
                  ))}
                  <button className="text-sm text-accent" onClick={() => {
                    const last = d.intervals[d.intervals.length - 1];
                    updateDay(d.weekday, { intervals: [...d.intervals, { start: last ? last.end : "10:00", end: "20:00" }] });
                  }}>+ интервал</button>
                </div>
              ) : <div className="text-sm text-muted">Выходной</div>}
            </Card>
          ))}
          {conflicts && <ConflictList conflicts={conflicts.list} tz={tz} saved={conflicts.saved} />}
          {conflicts?.retry && <Button variant="secondary" className="w-full" onClick={conflicts.retry}>Всё равно сохранить</Button>}
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
          <Button className="w-full" loading={busy} onClick={() => saveWeek(false)}>Сохранить график</Button>

          <div className="flex items-center justify-between pt-2">
            <h2 className="text-lg font-bold">Исключения</h2>
            <Button variant="secondary" className="!min-h-[38px] text-sm" onClick={() => setExOpen(true)}>+ Добавить</Button>
          </div>
          {!sched.data!.exceptions.length ? <div className="text-sm text-muted">Разовых изменений нет</div> :
            sched.data!.exceptions.map((e) => (
              <Card key={e.id} className="!p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold">{EX_LABEL[e.exception_type]}</div>
                    <div className="text-sm">{fmtDateTime(e.starts_at, tz)} — {localDate(e.starts_at, tz) === localDate(e.ends_at, tz) ? fmtTime(e.ends_at, tz) : fmtDateTime(e.ends_at, tz)}</div>
                    {e.reason && <div className="text-sm text-muted">{e.reason}</div>}
                  </div>
                  <button className="text-sm text-danger" onClick={() => deleteException(e.id)}>Удалить</button>
                </div>
              </Card>
            ))}
          <BookingParams />
          <ExceptionSheet open={exOpen} onClose={() => setExOpen(false)} tz={tz}
            onCreated={(c) => { setExOpen(false); sched.reload(); if (c.length) setConflicts({ list: c, saved: true }); }} />
        </>
      )}
    </Screen>
  );
}

function ExceptionSheet({ open, onClose, tz, onCreated }: { open: boolean; onClose: () => void; tz: string; onCreated: (c: Conflict[]) => void }) {
  const [kind, setKind] = useState<ExKind>("dayoff");
  const [date, setDate] = useState(todayIn(tz));
  const [dateTo, setDateTo] = useState(todayIn(tz));
  const [start, setStart] = useState("13:00");
  const [end, setEnd] = useState("14:00");
  const [reason, setReason] = useState("");
  const [conflicts, setConflicts] = useState<Conflict[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(force = false) {
    setError(null);
    const body = kind === "dayoff"
      ? { exception_type: "closed", starts_at: zonedToIso(date, "00:00", tz), ends_at: zonedToIso(addDays(dateTo < date ? date : dateTo, 1), "00:00", tz) }
      : { exception_type: kind, starts_at: zonedToIso(date, start, tz), ends_at: zonedToIso(date, end, tz) };
    try {
      const r = await api.post<{ conflicts: Conflict[] }>("/admin/schedule/exceptions", { ...body, reason: reason || null, force });
      setConflicts(null);
      onCreated(r.conflicts ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.code === "schedule_conflicts") setConflicts(e.details as Conflict[]);
      else setError(errorText(e));
    }
  }

  const kinds: [ExKind, string][] = [["dayoff", "Выходной"], ["closed", "Закрыть время"], ["break", "Перерыв"], ["open", "Доп. время"]];
  return (
    <Sheet open={open} onClose={onClose} title="Разовое изменение графика">
      <div className="flex flex-wrap gap-2">
        {kinds.map(([k, l]) => <button key={k} className={`chip ${kind === k ? "chip-active" : ""}`} onClick={() => { setKind(k); setConflicts(null); }}>{l}</button>)}
      </div>
      {kind === "dayoff" ? (
        <div className="grid grid-cols-2 gap-2">
          <Field label="С"><input type="date" className="field" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="По (включительно)"><input type="date" className="field" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></Field>
        </div>
      ) : (
        <>
          <Field label="Дата"><input type="date" className="field" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="С"><input type="time" className="field" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
            <Field label="До"><input type="time" className="field" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
          </div>
        </>
      )}
      <Field label="Комментарий"><input className="field" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Например: отпуск" /></Field>
      {conflicts && <ConflictList conflicts={conflicts} tz={tz} />}
      {error && <Notice kind="error">{error}</Notice>}
      {conflicts ? (
        <Button className="w-full" onClick={() => submit(true)}>Сохранить, записи разберу вручную</Button>
      ) : <Button className="w-full" onClick={() => submit(false)}>Сохранить</Button>}
    </Sheet>
  );
}

function BookingParams() {
  const s = useAsync(() => api.get<AdminSettings>("/admin/settings"), []);
  const [form, setForm] = useState<Partial<AdminSettings>>({});
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  if (!s.data) return null;
  const v = { ...s.data, ...form };
  const num = (k: keyof AdminSettings) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: Number(e.target.value) });
  async function save() {
    try {
      s.setData(await api.patch<AdminSettings>("/admin/settings", form));
      setForm({});
      setMsg({ kind: "success", text: "Параметры записи сохранены" });
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    }
  }
  return (
    <Card className="space-y-3">
      <h2 className="font-semibold">Параметры записи</h2>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Шаг начала, мин"><input type="number" className="field" value={v.slot_step_minutes} onChange={num("slot_step_minutes")} /></Field>
        <Field label="Буфер после, мин"><input type="number" className="field" value={v.buffer_minutes} onChange={num("buffer_minutes")} /></Field>
        <Field label="Горизонт, дней"><input type="number" className="field" value={v.booking_horizon_days} onChange={num("booking_horizon_days")} /></Field>
        <Field label="Мин. до визита, мин"><input type="number" className="field" value={v.min_lead_minutes} onChange={num("min_lead_minutes")} /></Field>
      </div>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {Object.keys(form).length > 0 && <Button className="w-full" onClick={save}>Сохранить параметры</Button>}
    </Card>
  );
}
