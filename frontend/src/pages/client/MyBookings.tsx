import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Empty, ErrorState, Loading, Notice, Screen, Sheet, StatusBadge, errorText } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtDuration, fmtPrice, fmtRange, phoneHref } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import { haptic } from "../../lib/telegram";
import type { Appointment, MyAppointments } from "../../lib/types";

type Tab = "upcoming" | "history" | "cancelled";
const TABS: [Tab, string][] = [["upcoming", "Предстоящие"], ["history", "История"], ["cancelled", "Отменённые"]];

export default function MyBookings() {
  const { info } = useSession();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("upcoming");
  const [cancelling, setCancelling] = useState<Appointment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const my = useAsync(() => api.get<MyAppointments>("/appointments/my"), []);

  async function cancel() {
    if (!cancelling) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/appointments/${cancelling.id}/cancel`, {});
      haptic.success();
      setCancelling(null);
      my.reload();
    } catch (e) {
      haptic.error();
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const list = my.data?.[tab] ?? [];
  const contact = info.contact_phone || info.contact_telegram;

  return (
    <Screen title="Мои записи">
      <div className="flex gap-2 overflow-x-auto">
        {TABS.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className={`chip ${tab === k ? "chip-active" : ""}`}>
            {label}{my.data && my.data[k].length ? ` · ${my.data[k].length}` : ""}
          </button>
        ))}
      </div>
      {my.loading ? <Loading /> : my.error ? <ErrorState error={my.error} onRetry={my.reload} /> : !list.length ? (
        tab === "upcoming"
          ? <Empty icon="🗓️" title="Нет предстоящих записей" action={<Button onClick={() => navigate("/book")}>Записаться</Button>} />
          : <Empty title={tab === "history" ? "История пока пуста" : "Отменённых записей нет"} />
      ) : list.map((a) => (
        <Card key={a.id}>
          <div className="flex items-start justify-between gap-2">
            <div className="font-semibold">{a.service_name}</div>
            <StatusBadge status={a.status} />
          </div>
          <div className="mt-1 text-[15px]">{fmtRange(a.starts_at, a.ends_at, info.timezone)}</div>
          <div className="text-sm text-muted">{fmtDuration(a.duration_minutes)} · {fmtPrice(a.price_minor, a.currency)}</div>
          {tab === "upcoming" && (
            a.can_cancel ? (
              <div className="mt-3 flex gap-2">
                {a.can_reschedule && <Button variant="secondary" className="flex-1" onClick={() => navigate(`/my/${a.id}/reschedule`)}>Перенести</Button>}
                <Button variant="danger" className="flex-1" onClick={() => { setError(null); setCancelling(a); }}>Отменить</Button>
              </div>
            ) : (
              <div className="mt-3">
                <Notice kind="warn">
                  До визита меньше {info.cancel_min_hours} ч — отменить или перенести запись можно только через массажиста.
                  {info.contact_phone && <> Телефон: <a className="font-semibold underline" href={phoneHref(info.contact_phone)}>{info.contact_phone}</a></>}
                  {!info.contact_phone && contact && <> Контакт: {contact}</>}
                </Notice>
              </div>
            )
          )}
        </Card>
      ))}

      <Sheet open={!!cancelling} onClose={() => setCancelling(null)} title="Отменить запись?">
        {cancelling && <div className="text-[15px]">{cancelling.service_name}, {fmtRange(cancelling.starts_at, cancelling.ends_at, info.timezone)}</div>}
        {error && <Notice kind="error">{error}</Notice>}
        <Button variant="danger" className="w-full" loading={busy} onClick={cancel}>Да, отменить</Button>
        <Button variant="ghost" className="w-full" onClick={() => setCancelling(null)}>Оставить запись</Button>
      </Sheet>
    </Screen>
  );
}
