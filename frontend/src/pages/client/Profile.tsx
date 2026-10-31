import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PhoneForm } from "../../components/PhoneForm";
import { Button, Card, Field, Notice, Row, Screen, Sheet, Toggle, errorText } from "../../components/ui";
import { api, authenticate } from "../../lib/api";
import { useSession } from "../../lib/session";
import type { User } from "../../lib/types";

export default function Profile() {
  const { user, setUser } = useSession();
  const navigate = useNavigate();
  const [name, setName] = useState(user.name);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [askDelete, setAskDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function deleteData() {
    setDeleting(true);
    setError(null);
    try {
      await api.del("/me");
      // Старый профиль обезличен; вход заново создаёт пустой профиль без телефона и согласия.
      setUser(await authenticate());
      setAskDelete(false);
      navigate("/");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setDeleting(false);
    }
  }

  async function patch(body: Partial<User>, msg: string) {
    setError(null);
    try {
      setUser(await api.patch<User>("/me/profile", body));
      setSaved(msg);
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <Screen title="Профиль">
      <Card>
        <Row label="Telegram ID" value={user.telegram_id ?? "—"} />
        <Row label="С нами с" value={new Date(user.created_at).toLocaleDateString("ru-RU")} />
        <Row label="Согласие на обработку данных"
          value={user.privacy_accepted_at ? new Date(user.privacy_accepted_at).toLocaleDateString("ru-RU") : "не давали"} />
      </Card>
      <Card className="space-y-3">
        <Field label="Имя">
          <input className="field" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
        </Field>
        {name.trim() && name.trim() !== user.name && (
          <Button variant="secondary" className="w-full" onClick={() => patch({ name: name.trim() }, "Имя сохранено")}>Сохранить имя</Button>
        )}
      </Card>
      <Card>
        {!user.phone && <div className="mb-3"><Notice kind="warn">Телефон обязателен для записи.</Notice></div>}
        <PhoneForm user={user} onSaved={(u) => { setUser(u); setSaved("Телефон сохранён"); }} />
      </Card>
      <Card>
        <Toggle checked={user.notifications_enabled} label="Напоминания о визитах"
          onChange={(v) => patch({ notifications_enabled: v }, v ? "Напоминания включены" : "Напоминания выключены")} />
        <p className="mt-1 text-xs text-muted">Подтверждения и отмены приходят всегда. Уведомления присылает бот — не блокируйте его.</p>
      </Card>
      {saved && <Notice kind="success">{saved}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      {user.role === "admin" && (
        <Button variant="secondary" className="w-full" onClick={() => { sessionStorage.removeItem("clientMode"); navigate("/admin"); }}>
          Панель администратора
        </Button>
      )}
      <Card className="space-y-2">
        <h2 className="font-semibold">Мои данные</h2>
        <Link to="/privacy" className="block text-[15px] text-accent">Политика конфиденциальности ›</Link>
        {user.role !== "admin" && (
          <Button variant="danger" className="w-full" onClick={() => setAskDelete(true)}>Удалить мои данные</Button>
        )}
      </Card>
      <Sheet open={askDelete} onClose={() => setAskDelete(false)} title="Удалить мои данные?">
        <p className="text-[15px]">
          Мы сотрём ваше имя, телефон и Telegram, а будущие записи отменим. Мастер увидит, что время освободилось.
          Отменить удаление будет нельзя. Записаться снова можно в любой момент — как новый клиент.
        </p>
        {error && <Notice kind="error">{error}</Notice>}
        <Button variant="danger" className="w-full" loading={deleting} onClick={deleteData}>Удалить</Button>
        <Button variant="secondary" className="w-full" onClick={() => setAskDelete(false)}>Не удалять</Button>
      </Sheet>
    </Screen>
  );
}
