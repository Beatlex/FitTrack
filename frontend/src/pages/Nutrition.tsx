import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, Heart, Pencil, Plus, Save, Search, Trash2, Utensils } from "lucide-react";
import { api } from "../services/api";

type Values = { calories: number; protein_g: number; carbs_g: number; fat_g: number };
type Food = Values & { id: number; name: string; basis_g: number; brand: string | null; is_favorite: boolean; is_system: boolean };
type Ingredient = Values & { id?: number; food_id: number; food_name: string; amount_g: number };
type Entry = Values & { id: number; food_name: string; amount_g: number; meal_type: string; ingredients: Ingredient[] };
type Daily = { goals: Values | null; consumed: Values; remaining: Values | null; entries: Entry[] };
type Recipe = Values & { id: number; name: string; meal_type: string; is_favorite: boolean; amount_g: number; ingredients: Ingredient[] };
type IngredientDraft = { foodId: string; amount: string };
type View = "today" | "recipes" | "foods";
const keys: { key: keyof Values; label: string; unit: string }[] = [
  { key: "calories", label: "Kalorien", unit: "kcal" },
  { key: "protein_g", label: "Protein", unit: "g" },
  { key: "carbs_g", label: "Kohlenhydrate", unit: "g" },
  { key: "fat_g", label: "Fett", unit: "g" },
];
const empty: Values = { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
const today = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
const n = (v: number) => v.toLocaleString("de-DE", { maximumFractionDigits: 1 });
const mealLabels: Record<string, string> = { breakfast: "Frühstück", lunch: "Mittagessen", dinner: "Abendessen", snack: "Snack" };

function CaloriesCard({ daily }: { daily: Daily | null }) {
  const target = daily?.goals?.calories ?? null;
  const consumed = daily?.consumed.calories ?? 0;
  const remaining = daily?.remaining?.calories ?? null;
  const progress = target && target > 0 ? Math.min(100, consumed / target * 100) : 0;
  return <article className="summary-card calorie-progress-card">
    <div className="calorie-card-heading"><span>Kalorien</span><small>{target == null ? "Tagesziel fehlt" : "Tagesfortschritt"}</small></div>
    <div className="calorie-numbers"><div><strong>{n(consumed)}</strong><small>kcal aufgenommen</small></div>
      <div className="calorie-free">{remaining == null ? "Ziel festlegen" : remaining >= 0 ? <><strong>{n(remaining)}</strong><small>kcal noch frei</small></> : <><strong>{n(-remaining)}</strong><small>kcal über Ziel</small></>}</div></div>
    <div className="calorie-track" role="progressbar" aria-label="Kalorienverbrauch des Tages" aria-valuemin={0} aria-valuemax={target ?? 0} aria-valuenow={Math.min(consumed, target ?? consumed)}><span style={{ width: progress + "%" }}/></div>
    <div className="calorie-track-labels"><span>0 kcal</span><span>Ziel: {target == null ? "–" : n(target) + " kcal"}</span></div>
    {remaining != null && <p className={remaining < 0 ? "calorie-over" : "calorie-available"}>{remaining < 0 ? "Tagesziel überschritten" : "Noch " + n(remaining) + " kcal verfügbar"}</p>}
  </article>;
}

export default function Nutrition({ onDataChanged }: { onDataChanged: () => Promise<void> }) {
  const [view, setView] = useState<View>("today");
  const [daily, setDaily] = useState<Daily | null>(null);
  const [foods, setFoods] = useState<Food[]>([]);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [goals, setGoals] = useState<Values>(empty);
  const [foodQuery, setFoodQuery] = useState("");
  const [recipeQuery, setRecipeQuery] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [foodName, setFoodName] = useState("");
  const [foodEditorOpen, setFoodEditorOpen] = useState(false);
  const [editingFoodId, setEditingFoodId] = useState<number | null>(null);
  const [foodValues, setFoodValues] = useState({ calories: "", protein_g: "", carbs_g: "", fat_g: "" });
  const [recipeName, setRecipeName] = useState("");
  const [editingRecipe, setEditingRecipe] = useState<Recipe | null>(null);
  const [recipeType, setRecipeType] = useState("breakfast");
  const [ingredients, setIngredients] = useState<IngredientDraft[]>([{ foodId: "", amount: "50" }]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadDay() {
    const data = await api<Daily>(`/api/nutrition/day?day=${today()}`);
    setDaily(data);
    if (data.goals) setGoals(data.goals);
  }
  async function loadFoods(search = foodQuery) {
    setFoods(await api<Food[]>(`/api/nutrition/foods?q=${encodeURIComponent(search)}`));
  }
  async function loadRecipes(search = recipeQuery, favorites = favoritesOnly) {
    setRecipes(await api<Recipe[]>(`/api/nutrition/recipes?q=${encodeURIComponent(search)}&favorites_only=${favorites}`));
  }
  async function reload() { await Promise.all([loadDay(), loadFoods(), loadRecipes()]); }
  useEffect(() => { void reload().catch((e: Error) => setError(e.message)); }, []);

  const favoriteRecipes = useMemo(() => recipes.filter(recipe => recipe.is_favorite), [recipes]);
  async function runAction(action: () => Promise<void>, success: string) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setNotice(success); }
    catch (e) { setError(e instanceof Error ? e.message : "Die Aktion ist fehlgeschlagen."); }
    finally { setBusy(false); }
  }
  async function saveGoals(e: FormEvent) {
    e.preventDefault();
    await runAction(async () => { await api("/api/nutrition/goals", { method: "PUT", body: JSON.stringify(goals) }); await loadDay(); await onDataChanged(); }, "Tagesziele gespeichert.");
  }
  async function saveFood(e: FormEvent) {
    e.preventDefault();
    const payload = {
      name: foodName.trim(), basis_g: 100,
      ...Object.fromEntries(keys.map(({ key }) => [key, Number(foodValues[key])])),
    };
    await runAction(async () => {
      if (editingFoodId !== null) {
        await api(`/api/nutrition/foods/${editingFoodId}`, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        const matches = await api<Food[]>(`/api/nutrition/foods?q=${encodeURIComponent(payload.name)}`);
        const existing = matches.find(item => item.name.trim().toLocaleLowerCase() === payload.name.toLocaleLowerCase());
        if (existing && !window.confirm(`„${existing.name}“ ist bereits vorhanden. Soll dieses Lebensmittel mit den neuen Nährwerten aktualisiert werden?`)) return;
        if (existing) await api(`/api/nutrition/foods/${existing.id}`, { method: "PUT", body: JSON.stringify(payload) });
        else await api("/api/nutrition/foods", { method: "POST", body: JSON.stringify(payload) });
      }
      setFoodName(""); setFoodValues({ calories: "", protein_g: "", carbs_g: "", fat_g: "" });
      setEditingFoodId(null); setFoodQuery(""); setFoodEditorOpen(false);
      await loadFoods("");
    }, editingFoodId !== null ? "Lebensmittel aktualisiert." : "Lebensmittel gespeichert oder aktualisiert.");
  }
  function editFood(food: Food) {
    setEditingFoodId(food.id); setFoodName(food.name);
    setFoodValues(Object.fromEntries(keys.map(({ key }) => [key, String(food[key])])) as typeof foodValues);
    setFoodEditorOpen(true);
  }
  async function archiveFood(food: Food) {
    if (!window.confirm(`„${food.name}“ aus der Lebensmittelauswahl entfernen? Bereits gespeicherte Mahlzeiten und Gerichte bleiben erhalten.`)) return;
    await runAction(async () => {
      await api(`/api/nutrition/foods/${food.id}`, { method: "DELETE" });
      await loadFoods("");
    }, "Lebensmittel wurde archiviert.");
  }
  async function toggleFood(food: Food) {
    await runAction(async () => {
      await api(`/api/nutrition/foods/${food.id}/favorite`, { method: "PATCH", body: JSON.stringify({ is_favorite: !food.is_favorite }) });
      await loadFoods();
    }, food.is_favorite ? "Favorit entfernt." : "Als Favorit gespeichert.");
  }
  async function saveRecipe(e: FormEvent) {
    e.preventDefault();
    const selected = ingredients.filter(item => item.foodId && Number(item.amount) > 0);
    if (!recipeName.trim() || !selected.length) { setError("Bitte einen Namen und mindestens eine Zutat auswählen."); return; }
    await runAction(async () => {
      const payload = { name: recipeName.trim(), meal_type: recipeType,
        ingredients: selected.map(item => ({ food_id: Number(item.foodId), amount_g: Number(item.amount) })) };
      if (editingRecipe) await api(`/api/nutrition/recipes/${editingRecipe.id}`, { method: "PUT", body: JSON.stringify(payload) });
      else await api("/api/nutrition/recipes", { method: "POST", body: JSON.stringify(payload) });
      setRecipeName(""); setRecipeType("breakfast"); setIngredients([{ foodId: "", amount: "50" }]);
      setEditingRecipe(null); await loadRecipes("", false); setFavoritesOnly(false); setRecipeQuery(""); setView("recipes");
    }, editingRecipe ? "Gericht wurde aktualisiert." : "Gericht wurde gespeichert.");
  }
  function editRecipe(recipe: Recipe) {
    setEditingRecipe(recipe); setRecipeName(recipe.name); setRecipeType(recipe.meal_type);
    setIngredients(recipe.ingredients.map(item => ({ foodId: String(item.food_id), amount: String(item.amount_g) })));
    setView("recipes");
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }
  async function toggleRecipe(recipe: Recipe) {
    await runAction(async () => {
      await api(`/api/nutrition/recipes/${recipe.id}/favorite`, { method: "PATCH", body: JSON.stringify({ is_favorite: !recipe.is_favorite }) });
      await loadRecipes();
    }, recipe.is_favorite ? "Favorit entfernt." : "Gericht zu Favoriten hinzugefügt.");
  }
  async function logRecipe(recipe: Recipe) {
    await runAction(async () => {
      await api(`/api/nutrition/recipes/${recipe.id}/log`, { method: "POST" });
      await loadDay(); await onDataChanged();
    }, recipe.name + " wurde für heute eingetragen.");
  }
  async function deleteRecipe(recipe: Recipe) {
    if (!window.confirm(`Gericht „${recipe.name}“ wirklich löschen? Bereits eingetragene Mahlzeiten bleiben erhalten.`)) return;
    await runAction(async () => { await api(`/api/nutrition/recipes/${recipe.id}`, { method: "DELETE" }); await loadRecipes(); }, "Gericht gelöscht.");
  }
  async function deleteMeal(id: number) {
    await runAction(async () => { await api(`/api/nutrition/meals/${id}`, { method: "DELETE" }); await loadDay(); await onDataChanged(); }, "Mahlzeit gelöscht.");
  }
  function updateIngredient(index: number, patch: Partial<IngredientDraft>) {
    setIngredients(current => current.map((item, i) => i === index ? { ...item, ...patch } : item));
  }

  return <div className="nutrition-page">
    <nav className="nutrition-nav" aria-label="Ernährungsbereiche">
      <button className={view === "today" ? "active" : ""} onClick={() => setView("today")}>Tagesübersicht</button>
      <button className={view === "recipes" ? "active" : ""} onClick={() => setView("recipes")}>Gerichte</button>
      <button className={view === "foods" ? "active" : ""} onClick={() => setView("foods")}>Lebensmittel</button>
    </nav>

    {view === "today" && <>
      <section className="panel">
        <div className="panel-heading"><div><h2>Deine persönlichen Tagesziele</h2><p>Pro Benutzer gespeichert · manuell anpassbar</p></div></div>
        <form onSubmit={saveGoals}>
          <div className="nutrition-grid">{keys.map(({ key, label, unit }) => <label key={key}>{label} ({unit})
            <input type="number" min="0" max="10000" step="0.1" required value={goals[key] || ""} onChange={e => setGoals({ ...goals, [key]: Number(e.target.value) })}/>
          </label>)}</div><button className="primary" disabled={busy}><Save size={16}/> Ziele speichern</button>
        </form>
      </section>
      <section className="nutrition-totals">
        <CaloriesCard daily={daily}/>
        {keys.filter(({ key }) => key !== "calories").map(({ key, label, unit }) => {
          const target = daily?.goals?.[key] ?? null, consumed = daily?.consumed[key] ?? 0, remaining = daily?.remaining?.[key] ?? null;
          const pct = target && target > 0 ? Math.min(100, consumed / target * 100) : 0;
          return <article className="summary-card" key={key}><span>{label}</span><strong>{n(consumed)} <small>{unit}</small></strong>
            <div className="nutrition-track"><span style={{ width: pct + "%" }}/></div><p>Ziel: {target == null ? "nicht gesetzt" : n(target) + " " + unit}</p>
            <em>{remaining == null ? "Tagesziel festlegen" : remaining >= 0 ? "Noch " + n(remaining) + " " + unit : n(-remaining) + " " + unit + " über Ziel"}</em>
          </article>;
        })}
      </section>
      <section className="panel">
        <div className="panel-heading"><div><h2>Heutige Mahlzeiten</h2><p>{daily?.entries.length ?? 0} Einträge</p></div>
          <button className="secondary-button" onClick={() => setView("recipes")}><Utensils size={15}/> Gericht auswählen</button></div>
        {!daily?.entries.length ? <div className="nutrition-empty"><Utensils/><p>Heute noch nichts eingetragen.</p><button className="primary" onClick={() => setView("recipes")}>Gericht auswählen</button></div> :
          daily.entries.map(entry => <article className="nutrition-entry" key={entry.id}>
            <div><b>{entry.food_name}</b><small>{mealLabels[entry.meal_type] ?? entry.meal_type} · {n(entry.amount_g)} g</small>
              {entry.ingredients?.length > 0 && <ul className="nutrition-ingredient-list">{entry.ingredients.map((item, i) => <li key={item.id ?? i}>{item.food_name} · {n(item.amount_g)} g</li>)}</ul>}</div>
            <span>{n(entry.calories)} kcal · P {n(entry.protein_g)} g · KH {n(entry.carbs_g)} g · F {n(entry.fat_g)} g</span>
            <button aria-label={`Mahlzeit ${entry.food_name} löschen`} disabled={busy} onClick={() => void deleteMeal(entry.id)}><Trash2 size={16}/></button>
          </article>)}
      </section>
      <section className="panel">
        <div className="panel-heading"><div><h2>Deine Favoriten</h2><p>Mit einem Klick in den heutigen Tag übernehmen</p></div><button className="secondary-button" onClick={() => { setFavoritesOnly(true); setView("recipes"); void loadRecipes("", true); }}>Alle Favoriten</button></div>
        {!favoriteRecipes.length ? <p className="muted">Noch keine Gerichte als Favorit markiert.</p> : <div className="recipe-cards">{favoriteRecipes.slice(0, 4).map(recipe => <RecipeCard key={recipe.id} recipe={recipe} busy={busy} onLog={() => void logRecipe(recipe)} onFavorite={() => void toggleRecipe(recipe)}/>)}</div>}
      </section>
    </>}

    {view === "recipes" && <>
      <section className="panel">
        <div className="panel-heading"><div><h2>Deine Gerichte</h2><p>Gespeicherte Mahlzeiten auswählen oder eigene Rezepte erstellen.</p></div>
          <button className="primary" onClick={() => setView("foods")}><Plus size={16}/> Lebensmittel verwalten</button></div>
        <div className="nutrition-tools"><div className="nutrition-search"><Search size={16}/><input placeholder="Gericht suchen" value={recipeQuery} onChange={e => { setRecipeQuery(e.target.value); void loadRecipes(e.target.value); }}/></div>
          <label className="favorite-filter"><input type="checkbox" checked={favoritesOnly} onChange={e => { setFavoritesOnly(e.target.checked); void loadRecipes(recipeQuery, e.target.checked); }}/> Nur Favoriten</label></div>
        {!recipes.length ? <div className="nutrition-empty"><Utensils/><p>Noch keine Gerichte gespeichert.</p><span>Erstelle dein erstes Gericht aus vorhandenen Lebensmitteln.</span></div> :
          <div className="recipe-cards">{recipes.map(recipe => <RecipeCard key={recipe.id} recipe={recipe} busy={busy} onLog={() => void logRecipe(recipe)} onFavorite={() => void toggleRecipe(recipe)} onDelete={() => void deleteRecipe(recipe)} onEdit={() => editRecipe(recipe)}/>)}</div>}
      </section>
      <section className="panel recipe-create-panel">
        <div className="panel-heading"><div><h2>{editingRecipe ? "Gericht bearbeiten" : "Neues Gericht erstellen"}</h2><p>Verwende vorhandene Lebensmittel und speichere das Rezept für später.</p></div></div>
        <form className="nutrition-recipe-form" onSubmit={saveRecipe}>
          <div className="recipe-meta"><label>Gerichtname<input required maxLength={160} value={recipeName} onChange={e => setRecipeName(e.target.value)} placeholder="z. B. Overnight Oats"/></label>
            <label>Typ<select value={recipeType} onChange={e => setRecipeType(e.target.value)}><option value="breakfast">Frühstück</option><option value="lunch">Mittagessen</option><option value="dinner">Abendessen</option><option value="snack">Snack</option></select></label></div>
          <div className="recipe-ingredients"><div className="recipe-ingredients-heading"><b>Zutaten</b><span>{ingredients.length} / 30</span></div>
            {ingredients.map((item, index) => <div className="recipe-ingredient-row" key={index}>
              <label>Lebensmittel<select required value={item.foodId} onChange={e => updateIngredient(index, { foodId: e.target.value })}><option value="">Auswählen</option>{foods.map(food => <option key={food.id} value={food.id}>{food.name}</option>)}</select></label>
              <label>Menge (g)<input type="number" min="0.1" max="10000" step="0.1" required value={item.amount} onChange={e => updateIngredient(index, { amount: e.target.value })}/></label>
              <button type="button" className="ingredient-remove" aria-label="Zutat entfernen" disabled={ingredients.length === 1 || busy} onClick={() => setIngredients(current => current.filter((_, i) => i !== index))}><Trash2 size={15}/></button>
            </div>)}
            <button type="button" className="add-ingredient" disabled={busy || ingredients.length >= 30} onClick={() => setIngredients(current => [...current, { foodId: "", amount: "50" }])}><Plus size={15}/> Zutat hinzufügen</button>
          </div>
          <div className="recipe-form-actions"><button className="primary" disabled={busy || foods.length === 0}><Save size={16}/> {editingRecipe ? "Änderungen speichern" : "Gericht speichern"}</button>{editingRecipe && <button type="button" className="secondary-button" onClick={() => { setEditingRecipe(null); setRecipeName(""); setIngredients([{ foodId: "", amount: "50" }]); }}>Abbrechen</button>}</div>
        </form>
      </section>
    </>}

    {view === "foods" && <>
      <section className="panel">
        <div className="panel-heading"><div><h2>Lebensmittel</h2><p>Einmal anlegen, beliebig oft in verschiedenen Gerichten verwenden.</p></div><button className="secondary-button" onClick={() => setView("recipes")}><ArrowLeft size={15}/> Zurück zu Gerichten</button></div>
        <div className="food-editor-toggle">
          <div><b>{editingFoodId !== null ? "Lebensmittel bearbeiten" : "Neues Lebensmittel"}</b><small>Stammdaten und Nährwerte je 100 g</small></div>
          <button className="secondary-button" type="button" onClick={() => { setFoodEditorOpen(value => !value); if (foodEditorOpen) { setEditingFoodId(null); setFoodName(""); setFoodValues({ calories: "", protein_g: "", carbs_g: "", fat_g: "" }); } }}>
            <Plus size={15}/> {foodEditorOpen ? "Einklappen" : "Lebensmittel anlegen"}
          </button>
        </div>
        {foodEditorOpen && <form className="food-editor-form" onSubmit={saveFood}>
          <label className="food-name-field">Name<input required maxLength={160} value={foodName} onChange={e => setFoodName(e.target.value)}/></label>
          <div className="nutrition-grid">{keys.map(({ key, label, unit }) => <label key={key}>{label} ({unit} je 100 g)<input type="number" min="0" max="10000" step="0.1" required value={foodValues[key]} onChange={e => setFoodValues({ ...foodValues, [key]: e.target.value })}/></label>)}</div>
          <div className="recipe-form-actions"><button className="primary" disabled={busy}><Save size={16}/> {editingFoodId !== null ? "Änderungen speichern" : "Lebensmittel speichern"}</button>
            <button type="button" className="secondary-button" onClick={() => { setFoodEditorOpen(false); setEditingFoodId(null); setFoodName(""); setFoodValues({ calories: "", protein_g: "", carbs_g: "", fat_g: "" }); }}>Abbrechen</button></div>
        </form>}
      </section>
      <section className="panel">
        <div className="nutrition-tools"><div className="nutrition-search"><Search size={16}/><input placeholder="Lebensmittel suchen" value={foodQuery} onChange={e => { setFoodQuery(e.target.value); void loadFoods(e.target.value); }}/></div></div>
        {!foods.length ? <div className="nutrition-empty"><p>Keine Lebensmittel gefunden.</p></div> :
          <div className="food-list">{foods.map(food => <article className="food-row" key={food.id}><div><b>{food.name}</b><small>Je {n(food.basis_g)} g · {n(food.calories)} kcal · P {n(food.protein_g)} g · KH {n(food.carbs_g)} g · F {n(food.fat_g)} g</small></div>
            <div className="food-actions"><button className="icon-action" aria-label={`${food.name} bearbeiten`} disabled={busy} onClick={() => editFood(food)}><Pencil size={16}/></button>
              <button className="icon-action danger" aria-label={`${food.name} löschen`} disabled={busy} onClick={() => void archiveFood(food)}><Trash2 size={16}/></button></div></article>)}</div>}
      </section>
    </>}}
    {error && <p className="form-message error-message" role="alert">{error}</p>}
    {notice && <p className="form-message success-message" role="status">{notice}</p>}
  </div>;
}

