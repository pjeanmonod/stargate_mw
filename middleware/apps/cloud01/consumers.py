# cloud01/consumers.py
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class PlanStatusConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        print("WebSocket client connected:", self.channel_name)
        # Accept the connection
        await self.accept()

        # Add to the "plan_updates" group so we can broadcast
        await self.channel_layer.group_add("plan_updates", self.channel_name)

    async def disconnect(self, close_code):
        # Remove from the group
        await self.channel_layer.group_discard("plan_updates", self.channel_name)

    # Receive updates from frontend (optional)
    async def receive_json(self, content):
        print("Received from frontend:", content)
        await self.send_json({"message": "Received!"})

    # Receive updates from the group
    async def plan_update(self, event):
        """
        event = {
            "type": "plan_update",
            "job_id": 123,
            "plan_status": "approved",
            "state_status": "locked",
        }
        """
        print("plan_update event:", event) 
        await self.send_json(event)
