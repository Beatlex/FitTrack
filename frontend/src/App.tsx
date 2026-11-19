import { useEffect, useState, type FormEvent } from "react";
import {
  Activity,
  Apple,
  ChartNoAxesCombined,
  CircleUserRound,
  Dumbbell,
  LogOut,
  House,
  Plus,
  Scale,
  Utensils,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "./services/api";
import BodyMeasurements from "./pages/BodyMeasurements";
import Nutrition from "./pages/Nutrition";
import HouseholdPage from "./pages/Household";

type User = { id: number; username: string };
type WeightPoint = { id: number; measured_at: string; weight_kg: number | null };
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
  { name: "Haushalt", icon: House },
];

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [nutritionToday, setNutritionToday] = useState<NutritionOverview | null>(null);
  const [weightHistory, setWeightHistory] = useState<WeightPoint[]>([]);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [section, setSection] = useState("Übersicht");
  const [weight, setWeight] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refreshDashboard() {
    const day = new Date();
    const localDate = new Date(day.getTime() - day.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const [data, nutrition, measurements] = await Promise.all([
      api<DashboardData>("/api/dashboard"),
      api<NutritionOverview>(`/api/nutrition/day?day=${localDate}`),
      api<WeightPoint[]>("/api/measurements"),
    ]);
    setDashboard(data);
    setNutritionToday(nutrition);
    setWeightHistory(measurements.filter((item) => item.weight_kg != null).slice(0, 30).reverse());
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


  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST" });
      setUser(null);
      setDashboard(null);
      setNutritionToday(null);
      setWeightHistory([]);
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

        {section === "Körperwerte" ? <BodyMeasurements /> : section === "Ernährung" ? <Nutrition onDataChanged={refreshDashboard} /> : section === "Haushalt" ? <HouseholdPage /> : section === "Übersicht" ? (
          <>
            <section className="welcome">
              <div><small>SCHÖN, DASS DU DA BIST</small><h2>Bleib dran, {user.username}.</h2><p>Kleine Schritte. Sichtbare Fortschritte.</p></div>
              <Dumbbell size={48} />
            </section>
            <DashboardWeightTrend points={weightHistory} />
            <h3>Dein heutiger Überblick</h3>
            <div className="nutrition-totals dashboard-nutrition">
              {([{key:"calories",label:"Kalorien",unit:"kcal"},{key:"protein_g",label:"Protein",unit:"g"},{key:"carbs_g",label:"Kohlenhydrate",unit:"g"},{key:"fat_g",label:"Fett",unit:"g"}] as const).map(({key,label,unit}) => {
                const goal = nutritionToday?.goals?.[key] ?? null;
                const consumed = nutritionToday?.consumed[key] ?? dashboard?.today[key] ?? 0;
                const remaining = nutritionToday?.remaining?.[key] ?? null;
                const progress = goal && goal > 0 ? Math.min(100, consumed / goal * 100) : 0;
                if (key === "calories") return <article className="summary-card calorie-progress-card" key={key}>
                  <div className="calorie-card-heading"><span>Kalorien</span><small>{goal == null ? "Tagesziel fehlt" : "Tagesfortschritt"}</small></div>
                  <div className="calorie-numbers"><div><strong>{Math.round(consumed * 10) / 10}</strong><small>kcal aufgenommen</small></div>
                    <div className="calorie-free">{remaining == null ? "Ziel festlegen" : remaining >= 0 ? <><strong>{Math.round(remaining * 10) / 10}</strong><small>kcal noch frei</small></> : <><strong>{Math.round(-remaining * 10) / 10}</strong><small>kcal über Ziel</small></>}</div></div>
                  <div className="calorie-track" role="progressbar" aria-label="Kalorienverbrauch des Tages" aria-valuemin={0} aria-valuemax={goal ?? 0} aria-valuenow={Math.min(consumed, goal ?? consumed)}><span style={{width: progress + "%"}}/></div>
                  <div className="calorie-track-labels"><span>0 kcal</span><span>Ziel: {goal == null ? "–" : goal + " kcal"}</span></div>
                  {remaining != null && <p className={remaining < 0 ? "calorie-over" : "calorie-available"}>{remaining < 0 ? "Tagesziel überschritten" : "Noch " + Math.round(remaining * 10) / 10 + " kcal verfügbar"}</p>}
                </article>;
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
              <section className="panel overview-nutrition-link">
                <h3><Apple /> Ernährung erfassen</h3>
                <p>Wähle ein gespeichertes Gericht oder erstelle ein neues Rezept mit Zutaten. So bleiben deine Tageswerte und Nährwert-Snapshots konsistent.</p>
                <button className="primary" type="button" onClick={() => { setSection("Ernährung"); setError(""); setNotice(""); }}>
                  Zur Ernährungsübersicht <Plus />
                </button>
              </section>
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


function DashboardWeightTrend({ points }: { points: WeightPoint[] }) {
  const values = points.map((point) => point.weight_kg as number);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const width = 720, height = 150, left = 44, right = 18, top = 16, bottom = 28;
  const x = (index: number) => left + (points.length < 2 ? 0 : index / (points.length - 1)) * (width - left - right);
  const y = (value: number) => top + ((max + range * 0.15 - value) / (range * 1.3)) * (height - top - bottom);
  const polyline = points.map((point, index) => `${x(index)},${y(point.weight_kg as number)}`).join(" ");
  const latest = points.at(-1);
  return (
    <section className="panel dashboard-weight-trend">
      <div className="panel-heading">
        <div><h2>Gewichtsverlauf</h2><p>Deine letzten {points.length} Gewichtsmessungen</p></div>
        {latest?.weight_kg != null && <strong className="dashboard-weight-current">{latest.weight_kg.toLocaleString("de-DE", { maximumFractionDigits: 1 })} kg</strong>}
      </div>
      {points.length === 0 ? <div className="dashboard-weight-empty">Noch keine Gewichtsmessungen vorhanden.</div> :
        points.length === 1 ? <div className="dashboard-weight-empty">Dein erster Messwert: <b>{points[0].weight_kg} kg</b>. Weitere Einträge zeigen hier deinen Verlauf.</div> :
        <div className="dashboard-weight-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Gewichtsverlauf der letzten 30 Messungen">
          {[0,1,2].map((step) => {
            const value = max + range * 0.15 - (range * 1.3 * step) / 2;
            const position = y(value);
            return <g key={step}><line x1={left} x2={width-right} y1={position} y2={position} className="chart-grid"/><text x={left-8} y={position+4} textAnchor="end" className="chart-label">{value.toLocaleString("de-DE",{maximumFractionDigits:1})}</text></g>;
          })}
          <polyline points={polyline} className="chart-line"/>
          {points.map((point,index)=><circle key={point.id} cx={x(index)} cy={y(point.weight_kg as number)} r="4" className="chart-point"><title>{new Date(point.measured_at).toLocaleDateString("de-DE")}: {point.weight_kg} kg</title></circle>)}
          <text x={left} y={height-5} className="chart-label">{new Date(points[0].measured_at).toLocaleDateString("de-DE")}</text>
          <text x={width-right} y={height-5} textAnchor="end" className="chart-label">{new Date(points[points.length-1].measured_at).toLocaleDateString("de-DE")}</text>
        </svg></div>}
    </section>
  );
}
