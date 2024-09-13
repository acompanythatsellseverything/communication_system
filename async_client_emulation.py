import asyncio
import socketio


sio = socketio.AsyncClient()

@sio.event
async def connect():
    print("Connected to the server")
    asyncio.create_task(send_periodic_messages())


@sio.event
async def message(data):
    print(f"Received message: {data}")


@sio.event
async def disconnect():
    print("Disconnected from the server")


async def send_periodic_messages():
    while True:
        await sio.emit('message', {'phone': '987654321', 'text': 'Periodic message from client!'})
        await asyncio.sleep(30)


async def start_server():
    await sio.connect('http://localhost:5000')
    await sio.wait()

if __name__ == "__main__":
    asyncio.run(start_server())
