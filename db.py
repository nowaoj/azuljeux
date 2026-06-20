import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "azul.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot1_name TEXT NOT NULL,
            bot2_name TEXT NOT NULL,
            num_games INTEGER NOT NULL,
            seed INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simulation_id INTEGER NOT NULL,
            game_index INTEGER NOT NULL,
            seed INTEGER,
            score1 INTEGER NOT NULL,
            score2 INTEGER NOT NULL,
            winner INTEGER NOT NULL,
            rounds INTEGER NOT NULL,
            total_turns INTEGER NOT NULL,
            FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS moves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            turn INTEGER NOT NULL,
            player INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            source_idx INTEGER,
            color TEXT,
            line_idx INTEGER,
            score_p1_before INTEGER,
            score_p2_before INTEGER,
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            turn INTEGER NOT NULL,
            state_json TEXT NOT NULL,
            action_desc TEXT,
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()


def create_simulation(bot1_name, bot2_name, num_games, seed=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO simulations (bot1_name, bot2_name, num_games, seed) VALUES (?, ?, ?, ?)",
        (bot1_name, bot2_name, num_games, seed),
    )
    sim_id = cur.lastrowid
    conn.commit()
    conn.close()
    return sim_id


def insert_game(sim_id, game_index, seed, score1, score2, winner, rounds, total_turns):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO games (simulation_id, game_index, seed, score1, score2, winner, rounds, total_turns) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (sim_id, game_index, seed, score1, score2, winner, rounds, total_turns),
    )
    game_id = cur.lastrowid
    conn.commit()
    conn.close()
    return game_id


def insert_move(game_id, turn, player, action_type, source_idx, color, line_idx, score_p1_before, score_p2_before):
    conn = get_conn()
    conn.execute(
        "INSERT INTO moves (game_id, turn, player, action_type, source_idx, color, line_idx, score_p1_before, score_p2_before) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (game_id, turn, player, action_type, source_idx, color, line_idx, score_p1_before, score_p2_before),
    )
    conn.commit()
    conn.close()


def insert_snapshot(game_id, turn, state_json, action_desc):
    conn = get_conn()
    conn.execute(
        "INSERT INTO snapshots (game_id, turn, state_json, action_desc) VALUES (?, ?, ?, ?)",
        (game_id, turn, state_json, action_desc),
    )
    conn.commit()
    conn.close()


def get_simulations(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM simulations ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_simulation(sim_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM simulations WHERE id = ?", (sim_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_games(sim_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM games WHERE simulation_id = ? ORDER BY game_index", (sim_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_game(game_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_moves(game_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM moves WHERE game_id = ? ORDER BY turn", (game_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_snapshots(game_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM snapshots WHERE game_id = ? ORDER BY turn", (game_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dashboard_stats():
    conn = get_conn()
    total_sims = conn.execute("SELECT COUNT(*) FROM simulations").fetchone()[0]
    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    matchup = conn.execute(
        "SELECT bot1_name, bot2_name, COUNT(*) as cnt FROM simulations GROUP BY bot1_name, bot2_name ORDER BY cnt DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "total_simulations": total_sims,
        "total_games": total_games,
        "top_matchup": dict(matchup) if matchup else None,
    }


init_db()
