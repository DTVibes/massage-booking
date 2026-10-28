import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { DatePicker } from "../../components/DatePicker";
import { SlotGrid } from "../../components/SlotGrid";
import { Button, Card, Empty, ErrorState, Loading, Notice, Screen, errorText } from "../../components/ui";
import { api, ApiError, qs } from "../../lib/api";
import { fmtDateLong, fmtRange, fmtTime } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import { haptic } from "../../lib/telegram";
import type { DateAvailability, MyAppointments, Slot } from "../../lib/types";

export default function Reschedule() {
  const { id } = useParams();
  const { info } = useSession();
  const navigate = useNavigate();
  const [date, setDate] = useState<string | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const appt = useAsync(async () => {
    const my = await api.get<MyAppointments>("/appointments/my");
    const a = my.upcoming.find((x) => x.id === id);
    if (!a) throw new ApiError(404, "not_found", "Запись не найдена или уже неактивна");
    return a;
  }, [id]);
  const a = appt.data;
  const dates = useAsync(
    () => (a?.service_id ? api.get<DateAvailability[]>(`/availability/dates${qs({ service_id: a.service_id })}`) : Promise.resolve([])),
    [a?.service_id],
  );
  const slots = useAsync(
    () => (a && date ? api.get<Slot[]>(`/availability/slots${qs({ date, exclude_appointment_id: a.id })}`) : Promise.resolve([])),
    [a?.id, date],
  );

  async function submit() {
    if (!a || !slot) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/appointments/${a.id}/reschedule`, { starts_at: slot.starts_at });
      haptic.success();
      navigate("/my", { replace: true });
    } catch (e) {
      haptic.error();
      setError(errorText(e) + (e instanceof ApiError && e.code === "slot_taken" ? " Ваша текущая запись сохранена." : ""));
      if (e instanceof ApiError && e.code === "slot_taken") { setSlot(null); slots.reload(); }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen title="Перенос записи" back="/my">
      {appt.loading ? <Loading /> : appt.error ? <ErrorState error={appt.error} /> : a && (
        <>
          <Card>
            <div className="text-sm text-muted">Сейчас</div>
            <div className="font-semibold">{a.service_name}</div>
            <div className="text-[15px]">{fmtRange(a.starts_at, a.ends_at, info.timezone)}</div>
          </Card>
          {!a.service_id ? <Notice kind="warn">Услуга больше недоступна. Свяжитесь с массажистом для переноса.</Notice> :
            dates.loading ? <Loading /> : dates.error ? <ErrorState error={dates.error} onRetry={dates.reload} /> : (
              <DatePicker dates={dates.data!} value={date} onChange={(d) => { setDate(d); setSlot(null); }} />
            )}
          {date && (
            <>
              <h2 className="font-semibold">{fmtDateLong(date)}</h2>
              {slots.loading ? <Loading /> : slots.error ? <ErrorState error={slots.error} onRetry={slots.reload} /> :
                !slots.data?.length ? <Empty icon="⏳" title="Свободного времени нет" /> :
                  <SlotGrid slots={slots.data.filter((s) => s.starts_at !== a.starts_at)} value={slot?.starts_at ?? null} onChange={setSlot} />}
            </>
          )}
          {error && <Notice kind="error">{error}</Notice>}
          {slot && (
            <Button className="w-full" loading={busy} onClick={submit}>
              Перенести на {fmtTime(slot.starts_at, info.timezone)}
            </Button>
          )}
        </>
      )}
    </Screen>
  );
}
