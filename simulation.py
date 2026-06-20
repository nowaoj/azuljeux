import csv
import random
from game import GameState, Color, COLOR_NAMES


class Simulator:
    def __init__(self, bot_p1, bot_p2):
        self.bots = [bot_p1, bot_p2]

    def run_games(self, n, seed=None, results_path=None, moves_path=None):
        results = []
        for game_id in range(n):
            actual_seed = seed + game_id if seed is not None else None
            if actual_seed is not None:
                random.seed(actual_seed)

            game = GameState()
            game.init_bag()
            game.start_round()
            move_log = []
            turn = 0

            while not game.game_over:
                player = game.current_player
                bot = self.bots[player]
                move = bot.choose_move(game, player)
                if move is None:
                    break

                scores_before = [game.players[0].score, game.players[1].score]
                move_log.append({
                    "turn": turn,
                    "player": player,
                    "move": move,
                    "scores_before": scores_before,
                })

                action_type, *args = move
                if action_type == "center":
                    _, _, color_val, line_val = move
                    args = (color_val, line_val)
                game.current_player_action(action_type, *args)
                turn += 1

                if game.phase == "wall_tiling":
                    game.resolve_wall_tiling()

            snapshot = game.get_state_snapshot()
            result = {
                "game_id": game_id,
                "seed": actual_seed,
                "bot1": self.bots[0].name,
                "bot2": self.bots[1].name,
                "score1": snapshot["players"][0]["score"],
                "score2": snapshot["players"][1]["score"],
                "bonus1": bonus_str(snapshot["players"][0]),
                "bonus2": bonus_str(snapshot["players"][1]),
                "winner": snapshot["winner"],
                "rounds": snapshot["round"],
                "total_turns": turn,
            }
            results.append((result, move_log if moves_path else None))

            self._print_progress(game_id, n, result)

        self._export_results(results_path, results)
        self._export_moves(moves_path, results)
        return results

    def _print_progress(self, game_id, total, result):
        if total <= 1:
            return
        w = "P1" if result["winner"] == 0 else "P2" if result["winner"] == 1 else "Tie"
        print(f"[{game_id + 1}/{total}] R{result['rounds']} | "
              f"{result['score1']}-{result['score2']} | {w}")

    def _export_results(self, path, results):
        if not path:
            return
        with open(path, "w", newline="") as f:
            fields = ["game_id", "seed", "bot1", "bot2",
                       "score1", "score2", "bonus1", "bonus2",
                       "winner", "rounds", "total_turns"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r, _ in results:
                w.writerow(r)
        print(f"Results saved to {path}")

    def _export_moves(self, path, results):
        if not path:
            return
        with open(path, "w", newline="") as f:
            fields = ["game_id", "turn", "player", "action_type",
                       "source_idx", "color", "line_idx",
                       "score_p1_before", "score_p2_before"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r, moves in results:
                if moves is None:
                    continue
                gid = r["game_id"]
                for m in moves:
                    atype, sidx, color, line = m["move"]
                    w.writerow({
                        "game_id": gid,
                        "turn": m["turn"],
                        "player": m["player"],
                        "action_type": atype,
                        "source_idx": sidx,
                        "color": COLOR_NAMES.get(color, str(color)),
                        "line_idx": line,
                        "score_p1_before": m["scores_before"][0],
                        "score_p2_before": m["scores_before"][1],
                    })
        print(f"Moves saved to {path}")


def bonus_str(b):
    parts = []
    if b["bonus_rows"] > 0:
        parts.append(f"+{b['bonus_rows'] * 2}")
    if b["bonus_cols"] > 0:
        parts.append(f"+{b['bonus_cols'] * 7}")
    if b["bonus_colors"] > 0:
        parts.append(f"+{b['bonus_colors'] * 10}")
    return f"({''.join(parts) if parts else '+0'})"


def run():
    from bots import GreedyBot, PlannedBot, RandomBot

    N = 100
    SEED = 42

    print("=== Reedy vs Random ===")
    sim = Simulator(GreedyBot(), RandomBot())
    sim.run_games(N, seed=SEED,
                  results_path="results_greedy_vs_random.csv",
                  moves_path="moves_greedy_vs_random.csv")

    print("\n=== Planned vs Random ===")
    sim2 = Simulator(PlannedBot(), RandomBot())
    sim2.run_games(N, seed=SEED + N,
                   results_path="results_planned_vs_random.csv",
                   moves_path="moves_planned_vs_random.csv")

    print("\n=== Reedy vs Planned ===")
    sim3 = Simulator(GreedyBot(), PlannedBot())
    sim3.run_games(N, seed=SEED + 2 * N,
                   results_path="results_greedy_vs_planned.csv",
                   moves_path="moves_greedy_vs_planned.csv")

    print("\nDone.")


if __name__ == "__main__":
    run()
