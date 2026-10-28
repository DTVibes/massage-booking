// Даты отображаются в часовом поясе массажиста (из настроек), а не устройства клиента.

const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
export const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
export const WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
export const WEEKDAYS_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];

function parts(iso: string | Date, tz: string) {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const p = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(d);
  const get = (t: string) => p.find((x) => x.type === t)!.value;
  return { y: +get("year"), m: +get("month"), d: +get("day"), hh: get("hour"), mm: get("minute") };
}

/** "YYYY-MM-DD" для момента времени в часовом поясе tz. */
export function localDate(iso: string | Date, tz: string): string {
  const p = parts(iso, tz);
  return `${p.y}-${String(p.m).padStart(2, "0")}-${String(p.d).padStart(2, "0")}`;
}

export function todayIn(tz: string): string {
  return localDate(new Date(), tz);
}

export function fmtTime(iso: string, tz: string): string {
  const p = parts(iso, tz);
  return `${p.hh}:${p.mm}`;
}

/** Номер дня недели 0 = понедельник для "YYYY-MM-DD". */
export function weekdayOf(date: string): number {
  const [y, m, d] = date.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

export function fmtDateLong(date: string): string {
  const [, m, d] = date.split("-").map(Number);
  return `${WEEKDAYS_FULL[weekdayOf(date)]}, ${d} ${MONTHS_GEN[m - 1]}`;
}

export function fmtDateShort(date: string): string {
  const [, m, d] = date.split("-").map(Number);
  return `${WEEKDAYS_SHORT[weekdayOf(date)].toLowerCase()}, ${d} ${MONTHS_GEN[m - 1]}`;
}

export function fmtDateTime(iso: string, tz: string): string {
  return `${fmtDateShort(localDate(iso, tz))}, ${fmtTime(iso, tz)}`;
}

export function fmtRange(start: string, end: string, tz: string): string {
  return `${fmtDateShort(localDate(start, tz))}, ${fmtTime(start, tz)}–${fmtTime(end, tz)}`;
}

export function addDays(date: string, n: number): string {
  const [y, m, d] = date.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.toISOString().slice(0, 10);
}

export function startOfWeek(date: string): string {
  return addDays(date, -weekdayOf(date));
}

export function monthGrid(date: string): { first: string; last: string; cells: (string | null)[] } {
  const [y, m] = date.split("-").map(Number);
  const first = `${y}-${String(m).padStart(2, "0")}-01`;
  const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const last = addDays(first, daysInMonth - 1);
  const cells: (string | null)[] = Array(weekdayOf(first)).fill(null);
  for (let i = 0; i < daysInMonth; i++) cells.push(addDays(first, i));
  while (cells.length % 7) cells.push(null);
  return { first, last, cells };
}

/** Локальные дата и время в часовом поясе tz → ISO-строка UTC. */
export function zonedToIso(date: string, time: string, tz: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const guess = Date.UTC(y, m - 1, d, hh, mm);
  const offset = (t: number) => {
    const p = parts(new Date(t), tz);
    return Date.UTC(p.y, p.m - 1, p.d, +p.hh, +p.mm) - t;
  };
  let ts = guess - offset(guess);
  ts = guess - offset(ts);
  return new Date(ts).toISOString();
}

export function fmtPrice(minor: number, currency: string): string {
  if (minor <= 0) return "по договорённости";
  try {
    return new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: minor % 100 ? 2 : 0 }).format(minor / 100);
  } catch {
    return `${minor / 100} ${currency}`;
  }
}

export function fmtDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return [h ? `${h} ч` : "", m ? `${m} мин` : ""].filter(Boolean).join(" ");
}

export const STATUS_LABEL: Record<string, string> = {
  booked: "Активна",
  cancelled_by_client: "Отменена клиентом",
  cancelled_by_admin: "Отменена массажистом",
  completed: "Визит состоялся",
  no_show: "Неявка",
};

export function phoneHref(phone: string): string {
  return `tel:${phone.replace(/[^+\d]/g, "")}`;
}
