import os
import asyncio
from json import dumps, loads
from queue import Queue

from sanic import Sanic
from sanic.response import json
from sanic.log import logger
from django.db.models import Q
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AndroidJavaWebsocket.settings')
django.setup()

from sms.models import IncomingSMS, OutgoingSMS, CallRecord

app = Sanic("WebSocketApp")
clients = set()
task_queue = Queue()


def phone_normalize(phone_number):
    return phone_number.replace('-', '').replace('(', '').replace(')', '').replace(' ', '')


async def add_event(obj, event):
    if event not in obj.events:
        if obj.events == "":
            obj.events = event
        else:
            obj.events += "\n" + event
    await obj.save()


# WebSocket Route
@app.websocket('/ws')
async def ws_handler(request, ws):
    logger.info("Client connected")
    clients.add(ws)

    await process_task_queue()

    try:
        while True:
            data = await ws.recv()
            logger.info(f"Received: {data}")
            message_data = loads(data)
            phone = message_data.get("phone")
            text = message_data.get("text")

            if isinstance(phone, list):
                for number in phone:
                    if not clients:
                        #TODO task
                        task_queue.put({"phone": phone, "text": text})
                    await IncomingSMS.objects.acreate(phone=number, text=text)
            else:
                await IncomingSMS.objects.acreate(phone=phone, text=text)

            # Broadcast message to all clients
            await broadcast({"phone": phone, "text": text})
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        clients.remove(ws)
        logger.info("Client disconnected")


async def broadcast(message):
    data = dumps(message)
    if clients:  # Only broadcast if there are connected clients
        for client in clients:
            try:
                await client.send(data)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
    else:
        # No clients connected, add message to the queue
        task_queue.put(message)
        logger.info(f"No clients connected, message added to queue: {message}")


# REST API route for sending SMS messages
@app.route("/send_message", methods=["POST"])
async def send_message(request):
    data = request.json
    text = data.get("text")
    phone = data.get("phone")

    if isinstance(phone, list):
        for number in phone:
            number = phone_normalize(number)
            await broadcast({"phone": number, "text": text})
            await OutgoingSMS.objects.acreate(phone=number, text=text)
    else:
        phone = phone_normalize(phone)
        await broadcast({"phone": phone, "text": text})
        await OutgoingSMS.objects.acreate(phone=phone, text=text)

    return json({"status": "Message sent"})


# Webhook handler example
@app.route("/webhook", methods=["POST"])
async def webhook_handle(request):
    data = request.form
    event = data.get("event")
    pbx_call_id = data.get("pbx_call_id")

    if event == "NOTIFY_ANSWER":
        call_record, _ = await CallRecord.objects.aget_or_create(pbx_call_id=pbx_call_id)
        call_record.caller_id = data.get("caller_id")
        call_record.client_number = data.get("caller_id")
        await add_event(call_record, event)

    # Handle other events similarly...

    return json({})


@app.route("/get_history", methods=["POST"])
async def get_history(request):
    data = request.json
    phone = data.get("phone")
    start_date = data.get("start_date")
    end_date = data.get("end_date")

    filter = Q(phone=phone)
    if start_date and end_date:
        filter &= Q(created_date__range=(start_date, end_date))

    incoming_sms = await IncomingSMS.objects.filter(filter).values()
    outgoing_sms = await OutgoingSMS.objects.filter(filter).values()

    sms_history = incoming_sms + outgoing_sms
    sms_history.sort(key=lambda sms: sms["created_date"])

    return json(sms_history)


async def process_task_queue():
    while not task_queue.empty():
        content = task_queue.get()
        logger.info(f"Processing queued message: {content}")
        await broadcast(content)
        await OutgoingSMS.objects.acreate(**content)
        task_queue.task_done()


# Task to periodically check the task queue for pending messages
async def send_queued_messages():
    while True:
        await asyncio.sleep(5)  # Polling interval
        await process_task_queue()


if __name__ == '__main__':
    # Start the queue worker
    app.add_task(send_queued_messages)

    # Run the Sanic server with WebSocket support
    app.run(host="0.0.0.0", port=5092)
