import os
from datetime import datetime
from json import loads

import django
from django.db.models import Q
from flask import Flask, request, jsonify
from flask_socketio import join_room, leave_room, send, SocketIO
from queue import Queue

from utils.device_connection_status import DeviceConnectionStatus
from utils.Zadarma_api import ZadarmaAPI

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AndroidJavaWebsocket.settings')
django.setup()

from sms.models import IncomingSMS, OutgoingSMS, CallRecord

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretdgdffghdgfhdgh'
socketio = SocketIO(app, logger=True, engineio_logger=True)

ROOM = "HTRT"
device = DeviceConnectionStatus()
task_queue = Queue()


def phone_normalize(phone_number):
    return phone_number.replace('-', '').replace('(', '').replace(')', '').replace(' ', '')


def add_event(obj, event):
    if event not in obj.events:
        if obj.events == "":
            obj.events = event
        else:
            obj.events += "\n" + event


# @app.route('/', methods=['GET', 'POST'])
# def home():
#     session.clear()
#     if request.method == 'POST':
#         name = request.form.get("name")
#         code = request.form.get("code")
#         join = request.form.get("join", False)
#         create = request.form.get("create", False)
#
#         if not name:
#             return render_template("home.html", error="Name is required", code=code, name=name)
#         if join is not False and not code:
#             return render_template("home.html", error="Code is required", code=code, name=name)
#
#         if create is not False:
#             rooms[ROOM] = {"members": 0, "messages": []}
#         elif code not in rooms:
#             return render_template("home.html", error="Room does not exist", code=code, name=name)
#
#
#         return redirect(url_for("room"))
#
#     return render_template("home.html")

# @app.route("/")
# def room():
#     device.connection = True
#     return render_template("room.html", code=ROOM)


@socketio.on("message", namespace='/sms')
def message(data):
    print(f"Raw data: {data}")
    print(f"data type:  {type(data)}")

    if isinstance(data, str):
        data_dict = loads(data)
    else:
        data_dict = data
    phone = data_dict.get("phone")
    text = data_dict.get("text")
    if isinstance(phone, list):
        for number in phone:
            IncomingSMS.objects.create(phone=number, text=text)
    else:
        IncomingSMS.objects.create(phone=phone, text=text)


@app.route("/send_message", methods=["POST"])
def bulk_or_single_send_message():
    data = request.json
    print(data)
    text = data.get("text")
    phone = data.get("phone")
    if isinstance(phone, list):
        for number in phone:
            number = phone_normalize(number)
            socketio.emit("send_sms", {"phone": f"{number}", "text": f"{text}"}, to=ROOM)
            OutgoingSMS.objects.create(phone=number, text=text)
    else:
        phone = phone_normalize(phone)
        socketio.emit("send_sms", {"phone": f"{phone}", "text": f"{text}"}, to=ROOM)
        OutgoingSMS.objects.create(phone=phone, text=text)
    return jsonify({"status": "Message sent"}), 200


@app.route("/webhook", methods=["POST", "GET"])
def webhook_handle():
    print(request.form, "form")
    zd_echo = request.args.get('zd_echo')
    if zd_echo:
        return zd_echo
    request_dict = request.form.to_dict()
    event = request_dict.get("event")
    print(event)
    call_start = request_dict.get("call_start")
    pbx_call_id = request_dict.get("pbx_call_id")
    destination_number = request_dict.get("destination")
    call_type = request_dict.get("calltype")
    status_code = request_dict.get("status_code")
    is_recorded = request_dict.get("is_recorded")
    disposition = request_dict.get("disposition")
    call_id_with_rec = request_dict.get("call_id_with_rec")
    duration = request_dict.get("duration")

    if event in ["NOTIFY_OUT_START", "NOTIFY_START"]:
        call_record, _ = CallRecord.objects.get_or_create(
            pbx_call_id=pbx_call_id)
        call_record.call_start_time = call_start
        call_record.caller_phone = request_dict.get("caller_id")
        call_record.caller_id = request_dict.get("internal")
        call_record.client_number = request_dict.get("caller_id")
        call_record.operator_number = request_dict.get("called_did")
        call_record.destination_number = destination_number
        call_record.call_type = call_type
        add_event(call_record, event)
        call_record.save()

    elif event == "NOTIFY_INTERNAL":
        call_record, _ = CallRecord.objects.get_or_create(
            pbx_call_id=pbx_call_id
        )
        call_record.call_start = call_start
        call_record.caller_phone = request_dict.get("caller_id")
        call_record.client_number = request_dict.get("called_id")
        call_record.operator_number = request_dict.get("caller_did")
        add_event(call_record, event)
        call_record.save()

    elif event == "NOTIFY_ANSWER":
        call_record, _ = (CallRecord.objects.get_or_create(pbx_call_id=pbx_call_id))
        call_record.caller_id = request_dict.get("caller_id")
        call_record.client_number = request_dict.get("caller_id")
        call_record.operator_number = destination_number
        call_record.call_type = call_type
        add_event(call_record, event)
        call_record.save()

    elif event in ["NOTIFY_OUT_END", "NOTIFY_END"]:
        call_record, _ = CallRecord.objects.get_or_create(pbx_call_id=pbx_call_id)
        call_record.duration = duration
        call_record.status_code = status_code
        call_record.is_recorded = is_recorded
        call_record.disposition = disposition
        call_record.call_id_with_rec = call_id_with_rec
        call_record.client_number = request_dict.get("caller_id")
        call_record.operator_number = request_dict.get("called_did")
        call_record.call_end_time = datetime.now()
        add_event(call_record, event)
        call_record.save()

    elif event == "NOTIFY_RECORD":
        zadarma_api = ZadarmaAPI(key=os.getenv("ZADARMA_KEY"), secret=os.getenv("ZADARMA_SECRET"))
        call = zadarma_api.call('/v1/pbx/record/request/', {
            "pbx_call_id": pbx_call_id,
            "lifetime": 5184000
        })

        call_record, _ = CallRecord.objects.get_or_create(pbx_call_id=pbx_call_id)

        call_record.caller_record_link = loads(call)["links"][0]
        add_event(call_record, event)
        call_record.save()

    return jsonify({}), 200