function RecipeCard({ recipe, busy, onLog, onFavorite, onDelete, onEdit }: {
  recipe: Recipe; busy: boolean; onLog: () => void; onFavorite: () => void; onDelete?: () => void; onEdit?: () => void;
}) {
  return <article className="recipe-card">
    <div className="recipe-card-heading"><div><h3>{recipe.name}</h3><small>{mealLabels[recipe.meal_type] ?? recipe.meal_type} · {recipe.ingredients.length} Zutaten · {n(recipe.amount_g)} g</small></div>
      <button className={recipe.is_favorite ? "favorite-button active" : "favorite-button"} aria-label={recipe.is_favorite ? "Favorit entfernen" : "Als Favorit markieren"} disabled={busy} onClick={onFavorite}><Heart size={17} fill={recipe.is_favorite ? "currentColor" : "none"}/></button></div>
    <ul>{recipe.ingredients.map((item, i) => <li key={item.id ?? item.food_id + "-" + i}>{item.food_name} · {n(item.amount_g)} g</li>)}</ul>
    <p className="recipe-nutrients">{n(recipe.calories)} kcal · P {n(recipe.protein_g)} g · KH {n(recipe.carbs_g)} g · F {n(recipe.fat_g)} g</p>
    <div className="recipe-card-actions">{onEdit && <button className="icon-action" aria-label={`${recipe.name} bearbeiten`} disabled={busy} onClick={onEdit}><Pencil size={16}/></button>}<button className="primary" disabled={busy} onClick={onLog}><Plus size={15}/> Heute eintragen</button>{onDelete && <button className="icon-action danger" disabled={busy} aria-label="Gericht löschen" onClick={onDelete}><Trash2 size={15}/></button>}</div>
  </article>;
}
