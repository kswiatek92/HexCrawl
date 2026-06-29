import { useGameStore } from "../store/gameStore";
import GameCanvas from "../render/GameCanvas";

export default function GameScreen() {
  const status = useGameStore((s) => s.status);
  const gameState = useGameStore((s) => s.gameState);

  // `useGameSocket` writes `gameState` into the store as turn frames arrive;
  // the renderer reads it here. The hook isn't mounted live yet — it needs a
  // session id (from start-game) and a JWT (from Supabase auth), both later in
  // Phase 5 — so until then the store stays `null` and the viewport is empty.
  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold">HexCrawl</h1>
      <p className="text-slate-400">
        Connection status: <span data-testid="conn-status">{status}</span>
      </p>
      <GameCanvas gameState={gameState} />
    </section>
  );
}
