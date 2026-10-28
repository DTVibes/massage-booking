import { useState } from "react";
import { api } from "../lib/api";
import { haptic } from "../lib/telegram";
import type { User } from "../lib/types";
import { Button, errorText, Field, Notice } from "./ui";

export function PhoneForm({ user, onSaved, submitLabel = "Сохранить" }: { user: User; onSaved: (u: User) => void; submitLabel?: string }) {
  const [phone, setPhone] = useState(user.phone ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const u = await api.patch<User>("/me/profile", { phone });
      haptic.success();
      onSaved(u);
    } catch (e) {
      haptic.error();
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <Field label="Номер телефона" hint="Нужен массажисту для связи. Виден только массажисту.">
        <input className="field" type="tel" inputMode="tel" autoComplete="tel" placeholder="+7 900 000-00-00"
          value={phone} onChange={(e) => setPhone(e.target.value)} />
      </Field>
      {error && <Notice kind="error">{error}</Notice>}
      <Button className="w-full" loading={saving} disabled={phone.trim().length < 5 || phone.trim() === (user.phone ?? "")} onClick={save}>{submitLabel}</Button>
    </div>
  );
}
