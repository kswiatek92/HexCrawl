import { useGameStore } from "../store/gameStore";

export default function GameScreen() {
  const status = useGameStore((s) => s.status);

  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-bold">HexCrawl</h1>
      <p className="text-slate-400">
        Connection status: <span data-testid="conn-status">{status}</span>
      </p>
    </section>
  );
}
