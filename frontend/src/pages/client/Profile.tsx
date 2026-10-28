import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PhoneForm } from "../../components/PhoneForm";
import { Button, Card, Field, Notice, Row, Screen, Toggle, errorText } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";
import type { User } from "../../lib/types";

export default function Profile() {
  const { user, setUser } = useSession();
  const navigate = useNavigate();
  const [name, setName] = useState(user.name);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    </Screen>
  );
}
