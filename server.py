import asyncio
import json
import random
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

app = FastAPI()

BASE = Path(__file__).parent

LETTERS = list("ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی")

CATEGORIES = [
    "name",
    "family",
    "city",
    "country",
    "food",
    "animal",
    "color",
    "thing"
]

waiting = None
rooms = {}


class Player:

    def __init__(self, ws):

        self.id = str(uuid.uuid4())

        self.ws = ws

        self.room = None


async def send(ws, data):

    try:

        await ws.send_text(
            json.dumps(
                data,
                ensure_ascii=False
            )
        )

    except Exception:
        pass


async def broadcast(room, data):

    for player in list(room["players"]):

        await send(
            player.ws,
            data
        )


def new_room():

    return {
        "players": [],
        "letter": random.choice(LETTERS),
        "answers": {},
        "submitted": set(),
        "timer": None
    }


async def start_game(room):

    room["letter"] = random.choice(LETTERS)

    room["answers"] = {}

    room["submitted"] = set()

    await broadcast(
        room,
        {
            "type": "game_start",
            "letter": room["letter"],
            "categories": CATEGORIES,
            "seconds": 60
        }
    )

    room["timer"] = asyncio.create_task(
        game_timer(room)
    )


async def game_timer(room):

    await asyncio.sleep(60)

    if room in rooms.values():

        await finish_game(room)


async def finish_game(room):

    await broadcast(
        room,
        {
            "type": "game_finished"
        }
    )


def calculate_score(answer):

    if not isinstance(answer, str):
        return 0

    answer = answer.strip()

    if not answer:
        return 0

    return 10


async def submit_answers(
    room,
    player,
    answers
):

    room["answers"][player.id] = answers

    room["submitted"].add(player.id)

    if len(room["submitted"]) < len(room["players"]):

        await send(
            player.ws,
            {
                "type": "waiting_result"
            }
        )

        return

    scores = {}

    for p in room["players"]:

        player_answers = room["answers"].get(
            p.id,
            {}
        )

        score = sum(
            calculate_score(v)
            for v in player_answers.values()
        )

        scores[p.id] = score

    result = []

    for p in room["players"]:

        result.append(
            {
                "id": p.id,
                "score": scores.get(
                    p.id,
                    0
                )
            }
        )

    await broadcast(
        room,
        {
            "type": "result",
            "scores": result
        }
    )


@app.get("/")
async def home():

    return FileResponse(
        BASE / "index.html"
    )


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):

    global waiting

    await ws.accept()

    player = Player(ws)

    await send(
        ws,
        {
            "type": "connected",
            "id": player.id
        }
    )

    try:

        while True:

            raw = await ws.receive_text()

            data = json.loads(raw)

            action = data.get("action")

            if action == "find":

                if player.room:
                    continue

                if waiting is None:

                    waiting = player

                    await send(
                        ws,
                        {
                            "type": "searching"
                        }
                    )

                else:

                    opponent = waiting

                    waiting = None

                    room = new_room()

                    room["players"] = [
                        opponent,
                        player
                    ]

                    opponent.room = room

                    player.room = room

                    rooms[str(id(room))] = room

                    await broadcast(
                        room,
                        {
                            "type": "matched"
                        }
                    )

                    await asyncio.sleep(1)

                    await start_game(room)

            elif action == "submit":

                if not player.room:
                    continue

                answers = data.get(
                    "answers",
                    {}
                )

                await submit_answers(
                    player.room,
                    player,
                    answers
                )

    except WebSocketDisconnect:

        if waiting is player:
            waiting = None

        if player.room:

            room = player.room

            if player in room["players"]:
                room["players"].remove(player)

            if room["players"]:

                await send(
                    room["players"][0].ws,
                    {
                        "type": "opponent_left"
                    }
                )

            else:

                rooms.pop(
                    str(id(room)),
                    None
                )


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
)
