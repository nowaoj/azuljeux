import json

from channels.generic.websocket import AsyncWebsocketConsumer


class GameStateConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.game_id = int(self.scope['url_route']['kwargs']['game_id'])
        self.game_group = f'game_{self.game_id}'

        await self.channel_layer.group_add(
            self.game_group, self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.game_group, self.channel_name
        )

    async def game_update(self, event):
        await self.send(text_data=json.dumps(event['data']))
