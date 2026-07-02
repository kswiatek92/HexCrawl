/**
 * Pure HUD model — constants and display math, no React.
 *
 * Split from `Hud.tsx` the same way `camera.ts` sits beside `GameCanvas.tsx`:
 * the component file exports only the component (fast-refresh friendly), and
 * the logic here is unit-testable without rendering.
 */

import type { ItemType } from "../types/gameState";

/** Slots in the inventory grid — a fixed rack, GBA-style, filled left to right. */
export const INVENTORY_SLOT_COUNT = 6;

/** One carried item, once the backend ships inventory on `PlayerState`. */
export interface InventoryItem {
  item_type: ItemType;
}

/** Bar colour by remaining HP: healthy → wounded → critical. */
export function hpBarColorClass(hp: number, maxHp: number): string {
  const ratio = maxHp > 0 ? hp / maxHp : 0;
  if (ratio > 0.5) return "bg-emerald-500";
  if (ratio > 0.25) return "bg-amber-500";
  return "bg-red-500";
}
