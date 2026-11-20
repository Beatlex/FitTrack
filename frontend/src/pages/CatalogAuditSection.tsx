import { Activity, Clock3, History } from "lucide-react";
import "./CatalogAuditSection.css";

export type CatalogAuditEvent = {
  id: number;
  actor_username: string;
  entity_type: "food" | "recipe";
  entity_id: number;
  entity_name: string;
  action: "created" | "updated" | "archived" | "deleted" | "access_granted" | "access_revoked";
  changes: Record<string, unknown>;
  created_at: string;
};

type Props = { events: CatalogAuditEvent[] };

const actionLabels: Record<CatalogAuditEvent["action"], string> = {
  created: "erstellt",
  updated: "bearbeitet",
  archived: "archiviert",
  deleted: "gelöscht",
  access_granted: "freigegeben",
  access_revoked: "Freigabe entzogen",
};

function detailLabel(event: CatalogAuditEvent): string {
  const member = event.changes.member_username;
  if (typeof member === "string") {
    return `für ${member}`;
  }
  if (event.action !== "updated") return "";
  const before = event.changes.before;
  const after = event.changes.after;
  if (!before || !after || typeof before !== "object" || typeof after !== "object") return "";
  const oldState = before as Record<string, unknown>;
  const newState = after as Record<string, unknown>;
  const changed = Object.keys(newState).filter(
    (key) => JSON.stringify(oldState[key]) !== JSON.stringify(newState[key]),
  );
  const labels: Record<string, string> = {
    name: "Name", brand: "Marke", basis_g: "Bezugsmenge",
    calories: "Kalorien", protein_g: "Protein", carbs_g: "Kohlenhydrate",
    fat_g: "Fett", meal_type: "Mahlzeitentyp", ingredients: "Zutaten",
  };
  return changed.length ? `Geändert: ${changed.map((key) => labels[key] ?? key).join(", ")}` : "Keine Feldänderung";
}

export default function CatalogAuditSection({ events }: Props) {
  return (
    <section className="panel household-section catalog-audit-section">
      <div className="panel-heading">
        <div><h2><History size={18}/> Änderungsverlauf</h2><p>Nachvollziehbare Änderungen am gemeinsamen Katalog und an Freigaben</p></div>
        <span className="catalog-audit-count">{events.length} Einträge</span>
      </div>
      {!events.length ? (
        <p className="catalog-audit-empty">Noch keine Änderungen protokolliert.</p>
      ) : (
        <ol className="catalog-audit-list">
          {events.map((event) => (
            <li className="catalog-audit-event" key={event.id}>
              <span className="catalog-audit-icon"><Activity size={15}/></span>
              <div className="catalog-audit-copy">
                <p><b>{event.actor_username}</b> {actionLabels[event.action]} <strong>{event.entity_type === "food" ? "Lebensmittel" : "Gericht"}: {event.entity_name}</strong></p>
                {detailLabel(event) && <small>{detailLabel(event)}</small>}
                <time dateTime={event.created_at}><Clock3 size={12}/> {new Date(event.created_at).toLocaleString("de-DE")}</time>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
