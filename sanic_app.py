import os
import asyncio
from datetime import datetime
from json import dumps, loads
from queue import Queue
from asgiref.sync import sync_to_async
from dotenv import load_dotenv

from sanic import Sanic, HTTPResponse
from sanic.response import json
from sanic.log import logger
from django.db.models import Q
import django

from utils.Zadarma_api import ZadarmaAPI

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AndroidJavaWebsocket.settings')
django.setup()

from sms.models import IncomingSMS, OutgoingSMS, CallRecord

app = Sanic("WebSocketApp")
clients = set()
task_queue = Queue()

load_dotenv(".env")


def phone_normalize(phone_number):
    return phone_number.replace('-', '').replace('(', '').replace(')', '').replace(' ', '')


async def add_event(obj, event):
    if event not in obj.events:
        if obj.events == "":
            obj.events = event
        else:
            obj.events += "\n" + event
    await obj.asave()


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
    data = request.data
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
@app.route("/webhook", methods=["POST", "GET"])
async def webhook_handle(request):
    data = request.form
    print(request.form, "form")
    zd_echo = request.args.get('zd_echo')
    if zd_echo:
        return HTTPResponse(zd_echo)
    event = data.get("event")
    call_start = data.get("call_start")
    pbx_call_id = data.get("pbx_call_id")
    destination_number = data.get("destination")
    call_type = data.get("calltype")
    status_code = data.get("status_code")
    is_recorded = data.get("is_recorded")
    disposition = data.get("disposition")
    call_id_with_rec = data.get("call_id_with_rec")
    duration = data.get("duration")

    if event in ["NOTIFY_OUT_START", "NOTIFY_START"]:
        print(event)
        call_record, _ = await CallRecord.objects.aget_or_create(
            pbx_call_id=pbx_call_id)
        call_record.call_start_time = call_start
        call_record.caller_phone = data.get("caller_id")
        call_record.caller_id = data.get("internal")
        call_record.client_number = data.get("caller_id")
        call_record.operator_number = data.get("called_did")
        call_record.destination_number = destination_number
        call_record.call_type = call_type
        await add_event(call_record, event)
        await call_record.asave()

    elif event == "NOTIFY_INTERNAL":
        print(event)
        call_record, _ = await CallRecord.objects.aget_or_create(
            pbx_call_id=pbx_call_id
        )
        call_record.call_start = call_start
        call_record.caller_phone = data.get("caller_id")
        call_record.client_number = data.get("called_id")
        call_record.operator_number = data.get("caller_did")
        await add_event(call_record, event)
        await call_record.asave()

    elif event == "NOTIFY_ANSWER":
        print(event)
        call_record, _ = await CallRecord.objects.aget_or_create(pbx_call_id=pbx_call_id)
        call_record.caller_id = data.get("caller_id")
        call_record.client_number = data.get("caller_id")
        call_record.operator_number = destination_number
        call_record.call_type = call_type
        await add_event(call_record, event)
        await call_record.asave()

    elif event in ["NOTIFY_OUT_END", "NOTIFY_END"]:
        print(event)
        call_record, _ = await CallRecord.objects.aget_or_create(pbx_call_id=pbx_call_id)
        call_record.duration = duration
        call_record.status_code = status_code
        call_record.is_recorded = is_recorded
        call_record.disposition = disposition
        call_record.call_id_with_rec = call_id_with_rec
        call_record.client_number = data.get("caller_id")
        call_record.operator_number = data.get("called_did")
        call_record.call_end_time = datetime.now()
        await add_event(call_record, event)
        await call_record.asave()

    elif event == "NOTIFY_RECORD":
        print(event)
        zadarma_api = ZadarmaAPI(key=os.getenv("ZADARMA_KEY"), secret=os.getenv("ZADARMA_SECRET"))
        call = await sync_to_async(zadarma_api.call)('/v1/pbx/record/request/', {
            "pbx_call_id": pbx_call_id,
            "lifetime": 5184000
        })

        call_record, _ = await CallRecord.objects.aget_or_create(pbx_call_id=pbx_call_id)
        print(loads(call)["links"][0])
        call_record.caller_record_link = loads(call)["links"][0]
        await add_event(call_record, event)
        print(call_record)
        await call_record.asave()

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

    incoming_sms = await IncomingSMS.objects.afilter(filter).values()
    outgoing_sms = await OutgoingSMS.objects.afilter(filter).values()

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
    app.run(host=os.getenv("CS_HOST"), port=int(os.getenv("CS_PORT")))
