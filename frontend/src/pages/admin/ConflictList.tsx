import { Link } from "react-router-dom";
import { Notice } from "../../components/ui";
import { fmtRange } from "../../lib/format";
import type { Conflict } from "../../lib/types";

export function ConflictList({ conflicts, tz, saved }: { conflicts: Conflict[]; tz: string; saved?: boolean }) {
  if (!conflicts.length) return null;
  return (
    <Notice kind="warn">
      <div className="mb-1 font-semibold">
        {saved ? "Изменения сохранены. Эти записи вне нового графика — перенесите или отмените их:"
          : "Изменение затрагивает существующие записи. Записи не будут удалены автоматически:"}
      </div>
      <ul className="space-y-1">
        {conflicts.map((c) => (
          <li key={c.appointment_id}>
            <Link className="underline" to={`/admin/appointments/${c.appointment_id}`}>{fmtRange(c.starts_at, c.ends_at, tz)}</Link>
            {" "}— {c.client_name}{c.client_phone ? `, ${c.client_phone}` : ""}
          </li>
        ))}
      </ul>
    </Notice>
  );
}
