import { useGameStore } from "../store/gameStore";
import GameCanvas from "../render/GameCanvas";

export default function GameScreen() {
  const status = useGameStore((s) => s.status);

  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold">HexCrawl</h1>
      <p className="text-slate-400">
        Connection status: <span data-testid="conn-status">{status}</span>
      </p>
      {/* Live game state is fed in task 5.6 (useGameSocket); until then the
          renderer paints an empty viewport. */}
      <GameCanvas gameState={null} />
    </section>
  );
}
