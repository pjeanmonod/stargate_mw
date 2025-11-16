# cloud01/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class PlanStatusConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # Accept the connection
        await self.accept()
        # Optionally add the user to a group if you want broadcast
        await self.channel_layer.group_add("plan_updates", self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("plan_updates", self.channel_name)

    # Receive a message from WebSocket
    async def receive_json(self, content):
        # Example: you can handle messages from frontend here
        print("Received from frontend:", content)
        await self.send_json({"message": "Received!"})

    # Method to receive updates from the group
    async def plan_update(self, event):
        """
        event is a dict like: {"type": "plan_update", "job_id": "123", "status": "approved"}
        """
        await self.send_json(event)
