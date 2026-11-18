import { useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  Apple,
  ChartNoAxesCombined,
  CircleUserRound,
  Dumbbell,
  LogOut,
  Plus,
  Scale,
  Utensils,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "./services/api";
import BodyMeasurements from "./pages/BodyMeasurements";
import Nutrition from "./pages/Nutrition";

type User = { id: number; username: string };
type DashboardData = {
  username: string;
  today: { calories: number; protein_g: number; carbs_g: number; fat_g: number };
  latest_measurement: { weight_kg: number | null } | null;
};
type NutritionOverview = { goals: { calories: number; protein_g: number; carbs_g: number; fat_g: number } | null; consumed: { calories: number; protein_g: number; carbs_g: number; fat_g: number }; remaining: { calories: number; protein_g: number; carbs_g: number; fat_g: number } | null; entries: unknown[] };
type NavigationItem = { name: string; icon: LucideIcon };

const navigation: NavigationItem[] = [
  { name: "Übersicht", icon: ChartNoAxesCombined },
  { name: "Körperwerte", icon: Scale },
  { name: "Ernährung", icon: Apple },
  { name: "Statistiken", icon: Activity },
];

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [nutritionToday, setNutritionToday] = useState<NutritionOverview | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [section, setSection] = useState("Übersicht");
  const [weight, setWeight] = useState("");
  const [foodName, setFoodName] = useState("");
  const [calories, setCalories] = useState("");
  const [protein, setProtein] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refreshDashboard() {
    const day = new Date();
    const localDate = new Date(day.getTime() - day.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const [data, nutrition] = await Promise.all([
      api<DashboardData>("/api/dashboard"),
      api<NutritionOverview>(`/api/nutrition/day?day=${localDate}`),
    ]);
    setDashboard(data);
    setNutritionToday(nutrition);
  }

  useEffect(() => {
    api<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (user) {
      refreshDashboard().catch((err: Error) => setError(err.message));
    }
  }, [user]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      if (authMode === "register") {
        await api<User>("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({ username, password }),
        });
        setAuthMode("login");
        setNotice("Konto wurde angelegt. Du kannst dich jetzt anmelden.");
        setPassword("");
        return;
      }
      const authenticatedUser = await api<User>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setUser(authenticatedUser);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
    }
  }

  async function addWeight(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api("/api/measurements", {
        method: "POST",
        body: JSON.stringify({ weight_kg: Number(weight) }),
      });
      setWeight("");
      await refreshDashboard();
      setNotice("Gewicht wurde gespeichert.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gewicht konnte nicht gespeichert werden.");
    }
  }

  async function addFood(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api("/api/food", {
        method: "POST",
        body: JSON.stringify({
          food_name: foodName,
          calories: Number(calories),
          protein_g: Number(protein || 0),
        }),
      });
      setFoodName("");
      setCalories("");
      setProtein("");
      await refreshDashboard();
      setNotice("Lebensmittel wurde gespeichert.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Eintrag konnte nicht gespeichert werden.");
    }
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
      setUser(null);
      setDashboard(null);
      setNutritionToday(null);
      setSection("Übersicht");
      setError("");
      setNotice("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Abmeldung fehlgeschlagen.");
    }
  }

  if (!user) {
    return (
      <main className="auth">
        <div className="brand"><i><Activity /></i>FIT<span>TRACK</span></div>
        <form className="authbox" onSubmit={submitAuth}>
          <small>DEIN PERSÖNLICHES TRACKING</small>
          <h1>{authMode === "login" ? "Willkommen zurück" : "Konto erstellen"}</h1>
          <p>Fitness und Ernährung im Blick behalten.</p>
          <label>Benutzername
            <input value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={40} autoComplete="username" required />
          </label>
          <label>Passwort
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={10} autoComplete={authMode === "login" ? "current-password" : "new-password"} required />
          </label>
          <button className="primary" type="submit">{authMode === "login" ? "Anmelden" : "Konto erstellen"}</button>
          {error && <p className="error" role="alert">{error}</p>}
          {notice && <p className="success-message" role="status">{notice}</p>}
          <button type="button" className="link" onClick={() => { setAuthMode(authMode === "login" ? "register" : "login"); setError(""); setNotice(""); }}>
            {authMode === "login" ? "Erstes Konto einrichten" : "Zur Anmeldung"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <div className="app">
      <aside>
        <div className="brand"><i><Activity /></i>FIT<span>TRACK</span></div>
        <small className="menu-label">MENÜ</small>
        <nav aria-label="Hauptnavigation">
          {navigation.map(({ name, icon: Icon }) => (
            <button key={name} className={section === name ? "selected" : ""} onClick={() => { setSection(name); setError(""); setNotice(""); }}>
              <Icon size={18} />{name}
            </button>
          ))}
        </nav>
        <div className="profile">
          <CircleUserRound />
          <b>{user.username}</b>
          <button aria-label="Abmelden" title="Abmelden" onClick={() => void logout()}><LogOut size={17} /></button>
        </div>
      </aside>

      <main className="content">
        <header>
          <div><small>DEIN FITNESS-BEREICH</small><h1>{section}</h1></div>
          <span className="today">● HEUTE</span>
        </header>
        {error && <p className="error" role="alert">{error}</p>}
        {notice && <p className="success-message" role="status">{notice}</p>}

        {section === "Körperwerte" ? <BodyMeasurements /> : section === "Ernährung" ? <Nutrition /> : section === "Übersicht" ? (
          <>
            <section className="welcome">
              <div><small>SCHÖN, DASS DU DA BIST</small><h2>Bleib dran, {user.username}.</h2><p>Kleine Schritte. Sichtbare Fortschritte.</p></div>
              <Dumbbell size={48} />
            </section>
            <h3>Dein heutiger Überblick</h3>
            <div className="nutrition-totals dashboard-nutrition">
              {([{key:"calories",label:"Kalorien",unit:"kcal"},{key:"protein_g",label:"Protein",unit:"g"},{key:"carbs_g",label:"Kohlenhydrate",unit:"g"},{key:"fat_g",label:"Fett",unit:"g"}] as const).map(({key,label,unit}) => {
                const goal = nutritionToday?.goals?.[key] ?? null;
                const consumed = nutritionToday?.consumed[key] ?? dashboard?.today[key] ?? 0;
                const remaining = nutritionToday?.remaining?.[key] ?? null;
                const progress = goal && goal > 0 ? Math.min(100, consumed / goal * 100) : 0;
                return <article className="summary-card" key={key}><span>{label}</span><strong>{Math.round(consumed * 10) / 10} <small>{unit}</small></strong><div className="nutrition-track"><span style={{width: progress + "%"}}/></div><p>Tagesziel: {goal == null ? "nicht festgelegt" : goal + " " + unit}</p><em>{remaining == null ? "Ziel festlegen" : remaining >= 0 ? "Noch " + Math.round(remaining * 10) / 10 + " " + unit : Math.round(-remaining * 10) / 10 + " " + unit + " über Ziel"}</em></article>;
              })}
            </div>
            <h3>Schnelle Einträge</h3>
            <div className="forms">
              <form className="panel" onSubmit={addWeight}>
                <h3><Scale /> Körpergewicht</h3>
                <p>Letzter Messwert: <b>{dashboard?.latest_measurement?.weight_kg ?? "–"} kg</b></p>
                <input type="number" step="0.1" min="1" max="500" placeholder="Gewicht in kg" value={weight} onChange={(event) => setWeight(event.target.value)} required />
                <button className="primary" type="submit"><Plus /> Speichern</button>
              </form>
              <form className="panel" onSubmit={addFood}>
                <h3><Apple /> Ernährung erfassen</h3>
                <input placeholder="Lebensmittel" maxLength={160} value={foodName} onChange={(event) => setFoodName(event.target.value)} required />
                <div className="twocol">
                  <input type="number" min="0" placeholder="kcal" value={calories} onChange={(event) => setCalories(event.target.value)} required />
                  <input type="number" min="0" placeholder="Protein (g)" value={protein} onChange={(event) => setProtein(event.target.value)} />
                </div>
                <button className="primary" type="submit">Eintrag speichern <Plus /></button>
              </form>
            </div>
          </>
        ) : (
          <section className="panel empty">
            <Activity size={40} /><h2>{section}</h2>
            <p>Dieser Bereich wird im nächsten Entwicklungsschritt ergänzt. Deine Daten bleiben privat und pro Benutzer getrennt.</p>
          </section>
        )}
        <footer>FITTRACK · PRIVATE FITNESS TRACKING</footer>
      </main>
    </div>
  );
}

function Metric({ icon: Icon, label, value, unit }: { icon: LucideIcon; label: string; value: number; unit: string }) {
  return (
    <article className="metric">
      <div className="metric-icon"><Icon /></div>
      <p>{label}</p>
      <strong>{Math.round(value)}<small>{unit}</small></strong>
      <div className="bar"><span /></div>
    </article>
  );
}
