import { FormEvent, useEffect, useMemo, useState } from "react";
import { Pencil, Ruler, Save, Scale, Trash2, X } from "lucide-react";
import { api } from "../services/api";

type Measurement = {
  id: number;
  measured_at: string;
  weight_kg: number | null;
  waist_cm: number | null;
  chest_cm: number | null;
  hip_cm: number | null;
  arm_cm: number | null;
  thigh_cm: number | null;
};

type FormValues = Record<"measured_at" | "weight_kg" | "waist_cm" | "chest_cm" | "hip_cm" | "arm_cm" | "thigh_cm", string>;
type Period = "7" | "30" | "90" | "all";
const fields = [
  ["weight_kg", "Gewicht", "kg"],
  ["waist_cm", "Bauchumfang", "cm"],
  ["chest_cm", "Brustumfang", "cm"],
  ["hip_cm", "Hüftumfang", "cm"],
  ["arm_cm", "Armumfang", "cm"],
  ["thigh_cm", "Oberschenkel", "cm"],
] as const;

function localDateTime(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 16);
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
function blankForm(): FormValues {
  return { measured_at: localDateTime(), weight_kg: "", waist_cm: "", chest_cm: "", hip_cm: "", arm_cm: "", thigh_cm: "" };
}
function asForm(entry: Measurement): FormValues {
  return {
    measured_at: localDateTime(new Date(entry.measured_at)),
    weight_kg: entry.weight_kg == null ? "" : String(entry.weight_kg),
    waist_cm: entry.waist_cm == null ? "" : String(entry.waist_cm),
    chest_cm: entry.chest_cm == null ? "" : String(entry.chest_cm),
    hip_cm: entry.hip_cm == null ? "" : String(entry.hip_cm),
    arm_cm: entry.arm_cm == null ? "" : String(entry.arm_cm),
    thigh_cm: entry.thigh_cm == null ? "" : String(entry.thigh_cm),
  };
}

