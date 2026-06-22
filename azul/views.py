import json
import uuid
import threading
import time
import random
import string
from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.conf import settings
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Profile, Simulation, Game, Move, Snapshot,
    PlayerGame, PlayerMove, PlayerSnapshot,
)
from .forms import RegisterForm, BotGameForm, PvPCreateForm, PvPJoinForm
from game import GameState, Color, WALL_LAYOUT, FLOOR_PENALTIES
from bots import (
    GreedyBot, PlannedBot, RandomBot, Move as BotMove,
    evaluate_move, get_legal_moves, get_legal_move_descriptions,
)

from .sim_runner import run_simulation as run_sim_async

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

BASE_DIR = Path(__file__).resolve().parent.parent

BOT_CHOICES = ['GreedyBot', 'PlannedBot', 'RandomBot']

COLOR_HEX = {
    Color.BLUE: '#0066CC', Color.YELLOW: '#FFCC00', Color.RED: '#CC3333',
    Color.BLACK: '#444444', Color.WHITE: '#DDDDDD',
}
COLOR_NAMES_MAP = {
    Color.BLUE: 'Blue', Color.YELLOW: 'Yellow', Color.RED: 'Red',
    Color.BLACK: 'Black', Color.WHITE: 'White',
}


# ── Active Games Manager ───────────────────────────────────────────

_active_games = {}
_active_games_lock = threading.Lock()
_next_game_id = 1


def _tile_images():
    ad = BASE_DIR / 'static' / 'assets'
    return {slug: (ad / ('%s.png' % slug)).exists()
            for slug in ['blue', 'yellow', 'red', 'black', 'white', 'start']}


def _assets_dir():
    return BASE_DIR / 'static' / 'assets'


def _create_bot(bot_name):
    if bot_name == 'GreedyBot':
        return GreedyBot()
    if bot_name == 'PlannedBot':
        return PlannedBot()
    if bot_name == 'RandomBot':
        return RandomBot()
    return None


def _run_bot_turn(game_data):
    game = game_data['game']
    new_snapshots = []

    while not game.game_over:
        if game.phase == "wall_tiling":
            game.resolve_wall_tiling()
            turn = len(game_data['moves'])
            for step in getattr(game, '_last_wall_steps', []):
                snap = {
                    'turn': turn,
                    'state_json': json.dumps(step['state']),
                    'action_desc': step.get('desc', step['type']),
                    'evaluations_json': None,
                    'step_data': step,
                }
                new_snapshots.append(snap)
                game_data['snapshots'].append(snap)
            continue

        cp = game.current_player
        bot = game_data.get('bot1') if cp == 0 else game_data.get('bot2')
        if bot is None:
            break

        move = bot.choose_move(game, cp)
        if move is None:
            break

        turn = len(game_data['moves'])
        evals_json = json.dumps(bot.last_evaluations, default=str) if bot.last_evaluations else None

        player_name = game_data.get('player1_name' if cp == 0 else 'player2_name', 'Player %d' % cp)
        action_desc = '%s: %s' % (player_name, bot.last_reason or 'chose a move')

        game.execute_move(cp, move.source_type, move.source_idx, move.color, move.line_idx)
        game_data['moves'].append(move)

        snap = {
            'turn': turn,
            'state_json': json.dumps(game.get_state_snapshot()),
            'action_desc': action_desc,
            'evaluations_json': evals_json,
        }
        new_snapshots.append(snap)
        game_data['snapshots'].append(snap)

        if game.game_over:
            break

        _notify_game_state(game_data.get('_game_id'))

    return new_snapshots


def _finish_active_game(game_id):
    global _active_games
    with _active_games_lock:
        gd = _active_games.pop(game_id, None)
    if gd is None:
        return

    game = gd['game']
    score1 = game.players[0].score
    score2 = game.players[1].score
    winner = game.winner
    rounds = game.round
    total_turns = len(gd['moves'])

    pg = PlayerGame.objects.get(id=gd['db_id'])
    pg.score1 = score1
    pg.score2 = score2
    pg.winner = winner
    pg.rounds = rounds
    pg.total_turns = total_turns
    pg.save(update_fields=['score1', 'score2', 'winner', 'rounds', 'total_turns'])

    snap_objs = [
        PlayerSnapshot(game=pg, turn=s['turn'], state_json=s['state_json'],
                        action_desc=s.get('action_desc', ''),
                        evaluations_json=s.get('evaluations_json'))
        for s in gd['snapshots']
    ]
    PlayerSnapshot.objects.bulk_create(snap_objs)


def _notify_game_state(game_id):
    with _active_games_lock:
        gd = _active_games.get(game_id)
    if gd is None:
        return
    status = gd.get('status', 'playing')
    game = gd['game']
    game_over = game.game_over
    if game_over:
        status = 'completed'
    state = {
        'status': status,
        'current_player': game.current_player,
        'game_over': game_over,
        'winner': game.winner,
        'current_turn': len(gd.get('moves', [])),
        'scores': [game.players[0].score, game.players[1].score],
        'player2_present': gd.get('player2_name') is not None,
    }
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f'game_{game_id}',
            {'type': 'game_update', 'data': state},
        )


# ── Helper: build board render data ────────────────────────────────

