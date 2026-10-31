import { Link, useNavigate } from "react-router-dom";
import { Button, Card, Loading, Screen, StatusBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtDuration, fmtRange, phoneHref } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import type { MyAppointments } from "../../lib/types";

export default function Home() {
  const { user, info } = useSession();
  const navigate = useNavigate();
  const my = useAsync(() => api.get<MyAppointments>("/appointments/my"), []);
  const next = my.data?.upcoming[0];
  const firstName = user.name.split(" ")[0];

  return (
    <Screen>
      <div className="pt-2">
        <div className="text-sm text-muted">{info.master_name || "Запись на массаж"}</div>
        <h1 className="mt-1 text-[26px] font-bold leading-tight">{info.studio_name}</h1>
      </div>
      <Card className="bg-accent-soft/60">
        <div className="text-lg font-semibold">Здравствуйте, {firstName}! 🌿</div>
        <p className="mt-1 text-[15px] text-muted">
          {info.welcome_text || "Выберите услугу, удобную дату и время — запись займёт меньше минуты."}
        </p>
        <Button className="mt-4 w-full" onClick={() => navigate("/book")}>Записаться на массаж</Button>
      </Card>

      {user.role === "admin" && (
        <Button variant="secondary" className="w-full" onClick={() => { sessionStorage.removeItem("clientMode"); navigate("/admin"); }}>
          Открыть панель администратора
        </Button>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Ближайшая запись</h2>
        {my.loading ? <Loading /> : next ? (
          <Card onClick={() => navigate("/my")}>
            <div className="flex items-start justify-between gap-2">
              <div className="font-semibold">{next.service_name}</div>
              <StatusBadge status={next.status} />
            </div>
            <div className="mt-1 text-[15px]">{fmtRange(next.starts_at, next.ends_at, info.timezone)}</div>
            <div className="text-sm text-muted">{fmtDuration(next.duration_minutes)}</div>
          </Card>
        ) : (
          <Card><div className="text-[15px] text-muted">У вас пока нет записей. Самое время позаботиться о себе — запишитесь на первый сеанс.</div></Card>
        )}
      </div>

      {(info.address || info.contact_phone || info.contact_telegram) && (
        <Card>
          <h2 className="mb-2 font-semibold">Контакты</h2>
          <div className="space-y-1.5 text-[15px]">
            {info.address && <div>📍 {info.address}</div>}
            {info.contact_phone && <div>📞 <a className="text-accent" href={phoneHref(info.contact_phone)}>{info.contact_phone}</a></div>}
            {info.contact_telegram && <div>✈️ {info.contact_telegram}</div>}
          </div>
        </Card>
      )}

      <Link to="/privacy" className="block text-center text-sm text-muted underline">Политика конфиденциальности</Link>
    </Screen>
  );
}
