import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Card, ErrorState, Field, Loading, Notice, Row, Screen, Sheet, StatusBadge, Toggle, errorText } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtDateShort, fmtRange, localDate, phoneHref } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import { openTelegramUser } from "../../lib/telegram";
import type { AdminClientDetail } from "../../lib/types";

export default function ClientCard() {
  const { id } = useParams();
  const { info } = useSession();
  const tz = info.timezone;
  const navigate = useNavigate();
  const [notes, setNotes] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [askAnon, setAskAnon] = useState(false);
  const [anonBusy, setAnonBusy] = useState(false);

  async function anonymize() {
    setAnonBusy(true);
    setMsg(null);
    try {
      const d = await api.post<AdminClientDetail>(`/admin/clients/${id}/anonymize`);
      c.setData(d);
      setNotes("");
      setMsg({ kind: "success", text: "Персональные данные клиента удалены" });
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setAnonBusy(false);
      setAskAnon(false);
    }
  }
  const c = useAsync(async () => {
    const d = await api.get<AdminClientDetail>(`/admin/clients/${id}`);
    setNotes(d.admin_notes ?? "");
    return d;
  }, [id]);

  async function patch(body: Record<string, unknown>, ok: string) {
    setMsg(null);
    try {
      const d = await api.patch<AdminClientDetail>(`/admin/clients/${id}`, body);
      c.setData(d);
      setMsg({ kind: "success", text: ok });
      setEditing(false);
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    }
  }

  const d = c.data;
  return (
    <Screen title="Клиент" back={true}>
      {c.loading && !d ? <Loading /> : c.error ? <ErrorState error={c.error} onRetry={c.reload} /> : d && (
        <>
          <Card>
            <div className="text-lg font-semibold">{d.name}</div>
            {d.phone ? <a className="text-[15px] text-accent" href={phoneHref(d.phone)}>📞 {d.phone}</a> : <div className="text-sm text-muted">Телефон не указан</div>}
            <div className="mt-2 border-t border-line pt-2">
              <Row label="Telegram ID" value={d.telegram_id ?? "—"} />
              {d.username && <Row label="Username" value={`@${d.username}`} />}
              <Row label="Регистрация" value={new Date(d.created_at).toLocaleDateString("ru-RU")} />
              <Row label="Визитов" value={d.completed_count} />
              <Row label="Отмен" value={d.cancelled_count} />
              <Row label="Неявок" value={d.no_show_count} />
              <Row label="Последний визит" value={d.last_visit_at ? fmtDateShort(localDate(d.last_visit_at, tz)) : "—"} />
              <Row label="Согласие на обработку данных"
                value={d.privacy_accepted_at ? new Date(d.privacy_accepted_at).toLocaleDateString("ru-RU") : "нет"} />
            </div>
            {d.anonymized_at && (
              <div className="mt-2">
                <Notice>Данные клиента удалены {new Date(d.anonymized_at).toLocaleDateString("ru-RU")} по запросу.</Notice>
              </div>
            )}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Button variant="secondary" onClick={() => navigate(`/admin/new?client=${d.id}`)}>Записать</Button>
              {(d.username || d.telegram_id)
                ? <Button variant="secondary" onClick={() => openTelegramUser(d.username, d.telegram_id)}>Написать</Button>
                : <Button variant="secondary" onClick={() => { setName(d.name); setPhone(d.phone ?? ""); setEditing(true); }}>Изменить</Button>}
            </div>
            {(d.username || d.telegram_id) && (
              <Button variant="ghost" className="mt-1 w-full" onClick={() => { setName(d.name); setPhone(d.phone ?? ""); setEditing(true); }}>Изменить данные</Button>
            )}
          </Card>

          {editing && (
            <Card className="space-y-3">
              <Field label="Имя"><input className="field" value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Телефон"><input className="field" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
              <Button className="w-full" onClick={() => patch({ name: name.trim(), phone: phone || null }, "Данные сохранены")}>Сохранить</Button>
            </Card>
          )}

          <Card className="space-y-2">
            <Field label="Внутренние заметки (клиент их не видит)" hint="Не храните здесь диагнозы и медицинские сведения.">
              <textarea className="field min-h-[90px]" value={notes ?? ""} maxLength={5000} onChange={(e) => setNotes(e.target.value)} />
            </Field>
            {notes !== (d.admin_notes ?? "") && (
              <Button variant="secondary" className="w-full" onClick={() => patch({ admin_notes: notes || null }, "Заметки сохранены")}>Сохранить заметки</Button>
            )}
            <Toggle checked={!d.is_active} onChange={(v) => patch({ is_active: !v }, v ? "Клиент заблокирован" : "Клиент разблокирован")}
              label="Заблокировать онлайн-запись" />
          </Card>
          {!d.anonymized_at && (
            <Button variant="danger" className="w-full" onClick={() => setAskAnon(true)}>Удалить персональные данные</Button>
          )}
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
          <Sheet open={askAnon} onClose={() => setAskAnon(false)} title="Удалить данные клиента?">
            <p className="text-[15px]">
              Делайте это, когда клиент попросил удалить свои данные. Сотрутся имя, телефон, Telegram, заметки и
              комментарии, будущие записи отменятся без уведомления клиенту. Прошедшие визиты останутся в статистике как
              «Клиент удалён». Отменить нельзя.
            </p>
            <Button variant="danger" className="w-full" loading={anonBusy} onClick={anonymize}>Удалить данные</Button>
            <Button variant="secondary" className="w-full" onClick={() => setAskAnon(false)}>Отмена</Button>
          </Sheet>

          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">История записей</h2>
          {!d.appointments.length ? <div className="text-sm text-muted">Записей нет</div> : d.appointments.map((a) => (
            <Card key={a.id} className="!p-3" onClick={() => navigate(`/admin/appointments/${a.id}`)}>
              <div className="flex items-start justify-between gap-2">
                <div className="text-[15px]">{fmtRange(a.starts_at, a.ends_at, tz)}</div>
                <StatusBadge status={a.status} />
              </div>
              <div className="text-sm text-muted">{a.service_name}</div>
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}
