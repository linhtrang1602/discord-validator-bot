import discord
import sys
import json
import time
import asyncio
import threading
import websocket

block_missing = 0
thread_id = ""
warned = False
error_code = 0
NewBlock = False
retries = 20

token = "YOUR.TOKEN"
channelID = "channel-id"

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

def login_client():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.login(token))
    print("Client logged in successfully.")

async def msg(msg):
    try:
        user = await client.fetch_channel(channelID)
        if user is not None:
            await user.send(msg)
            print('Message sent successfully!')
        else:
            print("User not found. Please check the user ID.")
    except discord.Forbidden:
        print("I can't send a message to this user. They might have DMs disabled or the bot may not have permission.")
    except discord.HTTPException as e:
        print(f'Error: {e}')

def message(message):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(msg(message))

def is_ws_connected(ws):
    try:
        # Try sending a simple ping message
        ws.send("ping", opcode=0x9)  # Opcode 0x9 is a ping in WebSockets
        return True  # If sending succeeds, it's likely connected
    except Exception as e:
        print(e)
        return False

def monitor_timeout(ws):
    global NewBlock, error_code, ws_connected
    while True:
        time.sleep(1800)

        if not is_ws_connected(ws):
            print("WebSocket is not connected, stopping timeout monitoring")
            continue
        
        if not NewBlock:
            print("No new data in 30 minutes")
            message(f"Check RPC {ws.url}!")
            ws.close()
            return
        else:
            NewBlock = False

def on_message(ws, message, name, hash, threshold):
    global NewBlock
    data = json.loads(message)
    data = data["result"]["data"]["value"]
    checkUptime(data, name, hash, threshold)
    NewBlock = True

def on_error(ws, error):
    print("Error:", error)
    
def on_close(ws, close_status_code, close_msg):
    global error_code, retries
    print(error_code)
    print(f"Retrying.... {retries} retries left")
    retries = retries - 1
    if retries == 0:
        if (error_code == 0):
            error_code = 1
            retries = 20
        elif error_code == 1:
            error_code = 2
    print("Connection closed with status code:", close_status_code, "message:", close_msg)
    time.sleep(10)
    
def on_open(ws):
    data = {
        "jsonrpc": "2.0",
        "method": "subscribe",
        "id": 0,
        "params": {"query": "tm.event='NewBlock'"}
    }
    ws.send(json.dumps(data))
    print("Subscribed to get block info")

def checkUptime(data, name, validator, threshold):
    global block_missing, alive
    alive = False
    signatures = data["block"]["last_commit"]["signatures"]

    for i in signatures:
        if i["validator_address"] == validator:
            alive = True
            print(f"{name} still alive: {int(data['block']['last_commit']['height']):,}")
            if block_missing != 0:
                if block_missing >= threshold:
                    message(f"Hurray, our {name} is up again!",)
                    print(f"Hurray, our {name} is up again!")
                block_missing = 0
            break
    
    if not alive:
        block_missing = block_missing + 1
        print(f"{name} miss {block_missing} blocks: {int(data['block']['last_commit']['height']):,}")
        if block_missing >= threshold and block_missing % threshold == 0:
            message(f"Our {name} missing {block_missing} blocks")

if __name__ == "__main__":
    chain = sys.argv[1]
    chains_data = json.load(open('chains.json'))
    chainData = chains_data[chain]
    websocket_url = chainData["rpc"].replace("http", "ws") + "/websocket"

    login_client()

    # websocket.enableTrace(True)
    while True:
        if error_code == 0:
            print(f"Connecting to {websocket_url} ...")
            ws = websocket.WebSocketApp(
                websocket_url,
                on_open=on_open,
                on_message=lambda ws, msg: on_message(ws, msg, chainData["name"], chainData["hash"], int(chainData["threshold"])),
                on_error=on_error,
                on_close=on_close,
            )
            timeout_thread = threading.Thread(target=monitor_timeout, args=(ws, ))
            timeout_thread.daemon = True
            timeout_thread.start()
            ws.run_forever()
        else:
            message(f"Check RPC!")
            break
        time.sleep(10)