def _build_board_data(game, my_player_idx, game_data):
    gd = game_data
    game = gd['game']
    my_name = gd['player1_name'] if my_player_idx == 0 else (gd['player2_name'] or 'Player 2')
    opp_name = gd['player2_name'] if my_player_idx == 0 else gd['player1_name']
    player_names = [gd['player1_name'], gd['player2_name'] or 'Waiting\u2026']
    is_my_turn = (game.current_player == my_player_idx and not game.game_over)

    bot_thinking = False
    if gd['mode'] == 'pve' and not game.game_over:
        cp = game.current_player
        if (cp == 0 and gd.get('bot1')) or (cp == 1 and gd.get('bot2')):
            bot_thinking = True

    legal_moves = []
    if is_my_turn:
        legal_moves = get_legal_move_descriptions(game, my_player_idx)

    factories = []
    for fi, f in enumerate(game.factories):
        if f:
            factories.append({
                'label': 'F%d' % (fi + 1),
                'tiles': [{'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]}
                          for t in f if isinstance(t, Color)],
            })
    center_tiles = [
        {'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]}
        for t in game.center if isinstance(t, Color)
    ]
    has_start = 'START' in game.center

    pattern_lines = []
    for pi in range(2):
        rows = []
        for li, pl in enumerate(game.players[pi].pattern_lines):
            row = [{'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]} for t in pl]
            rows.append({'index': li, 'max': li + 1, 'tiles': row, 'empty': (li + 1) - len(pl)})
        pattern_lines.append(rows)

    wall = []
    wall_bonuses = []
    for pi in range(2):
        rows = []
        for r in range(5):
            row = []
            row_complete = True
            for c in range(5):
                placed = game.players[pi].wall[r][c] is not None
                row_complete = row_complete and placed
                row.append({
                    'target': COLOR_NAMES_MAP[WALL_LAYOUT[r][c]],
                    'hex': COLOR_HEX[WALL_LAYOUT[r][c]],
                    'placed': placed,
                })
            rows.append({'cells': row, 'complete': row_complete})
        wall.append(rows)
        col_complete = [
            game.players[pi].is_col_complete(c) for c in range(5)
        ]
        color_complete = [
            game.players[pi].is_color_complete(c) for c in Color
        ]
        wall_bonuses.append({
            'col_complete': col_complete,
            'color_complete': color_complete,
            'rows': game.players[pi].count_complete_rows(),
            'cols': game.players[pi].count_complete_cols(),
            'colors': game.players[pi].count_complete_colors(),
            'color_detail': [
                {'name': COLOR_NAMES_MAP[c], 'hex': COLOR_HEX[c],
                 'complete': color_complete[i]}
                for i, c in enumerate(Color)
            ],
        })

    floor_lines = []
    for pi in range(2):
        floor_lines.append([
            {'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]} if isinstance(t, Color)
            else {'name': 'START', 'hex': '#888888'}
            for t in game.players[pi].floor_line
        ])

    return {
        'game_id': gd.get('_game_id'),
        'p': my_player_idx,
        'mode': gd['mode'],
        'game_over': game.game_over,
        'winner': game.winner,
        'round': game.round,
        'current_player': game.current_player,
        'is_my_turn': is_my_turn,
        'my_name': my_name,
        'opp_name': opp_name,
        'player_names': player_names,
        'scores': [game.players[0].score, game.players[1].score],
        'bot_thinking': bot_thinking,
        'legal_moves': legal_moves,
        'legal_moves_json': json.dumps(legal_moves),
        'factories': factories,
        'center_tiles': center_tiles,
        'has_start': has_start,
        'pattern_lines': pattern_lines,
        'wall': wall,
        'wall_bonuses': wall_bonuses,
        'floor_lines': floor_lines,
        'bag_tiles': [{'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]}
                      for t in (game.bag if hasattr(game, 'bag') else [])],
        'lid_tiles': [{'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]}
                      for t in (game.lid if hasattr(game, 'lid') else [])],
        'tile_images_json': json.dumps(_tile_images()),
        'other_player': 1 if my_player_idx == 0 else 0,
    }


# ═════════════════════════════════════════════════════════════════════
# Auth views
# ═════════════════════════════════════════════════════════════════════

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.create(user=user)
            login(request, user)
            messages.success(request, 'Account created!')
            return redirect('/')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('/')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('/')


@login_required
def profile(request):
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    games_p1 = PlayerGame.objects.filter(player1=user).order_by('-created_at')[:20]
    games_p2 = PlayerGame.objects.filter(player2=user).order_by('-created_at')[:20]
    all_games = list(games_p1) + list(games_p2)
    all_games.sort(key=lambda g: g.created_at, reverse=True)
    all_games = all_games[:20]
    total = profile.games_played or len(all_games)
    won = profile.games_won
    return render(request, 'registration/profile.html', {
        'profile': profile,
        'recent_games': all_games,
        'total_games': total,
        'games_won': won,
    })


# ═════════════════════════════════════════════════════════════════════
# Dashboard
# ═════════════════════════════════════════════════════════════════════

def index(request):
    total_sims = Simulation.objects.count()
    total_games = Game.objects.count()
    total_player_games = PlayerGame.objects.count()
    top_matchup = None
    from django.db.models import Count
    matchup_qs = Simulation.objects.values('bot1_name', 'bot2_name').annotate(
        cnt=Count('id')).order_by('-cnt')
    if matchup_qs:
        top_matchup = matchup_qs.first()

    stats = {
        'total_simulations': total_sims,
        'total_games': total_games + total_player_games,
        'total_player_games': total_player_games,
        'top_matchup': top_matchup,
    }
    sims = Simulation.objects.all()[:20]
    return render(request, 'index.html', {
        'stats': stats,
        'simulations': sims,
        'bot_choices': BOT_CHOICES,
    })


# ═════════════════════════════════════════════════════════════════════
# Simulations
# ═════════════════════════════════════════════════════════════════════

def run_form(request):
    return render(request, 'run.html', {'bot_choices': BOT_CHOICES})


def run_submit(request):
    if request.method == 'POST':
        bot1 = request.POST.get('bot1')
        bot2 = request.POST.get('bot2')
        num_games = int(request.POST.get('num_games', 100))
        seed = request.POST.get('seed') or None
        if seed is not None:
            seed = int(seed)
        hundred_point = request.POST.get('hundred_point') == 'on'
        sim = Simulation.objects.create(
            bot1_name=bot1, bot2_name=bot2,
            num_games=num_games, seed=seed,
            hundred_point_rule=hundred_point,
            status='pending',
        )
        # Run async in thread
        import threading as _t
        _t.Thread(target=run_sim_async, args=(sim.id,), daemon=True).start()
        return redirect('/simulations/%d/' % sim.id)
    return redirect('/run/')


def simulations_list(request):
    sims = Simulation.objects.all()[:100]
    return render(request, 'simulations.html', {'simulations': sims})


def simulation_detail(request, sim_id):
    sim = get_object_or_404(Simulation, id=sim_id)
    games = list(sim.games.all())

    total = len(games)
    wins1 = sum(1 for g in games if g.winner == 0)
    wins2 = sum(1 for g in games if g.winner == 1)
    draws = total - wins1 - wins2
    scores1 = [g.score1 for g in games]
    scores2 = [g.score2 for g in games]
    mean1 = sum(scores1) / total if total else 0
    mean2 = sum(scores2) / total if total else 0
    rounds_list = [g.rounds for g in games]
    mean_rounds = sum(rounds_list) / total if total else 0

    # Richer stats
    rows1_list = [g.rows1 for g in games]
    cols1_list = [g.cols1 for g in games]
    colors1_list = [g.colors1 for g in games]
    fp1_list = [g.floor_penalty_p1 for g in games]
    rows2_list = [g.rows2 for g in games]
    cols2_list = [g.cols2 for g in games]
    colors2_list = [g.colors2 for g in games]
    fp2_list = [g.floor_penalty_p2 for g in games]

    mean_rows1 = sum(rows1_list) / total if total else 0
    mean_cols1 = sum(cols1_list) / total if total else 0
    mean_colors1 = sum(colors1_list) / total if total else 0
    mean_fp1 = sum(fp1_list) / total if total else 0
    mean_rows2 = sum(rows2_list) / total if total else 0
    mean_cols2 = sum(cols2_list) / total if total else 0
    mean_colors2 = sum(colors2_list) / total if total else 0
    mean_fp2 = sum(fp2_list) / total if total else 0

    score_dist = {}
    for s in scores1 + scores2:
        bucket = (s // 10) * 10
        score_dist[bucket] = score_dist.get(bucket, 0) + 1
    max_count = max(score_dist.values()) if score_dist else 1
    dist_buckets = sorted(score_dist.items())

    hist_bars = []
    for bucket, count in dist_buckets:
        pct = round(count / max_count * 100, 0) if max_count else 0
        hist_bars.append({
            'label': '%d-%d' % (bucket, bucket + 9),
            'count': count,
            'pct': pct,
        })

    winrate1 = round(wins1 / total * 100, 1) if total else 0
    winrate2 = round(wins2 / total * 100, 1) if total else 0
    drawrate = round(draws / total * 100, 1) if total else 0

    return render(request, 'result.html', {
        'sim': sim, 'games': games,
        'total': total, 'wins1': wins1, 'wins2': wins2, 'draws': draws,
        'winrate1': winrate1, 'winrate2': winrate2, 'drawrate': drawrate,
        'mean1': round(mean1, 1), 'mean2': round(mean2, 1),
        'mean_rounds': round(mean_rounds, 1),
        'mean_rows1': round(mean_rows1, 1),
        'mean_cols1': round(mean_cols1, 1),
        'mean_colors1': round(mean_colors1, 1),
        'mean_fp1': round(mean_fp1, 1),
        'mean_rows2': round(mean_rows2, 1),
        'mean_cols2': round(mean_cols2, 1),
        'mean_colors2': round(mean_colors2, 1),
        'mean_fp2': round(mean_fp2, 1),
        'hist_bars': hist_bars,
        'sim_status': sim.status,
        'num_games': sim.num_games,
    })


@require_GET
def simulation_progress(request, sim_id):
    sim = get_object_or_404(Simulation, id=sim_id)
    games = list(sim.games.all())
    total = len(games)
    wins1 = sum(1 for g in games if g.winner == 0)
    wins2 = sum(1 for g in games if g.winner == 1)
    draws = total - wins1 - wins2
    scores1 = [g.score1 for g in games]
    scores2 = [g.score2 for g in games]
    mean1 = sum(scores1) / total if total else 0
    mean2 = sum(scores2) / total if total else 0
    winrate1 = round(wins1 / total * 100, 1) if total else 0
    winrate2 = round(wins2 / total * 100, 1) if total else 0
    drawrate = round(draws / total * 100, 1) if total else 0
    games_data = [{
        'id': g.id,
        'game_index': g.game_index,
        'score1': g.score1,
        'score2': g.score2,
        'winner': g.winner,
        'rounds': g.rounds,
        'total_turns': g.total_turns,
        'rows1': g.rows1,
        'cols1': g.cols1,
        'colors1': g.colors1,
        'floor_penalty_p1': g.floor_penalty_p1,
        'rows2': g.rows2,
        'cols2': g.cols2,
        'colors2': g.colors2,
        'floor_penalty_p2': g.floor_penalty_p2,
    } for g in games]
    return JsonResponse({
        'status': sim.status,
        'games_completed': total,
        'num_games': sim.num_games,
        'wins1': wins1,
        'wins2': wins2,
        'draws': draws,
        'winrate1': winrate1,
        'winrate2': winrate2,
        'drawrate': drawrate,
        'mean1': round(mean1, 1),
        'mean2': round(mean2, 1),
        'games': games_data,
    })


@require_POST
def simulation_delete(request, sim_id):
    sim = get_object_or_404(Simulation, id=sim_id)
    sim.delete()
    return redirect('/simulations/')


@require_POST
def game_delete(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    sim_id = game.simulation_id
    game.delete()
    return redirect('/simulations/%d/' % sim_id)


def game_replay(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    sim = game.simulation
    snapshots_raw = list(game.snapshots.all())
    snapshots = []
    for snap in snapshots_raw:
        s = {
            'turn': snap.turn,
            'state_json': snap.state_json,
            'action_desc': snap.action_desc or '',
            'evaluations': [],
        }
        if snap.evaluations_json:
            s['evaluations'] = json.loads(snap.evaluations_json)
        snapshots.append(s)
    return render(request, 'replay.html', {
        'game': game,
        'bot1_name': sim.bot1_name,
        'bot2_name': sim.bot2_name,
        'snapshots_json': json.dumps(snapshots),
        'total_steps': len(snapshots),
        'tile_images_json': json.dumps(_tile_images()),
    })


def player_game_replay(request, game_id):
    pg = get_object_or_404(PlayerGame, id=game_id)
    snapshots_raw = pg.snapshots.all()
    snapshots = []
    for snap in snapshots_raw:
        s = {
            'turn': snap.turn,
            'state_json': snap.state_json,
            'action_desc': snap.action_desc or '',
            'evaluations': [],
        }
        if snap.evaluations_json:
            s['evaluations'] = json.loads(snap.evaluations_json)
        snapshots.append(s)
    return render(request, 'replay.html', {
        'game': None,
        'bot1_name': pg.player1_name,
        'bot2_name': pg.player2_name or '',
        'snapshots_json': json.dumps(snapshots),
        'total_steps': len(snapshots),
        'tile_images_json': json.dumps(_tile_images()),
    })


# ═════════════════════════════════════════════════════════════════════
# Bot Guide
# ═════════════════════════════════════════════════════════════════════

def _build_example_state():
    gs = GameState()
    gs.factories = [
        [Color.BLUE, Color.BLUE, Color.RED, Color.YELLOW],
        [Color.RED, Color.RED, Color.RED, Color.BLACK],
        [], [], [],
    ]
    gs.center = ['START']
    p = gs.players[0]
    p.pattern_lines = [[], [Color.BLUE], [], [Color.RED, Color.RED], []]
    p.wall = [[None] * 5 for _ in range(5)]
    gs.current_player = 0
    gs._taken_from_center = [False, False]
    gs.round = 2
    return gs


def _explain_move(game, move):
    if move.source_type == 'factory':
        src = 'F%d' % (move.source_idx + 1)
    else:
        src = 'center'
    dest = 'line %d' % (move.line_idx + 1) if move.line_idx >= 0 else 'floor'
    return 'Take %s from %s to %s' % (COLOR_NAMES_MAP[move.color], src, dest)


def bots_docs(request):
    gs = _build_example_state()
    moves = get_legal_moves(gs, 0)
    scored = []
    for move in moves:
        ev = evaluate_move(gs, 0, move)
        scored.append({
            'move': _explain_move(gs, move),
            'source': 'factory' if move.source_type == 'factory' else 'center',
            'source_idx': move.source_idx,
            'color': COLOR_NAMES_MAP[move.color],
            'color_hex': COLOR_HEX[move.color],
            'line': move.line_idx,
            'S': ev['S'], 'P': ev['P'], 'R': ev['R'], 'C': ev['C'], 'K': ev['K'],
            'completes': ev['completes'],
            'finishes_game': ev['finishes_game'],
            'V_greedy': ev['S'] - ev['P'],
            'V_planned': ev['S'] - ev['P'] + ev['R'] * 1 + ev['C'] * 3 + ev['K'] * 5,
        })

    greedy_sorted = sorted(scored, key=lambda x: (
        -x['V_greedy'], -(x['line'] if x['line'] >= 0 else -999)))
    planned_sorted = sorted(scored, key=lambda x: (
        0 if x['completes'] else 1, x['line'] if x['line'] >= 0 else 999,
        -x['V_planned'], x['line'] if x['line'] >= 0 else 999))
    greedy_top = greedy_sorted[:8]
    planned_top = planned_sorted[:8]

    factories_display = []
    for fi, f in enumerate(gs.factories):
        if f:
            factories_display.append({
                'label': 'F%d' % (fi + 1),
                'tiles': [{'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]} for t in f],
            })
    center_tiles = [
        {'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]}
        for t in gs.center if isinstance(t, Color)
    ]
    has_start = 'START' in gs.center

    pattern_lines_display = []
    for li, pl in enumerate(gs.players[0].pattern_lines):
        row = [{'name': COLOR_NAMES_MAP[t], 'hex': COLOR_HEX[t]} for t in pl]
        pattern_lines_display.append({
            'index': li, 'max': li + 1,
            'tiles': row, 'empty': (li + 1) - len(pl),
        })

    wall_display = [[None] * 5 for _ in range(5)]
    for r in range(5):
        for c in range(5):
            wall_display[r][c] = {
                'target': COLOR_NAMES_MAP[WALL_LAYOUT[r][c]],
                'hex': COLOR_HEX[WALL_LAYOUT[r][c]],
                'placed': gs.players[0].wall[r][c] is not None,
            }

    all_moves_sorted = sorted(scored, key=lambda x: -x['V_planned'])

    return render(request, 'bots.html', {
        'factories': factories_display,
        'center_tiles': center_tiles,
        'has_start': has_start,
        'pattern_lines': pattern_lines_display,
        'wall': wall_display,
        'greedy_top': greedy_top,
        'planned_top': planned_top,
        'all_moves': all_moves_sorted,
        'COLOR_HEX': COLOR_HEX,
        'COLOR_NAMES_MAP': COLOR_NAMES_MAP,
    })


# ═════════════════════════════════════════════════════════════════════
# Math IA
# ═════════════════════════════════════════════════════════════════════

IA_METRICS = [
    {
        'id': 'win_rate',
        'name': 'Win rate with confidence interval',
        'description': 'For each bot in a matchup, compute the proportion of wins '
                       'across N games. Use the Wilson score interval to get a 95% '
                       'confidence interval around the observed win rate.',
        'formula': 'p\u0302 \u00b1 z\u221a(p\u0302(1\u2212p\u0302)/N + z\u00b2/4N\u00b2) / (1 + z\u00b2/N)',
        'visualisation': 'Bar chart of win rates with error bars.',
        'statistical_test': 'Chi-squared test (or G-test) of independence: does the '
                           'winner distribution depend on which bot plays first?',
    },
    {
        'id': 'score_diff',
        'name': 'Score difference distribution',
        'description': 'For each game compute \u0394 = score\u2081 \u2212 score\u2082. A positive mean '
                       'indicates bot\u2081 has an advantage. Visualise the distribution '
                       'and test whether the mean is significantly different from zero.',
        'formula': 'H\u2080: \u03bc_\u0394 = 0    H\u2081: \u03bc_\u0394 \u2260 0',
        'visualisation': 'Histogram of score differences + overlaid normal curve.',
        'statistical_test': 'One-sample t-test or Wilcoxon signed-rank test.',
    },
    {
        'id': 'first_player',
        'name': 'First-player advantage',
        'description': 'Compare win rates when a bot starts vs when it goes second. '
                       'Azul has a known first-player disadvantage (the first to take '
                       'from centre gets the \u22121 START penalty). Quantify this effect.',
        'formula': 'WinRate(starting) \u2212 WinRate(second)',
        'visualisation': 'Grouped bar chart: wins by bot + starting position.',
        'statistical_test': "Two-proportion z-test or Fisher's exact test.",
    },
    {
        'id': 'rounds',
        'name': 'Game length (rounds and turns)',
        'description': 'How many rounds does each bot pairing take to finish? '
                       'More aggressive bots may end the game faster.',
        'formula': 'Mean rounds \u00b1 SD, mean turns \u00b1 SD',
        'visualisation': 'Box plot of rounds per matchup.',
        'statistical_test': 'Two-sample t-test for rounds between different matchups.',
    },
    {
        'id': 'floor_penalty',
        'name': 'Floor penalty accumulation',
        'description': 'Track total floor penalty per game per bot. Do smarter bots '
                       'avoid the floor more effectively? Is floor penalty correlated '
                       'with losing?',
        'formula': 'Mean penalty per game per bot',
        'visualisation': 'Violin plot of floor penalties per bot.',
        'statistical_test': 'Mann-Whitney U test comparing penalties between bots.',
    },
    {
        'id': 'bonus_breakdown',
        'name': 'End-game bonus breakdown',
        'description': 'Record the three bonuses (rows, columns, colour sets) '
                       'separately. Which bonus type contributes most to the final '
                       'score? Do different bots prioritise different bonuses?',
        'formula': 'Mean row bonus, mean column bonus, mean colour-set bonus per bot',
        'visualisation': 'Stacked bar chart of score components.',
        'statistical_test': 'ANOVA: do the three bonus types differ in magnitude?',
    },
    {
        'id': 'move_diversity',
        'name': 'Move diversity and entropy',
        'description': 'For each bot, compute the entropy of chosen moves. '
                       'A deterministic bot (PlannedBot) will have lower entropy '
                       'than a random one. Measure how predictable each bot is.',
        'formula': 'H = \u2212\u2211 p(m) log\u2082 p(m)',
        'visualisation': 'Entropy bar chart per bot.',
        'statistical_test': 'Compare variance of move choices between bots (F-test).',
    },
    {
        'id': 'score_progression',
        'name': 'Score progression per round',
        'description': 'Track cumulative score after each round. Do bots that score '
                       'early maintain their lead, or do comeback wins happen?',
        'formula': 'Score_round(r) \u2212 Score_round(r\u22121)',
        'visualisation': 'Line chart of cumulative scores by round (one line per bot, '
                         'shaded \u00b11 SD).',
        'statistical_test': 'Repeated-measures ANOVA or mixed-effects model.',
    },
]

RECOMMENDED_PIPELINE = [
    'Install Jupyter notebook or use the web dashboard to explore data.',
    'Export simulation data from SQLite to a Pandas DataFrame for analysis.',
    'Start with descriptive statistics: means, variances, histograms.',
    'Move to inferential tests: t-tests, chi-squared, confidence intervals.',
    'Create visualisations for your IA: bar charts, box plots, histograms.',
    'Interpret results in the context of Azul game theory.',
]

DB_QUERY_EXAMPLES = [
    {
        'title': 'Win counts per bot',
        'sql': 'SELECT winner, COUNT(*) FROM azul_game GROUP BY winner;',
    },
    {
        'title': 'Average score per bot in a simulation',
        'sql': 'SELECT AVG(score1), AVG(score2) FROM azul_game WHERE simulation_id = 1;',
    },
    {
        'title': 'Games where winner scored less than loser (comebacks)',
        'sql': "SELECT * FROM azul_game WHERE (winner = 0 AND score1 < score2) OR (winner = 1 AND score2 < score1);",
    },
    {
        'title': 'Score difference distribution',
        'sql': 'SELECT score1 - score2 AS diff FROM azul_game;',
    },
]


def math_ia(request):
    return render(request, 'ia.html', {
        'metrics': IA_METRICS,
        'pipeline': RECOMMENDED_PIPELINE,
        'db_queries': DB_QUERY_EXAMPLES,
    })


# ═════════════════════════════════════════════════════════════════════
# Play — Menu
# ═════════════════════════════════════════════════════════════════════

def play_menu(request):
    player_games = PlayerGame.objects.all()[:20]
    return render(request, 'play.html', {
        'bot_choices': BOT_CHOICES,
        'player_games': player_games,
    })


#  ── PvE (player vs bot) ───────────────────────────────────────────

def play_bot_form(request):
    return render(request, 'play_bot.html', {'bot_choices': BOT_CHOICES})


@login_required
def play_bot_create(request):
    if request.method == 'POST':
        player_name = request.user.username
        bot_name = request.POST.get('bot_name', 'GreedyBot')
        seed_str = request.POST.get('seed', '')
        seed = int(seed_str) if seed_str else None

        global _next_game_id
        with _active_games_lock:
            game_id = _next_game_id
            _next_game_id += 1

            gs = GameState(seed=seed)
            gs.start_round()
            bot = _create_bot(bot_name)

            pg = PlayerGame.objects.create(
                player1_name=player_name,
                bot1_name=bot_name,
                mode='pve',
                seed=seed,
            )

            gd = {
                '_game_id': game_id,
                'game': gs,
                'db_id': pg.id,
                'player1_name': player_name,
                'player2_name': bot_name,
                'bot1': None,
                'bot2': bot,
                'mode': 'pve',
                'status': 'playing',
                'moves': [],
                'snapshots': [],
                'last_activity': time.time(),
            }
            _active_games[game_id] = gd

        snapshots = _run_bot_turn(gd)
        gd['last_activity'] = time.time()
        if gd['game'].game_over:
            _finish_active_game(game_id)

        request.session['active_game_%d' % game_id] = 0
        return redirect('/play/game/%d/?p=0' % game_id)

    return redirect('/play/bot/')


#  ── PvP ───────────────────────────────────────────────────────────

def play_human_lobby(request):
    return render(request, 'play_human.html')


@login_required
def play_pvp_create(request):
    if request.method == 'POST':
        player_name = request.user.username
        seed_str = request.POST.get('seed', '')
        seed = int(seed_str) if seed_str else None

        chars = string.ascii_uppercase.replace('O', '').replace('I', '') + string.digits.replace('0', '').replace('1', '')
        game_code = ''.join(random.choices(chars, k=5))

        global _next_game_id
        with _active_games_lock:
            game_id = _next_game_id
            _next_game_id += 1

            gs = GameState(seed=seed)

            pg = PlayerGame.objects.create(
                player1_name=player_name,
                mode='pvp',
                seed=seed,
            )

            gd = {
                '_game_id': game_id,
                'game': gs,
                'db_id': pg.id,
                'player1_name': player_name,
                'player2_name': None,
                'bot1': None,
                'bot2': None,
                'mode': 'pvp',
                'status': 'waiting',
                'moves': [],
                'snapshots': [],
                'game_code': game_code,
                'last_activity': time.time(),
            }
            _active_games[game_id] = gd

        _notify_game_state(game_id)
        request.session['active_game_%d' % game_id] = 0
        return redirect('/play/game/%d/?p=0' % game_id)
    return redirect('/play/human/')


@login_required
def play_pvp_join_lobby(request):
    return render(request, 'play_human.html')


@login_required
@require_POST
def play_pvp_join_by_code(request):
    code = request.POST.get('game_code', '').strip().upper()
    with _active_games_lock:
        for gid, gd in _active_games.items():
            if gd.get('game_code') == code and gd['mode'] == 'pvp' and gd['status'] == 'waiting':
                return redirect('/play/pvp/join/%d/' % gid)
    return render(request, 'play_human.html', {'error': 'Invalid or expired game code.'})


@login_required
def play_pvp_join_form(request, game_id):
    with _active_games_lock:
        gd = _active_games.get(game_id)
    if gd is None:
        return render(request, '404.html', {'message': 'Game not found.'}, status=404)
    if gd['player2_name'] is not None:
        return render(request, '404.html', {'message': 'Game is full.'}, status=400)
    return render(request, 'play_pvp_join.html', {
        'game_id': game_id,
        'host_name': gd['player1_name'],
    })


@login_required
@require_POST
def play_pvp_join(request, game_id):
    player_name = request.user.username

    with _active_games_lock:
        gd = _active_games.get(game_id)
        if gd is None:
            return render(request, '404.html', {'message': 'Game not found.'}, status=404)
        if gd['player2_name'] is not None:
            return render(request, '404.html', {'message': 'Game is full.'}, status=400)

        gd['player2_name'] = player_name
        gd['status'] = 'playing'
        gd['last_activity'] = time.time()
        gd['game'].start_round()

        pg = PlayerGame.objects.get(id=gd['db_id'])
        pg.player2_name = player_name
        pg.save(update_fields=['player2_name'])

    _notify_game_state(game_id)
    request.session['active_game_%d' % game_id] = 1
    return redirect('/play/game/%d/?p=1' % game_id)


def play_games_list(request):
    games = PlayerGame.objects.all()
    return render(request, 'play_games_list.html', {'games': games})


# ═════════════════════════════════════════════════════════════════════
# Play — Game Page
# ═════════════════════════════════════════════════════════════════════

def play_game_page(request, game_id):
    p = int(request.GET.get('p', 0))

    with _active_games_lock:
        gd = _active_games.get(game_id)
    if gd is None:
        pg = get_object_or_404(PlayerGame, id=game_id)
        pname = pg.player1_name if p == 0 else (pg.player2_name or 'Player 2')
        oppname = pg.player2_name if p == 0 else pg.player1_name
        return render(request, 'play_game.html', {
            'game_id': game_id, 'p': p,
            'mode': pg.mode,
            'game_over': True,
            'waiting': False,
            'winner': pg.winner,
            'round': pg.rounds,
            'current_player': -1,
            'is_my_turn': False,
            'my_name': pname,
            'opp_name': oppname or '',
            'player_names': [pg.player1_name, pg.player2_name or ''],
            'scores': [pg.score1, pg.score2],
            'bot_thinking': False,
            'legal_moves': [],
            'factories': [],
            'center_tiles': [],
            'has_start': False,
            'pattern_lines': [[], []],
            'wall': [[], []],
            'floor_lines': [[], []],
            'bag_tiles': [],
            'lid_tiles': [],
            'tile_images_json': json.dumps(_tile_images()),
            'other_player': 1 if p == 0 else 0,
            'snapshots': [],
        })

    if gd.get('status') == 'waiting':
        host_name = gd['player1_name']
        my_name = host_name if p == 0 else 'Player 2'
        return render(request, 'play_game.html', {
            'waiting': True,
            'game_id': game_id,
            'game_code': gd.get('game_code', ''),
            'p': p,
            'mode': gd['mode'],
            'my_name': my_name,
            'host_name': host_name,
            'game_over': False,
            'is_my_turn': False,
            'bot_thinking': False,
            'legal_moves': [],
            'player_names': [],
            'scores': [0, 0],
            'factories': [],
            'center_tiles': [],
            'has_start': False,
            'pattern_lines': [[], []],
            'wall': [[], []],
            'floor_lines': [[], []],
            'bag_tiles': [],
            'lid_tiles': [],
            'tile_images_json': json.dumps(_tile_images()),
            'other_player': 1 if p == 0 else 0,
        })

    ctx = _build_board_data(game_id, p, gd)
    ctx['waiting'] = False
    return render(request, 'play_game.html', ctx)


@require_POST
def play_game_move(request, game_id):
    p = int(request.POST.get('p', 0))
    source_type = request.POST.get('source_type', '')
    source_idx = int(request.POST.get('source_idx', 0))
    color_val = int(request.POST.get('color', 0))
    line_idx = int(request.POST.get('line_idx', 0))

    with _active_games_lock:
        gd = _active_games.get(game_id)
    if gd is None:
        return redirect('/play/game/%d/?p=%d' % (game_id, p))

    game = gd['game']
    if game.game_over or game.current_player != p:
        return redirect('/play/game/%d/?p=%d' % (game_id, p))

    move_color = Color(color_val)
    turn = len(gd['moves'])
    sp1 = game.players[0].score
    sp2 = game.players[1].score

    try:
        game.execute_move(p, source_type, source_idx, move_color, line_idx)
    except Exception:
        return redirect('/play/game/%d/?p=%d' % (game_id, p))

    had_wall_tiling = game.phase == "wall_tiling"
    if had_wall_tiling:
        game.resolve_wall_tiling()

    bmove = BotMove(source_type=source_type, source_idx=source_idx,
                     color=move_color, line_idx=line_idx)
    gd['moves'].append(bmove)

    player_name = gd['player1_name'] if p == 0 else (gd['player2_name'] or 'Player %d' % p)
    action_desc = '%s: took from %s' % (
        player_name,
        'F%d' % (source_idx + 1) if source_type == 'factory' else 'centre',
    )
    snap = {
        'turn': turn,
        'state_json': json.dumps(game.get_state_snapshot()),
        'action_desc': action_desc,
        'evaluations_json': None,
    }
    gd['snapshots'].append(snap)

    if had_wall_tiling:
        for step in getattr(game, '_last_wall_steps', []):
            gd['snapshots'].append({
                'turn': turn,
                'state_json': json.dumps(step['state']),
                'action_desc': step.get('desc', step['type']),
                'evaluations_json': None,
                'step_data': step,
            })

    if game.game_over:
        _finish_active_game(game_id)
        return redirect('/play/game/%d/?p=%d' % (game_id, p))

    _run_bot_turn(gd)
    gd['last_activity'] = time.time()

    if game.game_over:
        _finish_active_game(game_id)

    _notify_game_state(game_id)
    return redirect('/play/game/%d/?p=%d' % (game_id, p))


@require_POST
def play_game_forfeit(request, game_id):
    p = int(request.POST.get('p', 0))

    with _active_games_lock:
        gd = _active_games.get(game_id)
    if gd is None:
        return redirect('/play/')

    game = gd['game']
    if not game.game_over:
        game.game_over = True
        game.winner = 1 if p == 0 else 0
        snap = {
            'turn': len(gd['moves']),
            'state_json': json.dumps(game.get_state_snapshot()),
            'action_desc': '%s forfeited' % (gd['player1_name'] if p == 0 else gd['player2_name']),
            'evaluations_json': None,
        }
        gd['snapshots'].append(snap)
        _finish_active_game(game_id)

    _notify_game_state(game_id)
    return redirect('/play/game/%d/?p=%d' % (game_id, p))


@require_GET
def play_game_state(request, game_id):
    p = int(request.GET.get('p', 0))

    with _active_games_lock:
        gd = _active_games.get(game_id)
    if gd is None:
        return JsonResponse({'status': 'completed'})

    status = gd.get('status', 'playing')
    game = gd['game']
    current_turn = len(gd['moves'])
    game_over = game.game_over

    if game_over:
        status = 'completed'

    return JsonResponse({
        'status': status,
        'current_player': game.current_player,
        'game_over': game_over,
        'winner': game.winner,
        'current_turn': current_turn,
        'scores': [game.players[0].score, game.players[1].score],
        'player2_present': gd.get('player2_name') is not None,
        'is_my_turn': game.current_player == p and not game_over and status != 'waiting',
    })

# ═════════════════════════════════════════════════════════════════════
# Scenario Builder
# ═════════════════════════════════════════════════════════════════════

DEFAULT_SCENARIO_STATE = json.dumps({
    "factories": [[0, 0, 2, 3], [2, 2, 2, 4], [], [], []],
    "center": ["START"],
    "bag": [],
    "lid": [],
    "players": [
        {
            "pattern_lines": [[], [1], [], [2, 2], []],
            "wall": [[None]*5 for _ in range(5)],
            "floor_line": [],
            "score": 0,
        },
        {
            "pattern_lines": [[], [], [], [], []],
            "wall": [[None]*5 for _ in range(5)],
            "floor_line": [],
            "score": 0,
        }
    ],
    "current_player": 0,
    "starting_player": 0,
    "phase": "factory_offer",
    "round": 1,
    "game_over": False,
    "winner": -1,
}, indent=2)


def _build_state_from_form(data):
    factories = []
    for fi in range(5):
        tiles = []
        for ti in range(4):
            val = data.get(f'factory_{fi}_{ti}', '')
            if val != '':
                tiles.append(int(val))
        factories.append(tiles)

    center = []
    if data.get('center_start'):
        center.append('START')
    for ti in range(10):
        val = data.get(f'center_{ti}', '')
        if val != '':
            center.append(int(val))

    def _build_player(prefix):
        pattern_lines = []
        for r in range(5):
            row = []
            for t in range(r + 1):
                val = data.get(f'{prefix}_pattern_{r}_{t}', '')
                if val != '':
                    row.append(int(val))
            pattern_lines.append(row)

        wall = []
        for r in range(5):
            row = []
            for c in range(5):
                row.append(True if data.get(f'{prefix}_wall_{r}_{c}') else None)
            wall.append(row)

        floor_line = []
        for t in range(7):
            val = data.get(f'{prefix}_floor_{t}', '')
            if val != '':
                floor_line.append(int(val))

        score = int(data.get(f'{prefix}_score', 0))
        return {
            'pattern_lines': pattern_lines,
            'wall': wall,
            'floor_line': floor_line,
            'score': score,
        }

    players = [_build_player('p0'), _build_player('p1')]

    return {
        'factories': factories,
        'center': center,
        'bag': [],
        'lid': [],
        'players': players,
        'current_player': int(data.get('current_player', 0)),
        'starting_player': int(data.get('starting_player', 0)),
        'phase': data.get('phase', 'factory_offer'),
        'round': int(data.get('round', 1)),
        'game_over': data.get('game_over') == 'on',
        'winner': int(data.get('winner', -1)),
    }


def _get_wall_layout():
    layout = []
    for r in range(5):
        row = []
        for c in range(5):
            col = WALL_LAYOUT[r][c]
            row.append({'name': COLOR_NAMES_MAP[col], 'hex': COLOR_HEX[col], 'color_idx': col.value})
        layout.append(row)
    return layout


def scenario_builder(request):
    """Display the scenario builder form."""
    wall_layout = _get_wall_layout()
    return render(request, 'scenario.html', {
        'bot_choices': BOT_CHOICES,
        'default_state': DEFAULT_SCENARIO_STATE,
        'color_names': COLOR_NAMES_MAP,
        'color_hex': COLOR_HEX,
        'wall_layout': wall_layout,
        'floor_penalties': FLOOR_PENALTIES,
    })


def scenario_run(request):
    """Process a scenario builder request: build state, run bot, return results."""
    if request.method != 'POST':
        return redirect('/scenario/')

    wall_layout = _get_wall_layout()
    _ctx = {
        'bot_choices': BOT_CHOICES,
        'default_state': DEFAULT_SCENARIO_STATE,
        'color_names': COLOR_NAMES_MAP,
        'color_hex': COLOR_HEX,
        'wall_layout': wall_layout,
        'floor_penalties': FLOOR_PENALTIES,
    }

    bot_name = request.POST.get('bot_name', 'GreedyBot')
    player_idx = int(request.POST.get('player_idx', 0))
    hundred_point = request.POST.get('hundred_point') == 'on'
    state_json = request.POST.get('state_json', '')
    is_visual = request.POST.get('use_visual_builder') == '1'

    if is_visual:
        try:
            state_data = _build_state_from_form(request.POST)
        except Exception as e:
            return render(request, 'scenario.html', dict(_ctx, error=f'Failed to build state from form: {e}'))
    else:
        try:
            state_data = json.loads(state_json)
        except (json.JSONDecodeError, ValueError):
            return render(request, 'scenario.html', dict(_ctx, error='Invalid JSON state.'))

    # Build the game state from the JSON
    try:
        gs = GameState(hundred_point_rule=hundred_point)
        gs.load_state_snapshot(state_data)
    except Exception as e:
        return render(request, 'scenario.html', dict(_ctx, error=f'Failed to load state: {e}'))

    # Validate phase
    if gs.phase != "factory_offer":
        return render(request, 'scenario.html', dict(_ctx, error='State must be in factory_offer phase.'))

    # Get legal moves
    legal_moves = get_legal_moves(gs, player_idx)
    if not legal_moves:
        return render(request, 'scenario.html', dict(_ctx, error='No legal moves for the selected player.'))

    # Evaluate all legal moves
    evaluations = [evaluate_move(gs, player_idx, m) for m in legal_moves]

    # Run the chosen bot
    bot = _create_bot(bot_name)
    if bot is None:
        return render(request, 'scenario.html', dict(_ctx, error=f'Unknown bot: {bot_name}'))

    chosen_move = bot.choose_move(gs, player_idx)
    bot_reason = bot.last_reason or ''
    bot_evals = bot.last_evaluations or []

    # Mark the chosen move in the full evaluation list
    for e in evaluations:
        e['chosen'] = (e['move'] == chosen_move)
        e['V'] = e.get('V', e['S'] - e['P'])
        color = e['move'].color
        e['color_name'] = COLOR_NAMES_MAP.get(color, str(color))
        e['color_hex'] = COLOR_HEX.get(color, '#888')
        e['source_type'] = e['move'].source_type
        e['source_idx'] = e['move'].source_idx
        e['line_idx'] = e['move'].line_idx

    # Build display data
    score_p1_before = gs.players[0].score
    score_p2_before = gs.players[1].score

    # Simulate the chosen move so the user can see the result
    result_state = None
    if chosen_move is not None:
        gs.execute_move(player_idx, chosen_move.source_type,
                        chosen_move.source_idx, chosen_move.color,
                        chosen_move.line_idx)
        if gs.phase == "wall_tiling":
            gs.resolve_wall_tiling()
        result_state = gs.get_state_snapshot()

    # Sort evaluations for display
    if bot_name == 'PlannedBot':
        # Sort by V descending (PlannedBot V already computed)
        eval_display = sorted(evaluations, key=lambda e: -e.get('V', 0))
    else:
        # Sort by V=S-P descending for other bots
        eval_display = sorted(evaluations, key=lambda e: -(e['S'] - e['P']))

    return render(request, 'scenario.html', dict(_ctx, result={
        'bot_name': bot_name,
        'player_idx': player_idx,
        'chosen_move': chosen_move,
        'bot_reason': bot_reason,
        'evaluations': eval_display,
        'score_p1_before': score_p1_before,
        'score_p2_before': score_p2_before,
        'result_state': result_state,
        'hundred_point': hundred_point,
        'move_count': len(evaluations),
    }))


def csrf_failure_redirect(request, reason=""):
    messages.warning(request, "Your session has expired or the form was invalid. Please log in again.")
    return redirect("login")
