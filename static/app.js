const GAME_ID = "table";
const SUIT_SYMBOL = { C: "♣", D: "♦", H: "♥", S: "♠", NT: "NT" };
const RANK_LABEL = { T: "10" };
const SUIT_ORDER = ["S", "H", "C", "D"];

const els = {
  deal: document.getElementById("deal"),
  score: document.getElementById("score"),
  dealChip: document.getElementById("deal-chip"),
  scoreChip: document.getElementById("score-chip"),
  contract: document.getElementById("contract-line"),
  status: document.getElementById("status"),
  trick: document.getElementById("trick"),
  overlay: document.getElementById("overlay"),
  scoresheet: document.getElementById("scoresheet"),
};

let state = null;
let busy = false;
let showCompleted = false;

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}

function pretty(contract) {
  if (!contract) return "—";
  return String(contract)
    .replace("NT", "NT")
    .replace("C", "♣")
    .replace("D", "♦")
    .replace("H", "♥")
    .replace("S", "♠");
}

function cardNode(card, extra = "") {
  const el = document.createElement("button");
  el.type = "button";
  el.className = `card ${card.suit === "H" || card.suit === "D" ? "red" : "black"} ${extra}`.trim();
  el.dataset.cardId = String(card.id);
  const rank = RANK_LABEL[card.rank] || card.rank;
  const suit = SUIT_SYMBOL[card.suit];
  el.innerHTML = `<span class="rank">${rank}</span><span class="mini">${suit}</span><span class="pip">${suit}</span>`;
  return el;
}

function groupCards(cards) {
  const groups = [];
  for (const suit of SUIT_ORDER) {
    const inSuit = (cards || []).filter((card) => card.suit === suit);
    if (inSuit.length) groups.push(inSuit);
  }
  return groups;
}

function humanSeat() {
  return state.human_seat || (state.agent_seats || ["S"])[0];
}

function controller(seat = state.to_act) {
  if (state.phase === "play" && seat === state.dummy && state.declarer) return state.declarer;
  return seat;
}

function isHumanTurn() {
  return controller() === humanSeat();
}

function fillHand(seat, cards, counts) {
  const root = document.getElementById(`hand-${seat.toLowerCase()}`);
  root.innerHTML = "";
  const legal = new Set(state.legal_actions || []);
  const canClick = state.phase === "play" && state.to_act === seat && isHumanTurn();
  const dummyUp = Boolean(state.dummy_visible) && seat === state.dummy;
  const hidden = seat !== humanSeat() && !dummyUp && state.phase !== "deal_over";

  if (hidden || !cards) {
    const n = counts?.[seat] || cards?.length || 0;
    for (let i = 0; i < n; i += 1) {
      const back = document.createElement("div");
      back.className = "card-back";
      root.appendChild(back);
    }
    return;
  }

  for (const group of groupCards(cards)) {
    const wrap = document.createElement("div");
    wrap.className = "suit-group";
    for (const card of group) {
      const playable = canClick && legal.has(card.id);
      const node = cardNode(card, playable ? "legal" : "");
      if (playable) node.addEventListener("click", () => sendMove({ type: "play", card: card.id }));
      wrap.appendChild(node);
    }
    root.appendChild(wrap);
  }
}

