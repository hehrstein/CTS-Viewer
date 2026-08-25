const CARD_TYPE = "cts-departures-card";

const LINE_COLORS = {
  A: "#dc2333",
  B: "#4b9fd4",
  C: "#e88d14",
  D: "#088f7c",
  E: "#7a5aa6",
  F: "#198754",
};

class CTSDeparturesCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("La carte CTS nécessite l'option entity.");
    }

    this._config = {
      max_rows: 6,
      show_traffic: true,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    const rows = Number(this._config?.max_rows) || 6;
    return Math.max(3, rows + 2);
  }

  _render() {
    if (!this._config) {
      return;
    }

    const state = this._hass?.states?.[this._config.entity];
    if (!state) {
      this.shadowRoot.innerHTML = `${this._styles()}<ha-card><div class="error">Entité introuvable : ${this._escape(this._config.entity)}</div></ha-card>`;
      return;
    }

    const attributes = state.attributes || {};
    const rows = Array.isArray(attributes.board_rows)
      ? attributes.board_rows.slice(0, this._maxRows())
      : [];
    const messages = Array.isArray(attributes.traffic_information)
      ? attributes.traffic_information
      : [];
    const stopName = attributes.stop_name || attributes.stop_code || "Arrêt CTS";
    const title = this._config.title || "Départs tram";
    const updatedAt = this._formatUpdated(
      attributes.data_updated_at || attributes.recorded_at
    );

    this.shadowRoot.innerHTML = `
      ${this._styles()}
      <ha-card>
        <header class="card-header">
          <div class="title"><span class="cts-logo" aria-hidden="true">CTS</span>${this._escape(title)}</div>
          ${updatedAt ? `<div class="updated">Mis à jour à ${this._escape(updatedAt)}</div>` : ""}
        </header>
        <div class="stop-name">${this._escape(stopName)}</div>
        ${rows.length ? this._renderBoard(rows) : this._renderEmpty()}
        ${this._config.show_traffic ? this._renderMessages(messages) : ""}
      </ha-card>
    `;
  }

  _renderBoard(rows) {
    return `
      <div class="column-headings" aria-hidden="true">
        <span>Ligne</span><span>Destination</span><span>Prochain</span><span>Suivant</span>
      </div>
      <div class="departures" role="list">
        ${rows.map((row) => this._renderRow(row)).join("")}
      </div>
    `;
  }

  _renderRow(row) {
    const line = String(row?.line || "Tram");
    const destination = String(row?.direction || "Destination non renseignée");
    const next = row?.next;
    const following = row?.following;
    const colour = LINE_COLORS[line.toUpperCase()] || "#4d5967";
    const nextLabel = this._departureLabel(next);
    const followingLabel = this._departureLabel(following);

    return `
      <article class="departure-row" role="listitem">
        <span class="line" style="background:${colour}">${this._escape(line)}</span>
        <span class="destination">${this._escape(destination)}</span>
        <span class="time ${next?.is_realtime ? "realtime" : ""}" aria-label="Prochain : ${this._escape(nextLabel)}">${this._escape(nextLabel)}</span>
        <span class="time" aria-label="Suivant : ${this._escape(followingLabel)}">${this._escape(followingLabel)}</span>
      </article>
    `;
  }

  _renderEmpty() {
    return '<div class="empty">Aucun passage à venir communiqué par la CTS.</div>';
  }

  _renderMessages(messages) {
    const visibleMessages = messages
      .map((message) => message?.title || message?.details)
      .filter((message) => typeof message === "string" && message.trim())
      .slice(0, 2);

    if (!visibleMessages.length) {
      return "";
    }

    return `
      <section class="traffic" aria-label="Informations trafic CTS">
        <span class="warning" aria-hidden="true">!</span>
        <div>${visibleMessages.map((message) => `<div>${this._escape(message)}</div>`).join("")}</div>
      </section>
    `;
  }

  _departureLabel(departure) {
    if (!departure) {
      return "—";
    }
    const minutes = Number(departure.minutes);
    if (Number.isFinite(minutes)) {
      return minutes === 0 ? "À quai" : `${minutes} min`;
    }
    return departure.time ? String(departure.time) : "—";
  }

  _formatUpdated(value) {
    if (!value) {
      return "";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    return new Intl.DateTimeFormat("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  _maxRows() {
    const value = Number(this._config.max_rows);
    return Number.isInteger(value) && value > 0 ? value : 6;
  }

  _escape(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _styles() {
    return `
      <style>
        :host { display: block; }
        ha-card { overflow: hidden; }
        .card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 18px 14px; border-bottom: 1px solid var(--divider-color); background: color-mix(in srgb, var(--card-background-color) 88%, var(--primary-text-color)); }
        .title { display: flex; align-items: center; gap: 9px; font-size: 15px; font-weight: 700; letter-spacing: .03em; text-transform: uppercase; }
        .cts-logo { display: grid; place-items: center; width: 28px; height: 22px; border-radius: 4px; background: #d91e2c; color: #fff; font-size: 11px; font-weight: 800; }
        .updated { color: var(--secondary-text-color); font-size: 12px; white-space: nowrap; }
        .stop-name { padding: 16px 18px 12px; font-size: 21px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .column-headings, .departure-row { display: grid; grid-template-columns: 48px minmax(0, 1fr) 82px 82px; align-items: center; column-gap: 10px; }
        .column-headings { padding: 0 18px 8px; color: var(--secondary-text-color); font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
        .column-headings span:nth-child(3), .column-headings span:nth-child(4) { text-align: right; }
        .departures { margin: 0 18px 14px; border-top: 1px solid var(--divider-color); }
        .departure-row { min-height: 61px; border-bottom: 1px solid var(--divider-color); }
        .line { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 5px; color: #fff; font-size: 20px; font-weight: 800; line-height: 1; }
        .destination { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 15px; font-weight: 500; }
        .time { position: relative; text-align: right; font-size: 19px; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -.03em; white-space: nowrap; }
        .time.realtime::after { content: ""; display: inline-block; width: 6px; height: 6px; margin: 0 0 9px 4px; border-radius: 50%; background: #22a56d; }
        .traffic { display: flex; align-items: flex-start; gap: 9px; margin: 0 18px 18px; padding: 11px 12px; border-radius: 8px; color: var(--warning-color, #bf8c00); background: color-mix(in srgb, var(--warning-color, #ffc107) 16%, transparent); font-size: 13px; line-height: 1.35; }
        .warning { display: grid; place-items: center; flex: 0 0 auto; width: 16px; height: 16px; border-radius: 50%; background: currentColor; color: var(--card-background-color); font-size: 12px; font-weight: 800; }
        .empty, .error { margin: 0 18px 18px; padding: 15px 0; color: var(--secondary-text-color); border-top: 1px solid var(--divider-color); }
        .error { color: var(--error-color); }
        @media (max-width: 480px) {
          .card-header, .stop-name, .column-headings { padding-left: 14px; padding-right: 14px; }
          .departures, .traffic, .empty, .error { margin-left: 14px; margin-right: 14px; }
          .column-headings, .departure-row { grid-template-columns: 42px minmax(0, 1fr) 58px 58px; column-gap: 6px; }
          .stop-name { font-size: 19px; }
          .time { font-size: 17px; }
          .updated { display: none; }
        }
      </style>
    `;
  }
}

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, CTSDeparturesCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === `custom:${CARD_TYPE}`)) {
  window.customCards.push({
    type: `custom:${CARD_TYPE}`,
    name: "CTS départs tram",
    description: "Affiche les deux prochains trams par ligne et destination.",
  });
}
