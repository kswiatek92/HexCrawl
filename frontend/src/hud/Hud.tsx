/**
 * The HUD (task 5.8) — HP, floor, run stats, inventory, and protocol errors.
 *
 * **HTML over canvas, not drawn into it** (QUIZZES 5.8 Q3): the 240×160 backing
 * buffer is for the world; UI text drawn there would be blurry at scale and
 * invisible to accessibility tooling. DOM elements get browser layout, crisp
 * text, and testability for free — the right trade for a backend-focused
 * portfolio app.
 *
 * Reads the store directly via selectors (no props), so it subscribes
 * independently of `GameScreen` and re-renders only when the slices it reads
 * change — the same decoupling the canvas gets from `gameState`.
 *
 * Two deliberate gaps, mirroring the backend's v1 scope:
 *  - **No live score.** Score is computed once at game over (`SubmitScore`);
 *    `damage_taken` never crosses the wire, so a client-side figure would lie.
 *    The HUD shows the score *inputs* the player controls: floor, kills, turns.
 *  - **Inventory is structural only.** `PickUp`/`UseItem` are
 *    `not_implemented_v1` server-side and `PlayerState` carries no inventory,
 *    so the slot grid renders empty today; slots already know how to paint an
 *    item icon (via the 5.5a `ITEM_URLS` registry), so the panel lights up the
 *    day the backend field ships.
 */

import { useGameStore } from "../store/gameStore";
import { ITEM_URLS } from "../render/itemSprites";
import {
  INVENTORY_SLOT_COUNT,
  hpBarColorClass,
  type InventoryItem,
} from "./hudModel";

/**
 * The player's carried items. Always empty in v1 — see the module docstring.
 * Kept as a named constant (not an inline `[]`) so the seam the backend field
 * will replace is explicit.
 */
const INVENTORY: readonly InventoryItem[] = [];

function InventorySlot({ item }: { item: InventoryItem | undefined }) {
  return (
    <div
      data-testid="hud-inventory-slot"
      className="flex h-10 w-10 items-center justify-center rounded border border-slate-700 bg-slate-800"
    >
      {item && (
        <img
          src={ITEM_URLS[item.item_type]}
          alt={item.item_type.toLowerCase()}
          className="h-8 w-8"
          style={{ imageRendering: "pixelated" }}
        />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-400">{label}</dt>
      <dd
        data-testid={`hud-${label.toLowerCase()}`}
        className="font-mono text-slate-100"
      >
        {value}
      </dd>
    </div>
  );
}

export default function Hud() {
  const gameState = useGameStore((s) => s.gameState);
  const kills = useGameStore((s) => s.kills);
  const lastError = useGameStore((s) => s.lastError);

  if (gameState === null) {
    // Dormant, like the rest of the turn loop before start-game + auth (5.11/5.12).
    return (
      <aside
        data-testid="hud"
        className="w-56 rounded border border-slate-700 bg-slate-800/50 p-4 text-sm text-slate-500"
      >
        No active run.
      </aside>
    );
  }

  const { player, current_floor_index, turn_count } = gameState;
  const hpPercent =
    player.max_hp > 0
      ? Math.max(0, Math.min(100, (player.hp / player.max_hp) * 100))
      : 0;

  return (
    <aside
      data-testid="hud"
      className="w-56 space-y-4 rounded border border-slate-700 bg-slate-800/50 p-4 text-sm"
    >
      <header className="font-semibold text-slate-100">{player.name}</header>

      <div className="space-y-1">
        <div className="flex justify-between">
          <span className="text-slate-400">HP</span>
          <span data-testid="hud-hp" className="font-mono text-slate-100">
            {player.hp}/{player.max_hp}
          </span>
        </div>
        <div
          className="h-2.5 overflow-hidden rounded bg-slate-700"
          role="meter"
          aria-label="HP"
          aria-valuenow={player.hp}
          aria-valuemin={0}
          aria-valuemax={player.max_hp}
        >
          <div
            data-testid="hud-hp-bar"
            className={`h-full ${hpBarColorClass(player.hp, player.max_hp)}`}
            style={{ width: `${hpPercent}%` }}
          />
        </div>
      </div>

      <dl className="space-y-1">
        {/* 0-based engine index → 1-based display, the leaderboard convention. */}
        <Stat label="Floor" value={current_floor_index + 1} />
        <Stat label="Turns" value={turn_count} />
        <Stat label="Kills" value={kills} />
        <Stat label="ATK" value={player.attack} />
        <Stat label="DEF" value={player.defense} />
      </dl>

      <div className="space-y-1">
        <h2 className="text-slate-400">Inventory</h2>
        <div className="grid grid-cols-3 gap-1">
          {Array.from({ length: INVENTORY_SLOT_COUNT }, (_, i) => (
            <InventorySlot key={i} item={INVENTORY[i]} />
          ))}
        </div>
      </div>

      {lastError !== null && (
        <p data-testid="hud-error" className="text-xs text-amber-400">
          {lastError}
        </p>
      )}
    </aside>
  );
}
