import { useEffect, useState, type FormEvent } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { api } from "../services/api";

type Values = { calories: number; protein_g: number; carbs_g: number; fat_g: number };
type Food = Values & { id: number; name: string; basis_g: number; brand: string | null };
type Ingredient = Values & { id: number; food_id: number | null; food_name: string; amount_g: number };
type Entry = Values & { id: number; food_name: string; amount_g: number; meal_type: string; ingredients: Ingredient[] };
type Daily = { goals: Values | null; consumed: Values; remaining: Values | null; entries: Entry[] };
type IngredientDraft = { foodId: string; amount: string };
const keys: { key: keyof Values; label: string; unit: string }[] = [
  { key: "calories", label: "Kalorien", unit: "kcal" },
  { key: "protein_g", label: "Protein", unit: "g" },
  { key: "carbs_g", label: "Kohlenhydrate", unit: "g" },
  { key: "fat_g", label: "Fett", unit: "g" },
];
const empty: Values = { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
const n = (v: number) => v.toLocaleString("de-DE", { maximumFractionDigits: 1 });
const mealLabels: Record<string, string> = {
  breakfast: "Frühstück", lunch: "Mittagessen", dinner: "Abendessen", snack: "Snack",
};

function CaloriesCard({ daily }: { daily: Daily | null }) {
  const target = daily?.goals?.calories ?? null;
  const consumed = daily?.consumed.calories ?? 0;
  const remaining = daily?.remaining?.calories ?? null;
  const progress = target && target > 0 ? Math.min(100, consumed / target * 100) : 0;
  return (
    <article className="summary-card calorie-progress-card">
      <div className="calorie-card-heading"><span>Kalorien</span><small>{target == null ? "Tagesziel fehlt" : "Tagesfortschritt"}</small></div>
      <div className="calorie-numbers">
        <div><strong>{n(consumed)}</strong><small>kcal aufgenommen</small></div>
        <div className="calorie-free">{remaining == null ? "Ziel festlegen" : remaining >= 0 ? <><strong>{n(remaining)}</strong><small>kcal noch frei</small></> : <><strong>{n(-remaining)}</strong><small>kcal über Ziel</small></>}</div>
      </div>
      <div className="calorie-track" role="progressbar" aria-label="Kalorienverbrauch des Tages"
        aria-valuemin={0} aria-valuemax={target ?? 0} aria-valuenow={Math.min(consumed, target ?? consumed)}>
        <span style={{ width: progress + "%" }} />
      </div>
      <div className="calorie-track-labels"><span>0 kcal</span><span>Ziel: {target == null ? "–" : n(target) + " kcal"}</span></div>
      {remaining != null && <p className={remaining < 0 ? "calorie-over" : "calorie-available"}>{remaining < 0 ? "Tagesziel überschritten" : "Noch " + n(remaining) + " kcal verfügbar"}</p>}
    </article>
  );
}

export default function Nutrition({ onDataChanged }: { onDataChanged: () => Promise<void> }) {
  const [daily, setDaily] = useState<Daily | null>(null);
  const [foods, setFoods] = useState<Food[]>([]);
  const [goals, setGoals] = useState<Values>(empty);
  const [foodName, setFoodName] = useState("");
  const [foodValues, setFoodValues] = useState({ calories: "", protein_g: "", carbs_g: "", fat_g: "" });
  const [ingredients, setIngredients] = useState<IngredientDraft[]>([{ foodId: "", amount: "100" }]);
  const [mealName, setMealName] = useState("");
  const [mealType, setMealType] = useState("breakfast");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadFoods(search = query) {
    const found = await api<Food[]>(`/api/nutrition/foods?q=${encodeURIComponent(search)}`);
    setFoods(found);
    setIngredients(current => current.map((item, index) => ({
      ...item,
      foodId: item.foodId && found.some(food => String(food.id) === item.foodId)
        ? item.foodId : index === 0 && found[0] ? String(found[0].id) : "",
    })));
  }
  async function loadDay() {
    const data = await api<Daily>(`/api/nutrition/day?day=${today()}`);
    setDaily(data);
    if (data.goals) setGoals(data.goals);
  }
  async function reload() {
    await Promise.all([loadDay(), loadFoods()]);
  }
  useEffect(() => {
    void reload().catch((e: Error) => setError(e.message));
  }, []);

  async function saveGoals(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      await api("/api/nutrition/goals", { method: "PUT", body: JSON.stringify(goals) });
      await reload(); await onDataChanged(); setNotice("Tagesziele gespeichert.");
    } catch (e) { setError(e instanceof Error ? e.message : "Speichern fehlgeschlagen."); }
    finally { setBusy(false); }
  }
  async function addFood(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const food = await api<Food>("/api/nutrition/foods", { method: "POST", body: JSON.stringify({
        name: foodName, basis_g: 100,
        ...Object.fromEntries(keys.map(({ key }) => [key, Number(foodValues[key])])),
      }) });
      setFoodName(""); setFoodValues({ calories: "", protein_g: "", carbs_g: "", fat_g: "" });
      await loadFoods(); setIngredients([{ foodId: String(food.id), amount: "100" }]);
      setNotice("Eigenes Lebensmittel gespeichert.");
    } catch (e) { setError(e instanceof Error ? e.message : "Lebensmittel konnte nicht gespeichert werden."); }
    finally { setBusy(false); }
  }
  async function addMeal(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    const validIngredients = ingredients.filter(item => item.foodId && Number(item.amount) > 0);
    if (!mealName.trim() || validIngredients.length === 0) {
      setError("Bitte einen Mahlzeitnamen und mindestens eine gültige Zutat angeben.");
      setBusy(false); return;
    }
    try {
      await api("/api/nutrition/meals", { method: "POST", body: JSON.stringify({
        meal_name: mealName.trim(), meal_type: mealType,
        ingredients: validIngredients.map(item => ({ food_id: Number(item.foodId), amount_g: Number(item.amount) })),
      }) });
      setMealName(""); setIngredients([{ foodId: foods[0] ? String(foods[0].id) : "", amount: "100" }]);
      await reload(); await onDataChanged(); setNotice("Mahlzeit mit Zutaten eingetragen.");
    } catch (e) { setError(e instanceof Error ? e.message : "Eintrag fehlgeschlagen."); }
    finally { setBusy(false); }
  }
  async function deleteMeal(id: number) {
    setBusy(true); setError(""); setNotice("");
    try { await api(`/api/nutrition/meals/${id}`, { method: "DELETE" }); await reload(); await onDataChanged(); setNotice("Mahlzeit gelöscht."); }
    catch (e) { setError(e instanceof Error ? e.message : "Löschen fehlgeschlagen."); }
    finally { setBusy(false); }
  }
  function updateIngredient(index: number, patch: Partial<IngredientDraft>) {
    setIngredients(current => current.map((item, i) => i === index ? { ...item, ...patch } : item));
  }

  return <div className="nutrition-page">
    <section className="panel">
      <div className="panel-heading"><div><h2>Deine persönlichen Tagesziele</h2><p>Pro Benutzer gespeichert · manuell anpassbar</p></div></div>
      <form onSubmit={saveGoals}>
        <div className="nutrition-grid">{keys.map(({ key, label, unit }) => <label key={key}>{label} ({unit})
          <input type="number" min="0" max="10000" step="0.1" required value={goals[key] || ""}
            onChange={e => setGoals({ ...goals, [key]: Number(e.target.value) })} />
        </label>)}</div>
        <button className="primary" disabled={busy}><Save size={16}/> Ziele speichern</button>
      </form>
    </section>

    <section className="nutrition-totals">
      <CaloriesCard daily={daily} />
      {keys.filter(({ key }) => key !== "calories").map(({ key, label, unit }) => {
        const target = daily?.goals?.[key] ?? null;
        const consumed = daily?.consumed[key] ?? 0;
        const remaining = daily?.remaining?.[key] ?? null;
        const pct = target && target > 0 ? Math.min(100, consumed / target * 100) : 0;
        return <article className="summary-card" key={key}>
          <span>{label}</span><strong>{n(consumed)} <small>{unit}</small></strong>
          <div className="nutrition-track"><span style={{ width: pct + "%" }}/></div>
          <p>Ziel: {target == null ? "nicht gesetzt" : n(target) + " " + unit}</p>
          <em>{remaining == null ? "Tagesziel festlegen" : remaining >= 0 ? "Noch " + n(remaining) + " " + unit : n(-remaining) + " " + unit + " über Ziel"}</em>
        </article>;
      })}
    </section>

    <section className="panel">
      <div className="panel-heading"><div><h2>Heutige Mahlzeiten</h2><p>{daily?.entries.length ?? 0} Einträge</p></div></div>
      {!daily?.entries.length ? <p className="muted">Noch keine Mahlzeiten eingetragen.</p> : daily.entries.map(entry => (
        <article className="nutrition-entry" key={entry.id}>
          <div><b>{entry.food_name}</b><small>{mealLabels[entry.meal_type] ?? entry.meal_type} · {n(entry.amount_g)} g</small>
            {entry.ingredients?.length > 0 && <ul className="nutrition-ingredient-list">{entry.ingredients.map(item =>
              <li key={item.id}>{item.food_name} · {n(item.amount_g)} g</li>)}</ul>}
          </div>
          <span>{n(entry.calories)} kcal · P {n(entry.protein_g)} g · KH {n(entry.carbs_g)} g · F {n(entry.fat_g)} g</span>
          <button aria-label={`Mahlzeit ${entry.food_name} löschen`} disabled={busy} onClick={() => void deleteMeal(entry.id)}><Trash2 size={16}/></button>
        </article>
      ))}
    </section>

    <section className="panel">
      <div className="panel-heading"><div><h2>Mahlzeit erfassen</h2><p>Eine Mahlzeit kann aus mehreren Zutaten bestehen. Nährwerte werden automatisch addiert und historisch gespeichert.</p></div></div>
      <div className="nutrition-tools">
        <input placeholder="Lebensmittel suchen" value={query} onChange={e => setQuery(e.target.value)}/>
        <button className="secondary-button" type="button" disabled={busy} onClick={() => loadFoods().catch(e => setError(e.message))}>Suchen</button>
      </div>
      <form className="nutrition-recipe-form" onSubmit={addMeal}>
        <label>Mahlzeitenname<input required maxLength={160} value={mealName} onChange={e => setMealName(e.target.value)} placeholder="z. B. Overnight Oats"/></label>
        <label>Mahlzeit<select value={mealType} onChange={e => setMealType(e.target.value)}>
          <option value="breakfast">Frühstück</option><option value="lunch">Mittagessen</option>
          <option value="dinner">Abendessen</option><option value="snack">Snack</option>
        </select></label>
        <div className="recipe-ingredients"><div className="recipe-ingredients-heading"><b>Zutaten</b><span>{ingredients.length} / 30</span></div>
          {ingredients.map((item, index) => <div className="recipe-ingredient-row" key={index}>
            <label>Lebensmittel<select required value={item.foodId} onChange={e => updateIngredient(index, { foodId: e.target.value })}>
              <option value="">Auswählen</option>{foods.map(food => <option key={food.id} value={food.id}>{food.name}</option>)}
            </select></label>
            <label>Menge (g)<input type="number" min="0.1" max="10000" step="0.1" required value={item.amount}
              onChange={e => updateIngredient(index, { amount: e.target.value })}/></label>
            <button type="button" className="ingredient-remove" aria-label="Zutat entfernen" disabled={ingredients.length === 1 || busy}
              onClick={() => setIngredients(current => current.filter((_, i) => i !== index))}><Trash2 size={15}/></button>
          </div>)}
          <button type="button" className="add-ingredient" disabled={busy || ingredients.length >= 30}
            onClick={() => setIngredients(current => [...current, { foodId: "", amount: "100" }])}><Plus size={15}/> Zutat hinzufügen</button>
        </div>
        <button className="primary" disabled={busy || foods.length === 0}><Plus size={16}/> Mahlzeit eintragen</button>
      </form>
      <details className="nutrition-add-food"><summary><Plus size={15}/> Eigenes Lebensmittel anlegen</summary>
        <form onSubmit={addFood}><label>Name<input required maxLength={160} value={foodName} onChange={e => setFoodName(e.target.value)}/></label>
          <div className="nutrition-grid">{keys.map(({ key, label, unit }) => <label key={key}>{label} ({unit} je 100 g)
            <input type="number" min="0" max="10000" step="0.1" required value={foodValues[key]}
              onChange={e => setFoodValues({ ...foodValues, [key]: e.target.value })}/>
          </label>)}</div><button className="primary" disabled={busy}>Lebensmittel speichern</button>
        </form>
      </details>
    </section>
    {error && <p className="form-message error-message" role="alert">{error}</p>}
    {notice && <p className="form-message success-message" role="status">{notice}</p>}
  </div>;
}
