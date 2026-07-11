import { useGameStore } from "../store/gameStore";
import { useAuthStore } from "../auth/authStore";
import GameCanvas from "../render/GameCanvas";
import Hud from "../hud/Hud";
import GameOver from "../gameover/GameOver";
import { useGameSocket } from "../net/useGameSocket";
import { useStartGame, playerNameFromEmail } from "../net/useStartGame";
import { useKeyboardInput } from "../input/useKeyboardInput";

export default function GameScreen() {
  const status = useGameStore((s) => s.status);
  const gameState = useGameStore((s) => s.gameState);
  const resetRun = useGameStore((s) => s.resetRun);
  const session = useAuthStore((s) => s.session);
  const { request, start, reset } = useStartGame();

  // The full auth→run→socket chain (5.12): RequireAuth guarantees a session
  // here, "Start Run" POSTs /game/start with its bearer token, and the
  // returned game_id + the token bring the (previously dormant) socket up.
  // Both stay null until then, so the socket hook simply doesn't connect.
  const token = session?.access_token ?? null;
  const gameId = request.status === "started" ? request.gameId : null;

  const { sendAction } = useGameSocket({ sessionId: gameId, token });
  useKeyboardInput(sendAction, { enabled: status === "open" });

  const handleStart = () => {
    if (token === null) return; // unreachable behind RequireAuth; type-narrowing
    void start(token, playerNameFromEmail(session?.user.email));
  };

  // New Run = clear the finished run in both machines (store phase → idle,
  // request → idle, which also drops game_id and closes the old socket via
  // the effect cleanup), then mint a fresh run.
  const handleNewRun = () => {
    resetRun();
    reset();
    handleStart();
  };

  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold">HexCrawl</h1>
      <p className="text-slate-400">
        Connection status: <span data-testid="conn-status">{status}</span>
      </p>

      {/* The start-run controls render every request state explicitly (5.10
          doctrine); once a run is minted the world below takes over. */}
      {request.status === "idle" && (
        <button
          type="button"
          data-testid="start-run"
          onClick={handleStart}
          className="rounded bg-emerald-600 px-4 py-1.5 font-semibold text-white hover:bg-emerald-500"
        >
          Start Run
        </button>
      )}
      {request.status === "starting" && (
        <p data-testid="start-run-pending" className="text-slate-400">
          Starting run…
        </p>
      )}
      {request.status === "error" && (
        <div data-testid="start-run-error" className="space-y-2">
          <p className="text-amber-400">Could not start a run.</p>
          <button
            type="button"
            onClick={handleNewRun}
            className="rounded bg-slate-700 px-3 py-1 font-semibold text-slate-100 hover:bg-slate-600"
          >
            Retry
          </button>
        </div>
      )}

      {/* World + HUD side by side: the canvas flexes into the remaining width
          (its container is what the largest-fit integer scaling measures) and
          the HUD keeps its fixed rail. HTML over canvas, not drawn into it. */}
      <div className="flex items-start gap-4">
        {/* `relative` anchors the game-over overlay (5.9) over the world. */}
        <div className="relative min-w-0 flex-1">
          <GameCanvas gameState={gameState} />
          <GameOver onNewRun={handleNewRun} />
        </div>
        <Hud />
      </div>
    </section>
  );
}
