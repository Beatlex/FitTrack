import { useMemo, useState } from "react";
import { ChevronDown, Search, ShieldCheck } from "lucide-react";

export type HouseholdMember = {
  user_id: number;
  username: string;
  role: "owner" | "member";
  joined_at: string;
};

export type CatalogItem = {
  id: number;
  name: string;
  owner_id: number | null;
  granted_user_ids: number[];
};

export type CatalogAccessData = {
  members: Pick<HouseholdMember, "user_id" | "username" | "role">[];
  foods: CatalogItem[];
  recipes: CatalogItem[];
};

type CatalogKind = "foods" | "recipes";

type Props = {
  catalogAccess: CatalogAccessData;
  members: HouseholdMember[];
  currentUserId: number;
  busy: boolean;
  onGrantChange: (kind: CatalogKind, item: CatalogItem, member: HouseholdMember, granted: boolean) => void;
};

const categories: { kind: CatalogKind; label: string }[] = [
  { kind: "foods", label: "Lebensmittel" },
  { kind: "recipes", label: "Gerichte" },
];

export default function CatalogAccessSection({
  catalogAccess,
  members,
  currentUserId,
  busy,
  onGrantChange,
}: Props) {
  const [search, setSearch] = useState("");
  const normalizedSearch = search.trim().toLocaleLowerCase("de-DE");
  const visibleItems = useMemo(
    () => ({
      foods: catalogAccess.foods.filter((item) => item.name.toLocaleLowerCase("de-DE").includes(normalizedSearch)),
      recipes: catalogAccess.recipes.filter((item) => item.name.toLocaleLowerCase("de-DE").includes(normalizedSearch)),
    }),
    [catalogAccess, normalizedSearch],
  );
  const editableMembers = members.filter((member) => member.role !== "owner");

  const totalItems = catalogAccess.foods.length + catalogAccess.recipes.length;

  return (
    <details className="panel household-section catalog-access-panel">
      <summary className="catalog-access-summary">
        <span className="catalog-access-summary-icon"><ShieldCheck size={18} /></span>
        <span className="catalog-access-summary-copy">
          <strong>Einzelberechtigungen</strong>
          <small>{totalItems} Katalogeinträge · gezielte Freigabe pro Mitglied</small>
        </span>
        <ChevronDown className="catalog-access-chevron" size={18} aria-hidden="true" />
      </summary>

      <div className="catalog-access-content">
        <p className="catalog-access-description">
          Verwalte separat, welche Mitglieder einzelne Lebensmittel und Gerichte sehen und verwenden dürfen.
          Ersteller und Admin behalten immer Zugriff.
        </p>

        <label className="catalog-access-search">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Lebensmittel und Gerichte suchen</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Lebensmittel oder Gerichte suchen …"
            maxLength={120}
          />
        </label>

        {categories.map(({ kind, label }) => {
          const items = visibleItems[kind];
          const total = catalogAccess[kind].length;
          return (
            <section className="catalog-access-group" key={kind} aria-label={label}>
              <h3>{label} <span>({items.length}{normalizedSearch ? ` von ${total}` : ""})</span></h3>
              {!items.length ? (
                <p className="muted">
                  {total === 0 ? `Noch keine ${label.toLocaleLowerCase("de-DE")} im Haushalt.` : "Keine passenden Einträge gefunden."}
                </p>
              ) : items.map((item) => (
                <article className="catalog-access-item" key={item.id}>
                  <div className="catalog-access-heading">
                    <b>{item.name}</b>
                    <small>
                      {item.owner_id == null
                        ? "Gemeinsamer Eintrag"
                        : item.owner_id === currentUserId
                          ? "Von dir erstellt"
                          : `Ersteller: ${members.find((member) => member.user_id === item.owner_id)?.username ?? "ehemaliges Mitglied"}`}
                    </small>
                  </div>
                  <div className="catalog-access-members">
                    {editableMembers.map((member) => {
                      const checked = item.granted_user_ids.includes(member.user_id);
                      const protectedCreator = item.owner_id === member.user_id;
                      return (
                        <label className="catalog-access-toggle" key={member.user_id}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={busy || protectedCreator}
                            aria-label={`${label}: ${item.name} für ${member.username} freigeben`}
                            onChange={(event) => onGrantChange(kind, item, member, event.target.checked)}
                          />
                          <span>{member.username}{protectedCreator ? " · Ersteller" : ""}</span>
                        </label>
                      );
                    })}
                  </div>
                </article>
              ))}
            </section>
          );
        })}
      </div>
    </details>
  );
}