function render() {
  if (!state) return;
  els.deal.textContent = state.deal_number;
  els.score.textContent = state.score;
  els.dealChip.textContent = state.deal_number;
  els.scoreChip.textContent = state.score;
  const rulesLine = document.getElementById("rules-line");
  if (rulesLine) {
    rulesLine.innerHTML =
      state.rules === "minibridge"
        ? "MiniBridge: pick trump and a goal · <b>As</b> <b>*h</b> <b>#9</b>"
        : "Auction: <b>1H</b> <b>1NT</b> <b>P</b> <b>X</b> · play <b>NAs</b> · dummy after the lead";
  }
  const rulesSel = document.getElementById("cfg-rules");
  if (rulesSel && state.rules) rulesSel.value = state.rules;
  els.contract.textContent = state.contract
    ? `${pretty(state.contract)} by ${state.declarer} · NS ${state.tricks_ns}  EW ${state.tricks_ew}`
    : state.phase === "auction"
      ? `${state.dealer || "N"} deals · ${state.vulnerability || "none"} vul`
      : `NS ${state.hcp_ns} HCP · EW ${state.hcp_ew} HCP`;
  if (els.scoresheet) {
    els.scoresheet.textContent = state.scoresheet || "…";
  }

  for (const seat of state.seats || []) {
    const el = document.getElementById(`label-${seat.seat.toLowerCase()}`);
    el.classList.toggle("active", Boolean(seat.to_act));
    const role = seat.is_declarer ? "Declarer" : seat.is_dummy ? "Dummy" : seat.label;
    const kind = seat.kind && seat.kind !== "human" ? ` · ${seat.kind}` : "";
    el.innerHTML = `<b>${seat.seat}</b> ${role}${kind}`;
  }

  for (const seat of ["N", "E", "S", "W"]) {
    fillHand(seat, state.hands?.[seat], state.hand_counts);
  }

  if (state.phase === "auction") {
    els.status.hidden = false;
    els.status.innerHTML = `
      <div><strong>Auction</strong> · ${state.dealer} deals · ${state.vulnerability} vul</div>
      <div>${
        isHumanTurn()
          ? "Your call — use the bidding box"
          : `${state.to_act} to call`
      }</div>`;
  } else if (state.phase === "play") {
    els.status.hidden = false;
    const dummy = state.to_act === state.dummy && isHumanTurn();
    els.status.innerHTML = `
      <div><strong>${pretty(state.contract)}</strong> · NS ${state.tricks_ns} &nbsp; EW ${state.tricks_ew}</div>
      <div>${
        dummy
          ? "Play dummy — click a highlighted card"
          : isHumanTurn()
            ? "Your turn — click a highlighted card"
            : state.waiting_for?.kind === "llm"
              ? `Waiting for ${state.waiting_for.controller} (LLM). POST a text move to /api/games/table/step`
              : `${state.to_act} to play`
      }</div>`;
  } else {
    els.status.hidden = true;
  }

  const plays = state.current_trick?.length ? state.current_trick : (showCompleted ? state.last_trick : []);
  els.trick.innerHTML = "";
  for (const play of plays || []) {
    const wrap = document.createElement("div");
    wrap.className = "played";
    wrap.dataset.seat = play.seat;
    wrap.appendChild(cardNode(play.card));
    els.trick.appendChild(wrap);
  }

  const overlay = els.overlay;
  if (state.phase === "auction" && isHumanTurn()) {
    const legal = new Set(state.legal_action_labels || []);
    const strains = [
      ["C", "♣"],
      ["D", "♦"],
      ["H", "♥"],
      ["S", "♠"],
      ["NT", "NT"],
    ];
    const rows = [1, 2, 3, 4, 5, 6, 7]
      .map((level) => {
        const buttons = strains
          .map(([strain, label]) => {
            const token = `${level}${strain}`;
            const on = legal.has(token);
            return `<button class="bid" data-call="${token}" ${on ? "" : "disabled"}>${level}${label}</button>`;
          })
          .join("");
        return `<div class="bid-row">${buttons}</div>`;
      })
      .join("");
    overlay.hidden = false;
    overlay.innerHTML = `
      <h3>Your call</h3>
      <div class="bid-box">${rows}</div>
      <div class="choices">
        <button data-call="P" ${legal.has("P") ? "" : "disabled"}>Pass</button>
        <button data-call="X" ${legal.has("X") ? "" : "disabled"}>X</button>
        <button data-call="XX" ${legal.has("XX") ? "" : "disabled"}>XX</button>
      </div>
      <p class="muted">${state.dealer} deals · ${state.vulnerability} vul · HCP ${state.hcp?.[humanSeat()] ?? ""}</p>`;
    overlay.querySelectorAll("[data-call]").forEach((btn) => {
      if (btn.disabled) return;
      btn.addEventListener("click", () => sendMove({ type: "bid", call: btn.dataset.call }));
    });
    return;
  }
  if (state.phase === "select_trump" && isHumanTurn()) {
    overlay.hidden = false;
    overlay.innerHTML = `
      <h3>Select your trump suit</h3>
      <div class="choices">
        <button data-trump="C">♣</button>
        <button data-trump="D">♦</button>
        <button data-trump="H">♥</button>
        <button data-trump="S">♠</button>
        <button data-trump="NT">NT</button>
      </div>
      <p class="muted">NS ${state.hcp_ns} HCP · EW ${state.hcp_ew} HCP · Declarer ${state.declarer}</p>`;
    overlay.querySelectorAll("[data-trump]").forEach((btn) => {
      btn.addEventListener("click", () => sendMove({ type: "trump", trump: btn.dataset.trump }));
    });
    return;
  }
  if (state.phase === "select_goal" && isHumanTurn()) {
    overlay.hidden = false;
    overlay.innerHTML = `
      <h3>Select trick goal</h3>
      <div class="choices">${[7, 8, 9, 10, 11, 12, 13].map((n) => `<button data-goal="${n}">${n}</button>`).join("")}</div>
      <p class="muted">Trump ${SUIT_SYMBOL[state.trump] || state.trump}. Bonuses start at 9 tricks.</p>`;
    overlay.querySelectorAll("[data-goal]").forEach((btn) => {
      btn.addEventListener("click", () => sendMove({ type: "goal", goal: Number(btn.dataset.goal) }));
    });
    return;
  }
  if (state.phase === "deal_over" && state.deal_result) {
    const result = state.deal_result;
    overlay.hidden = false;
    overlay.innerHTML = result.passed_out
      ? `<h3>Passed out</h3>
      <div class="scoreline">0</div>
      <p class="muted">${result.vulnerability || ""} vul · ${result.dealer || ""} dealt</p>
      <button class="primary" id="next-deal">Next deal</button>`
      : `<h3>${pretty(result.contract)} by ${result.declarer} ${result.made ? "made" : "down"}</h3>
      <div class="scoreline">${result.ns_points >= 0 ? "+" : ""}${result.ns_points}</div>
      <p class="muted">NS ${result.tricks_ns} tricks · EW ${result.tricks_ew} tricks · bonus ${result.bonus}</p>
      <button class="primary" id="next-deal">Next deal</button>`;
    document.getElementById("next-deal").addEventListener("click", () => resetDeal());
    return;
  }
  overlay.hidden = true;
  overlay.innerHTML = "";
}

