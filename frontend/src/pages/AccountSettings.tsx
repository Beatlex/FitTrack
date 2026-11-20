import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import { api } from "../services/api";

const TIMEZONE_GROUPS = [
  { label: "Europa", zones: ["Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "Europe/London", "Europe/Paris", "Europe/Amsterdam", "Europe/Madrid", "Europe/Rome", "Europe/Stockholm", "Europe/Warsaw", "Europe/Athens", "Europe/Istanbul"] },
  { label: "Nord- und Südamerika", zones: ["America/St_Johns", "America/Halifax", "America/Toronto", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Vancouver", "America/Mexico_City", "America/Sao_Paulo"] },
  { label: "Asien", zones: ["Asia/Dubai", "Asia/Kolkata", "Asia/Bangkok", "Asia/Singapore", "Asia/Shanghai", "Asia/Tokyo", "Asia/Seoul"] },
  { label: "Australien und Pazifik", zones: ["Australia/Perth", "Australia/Adelaide", "Australia/Sydney", "Pacific/Auckland", "Pacific/Honolulu"] },
  { label: "Weitere", zones: ["UTC"] },
] as const;

type Props = {
  username: string;
  timezone: string;
  onTimezoneChanged: (timezone_name: string) => void;
  onDeleted: () => void;
};

export default function AccountSettings({ username, timezone, onTimezoneChanged, onDeleted }: Props) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [timezoneDraft, setTimezoneDraft] = useState(timezone);
  const [timezoneBusy, setTimezoneBusy] = useState(false);
  const [timezoneError, setTimezoneError] = useState("");
  const [timezoneNotice, setTimezoneNotice] = useState("");

  useEffect(() => setTimezoneDraft(timezone), [timezone]);

  async function saveTimezone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTimezoneBusy(true);
    setTimezoneError("");
    setTimezoneNotice("");
    try {
      const result = await api<{ timezone_name: string }>("/api/auth/timezone", {
        method: "PATCH",
        body: JSON.stringify({ timezone_name: timezoneDraft.trim() }),
      });
      setTimezoneDraft(result.timezone_name);
      onTimezoneChanged(result.timezone_name);
      setTimezoneNotice("Zeitzone wurde gespeichert.");
    } catch (err) {
      setTimezoneError(err instanceof Error ? err.message : "Zeitzone konnte nicht gespeichert werden.");
    } finally {
      setTimezoneBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (confirmation !== username) {
      setError("Der Benutzername stimmt nicht exakt überein.");
      return;
    }
    if (!window.confirm("Dein Konto und deine persönlichen Daten endgültig löschen? Diese Aktion kann nicht rückgängig gemacht werden.")) {
      return;
    }

    setBusy(true);
    try {
      await api<void>("/api/auth/account", {
        method: "DELETE",
        body: JSON.stringify({ password, confirmation }),
      });
      setPassword("");
      setConfirmation("");
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Das Konto konnte nicht gelöscht werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="account-settings-page">
      <section className="panel account-profile-panel">
        <h2>Kontoverwaltung</h2>
        <p>Angemeldet als <b>{username}</b></p>
      </section>
      <section className="panel account-timezone-panel">
        <h2>Zeitzone</h2>
        <p>Legt fest, welchem Kalendertag deine Mahlzeiten und Tageswerte zugeordnet werden. Zeitstempel werden weiterhin in UTC gespeichert.</p>
        <form className="account-timezone-form" onSubmit={saveTimezone}>
          <label htmlFor="account-timezone">Zeitzone auswählen</label>
          <select
            id="account-timezone"
            value={timezoneDraft}
            onChange={event => setTimezoneDraft(event.target.value)}
            required
          >
            <option value="" disabled>Bitte Zeitzone auswählen</option>
            {timezoneDraft && !TIMEZONE_GROUPS.some(group => (group.zones as readonly string[]).includes(timezoneDraft)) && (
              <option value={timezoneDraft}>{timezoneDraft} (aktuell gespeichert)</option>
            )}
            {TIMEZONE_GROUPS.map(group => (
              <optgroup key={group.label} label={group.label}>
                {group.zones.map(zone => <option key={zone} value={zone}>{zone.replaceAll("_", " ")}</option>)}
              </optgroup>
            ))}
          </select>
          <small>Die Auswahl berücksichtigt Sommer- und Winterzeit automatisch.</small>
          {timezoneError && <p className="error-message form-message" role="alert">{timezoneError}</p>}
          {timezoneNotice && <p className="success-message" role="status">{timezoneNotice}</p>}
          <button className="primary" type="submit" disabled={timezoneBusy || !timezoneDraft.trim() || timezoneDraft.trim() === timezone}>
            {timezoneBusy ? "Wird gespeichert …" : "Zeitzone speichern"}
          </button>
        </form>
      </section>\n      <section className="panel account-danger-panel">
        <div className="account-danger-heading">
          <div className="account-danger-icon"><AlertTriangle size={19}/></div>
          <div><h2>Konto endgültig löschen</h2><p>Diese Aktion kann nicht rückgängig gemacht werden.</p></div>
        </div>
        <ul>
          <li>Dein Zugang und deine persönlichen Messungen, Ziele und Mahlzeiten werden gelöscht.</li>
          <li>Gemeinsam verwendete Lebensmittel und Gerichte bleiben für die übrigen berechtigten Mitglieder erhalten.</li>
          <li>Ist dein Konto Haushalts-Admin, wird die Verantwortung an ein verbleibendes Mitglied übertragen.</li>
        </ul>
        <form className="account-delete-form" onSubmit={submit}>
          <label htmlFor="delete-account-password">Aktuelles Passwort</label>
          <input
            id="delete-account-password"
            type="password"
            value={password}
            onChange={event => setPassword(event.target.value)}
            autoComplete="current-password"
            maxLength={256}
            required
          />
          <label htmlFor="delete-account-confirmation">Zur Bestätigung deinen Benutzernamen eingeben: <b>{username}</b></label>
          <input
            id="delete-account-confirmation"
            value={confirmation}
            onChange={event => setConfirmation(event.target.value)}
            autoComplete="off"
            maxLength={40}
            required
          />
          {error && <p className="error-message form-message" role="alert">{error}</p>}
          <button className="account-delete-button" type="submit" disabled={busy || !password || confirmation !== username}>
            <Trash2 size={16}/>{busy ? "Konto wird gelöscht …" : "Konto endgültig löschen"}
          </button>
        </form>
      </section>
    </div>
  );
}
