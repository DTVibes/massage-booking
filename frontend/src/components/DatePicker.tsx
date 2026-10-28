import { addDays, MONTHS, weekdayOf, WEEKDAYS_SHORT } from "../lib/format";
import type { DateAvailability } from "../lib/types";

/** Календарь доступности: недоступные даты заблокированы, занятые дни визуально отличаются. */
export function DatePicker({ dates, value, onChange }: { dates: DateAvailability[]; value: string | null; onChange: (d: string) => void }) {
  if (!dates.length) return null;
  const byDate = new Map(dates.map((d) => [d.date, d]));
  const first = addDays(dates[0].date, -weekdayOf(dates[0].date));
  const lastDate = dates[dates.length - 1].date;
  const cells: string[] = [];
  for (let d = first; d <= lastDate || cells.length % 7; d = addDays(d, 1)) cells.push(d);
  const months = Array.from(new Set(dates.map((d) => +d.date.slice(5, 7))));

  return (
    <div className="rounded-2xl border border-line bg-card p-3">
      <div className="mb-2 px-1 text-sm font-semibold">{months.map((m) => MONTHS[m - 1]).join(" — ")}</div>
      <div className="grid grid-cols-7 gap-1.5 text-center">
        {WEEKDAYS_SHORT.map((w) => <div key={w} className="pb-1 text-xs text-muted">{w}</div>)}
        {cells.map((d) => {
          const a = byDate.get(d);
          const day = +d.slice(8, 10);
          if (!a) return <div key={d} className="py-2.5 text-sm text-muted/40">{day}</div>;
          const selected = value === d;
          const base = "relative rounded-xl py-2.5 text-[15px] transition";
          if (a.status === "closed")
            return <div key={d} className={`${base} text-muted/50`} title="Нерабочий день">{day}</div>;
          if (a.status === "full")
            return (
              <div key={d} className={`${base} bg-line/50 text-muted line-through decoration-muted/60`} title="Всё занято">{day}</div>
            );
          return (
            <button key={d} onClick={() => onChange(d)}
              className={`${base} font-semibold ${selected ? "bg-accent text-on-accent" : "bg-accent-soft text-accent active:scale-95"}`}>
              {day}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 px-1 text-xs text-muted">
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded bg-accent-soft ring-1 ring-accent/40" />есть время</span>
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded bg-line" />всё занято</span>
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded ring-1 ring-line" />выходной</span>
      </div>
    </div>
  );
}
