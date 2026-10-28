import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DatePicker } from "../../components/DatePicker";
import { PhoneForm } from "../../components/PhoneForm";
import { SlotGrid } from "../../components/SlotGrid";
import { Button, Card, Empty, ErrorState, Field, Loading, Notice, Row, Screen, errorText } from "../../components/ui";
import { api, ApiError, newIdempotencyKey, qs } from "../../lib/api";
import { fmtDateLong, fmtDuration, fmtPrice, fmtTime } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import { haptic } from "../../lib/telegram";
import type { Appointment, DateAvailability, Service, Slot } from "../../lib/types";

type Step = "service" | "date" | "time" | "confirm" | "done";

export default function Book() {
  const navigate = useNavigate();
  const { user, info, setUser } = useSession();
  const [step, setStep] = useState<Step>("service");
  const [service, setService] = useState<Service | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [comment, setComment] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Appointment | null>(null);
  // Один ключ на попытку подтверждения: повторная отправка не создаст дубль.
  const idemKey = useMemo(() => newIdempotencyKey(), [service?.id, slot?.starts_at]);

  const services = useAsync(() => api.get<Service[]>("/services"), []);
  useEffect(() => {
    if (services.data?.length === 1 && !service) setService(services.data[0]);
  }, [services.data, service]);

  const dates = useAsync(
    () => (service ? api.get<DateAvailability[]>(`/availability/dates${qs({ service_id: service.id })}`) : Promise.resolve([])),
    [service?.id, step === "date"],
  );
  const slots = useAsync(
    () => (service && date ? api.get<Slot[]>(`/availability/slots${qs({ service_id: service.id, date })}`) : Promise.resolve([])),
    [service?.id, date, step === "time"],
  );

  const back = useCallback(() => {
    setError(null);
    if (step === "service" || step === "done") navigate("/");
    else if (step === "date") setStep(services.data && services.data.length > 1 ? "service" : "service");
    else if (step === "time") setStep("date");
    else if (step === "confirm") setStep("time");
  }, [step, navigate, services.data]);

  async function confirm() {
    if (!service || !slot) return;
    setSubmitting(true);
    setError(null);
    try {
      const a = await api.post<Appointment>("/appointments",
        { service_id: service.id, starts_at: slot.starts_at, comment: comment.trim() || null },
        { "Idempotency-Key": idemKey });
      haptic.success();
      setCreated(a);
      setStep("done");
    } catch (e) {
      haptic.error();
      if (e instanceof ApiError && (e.code === "slot_taken" || e.code === "too_soon" || e.code === "past_time")) {
        setNotice(e.message);
        setSlot(null);
        setStep("time");
        slots.reload();
      } else setError(errorText(e));
    } finally {
      setSubmitting(false);
    }
  }

  const tz = info.timezone;

  if (step === "done" && created) {
    return (
      <Screen>
        <div className="flex flex-col items-center gap-2 pt-8 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent-soft text-3xl">✓</div>
          <h1 className="text-[22px] font-bold">Вы записаны!</h1>
          <p className="text-[15px] text-muted">Подтверждение придёт в чат с ботом. Напомним за 24 и за 2 часа до визита.</p>
        </div>
        <Card>
          <Row label="Услуга" value={created.service_name} />
          <Row label="Дата" value={fmtDateLong(date!)} />
          <Row label="Время" value={`${fmtTime(created.starts_at, tz)}–${fmtTime(created.ends_at, tz)}`} />
          {info.address && <Row label="Адрес" value={info.address} />}
        </Card>
        <Button className="w-full" onClick={() => navigate("/my")}>Мои записи</Button>
        <Button variant="ghost" className="w-full" onClick={() => navigate("/")}>На главную</Button>
      </Screen>
    );
  }

  if (step === "service" || !service) {
    return (
      <Screen title="Выберите услугу" back={back}>
        {services.loading ? <Loading /> : services.error ? <ErrorState error={services.error} onRetry={services.reload} /> :
          !services.data?.length ? (
            <Empty icon="🌙" title="Запись временно недоступна" text="Сейчас нет доступных услуг. Пожалуйста, свяжитесь с массажистом." />
          ) : services.data.map((s) => (
            <Card key={s.id} onClick={() => { setService(s); setDate(null); setSlot(null); setStep("date"); }}
              className={service?.id === s.id ? "border-accent" : ""}>
              <div className="flex items-start justify-between gap-3">
                <div className="text-[17px] font-semibold">{s.name}</div>
                <div className="whitespace-nowrap font-semibold text-accent">{fmtPrice(s.price_minor, s.currency)}</div>
              </div>
              {s.description && <p className="mt-1 text-[15px] text-muted">{s.description}</p>}
              <div className="mt-2 text-sm text-muted">⏱ {fmtDuration(s.duration_minutes)}</div>
            </Card>
          ))}
        {services.data?.length === 1 && service && (
          <Button className="w-full" onClick={() => setStep("date")}>Выбрать дату</Button>
        )}
      </Screen>
    );
  }

  if (step === "date") {
    const anyFree = dates.data?.some((d) => d.status === "available");
    return (
      <Screen title="Выберите дату" back={back}>
        <ServiceSummary service={service} />
        {dates.loading ? <Loading /> : dates.error ? <ErrorState error={dates.error} onRetry={dates.reload} /> : (
          <>
            <DatePicker dates={dates.data!} value={date} onChange={(d) => { setDate(d); setSlot(null); setNotice(null); setStep("time"); }} />
            {!anyFree && (
              <Notice kind="warn">На ближайшие {info.booking_horizon_days} дн. свободного времени нет. Загляните позже или свяжитесь с массажистом.</Notice>
            )}
          </>
        )}
      </Screen>
    );
  }

  if (step === "time") {
    return (
      <Screen title={fmtDateLong(date!)} back={back}>
        <ServiceSummary service={service} />
        {notice && <Notice kind="warn">{notice}</Notice>}
        {slots.loading ? <Loading /> : slots.error ? <ErrorState error={slots.error} onRetry={slots.reload} /> :
          !slots.data?.length ? (
            <Empty icon="⏳" title="На эту дату свободного времени нет" action={<Button variant="secondary" onClick={() => setStep("date")}>Выбрать другую дату</Button>} />
          ) : (
            <>
              <SlotGrid slots={slots.data} value={slot?.starts_at ?? null} onChange={(s) => { haptic.tap(); setSlot(s); }} />
              <Button className="w-full" disabled={!slot} onClick={() => { setNotice(null); setStep("confirm"); }}>Продолжить</Button>
            </>
          )}
      </Screen>
    );
  }

  // confirm
  return (
    <Screen title="Подтверждение" back={back}>
      <Card>
        <Row label="Услуга" value={service.name} />
        <Row label="Дата" value={fmtDateLong(date!)} />
        <Row label="Время" value={`${fmtTime(slot!.starts_at, tz)}–${fmtTime(slot!.ends_at, tz)}`} />
        <Row label="Длительность" value={fmtDuration(service.duration_minutes)} />
        <Row label="Стоимость" value={fmtPrice(service.price_minor, service.currency)} />
        {user.phone && <Row label="Телефон" value={user.phone} />}
        {info.address && <Row label="Адрес" value={info.address} />}
      </Card>

      {!user.phone && (
        <Card>
          <div className="mb-3 font-semibold">Укажите телефон, чтобы завершить запись</div>
          <PhoneForm user={user} onSaved={setUser} submitLabel="Сохранить телефон" />
        </Card>
      )}

      <Field label="Комментарий для массажиста (необязательно)">
        <textarea className="field min-h-[72px]" maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
      </Field>

      <Notice>
        Отменить или перенести запись можно в приложении не позднее чем за {info.cancel_min_hours} ч до визита.
        Оплата — на месте.
      </Notice>
      {error && <Notice kind="error">{error}</Notice>}
      <Button className="w-full" loading={submitting} disabled={!user.phone} onClick={confirm}>Подтвердить запись</Button>
    </Screen>
  );
}

function ServiceSummary({ service }: { service: Service }) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-accent-soft/60 px-3.5 py-2.5 text-sm">
      <span className="font-medium">{service.name}</span>
      <span className="text-muted">{fmtDuration(service.duration_minutes)} · {fmtPrice(service.price_minor, service.currency)}</span>
    </div>
  );
}
