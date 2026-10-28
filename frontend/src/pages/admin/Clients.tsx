import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Empty, ErrorState, Field, Loading, Notice, Screen, Sheet, errorText } from "../../components/ui";
import { api, qs } from "../../lib/api";
import { fmtDateShort, localDate } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import { useSession } from "../../lib/session";
import type { AdminClient, AdminClientDetail, Page } from "../../lib/types";

const PAGE_SIZE = 20;

export default function Clients() {
  const { info } = useSession();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => { setDebounced(q.trim()); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [q]);
  const data = useAsync(() => api.get<Page<AdminClient>>(`/admin/clients${qs({ q: debounced, page, page_size: PAGE_SIZE })}`), [debounced, page]);
  const pages = data.data ? Math.max(1, Math.ceil(data.data.total / PAGE_SIZE)) : 1;

  async function create() {
    setError(null);
    try {
      const c = await api.post<AdminClientDetail>("/admin/clients", { name: name.trim(), phone });
      navigate(`/admin/clients/${c.id}`);
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <Screen title="Клиенты" actions={<Button className="!min-h-[40px] !px-3 text-sm" onClick={() => setAdding(true)}>+ Клиент</Button>}>
      <input className="field" placeholder="Поиск: имя, телефон, Telegram" value={q} onChange={(e) => setQ(e.target.value)} />
      {data.loading ? <Loading /> : data.error ? <ErrorState error={data.error} onRetry={data.reload} /> : !data.data!.items.length ? (
        <Empty icon="👥" title={debounced ? "Никого не нашли" : "Клиентов пока нет"} />
      ) : (
        <>
          <div className="text-sm text-muted">Найдено: {data.data!.total}</div>
          {data.data!.items.map((c) => (
            <Card key={c.id} className="!p-3" onClick={() => navigate(`/admin/clients/${c.id}`)}>
              <div className="flex items-start justify-between gap-2">
                <div className="font-semibold">{c.name}</div>
                <div className="text-sm text-muted">{c.phone ?? "без телефона"}</div>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted">
                <span>визитов: {c.completed_count}</span>
                <span>отмен: {c.cancelled_count}</span>
                {c.no_show_count > 0 && <span>неявок: {c.no_show_count}</span>}
                {c.last_visit_at && <span>последний: {fmtDateShort(localDate(c.last_visit_at, info.timezone))}</span>}
                <span>с {new Date(c.created_at).toLocaleDateString("ru-RU")}</span>
                {c.telegram_id && <span>TG {c.telegram_id}</span>}
              </div>
            </Card>
          ))}
          {pages > 1 && (
            <div className="flex items-center gap-2">
              <Button variant="secondary" className="flex-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Назад</Button>
              <span className="text-sm text-muted">{page} / {pages}</span>
              <Button variant="secondary" className="flex-1" disabled={page >= pages} onClick={() => setPage(page + 1)}>Далее ›</Button>
            </div>
          )}
        </>
      )}
      <Sheet open={adding} onClose={() => setAdding(false)} title="Новый клиент">
        <p className="text-sm text-muted">Для клиентов, которые записываются по телефону, без Telegram.</p>
        <Field label="Имя"><input className="field" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Телефон"><input className="field" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></Field>
        {error && <Notice kind="error">{error}</Notice>}
        <Button className="w-full" disabled={!name.trim() || !phone.trim()} onClick={create}>Добавить</Button>
      </Sheet>
    </Screen>
  );
}