export default function BodyMeasurements() {
  const [entries, setEntries] = useState<Measurement[]>([]);
  const [form, setForm] = useState<FormValues>(blankForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [period, setPeriod] = useState<Period>("30");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadEntries() {
    setLoading(true);
    try {
      const data = await api<Measurement[]>("/api/measurements");
      setEntries(data);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Messwerte konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { void loadEntries(); }, []);

  const filteredEntries = useMemo(() => {
    if (period === "all") return entries;
    const cutoff = Date.now() - Number(period) * 24 * 60 * 60 * 1000;
    return entries.filter((entry) => new Date(entry.measured_at).getTime() >= cutoff);
  }, [entries, period]);

  const weightEntries = entries.filter((entry) => entry.weight_kg != null);
  const latestWeight = weightEntries[0] ?? null;
  const previousWeight = weightEntries[1]?.weight_kg ?? null;
  const weightChange = latestWeight?.weight_kg != null && previousWeight != null ? latestWeight.weight_kg - previousWeight : null;
  const weightPoints = [...filteredEntries]
    .filter((entry) => entry.weight_kg != null)
    .sort((a, b) => new Date(a.measured_at).getTime() - new Date(b.measured_at).getTime());

  function resetForm() {
    setForm(blankForm());
    setEditingId(null);
    setError("");
  }
  function startEdit(entry: Measurement) {
    setForm(asForm(entry));
    setEditingId(entry.id);
    setNotice("");
    setError("");
    document.getElementById("measurement-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const payload: Record<string, string | number> = { measured_at: new Date(form.measured_at).toISOString() };
    for (const [key] of fields) {
      if (form[key] !== "") payload[key] = Number(form[key]);
    }
    if (Object.keys(payload).length === 1) {
      setError("Bitte mindestens einen Körperwert eintragen.");
      setSaving(false);
      return;
    }
    try {
      if (editingId == null) {
        await api<Measurement>("/api/measurements", { method: "POST", body: JSON.stringify(payload) });
        setNotice("Messung wurde gespeichert.");
      } else {
        await api<Measurement>(`/api/measurements/${editingId}`, { method: "PATCH", body: JSON.stringify(payload) });
        setNotice("Messung wurde aktualisiert.");
      }
      resetForm();
      await loadEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  }
  async function removeEntry(id: number) {
    if (!window.confirm("Möchtest du diese Messung wirklich löschen?")) return;
    setError("");
    setNotice("");
    try {
      await api<void>(`/api/measurements/${id}`, { method: "DELETE" });
      if (editingId === id) resetForm();
      setNotice("Messung wurde gelöscht.");
      await loadEntries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    }
  }

  return (
    <div className="measurements-page">
      <section className="measurement-summary">
        <article className="summary-card">
          <div className="summary-icon"><Scale size={19} /></div>
          <span>Letztes Gewicht</span>
          <strong>{latestWeight?.weight_kg != null ? latestWeight.weight_kg.toLocaleString("de-DE", { maximumFractionDigits: 1 }) : "–"}<small> kg</small></strong>
          <em>{latestWeight ? formatDate(latestWeight.measured_at) : "Noch keine Messung"}</em>
        </article>
        <article className="summary-card">
          <div className="summary-icon"><Ruler size={19} /></div>
          <span>Erfasste Messungen</span>
          <strong>{entries.length}</strong>
          <em>Dein persönlicher Verlauf</em>
        </article>
        <article className="summary-card">
          <div className="summary-icon"><Scale size={19} /></div>
          <span>Veränderung zum vorherigen Gewicht</span>
          <strong className={weightChange == null ? "" : weightChange > 0 ? "value-up" : weightChange < 0 ? "value-down" : ""}>
            {weightChange == null ? "–" : `${weightChange > 0 ? "+" : ""}${weightChange.toLocaleString("de-DE", { maximumFractionDigits: 1 })}`}
            <small>{weightChange == null ? "" : " kg"}</small>
          </strong>
          <em>Vergleich der letzten zwei Gewichtseinträge</em>
        </article>
      </section>

      <section className="panel measurement-chart-panel">
        <div className="panel-heading">
          <div><h2>Gewichtsverlauf</h2><p>Deine Entwicklung im Zeitverlauf</p></div>
          <div className="period-switch" aria-label="Zeitraum auswählen">
            {(["7", "30", "90", "all"] as Period[]).map((value) => (
              <button key={value} className={period === value ? "active" : ""} onClick={() => setPeriod(value)}>
                {value === "all" ? "Gesamt" : `${value} T`}
              </button>
            ))}
          </div>
        </div>
        <WeightChart points={weightPoints} />
      </section>

      <section className="panel measurement-form-panel" id="measurement-form">
        <div className="panel-heading">
          <div><h2>{editingId == null ? "Neue Messung" : "Messung bearbeiten"}</h2><p>Alle Angaben sind optional – mindestens ein Körperwert ist erforderlich.</p></div>
          {editingId != null && <button className="secondary-button" onClick={resetForm}><X size={16}/> Abbrechen</button>}
        </div>
        <form onSubmit={submit}>
          <label className="measurement-date">Messdatum und Uhrzeit
            <input type="datetime-local" value={form.measured_at} onChange={(event) => setForm({ ...form, measured_at: event.target.value })} required />
          </label>
          <div className="measurement-fields">
            {fields.map(([key, label, unit]) => (
              <label key={key}>{label} <span>({unit})</span>
                <input type="number" min="0.1" max="500" step="0.1" inputMode="decimal" placeholder="–" value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
              </label>
            ))}
          </div>
          <button className="primary" type="submit" disabled={saving}><Save size={16}/>{saving ? "Speichert…" : editingId == null ? "Messung speichern" : "Änderungen speichern"}</button>
        </form>
        {error && <p className="form-message error-message" role="alert">{error}</p>}
        {notice && <p className="form-message success-message" role="status">{notice}</p>}
      </section>

      <section className="panel measurement-history">
        <div className="panel-heading"><div><h2>Messhistorie</h2><p>{entries.length} gespeicherte {entries.length === 1 ? "Messung" : "Messungen"}</p></div></div>
        {loading ? <p className="muted">Messungen werden geladen…</p> : entries.length === 0 ? (
          <div className="history-empty"><Scale size={30}/><p>Noch keine Messungen vorhanden.</p><span>Trage oben deine erste Messung ein.</span></div>
        ) : (
          <div className="table-scroll"><table className="measurement-table">
            <thead><tr><th>Datum</th><th>Gewicht</th><th>Bauch</th><th>Brust</th><th>Hüfte</th><th>Arm</th><th>Oberschenkel</th><th>Aktionen</th></tr></thead>
            <tbody>{entries.map((entry) => <tr key={entry.id}>
              <td>{formatDate(entry.measured_at)}</td>
              <td>{formatValue(entry.weight_kg, "kg")}</td><td>{formatValue(entry.waist_cm, "cm")}</td><td>{formatValue(entry.chest_cm, "cm")}</td><td>{formatValue(entry.hip_cm, "cm")}</td><td>{formatValue(entry.arm_cm, "cm")}</td><td>{formatValue(entry.thigh_cm, "cm")}</td>
              <td><div className="table-actions"><button aria-label="Messung bearbeiten" title="Bearbeiten" onClick={() => startEdit(entry)}><Pencil size={16}/></button><button aria-label="Messung löschen" title="Löschen" onClick={() => void removeEntry(entry.id)}><Trash2 size={16}/></button></div></td>
            </tr>)}</tbody>
          </table></div>
        )}
      </section>
    </div>
  );
}

function formatValue(value: number | null, unit: string) {
  return value == null ? "–" : `${value.toLocaleString("de-DE", { maximumFractionDigits: 1 })} ${unit}`;
}

function WeightChart({ points }: { points: Measurement[] }) {
  if (points.length === 0) return <div className="chart-empty">Noch keine Gewichtswerte für diesen Zeitraum.</div>;
  if (points.length === 1) return <div className="chart-single"><strong>{formatValue(points[0].weight_kg, "kg")}</strong><span>{formatDate(points[0].measured_at)}</span><p>Trage weitere Gewichtswerte ein, um deinen Verlauf zu sehen.</p></div>;

  const values = points.map((point) => point.weight_kg as number);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = Math.max((max - min) * 0.2, 1);
  const low = min - padding;
  const high = max + padding;
  const width = 720;
  const height = 210;
  const left = 42;
  const right = 18;
  const top = 18;
  const bottom = 32;
  const x = (index: number) => left + (index / (points.length - 1)) * (width - left - right);
  const y = (value: number) => top + ((high - value) / (high - low)) * (height - top - bottom);
  const polyline = points.map((point, index) => `${x(index)},${y(point.weight_kg as number)}`).join(" ");
  return (
    <div className="weight-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Diagramm des Gewichtsverlaufs">
        {[0, 1, 2, 3].map((step) => {
          const value = high - ((high - low) * step) / 3;
          const position = y(value);
          return <g key={step}><line x1={left} y1={position} x2={width - right} y2={position} className="chart-grid"/><text x={left - 8} y={position + 4} textAnchor="end" className="chart-label">{value.toLocaleString("de-DE", { maximumFractionDigits: 1 })}</text></g>;
        })}
        <polyline points={polyline} className="chart-line" />
        {points.map((point, index) => <circle key={point.id} cx={x(index)} cy={y(point.weight_kg as number)} r="4.5" className="chart-point"><title>{formatDate(point.measured_at)}: {formatValue(point.weight_kg, "kg")}</title></circle>)}
        <text x={left} y={height - 7} className="chart-label">{new Date(points[0].measured_at).toLocaleDateString("de-DE")}</text>
        <text x={width - right} y={height - 7} textAnchor="end" className="chart-label">{new Date(points[points.length - 1].measured_at).toLocaleDateString("de-DE")}</text>
      </svg>
    </div>
  );
}
