import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Leaderboard from "./Leaderboard";
import type { LeaderboardEntry } from "../types/leaderboard";

/** A ranked row with plausible defaults; override what the test asserts on. */
const entry = (over?: Partial<LeaderboardEntry>): LeaderboardEntry => ({
  rank: 1,
  user_id: "a1b2c3d4-5e6f-7081-92a3-b4c5d6e7f809",
  value: 900,
  floors_reached: 3,
  kills: 12,
  computed_at: "2026-07-06T21:14:03Z",
  ...over,
});

/** A minimal fetch Response double — only what the hook reads. */
const okJson = (body: unknown): Response =>
  ({ ok: true, status: 200, json: () => Promise.resolve(body) }) as Response;

const httpError = (status: number): Response =>
  ({ ok: false, status, json: () => Promise.resolve({}) }) as Response;

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("Leaderboard", () => {
  it("shows the loading state while the request is in flight", () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // never settles
    render(<Leaderboard />);

    expect(screen.getByTestId("leaderboard-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("leaderboard-row")).not.toBeInTheDocument();
  });

  it("fetches the global board first and renders its entries", async () => {
    fetchMock.mockResolvedValue(
      okJson({
        period: "GLOBAL",
        entries: [
          entry(),
          entry({
            rank: 2,
            user_id: "deadbeef-0000-0000-0000-000000000000",
            value: 640,
            floors_reached: 2,
            kills: 7,
          }),
        ],
      }),
    );
    render(<Leaderboard />);

    const rows = await screen.findAllByTestId("leaderboard-row");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/leaderboard/global",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(rows).toHaveLength(2);
    // Values must come from the mocked payload, not markup defaults.
    expect(rows[0]).toHaveTextContent("a1b2c3d4");
    expect(rows[0]).toHaveTextContent("900");
    expect(rows[0]).toHaveTextContent("2026-07-06");
    expect(rows[1]).toHaveTextContent("deadbeef");
    expect(rows[1]).toHaveTextContent("640");
    expect(rows[1]).toHaveTextContent("7");
  });

  it("renders the empty state for a board with no scores", async () => {
    fetchMock.mockResolvedValue(okJson({ period: "GLOBAL", entries: [] }));
    render(<Leaderboard />);

    expect(await screen.findByTestId("leaderboard-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("leaderboard-row")).not.toBeInTheDocument();
  });

  it("renders the error state on an HTTP error and retries on demand", async () => {
    fetchMock
      .mockResolvedValueOnce(httpError(500))
      .mockResolvedValueOnce(okJson({ period: "GLOBAL", entries: [entry()] }));
    render(<Leaderboard />);

    expect(await screen.findByTestId("leaderboard-error")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByTestId("leaderboard-row")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("renders the error state when the network request rejects", async () => {
    fetchMock.mockRejectedValue(new TypeError("network down"));
    render(<Leaderboard />);

    expect(await screen.findByTestId("leaderboard-error")).toBeInTheDocument();
  });

  it("switches to the weekly board on tab click", async () => {
    fetchMock.mockImplementation((input) =>
      Promise.resolve(
        String(input).endsWith("/weekly")
          ? okJson({
              period: "WEEKLY",
              entries: [entry({ value: 123 })],
            })
          : okJson({ period: "GLOBAL", entries: [] }),
      ),
    );
    render(<Leaderboard />);
    await screen.findByTestId("leaderboard-empty");

    fireEvent.click(screen.getByRole("tab", { name: "Weekly" }));

    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/leaderboard/weekly",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByRole("tab", { name: "Weekly" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Global" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
    expect(await screen.findByTestId("leaderboard-row")).toHaveTextContent(
      "123",
    );
  });

  it("aborts the in-flight request on unmount", () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // stays in flight
    const { unmount } = render(<Leaderboard />);

    const init = fetchMock.mock.calls[0]?.[1];
    const signal = init?.signal;
    expect(signal?.aborted).toBe(false);

    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
