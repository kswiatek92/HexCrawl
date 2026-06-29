import { useGameStore } from "../store/gameStore";
import GameCanvas from "../render/GameCanvas";
import { useGameSocket } from "../net/useGameSocket";
import { useKeyboardInput } from "../input/useKeyboardInput";

export default function GameScreen() {
  const status = useGameStore((s) => s.status);
  const gameState = useGameStore((s) => s.gameState);

  // The full input→socket→store path is wired here: `useGameSocket` writes
  // `gameState` as turn frames arrive (the renderer reads it below), and
  // `useKeyboardInput` drives the loop the other way — WASD/arrows/space →
  // `sendAction`. Both are dormant for now: the socket needs a session id (from
  // start-game) and a JWT (from Supabase auth), both later in Phase 5, so with
  // `null` params it never connects and keystrokes no-op until then.
  const { sendAction } = useGameSocket({ sessionId: null, token: null });
  useKeyboardInput(sendAction);

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
