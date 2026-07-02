import { useGameStore } from "../store/gameStore";
import GameCanvas from "../render/GameCanvas";
import Hud from "../hud/Hud";
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
  // `null` params it never connects. The keyboard handler is gated on a live
  // connection (`status === "open"`), so until then no listener is attached and
  // keys pass straight through to the browser (no captured scroll, no no-op).
  const { sendAction } = useGameSocket({ sessionId: null, token: null });
  useKeyboardInput(sendAction, { enabled: status === "open" });

  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold">HexCrawl</h1>
      <p className="text-slate-400">
        Connection status: <span data-testid="conn-status">{status}</span>
      </p>
      {/* World + HUD side by side: the canvas flexes into the remaining width
          (its container is what the largest-fit integer scaling measures) and
          the HUD keeps its fixed rail. HTML over canvas, not drawn into it. */}
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <GameCanvas gameState={gameState} />
        </div>
        <Hud />
      </div>
    </section>
  );
}