def send_message(phone, text):
    content = {
        "phone": phone,
        "text": text
    }
    print("send_message_func", device.connection)
    if device.connection:
        socketio.emit("message", content, to=ROOM)
        OutgoingSMS.objects.create(**content)
    else:
        task_queue.put(content)
        print("how many unfinished tasks", task_queue.unfinished_tasks)


@app.route("/get_history", methods=["POST"])
def get_history():
    data = request.json
    phone = data.get("phone")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    filter = Q(phone=phone)
    if start_date and end_date:
        filter &= Q(created_date__range=(
            datetime.fromisoformat(start_date),
            datetime.fromisoformat(end_date)
        ))
    sms_history = []
    for sms in IncomingSMS.objects.filter(filter):
        sms_history.append({
            "phone": sms.phone,
            "text": sms.text,
            "date": sms.created_date,
            "type": "incoming"
        })
    for sms in OutgoingSMS.objects.filter(filter):
        sms_history.append({
            "phone": sms.phone,
            "text": sms.text,
            "date": sms.created_date,
            "type": "outgoing"
        })
    sms_history.sort(key=lambda sms: sms["date"])
    for sms in sms_history:
        sms["date"] = sms["date"].isoformat()
    return jsonify(sms_history), 200


@app.route("/get_call_history", methods=["POST"])
def get_call_history():
    data = request.json
    call_history = []
    for call in CallRecord.objects.filter(client_number=data.get("phone")):
        call_history.append({
            "pbx_call_id": call.pbx_call_id,
            "call_id_with_rec": call.call_id_with_rec,
            "caller_id": call.caller_id,
            "caller_phone": call.caller_phone,
            "client_number": call.client_number,
            "operator_number": call.operator_number,
            "call_start_time": call.call_start_time,
            "call_end_time": call.call_end_time,
            "destination_number": call.destination_number,
            "call_type": call.call_type,
            "duration": call.duration,
            "status_code": call.status_code,
            "is_recorder": call.is_recorder,
            "disposition": call.disposition,
            "caller_record_link": call.caller_record_link,
            "events": call.events
        })
    call_history.sort(key=lambda call: call["call_start_time"])
    for call in call_history:
        call["call_start_time"] = call["call_start_time"].isoformat()
        call["call_end_time"] = call["call_end_time"].isoformat()
    return jsonify(call_history), 200


@socketio.on("phone_connect", namespace='/sms')
def phone_connect():
    print("connected_emit")
    device.connection = True
    join_room(ROOM)
    send({"phone": "connect", "text": "has entered the room"}, to=ROOM, namespace='/sms')
    while not task_queue.empty():
        content = task_queue.get()
        socketio.emit("message", content, to=ROOM, namespace='/sms')
        OutgoingSMS.objects.create(**content)
        task_queue.task_done()
        print("Message sent from queue")


@socketio.on("phone_disconnect", namespace='/sms')
def phone_disconnect():
    print("disconnected_emit")

    device.connection = False
    leave_room(ROOM)
    send({"phone": "disconnect", "text": "has left the room"}, to=ROOM)


if __name__ == '__main__':
    socketio.run(app, host=os.getenv('APP_HOST'), port=os.getenv('APP_PORT'), debug=True, allow_unsafe_werkzeug=True)
