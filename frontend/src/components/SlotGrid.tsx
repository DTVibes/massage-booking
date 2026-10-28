import type { Slot } from "../lib/types";

export function SlotGrid({ slots, value, onChange }: { slots: Slot[]; value: string | null; onChange: (s: Slot) => void }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {slots.map((s) => (
        <button key={s.starts_at} onClick={() => onChange(s)}
          className={`rounded-xl border py-3 text-[15px] font-semibold transition active:scale-95 ${
            value === s.starts_at ? "border-accent bg-accent text-on-accent" : "border-line bg-card text-ink"}`}>
          {s.local_time}
        </button>
      ))}
    </div>
  );
}