async function sendMove(body) {
  if (busy) return;
  busy = true;
  const prev = state?.tricks_played || 0;
  try {
    state = await api(`/api/games/${GAME_ID}/step`, { method: "POST", body: JSON.stringify(body) });
    const doneTrick = state.tricks_played > prev && !(state.current_trick || []).length;
    if (doneTrick) {
      showCompleted = true;
      render();
      await new Promise((resolve) => setTimeout(resolve, 650));
      showCompleted = false;
    }
    render();
  } catch (error) {
    els.overlay.hidden = false;
    els.overlay.innerHTML = `<h3>Illegal move</h3><p class="muted">${error.message}</p>`;
  } finally {
    busy = false;
  }
}

async function resetDeal() {
  state = await api(`/api/games/${GAME_ID}/reset`, {
    method: "POST",
    body: JSON.stringify({ new_match: false }),
  });
  render();
}

document.getElementById("new-deal").addEventListener("click", resetDeal);
document.getElementById("cfg-rules").addEventListener("change", () => {
  document.getElementById("cfg-apply").click();
});

document.getElementById("cfg-apply").addEventListener("click", async () => {
  state = await api(`/api/games/${GAME_ID}/config`, {
    method: "POST",
    body: JSON.stringify({
      rules: document.getElementById("cfg-rules").value,
      partner: document.getElementById("cfg-partner").value,
      opponents: document.getElementById("cfg-opponents").value,
      llm_model: document.getElementById("cfg-model").value,
      llm_base_url: document.getElementById("cfg-url").value,
      llm_api_key: document.getElementById("cfg-key").value,
    }),
  });
  render();
});

setInterval(async () => {
  if (busy || !state || isHumanTurn() || state.phase === "deal_over") return;
  try {
    state = await api(`/api/games/${GAME_ID}`);
    render();
  } catch {
    /* keep last frame */
  }
}, 1500);

api(`/api/games/${GAME_ID}`)
  .then((data) => { state = data; render(); })
  .catch((error) => {
    els.overlay.hidden = false;
    els.overlay.innerHTML = `<h3>Could not load the table</h3><p class="muted">${error.message}</p>`;
  });
