import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

from game import GameState
from bots import GreedyBot, PlannedBot, RandomBot
from azul.models import Simulation, Game, Move, Snapshot


BOT_CLASSES = {
    'GreedyBot': GreedyBot,
    'PlannedBot': PlannedBot,
    'RandomBot': RandomBot,
}


def _simulate_one(args):
    bot1_cls, bot2_cls, game_index, seed, hundred_point = args
    b1 = bot1_cls()
    b2 = bot2_cls()
    bots = [b1, b2]

    gs = GameState(seed=seed, hundred_point_rule=hundred_point)
    gs.start_round()

    moves_data = []
    snapshots_data = []

    turn = 0
    while not gs.game_over:
        cp = gs.current_player
        bot = bots[cp]
        move = bot.choose_move(gs, cp)

        if move is None and gs.phase == "wall_tiling":
            gs.resolve_wall_tiling()
            steps = getattr(gs, '_last_wall_steps', None)
            if steps:
                for step in steps:
                    snapshots_data.append({
                        'turn': turn,
                        'state_json': json.dumps(step['state']),
                        'action_desc': step.get('desc', step['type']),
                        'evaluations_json': None,
                        'step_data': step,
                    })
            else:
                snapshots_data.append({
                    'turn': turn,
                    'state_json': json.dumps(gs.get_state_snapshot()),
                    'action_desc': 'wall_tiling',
                    'evaluations_json': None,
                })
            continue

        if move is None:
            break

        sp1 = gs.players[0].score
        sp2 = gs.players[1].score
        evals = bot.last_evaluations
        evals_json = json.dumps(evals, default=str) if evals else None
        reason = bot.last_reason or ''

        gs.execute_move(cp, move.source_type, move.source_idx,
                         move.color, move.line_idx)

        bot_name = bot.__class__.__name__
        action_desc = '%s | %s: %s' % (
            '%s took from %s' % (
                bot_name,
                'F%d' % (move.source_idx + 1) if move.source_type == 'factory' else 'centre'
            ),
            bot_name,
            reason,
        )

        moves_data.append({
            'turn': turn, 'player': cp,
            'action_type': move.source_type,
            'source_idx': move.source_idx,
            'color': str(move.color.name),
            'line_idx': move.line_idx,
            'score_p1_before': sp1, 'score_p2_before': sp2,
        })

        snapshots_data.append({
            'turn': turn,
            'state_json': json.dumps(gs.get_state_snapshot()),
            'action_desc': action_desc,
            'evaluations_json': evals_json,
        })

        turn += 1

    # Compute floor penalties for each player by summing penalty values
    # from the floor line snapshots
    fp1 = 0
    fp2 = 0
    for s in snapshots_data:
        step = s.get('step_data') or {}
        if step.get('type') == 'floor':
            if step.get('player') == 0:
                fp1 += step.get('penalty', 0)
            else:
                fp2 += step.get('penalty', 0)

    return {
        'game_index': game_index,
        'seed': seed,
        'score1': gs.players[0].score,
        'score2': gs.players[1].score,
        'winner': gs.winner,
        'rounds': gs.round,
        'turns': turn,
        'rows1': gs.players[0].count_complete_rows(),
        'cols1': gs.players[0].count_complete_cols(),
        'colors1': gs.players[0].count_complete_colors(),
        'floor_penalty_p1': fp1,
        'rows2': gs.players[1].count_complete_rows(),
        'cols2': gs.players[1].count_complete_cols(),
        'colors2': gs.players[1].count_complete_colors(),
        'floor_penalty_p2': fp2,
        'moves': moves_data,
        'snapshots': snapshots_data,
    }


def run_simulation(sim_id):
    try:
        sim = Simulation.objects.get(id=sim_id)
    except Simulation.DoesNotExist:
        return

    b1_cls = BOT_CLASSES.get(sim.bot1_name)
    b2_cls = BOT_CLASSES.get(sim.bot2_name)
    if not b1_cls or not b2_cls:
        sim.status = 'failed'
        sim.save(update_fields=['status'])
        return

    sim.status = 'running'
    sim.save(update_fields=['status'])

    base_seed = sim.seed or random.randint(0, 999999)
    hundred_point = sim.hundred_point_rule
    args_list = [
        (b1_cls, b2_cls, i, base_seed + i, hundred_point)
        for i in range(sim.num_games)
    ]

    try:
        # Clean up any previous runs for this simulation
        Game.objects.filter(simulation=sim).delete()

        completed = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_simulate_one, a): a for a in args_list}
            for f in as_completed(futures):
                r = f.result()
                game = Game(
                    simulation=sim,
                    game_index=r['game_index'],
                    seed=r['seed'],
                    score1=r['score1'],
                    score2=r['score2'],
                    winner=r['winner'],
                    rounds=r['rounds'],
                    total_turns=r['turns'],
                    rows1=r['rows1'],
                    cols1=r['cols1'],
                    colors1=r['colors1'],
                    floor_penalty_p1=r['floor_penalty_p1'],
                    rows2=r['rows2'],
                    cols2=r['cols2'],
                    colors2=r['colors2'],
                    floor_penalty_p2=r['floor_penalty_p2'],
                )
                game.save()

                move_objs = [
                    Move(game=game, **m) for m in r['moves']
                ]
                Move.objects.bulk_create(move_objs)

                snap_objs = [
                    Snapshot(game=game, turn=s['turn'],
                              state_json=s['state_json'],
                              action_desc=s['action_desc'],
                              evaluations_json=s['evaluations_json'])
                    for s in r['snapshots']
                ]
                Snapshot.objects.bulk_create(snap_objs)

                completed += 1
                sim.games_completed = completed
                sim.save(update_fields=['games_completed'])

        sim.status = 'done'
        sim.save(update_fields=['status'])

    except Exception as exc:
        sim.status = 'failed'
        sim.save(update_fields=['status'])
        raise
