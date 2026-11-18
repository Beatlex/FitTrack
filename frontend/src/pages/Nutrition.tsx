import { useEffect, useState, type FormEvent } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { api } from "../services/api";

type Values = { calories: number; protein_g: number; carbs_g: number; fat_g: number };
type Food = Values & { id: number; name: string; basis_g: number; brand: string | null };
type Entry = Values & { id: number; food_name: string; amount_g: number; meal_type: string };
type Daily = { goals: Values | null; consumed: Values; remaining: Values | null; entries: Entry[] };
const keys: { key: keyof Values; label: string; unit: string }[] = [
  { key: "calories", label: "Kalorien", unit: "kcal" }, { key: "protein_g", label: "Protein", unit: "g" },
  { key: "carbs_g", label: "Kohlenhydrate", unit: "g" }, { key: "fat_g", label: "Fett", unit: "g" },
];
const empty: Values = { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
const today = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
const n = (v: number) => v.toLocaleString("de-DE", { maximumFractionDigits: 1 });

export default function Nutrition() {
  const [daily, setDaily] = useState<Daily | null>(null);
  const [foods, setFoods] = useState<Food[]>([]);
  const [goals, setGoals] = useState<Values>(empty);
  const [foodName, setFoodName] = useState("");
  const [foodValues, setFoodValues] = useState({ calories: "", protein_g: "", carbs_g: "", fat_g: "" });
  const [foodId, setFoodId] = useState("");
  const [amount, setAmount] = useState("100");
  const [mealType, setMealType] = useState("breakfast");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    const [d, f] = await Promise.all([
      api<Daily>(`/api/nutrition/day?day=${today()}`),
      api<Food[]>(`/api/nutrition/foods?q=${encodeURIComponent(query)}`),
    ]);
    setDaily(d); setFoods(f);
    if (d.goals) setGoals(d.goals);
    if (!foodId && f[0]) setFoodId(String(f[0].id));
  }
  useEffect(() => { load().catch((e: Error) => setError(e.message)); }, []);
  async function saveGoals(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { await api("/api/nutrition/goals", { method: "PUT", body: JSON.stringify(goals) }); await load(); setNotice("Tagesziele gespeichert."); }
    catch (e) { setError(e instanceof Error ? e.message : "Speichern fehlgeschlagen."); } finally { setBusy(false); }
  }
  async function addFood(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const f = await api<Food>("/api/nutrition/foods", { method: "POST", body: JSON.stringify({
        name: foodName, basis_g: 100, ...Object.fromEntries(keys.map(({ key }) => [key, Number(foodValues[key])])),
      }) });
      setFoodName(""); setFoodValues({ calories: "", protein_g: "", carbs_g: "", fat_g: "" });
      await load(); setFoodId(String(f.id)); setNotice("Eigenes Lebensmittel gespeichert.");
    } catch (e) { setError(e instanceof Error ? e.message : "Lebensmittel konnte nicht gespeichert werden."); } finally { setBusy(false); }
  }
  async function addMeal(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { await api("/api/nutrition/meals", { method: "POST", body: JSON.stringify({ food_id: Number(foodId), amount_g: Number(amount), meal_type: mealType }) }); await load(); setNotice("Mahlzeit eingetragen."); }
    catch (e) { setError(e instanceof Error ? e.message : "Eintrag fehlgeschlagen."); } finally { setBusy(false); }
  }
  async function deleteMeal(id: number) {
    try { await api(`/api/nutrition/meals/${id}`, { method: "DELETE" }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Löschen fehlgeschlagen."); }
  }
  return <div className="nutrition-page">
    <section className="panel"><div className="panel-heading"><div><h2>Deine persönlichen Tagesziele</h2><p>Pro Benutzer gespeichert · manuell anpassbar</p></div></div>
      <form onSubmit={saveGoals}><div className="nutrition-grid">{keys.map(({ key, label, unit }) => <label key={key}>{label} ({unit})<input type="number" min="0" max="10000" step="0.1" required value={goals[key] || ""} onChange={e => setGoals({ ...goals, [key]: Number(e.target.value) })}/></label>)}</div><button className="primary" disabled={busy}><Save size={16}/> Ziele speichern</button></form>
    </section>
    <section className="nutrition-totals">{keys.map(({ key, label, unit }) => {
      const target = daily?.goals?.[key] ?? null, consumed = daily?.consumed[key] ?? 0, remaining = daily?.remaining?.[key] ?? null;
      const pct = target && target > 0 ? Math.min(100, consumed / target * 100) : 0;
      return <article className="summary-card" key={key}><span>{label}</span><strong>{n(consumed)} <small>{unit}</small></strong><div className="nutrition-track"><span style={{ width: pct + "%" }}/></div><p>Ziel: {target == null ? "nicht gesetzt" : n(target) + " " + unit}</p><em>{remaining == null ? "Tagesziel festlegen" : remaining >= 0 ? "Noch " + n(remaining) + " " + unit : n(-remaining) + " " + unit + " über Ziel"}</em></article>;
    })}</section>
    <section className="panel"><div className="panel-heading"><div><h2>Mahlzeit erfassen</h2><p>Berechnung nach Menge; Nährwerte bleiben als historischer Snapshot erhalten.</p></div></div>
      <div className="nutrition-tools"><input placeholder="Lebensmittel suchen" value={query} onChange={e => setQuery(e.target.value)}/><button className="secondary-button" type="button" onClick={() => load().catch(e => setError(e.message))}>Suchen</button></div>
      <form className="nutrition-meal-form" onSubmit={addMeal}><label>Lebensmittel<select required value={foodId} onChange={e => setFoodId(e.target.value)}><option value="">Auswählen</option>{foods.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label><label>Menge (g)<input type="number" min="0.1" max="10000" step="0.1" value={amount} onChange={e => setAmount(e.target.value)}/></label><label>Mahlzeit<select value={mealType} onChange={e => setMealType(e.target.value)}><option value="breakfast">Frühstück</option><option value="lunch">Mittagessen</option><option value="dinner">Abendessen</option><option value="snack">Snack</option></select></label><button className="primary" disabled={busy || !foodId}><Plus size={16}/> Eintragen</button></form>
      <details className="nutrition-add-food"><summary><Plus size={15}/> Eigenes Lebensmittel anlegen</summary><form onSubmit={addFood}><label>Name<input required maxLength={160} value={foodName} onChange={e => setFoodName(e.target.value)}/></label><div className="nutrition-grid">{keys.map(({ key, label, unit }) => <label key={key}>{label} ({unit} je 100 g)<input type="number" min="0" max="10000" step="0.1" required value={foodValues[key]} onChange={e => setFoodValues({ ...foodValues, [key]: e.target.value })}/></label>)}</div><button className="primary" disabled={busy}>Lebensmittel speichern</button></form></details>
    </section>
    <section className="panel"><div className="panel-heading"><div><h2>Heutige Mahlzeiten</h2><p>{daily?.entries.length ?? 0} Einträge</p></div></div>
      {!daily?.entries.length ? <p className="muted">Noch keine Einträge. Du kannst zum Testen Overnight Oats als eigenes Lebensmittel anlegen.</p> : daily.entries.map(entry => <article className="nutrition-entry" key={entry.id}><div><b>{entry.food_name}</b><small>{entry.meal_type} · {n(entry.amount_g)} g</small></div><span>{n(entry.calories)} kcal · P {n(entry.protein_g)} g · KH {n(entry.carbs_g)} g · F {n(entry.fat_g)} g</span><button aria-label="Eintrag löschen" onClick={() => void deleteMeal(entry.id)}><Trash2 size={16}/></button></article>)}
    </section>
    {error && <p className="form-message error-message" role="alert">{error}</p>}{notice && <p className="form-message success-message" role="status">{notice}</p>}
  </div>;
}
