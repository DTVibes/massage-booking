import { HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { BottomNav, Button, Loading } from "./components/ui";
import type { ApiError } from "./lib/api";
import { SessionProvider, useSession } from "./lib/session";
import AdminAppointment from "./pages/admin/AppointmentCard";
import AdminClientCard from "./pages/admin/ClientCard";
import AdminClients from "./pages/admin/Clients";
import AdminCreateAppointment from "./pages/admin/CreateAppointment";
import AdminSchedule from "./pages/admin/Schedule";
import AdminServices from "./pages/admin/Services";
import AdminSettings from "./pages/admin/Settings";
import AdminWorkHours from "./pages/admin/WorkHours";
import Book from "./pages/client/Book";
import Home from "./pages/client/Home";
import MyBookings from "./pages/client/MyBookings";
import Privacy from "./pages/client/Privacy";
import Profile from "./pages/client/Profile";
import Reschedule from "./pages/client/Reschedule";

const CLIENT_NAV = [
  { to: "/home", label: "Записаться", icon: "🗓️", also: ["/", "/book"], end: true },
  { to: "/my", label: "Мои записи", icon: "📋", also: [] as string[] },
  { to: "/profile", label: "Профиль", icon: "👤" },
];

const ADMIN_NAV = [
  { to: "/admin", label: "Расписание", icon: "🗓️", end: true },
  { to: "/admin/clients", label: "Клиенты", icon: "👥" },
  { to: "/admin/hours", label: "График", icon: "🕘" },
  { to: "/admin/services", label: "Услуги", icon: "💆" },
  { to: "/admin/settings", label: "Настройки", icon: "⚙️" },
];

function AuthFallback({ error, retry }: { error: ApiError | null; retry: () => void }) {
  if (!error) return <Loading text="Входим через Telegram…" />;
  const noTelegram = error.code === "no_init_data";
  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="text-4xl">{noTelegram ? "📱" : "⚠️"}</div>
      <div className="text-lg font-semibold">{noTelegram ? "Откройте приложение в Telegram" : "Не удалось войти"}</div>
      <div className="text-sm text-muted">
        {noTelegram ? "Запись доступна через бота в Telegram: нажмите кнопку «Записаться» в чате с ботом." : error.message}
      </div>
      {!noTelegram && <Button onClick={retry}>Повторить</Button>}
    </div>
  );
}

function AdminOnly({ children }: { children: JSX.Element }) {
  const { user } = useSession();
  // Только интерфейсная защита: реальные права проверяет сервер на каждом запросе.
  return user.role === "admin" ? children : <Navigate to="/" replace />;
}

function Shell() {
  const { user } = useSession();
  const { pathname } = useLocation();
  const isAdminArea = pathname.startsWith("/admin") && user.role === "admin";
  return (
    <>
      <Routes>
        <Route path="/" element={user.role === "admin" && !sessionStorage.getItem("clientMode") ? <Navigate to="/admin" replace /> : <Home />} />
        <Route path="/home" element={<Home />} />
        <Route path="/book" element={<Book />} />
        <Route path="/my" element={<MyBookings />} />
        <Route path="/my/:id/reschedule" element={<Reschedule />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/admin" element={<AdminOnly><AdminSchedule /></AdminOnly>} />
        <Route path="/admin/new" element={<AdminOnly><AdminCreateAppointment /></AdminOnly>} />
        <Route path="/admin/appointments/:id" element={<AdminOnly><AdminAppointment /></AdminOnly>} />
        <Route path="/admin/clients" element={<AdminOnly><AdminClients /></AdminOnly>} />
        <Route path="/admin/clients/:id" element={<AdminOnly><AdminClientCard /></AdminOnly>} />
        <Route path="/admin/hours" element={<AdminOnly><AdminWorkHours /></AdminOnly>} />
        <Route path="/admin/services" element={<AdminOnly><AdminServices /></AdminOnly>} />
        <Route path="/admin/settings" element={<AdminOnly><AdminSettings /></AdminOnly>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <BottomNav items={isAdminArea ? ADMIN_NAV : CLIENT_NAV} />
    </>
  );
}

export default function App() {
  return (
    <HashRouter>
      <SessionProvider fallback={(s) => <AuthFallback {...s} />}>
        <Shell />
      </SessionProvider>
    </HashRouter>
  );
}
