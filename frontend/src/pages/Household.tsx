import { useEffect, useState, type FormEvent } from "react";
import { Check, Crown, Home, Link2, LogOut, Plus, ShieldCheck, UserMinus, Users, X } from "lucide-react";
import { api } from "../services/api";

type Member = { user_id: number; username: string; role: "owner" | "member"; joined_at: string };
type Invitation = { id: number; household_name?: string; invited_by?: string; username?: string; created_at: string };
type HouseholdData = {
  id: number;
  name: string;
  owner_id: number;
  current_user_role: "owner" | "member";
  members: Member[];
};
type ResponseData = {
  household: HouseholdData | null;
  invitations: Invitation[];
  pending_invitations?: Invitation[];
};

const dateLabel = (value: string) => new Date(value).toLocaleDateString("de-DE");

export default function HouseholdPage() {
  const [data, setData] = useState<ResponseData | null>(null);
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setLoading(true);
    try {
      setData(await api<ResponseData>("/api/household"));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Haushalt konnte nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load();
      setNotice(success);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = username.trim().toLowerCase();
    if (!clean) return;
    await run(async () => {
      await api("/api/household/invitations", {
        method: "POST",
        body: JSON.stringify({ username: clean }),
      });
      setUsername("");
    }, "Einladung wurde erstellt. Der Benutzer muss sie noch annehmen.");
  }

  if (loading && !data) return <section className="panel household-loading">Haushalt wird geladen …</section>;

  const household = data?.household;
  const isOwner = household?.current_user_role === "owner";

  return (
    <div className="household-page">
      <section className="panel household-hero">
        <div className="household-icon"><Home /></div>
        <div>
          <small>GEMEINSAM VERWALTEN</small>
          <h2>{household?.name ?? "Noch kein Haushalt"}</h2>
          <p>{household ? "Lebensmittel und gespeicherte Gerichte werden mit den Mitgliedern dieses Haushalts geteilt." : "Nimm eine offene Einladung an, um einem Haushalt beizutreten."}</p>
        </div>
        {household && <span className="household-role">{isOwner ? "Inhaber" : "Mitglied"}</span>}
      </section>

      {error && <p className="error-message form-message" role="alert">{error}</p>}
      {notice && <p className="success-message form-message" role="status">{notice}</p>}

      {data?.invitations.length ? <section className="panel household-section">
        <div className="panel-heading"><div><h2>Einladungen für dich</h2><p>Du entscheidest selbst, welchem Haushalt du beitrittst.</p></div></div>
        <div className="household-list">
          {data.invitations.map(invitation => <article className="household-invite" key={invitation.id}>
            <div className="member-avatar"><Home size={17}/></div>
            <div className="member-info"><b>{invitation.household_name}</b><small>Eingeladen von {invitation.invited_by} · {dateLabel(invitation.created_at)}</small></div>
            <div className="household-actions">
              <button className="primary compact" disabled={busy} onClick={() => void run(async () => {
                await api(`/api/household/invitations/${invitation.id}/accept`, { method: "POST" });
              }, "Du bist dem Haushalt beigetreten.")}><Check size={15}/> Annehmen</button>
              <button className="secondary-button" disabled={busy} onClick={() => void run(async () => {
                await api(`/api/household/invitations/${invitation.id}`, { method: "DELETE" });
              }, "Einladung abgelehnt.")}><X size={15}/> Ablehnen</button>
            </div>
          </article>)}
        </div>
      </section> : null}

      {household && <>
        <section className="panel household-section">
          <div className="panel-heading"><div><h2><Users size={18}/> Mitglieder</h2><p>Alle Mitglieder können den gemeinsamen Lebensmittel- und Gerichtekatalog nutzen.</p></div><span className="member-count">{household.members.length} Mitglieder</span></div>
          <div className="household-list">
            {household.members.map(member => <article className="household-member" key={member.user_id}>
              <div className="member-avatar"><Users size={17}/></div>
              <div className="member-info"><b>{member.username}{member.user_id === household.owner_id ? " (du)" : ""}</b><small>{member.role === "owner" ? "Haushaltsinhaber" : "Mitglied"} · Seit {dateLabel(member.joined_at)}</small></div>
              {member.role === "owner" ? <span className="owner-tag"><Crown size={14}/> Inhaber</span> :
                isOwner ? <button className="icon-danger" title={member.user_id === household.owner_id ? "Inhaber kann nicht entfernt werden" : "Mitglied aus Haushalt entfernen"} disabled={busy} onClick={() => {
                  if (window.confirm(`${member.username} wirklich aus dem Haushalt entfernen? Der Zugriff auf gemeinsame Lebensmittel und Gerichte endet sofort.`)) {
                    void run(async () => { await api(`/api/household/members/${member.user_id}`, { method: "DELETE" }); }, "Mitglied wurde entfernt.");
                  }
                }}><UserMinus size={17}/></button> :
                <span className="member-tag">Mitglied</span>}
            </article>)}
          </div>
        </section>

        {isOwner && <section className="panel household-section">
          <div className="panel-heading"><div><h2><Plus size={18}/> Benutzer einladen</h2><p>Die Einladung geht an ein bestehendes FitTrack-Konto mit bekanntem Benutzernamen.</p></div></div>
          <form className="household-invite-form" onSubmit={invite}>
            <label htmlFor="household-username">Benutzername</label>
            <div className="invite-input-row">
              <input id="household-username" value={username} onChange={event => setUsername(event.target.value)} minLength={3} maxLength={40} pattern="[A-Za-z0-9_.-]+" placeholder="Benutzername eingeben" required />
              <button className="primary" type="submit" disabled={busy || !username.trim()}><Plus size={16}/> Einladen</button>
            </div>
          </form>
          {!!data?.pending_invitations?.length && <div className="pending-list">
            <h3>Offene Einladungen</h3>
            {data.pending_invitations.map(invitation => <div className="pending-row" key={invitation.id}>
              <span>{invitation.username}</span><small>Ausstehend · {dateLabel(invitation.created_at)}</small>
              <button className="secondary-button" disabled={busy} onClick={() => void run(async () => {
                await api(`/api/household/invitations/${invitation.id}`, { method: "DELETE" });
              }, "Einladung wurde zurückgezogen.")}><X size={14}/> Zurückziehen</button>
            </div>)}
          </div>}
        </section>}

        {!isOwner && <section className="panel household-section leave-household">
          <div><h2><LogOut size={18}/> Haushalt verlassen</h2><p>Du verlierst dadurch den Zugriff auf gemeinsame Lebensmittel und Gerichte. Deine persönlichen Messungen und Mahlzeiten bleiben erhalten.</p></div>
          <button className="secondary-button" disabled={busy} onClick={() => {
            if (window.confirm("Möchtest du diesen Haushalt wirklich verlassen?")) {
              void run(async () => { await api(`/api/household/members/${household.members.find(m => m.role !== "owner" && m.user_id !== household.owner_id)?.user_id ?? 0}`, { method: "DELETE" }); }, "Du hast den Haushalt verlassen.");
            }
          }}>Haushalt verlassen</button>
        </section>}
      </>}

      <section className="household-future-grid">
        <article className="panel future-module"><CalendarIcon/><div><b>Wochenplan</b><small>Gemeinsame Planung eurer Gerichte</small><span>In Planung</span></div></article>
        <article className="panel future-module"><ShoppingIcon/><div><b>Einkaufsplan</b><small>Zutaten automatisch zusammenfassen</small><span>In Planung</span></div></article>
      </section>
      <section className="household-sharing-note"><ShieldCheck size={17}/><p>Gemeinsam: Lebensmittel und Gerichte. Privat: Körperwerte, Tagesziele und protokollierte Mahlzeiten.</p></section>
    </div>
  );
}

function CalendarIcon() { return <Link2 className="future-icon"/>; }
function ShoppingIcon() { return <Link2 className="future-icon"/>; }
