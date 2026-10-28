import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Card, Empty, ErrorState, Loading, Screen, StatusBadge } from "../../components/ui";
import { api, qs } from "../../lib/api";
import {
  addDays, fmtDateLong, fmtDateShort, fmtTime, localDate, MONTHS, monthGrid, startOfWeek, todayIn, WEEKDAYS_SHORT,
} from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import type { AdminAppointment, AppointmentStatus } from "../../lib/types";

type View = "day" | "week" | "month";
const FILTERS: [string, string, AppointmentStatus[]][] = [
  ["all", "Все", []],
  ["booked", "Активные", ["booked"]],
  ["completed", "Состоялись", ["completed"]],
  ["no_show", "Неявки", ["no_show"]],
  ["cancelled", "Отменённые", ["cancelled_by_client", "cancelled_by_admin"]],
];

export default function Schedule() {
  const { info } = useSession();
  const tz = info.timezone;
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") as View) || "day";
  const date = params.get("date") || todayIn(tz);
  const filter = params.get("status") || "all";
  const set = (patch: Record<string, string>) => setParams({ view, date, status: filter, ...patch }, { replace: true });

  const range = view === "day" ? { from: date, to: date }
    : view === "week" ? { from: startOfWeek(date), to: addDays(startOfWeek(date), 6) }
    : { from: monthGrid(date).first, to: monthGrid(date).last };
  const statuses = FILTERS.find((f) => f[0] === filter)?.[2] ?? [];
  const data = useAsync(
    () => api.get<AdminAppointment[]>(`/admin/appointments${qs({ date_from: range.from, date_to: range.to, status: statuses })}`),
    [range.from, range.to, filter],
  );

  const step = (dir: number) => {
    if (view === "day") set({ date: addDays(date, dir) });
    else if (view === "week") set({ date: addDays(date, 7 * dir) });
    else {
      const [y, m] = date.split("-").map(Number);
      const d = new Date(Date.UTC(y, m - 1 + dir, 1));
      set({ date: d.toISOString().slice(0, 10) });
    }
  };
  const title = view === "day" ? fmtDateLong(date)
    : view === "week" ? `${fmtDateShort(range.from)} — ${fmtDateShort(range.to)}`
    : `${MONTHS[+date.slice(5, 7) - 1]} ${date.slice(0, 4)}`;

  const byDay = new Map<string, AdminAppointment[]>();
  for (const a of data.data ?? []) {
    const d = localDate(a.starts_at, tz);
    byDay.set(d, [...(byDay.get(d) ?? []), a]);
  }

  return (
    <Screen title="Расписание" actions={<Button className="!min-h-[40px] !px-3 text-sm" onClick={() => navigate(`/admin/new?date=${date}`)}>+ Запись</Button>}>
      <div className="flex rounded-xl bg-line/60 p-1">
        {(["day", "week", "month"] as View[]).map((v) => (
          <button key={v} onClick={() => set({ view: v })}
            className={`flex-1 rounded-lg py-2 text-sm font-medium ${view === v ? "bg-card shadow-sm" : "text-muted"}`}>
            {{ day: "День", week: "Неделя", month: "Месяц" }[v]}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button className="h-10 w-10 rounded-xl border border-line bg-card text-xl" onClick={() => step(-1)} aria-label="Назад">‹</button>
        <div className="flex-1 text-center text-[15px] font-semibold">{title}</div>
        <button className="h-10 w-10 rounded-xl border border-line bg-card text-xl" onClick={() => step(1)} aria-label="Вперёд">›</button>
      </div>
      <div className="flex items-center gap-2">
        <input type="date" className="field !py-2" value={date} onChange={(e) => e.target.value && set({ date: e.target.value })} />
        <Button variant="secondary" className="!min-h-[42px] shrink-0 text-sm" onClick={() => set({ date: todayIn(tz) })}>Сегодня</Button>
      </div>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4">
        {FILTERS.map(([k, label]) => (
          <button key={k} className={`chip ${filter === k ? "chip-active" : ""}`} onClick={() => set({ status: k })}>{label}</button>
        ))}
      </div>

      {data.loading ? <Loading /> : data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : view === "month" ? (
        <MonthView date={date} byDay={byDay} onPick={(d) => set({ view: "day", date: d })} today={todayIn(tz)} />
      ) : view === "week" ? (
        Array.from({ length: 7 }, (_, i) => addDays(range.from, i)).map((d) => (
          <div key={d}>
            <button className="mb-1.5 text-sm font-semibold text-muted" onClick={() => set({ view: "day", date: d })}>
              {fmtDateShort(d)} {d === todayIn(tz) && <span className="text-accent">· сегодня</span>}
            </button>
            {(byDay.get(d) ?? []).length ? (
              <div className="space-y-2">{byDay.get(d)!.map((a) => <ApptRow key={a.id} a={a} tz={tz} />)}</div>
            ) : <div className="rounded-xl border border-dashed border-line px-3 py-2.5 text-sm text-muted">Записей нет</div>}
          </div>
        ))
      ) : !(data.data ?? []).length ? (
        <Empty icon="🌿" title="На этот день записей нет" action={<Button variant="secondary" onClick={() => navigate(`/admin/new?date=${date}`)}>Создать запись</Button>} />
      ) : (
        <div className="space-y-2">{data.data!.map((a) => <ApptRow key={a.id} a={a} tz={tz} />)}</div>
      )}
    </Screen>
  );
}

function ApptRow({ a, tz }: { a: AdminAppointment; tz: string }) {
  const navigate = useNavigate();
  const cancelled = a.status.startsWith("cancelled");
  return (
    <Card className={`!p-3 ${cancelled ? "opacity-60" : ""}`} onClick={() => navigate(`/admin/appointments/${a.id}`)}>
      <div className="flex gap-3">
        <div className="w-14 shrink-0 text-center">
          <div className="text-[17px] font-bold">{fmtTime(a.starts_at, tz)}</div>
          <div className="text-xs text-muted">{fmtTime(a.ends_at, tz)}</div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="truncate font-semibold">{a.client.name}</div>
            <StatusBadge status={a.status} />
          </div>
          <div className="truncate text-sm text-muted">{a.service_name}{a.client.phone ? ` · ${a.client.phone}` : ""}</div>
          {a.comment && <div className="mt-0.5 truncate text-sm">💬 {a.comment}</div>}
        </div>
      </div>
    </Card>
  );
}

function MonthView({ date, byDay, onPick, today }: { date: string; byDay: Map<string, AdminAppointment[]>; onPick: (d: string) => void; today: string }) {
  const { cells } = monthGrid(date);
  return (
    <div className="rounded-2xl border border-line bg-card p-2">
      <div className="grid grid-cols-7 gap-1 text-center">
        {WEEKDAYS_SHORT.map((w) => <div key={w} className="py-1 text-xs text-muted">{w}</div>)}
        {cells.map((d, i) => {
          if (!d) return <div key={i} />;
          const items = byDay.get(d) ?? [];
          const active = items.filter((a) => a.status === "booked").length;
          return (
            <button key={d} onClick={() => onPick(d)}
              className={`flex aspect-square flex-col items-center justify-center rounded-xl text-sm ${d === today ? "ring-2 ring-accent" : ""} ${items.length ? "bg-accent-soft" : ""}`}>
              <span className="font-medium">{+d.slice(8)}</span>
              {items.length > 0 && <span className="text-[11px] font-semibold text-accent">{active || items.length}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
