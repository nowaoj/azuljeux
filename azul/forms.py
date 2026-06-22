from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class BotGameForm(forms.Form):
    player_name = forms.CharField(max_length=100, label='Your Name')
    bot_name = forms.ChoiceField(
        choices=[('GreedyBot', 'GreedyBot'), ('PlannedBot', 'PlannedBot'),
                 ('RandomBot', 'RandomBot')],
        label='Choose Bot',
    )
    seed = forms.IntegerField(required=False, label='Seed (optional)')


class PvPCreateForm(forms.Form):
    player_name = forms.CharField(max_length=100, label='Your Name')
    seed = forms.IntegerField(required=False, label='Seed (optional)')


class PvPJoinForm(forms.Form):
    player_name = forms.CharField(max_length=100, label='Your Name')
