import json
from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='azul_profile')
    games_played = models.IntegerField(default=0)
    games_won = models.IntegerField(default=0)

    def __str__(self):
        return self.user.username


# ── Bot-vs-Bot simulations ─────────────────────────────────────────

class Simulation(models.Model):
    bot1_name = models.CharField(max_length=50)
    bot2_name = models.CharField(max_length=50)
    num_games = models.IntegerField(default=100)
    seed = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')
    games_completed = models.IntegerField(default=0)
    hundred_point_rule = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Game(models.Model):
    simulation = models.ForeignKey(
        Simulation, on_delete=models.CASCADE, related_name='games'
    )
    game_index = models.IntegerField()
    seed = models.IntegerField(null=True, blank=True)
    score1 = models.IntegerField(default=0)
    score2 = models.IntegerField(default=0)
    winner = models.IntegerField(default=-1)
    rounds = models.IntegerField(default=0)
    total_turns = models.IntegerField(default=0)
    # Richer end-of-game stats
    rows1 = models.IntegerField(default=0)
    cols1 = models.IntegerField(default=0)
    colors1 = models.IntegerField(default=0)
    floor_penalty_p1 = models.IntegerField(default=0)
    rows2 = models.IntegerField(default=0)
    cols2 = models.IntegerField(default=0)
    colors2 = models.IntegerField(default=0)
    floor_penalty_p2 = models.IntegerField(default=0)

    class Meta:
        ordering = ['game_index']


class Move(models.Model):
    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name='moves'
    )
    turn = models.IntegerField()
    player = models.IntegerField()
    action_type = models.CharField(max_length=20, blank=True)
    source_idx = models.IntegerField(default=0)
    color = models.CharField(max_length=20, blank=True)
    line_idx = models.IntegerField(default=0)
    score_p1_before = models.IntegerField(default=0)
    score_p2_before = models.IntegerField(default=0)

    class Meta:
        ordering = ['turn']


class Snapshot(models.Model):
    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name='snapshots'
    )
    turn = models.IntegerField()
    state_json = models.TextField()
    action_desc = models.TextField(blank=True)
    evaluations_json = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['turn']


# ── Player (human) games ───────────────────────────────────────────

class PlayerGame(models.Model):
    MODE_CHOICES = [('pve', 'vs Bot'), ('pvp', 'vs Human')]

    player1 = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='player_games_as_p1'
    )
    player2 = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='player_games_as_p2'
    )
    player1_name = models.CharField(max_length=100)
    player2_name = models.CharField(max_length=100, blank=True)
    bot1_name = models.CharField(max_length=50, blank=True)
    bot2_name = models.CharField(max_length=50, blank=True)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='pve')
    seed = models.IntegerField(null=True, blank=True)
    score1 = models.IntegerField(default=0)
    score2 = models.IntegerField(default=0)
    winner = models.IntegerField(default=-1)
    rounds = models.IntegerField(default=0)
    total_turns = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class PlayerMove(models.Model):
    game = models.ForeignKey(
        PlayerGame, on_delete=models.CASCADE, related_name='moves'
    )
    turn = models.IntegerField()
    player = models.IntegerField()
    action_type = models.CharField(max_length=20, blank=True)
    source_idx = models.IntegerField(default=0)
    color = models.CharField(max_length=20, blank=True)
    line_idx = models.IntegerField(default=0)
    score_p1_before = models.IntegerField(default=0)
    score_p2_before = models.IntegerField(default=0)

    class Meta:
        ordering = ['turn']


class PlayerSnapshot(models.Model):
    game = models.ForeignKey(
        PlayerGame, on_delete=models.CASCADE, related_name='snapshots'
    )
    turn = models.IntegerField()
    state_json = models.TextField()
    action_desc = models.TextField(blank=True)
    evaluations_json = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['turn']
