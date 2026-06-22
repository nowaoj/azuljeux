from django.contrib import admin
from .models import (
    Profile, Simulation, Game, Move, Snapshot,
    PlayerGame, PlayerMove, PlayerSnapshot,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'games_played', 'games_won']


@admin.register(Simulation)
class SimulationAdmin(admin.ModelAdmin):
    list_display = ['id', 'bot1_name', 'bot2_name', 'num_games',
                    'games_completed', 'status', 'created_at']
    list_filter = ['status', 'bot1_name', 'bot2_name']


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['id', 'simulation', 'game_index', 'score1',
                    'score2', 'winner', 'rounds']


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'turn', 'player', 'action_type']


@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'turn', 'action_desc']


@admin.register(PlayerGame)
class PlayerGameAdmin(admin.ModelAdmin):
    list_display = ['id', 'player1_name', 'player2_name', 'mode',
                    'score1', 'score2', 'winner', 'created_at']


@admin.register(PlayerMove)
class PlayerMoveAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'turn', 'player']


@admin.register(PlayerSnapshot)
class PlayerSnapshotAdmin(admin.ModelAdmin):
    list_display = ['id', 'game', 'turn']
