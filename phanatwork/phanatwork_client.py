from typing import Dict, Optional
import asyncio
import json
from phanatwork_quic import PhanatworkQuicConnection, QuicStreamEvent
import pdu

# currently setting both error and close to make the client stop
# TODO: Need to consider how to handle errors that are recoverable
TERMINAL_MESSAGE_TYPES = {pdu.MSG_TYPE_ERROR, pdu.MSG_TYPE_CLOSE, pdu.MSG_TYPE_GAME_OVER}


# main client protocol setup
# Goes through HELLO, AUTH, JOIN, ROSTER_UPDATE, READY, GAME_UPDATE,
# and PLAY_ACTION until the server sends GAME_OVER or CLOSE.
async def phanatwork_client_proto(scope:Dict, conn:PhanatworkQuicConnection):
    log_protocol = bool(scope.get('log_protocol', True))
    on_game_update = scope.get('on_game_update')
    on_game_over = scope.get('on_game_over')
    on_connection_close = scope.get('on_connection_close')
    on_protocol_error = scope.get('on_protocol_error')
    action_selector = scope.get('action_selector')
    if log_protocol:
        print('[cli] starting Phanatwork client')
    name = scope.get('name', 'Player')
    team = scope.get('team', 'Team')
    role = scope.get('role', pdu.ROLE_NONE)
    username = scope.get('username', name)
    password = scope.get('password', 'password')
    action = scope.get('action', 0)
    turns = scope.get('turns', 1)
    play_mode = scope.get('play_mode', 'auto')
    auto_delay = float(scope.get('auto_delay', 0.25))
    players = scope.get('players') or default_players(team)

    stream_id = conn.new_stream()

    # SETUP: HELLO -> HELLO_ACK
    response = await send_and_receive(
        conn,
        stream_id,
        pdu.Datagram(
            pdu.MSG_TYPE_HELLO,
            "HELLO",
            payload={"name": name, "requested_major": 1, "requested_minor": 0, "option_flags": 0},
        ),
        log_protocol=log_protocol,
    )
    if is_terminal(response, log_protocol, on_connection_close, on_protocol_error):
        return
    session_id = response.session_id
    turn_id = response.turn_id

    # AUTH -> AUTH_RESULT
    response = await send_and_receive(
        conn,
        stream_id,
        pdu.Datagram(
            pdu.MSG_TYPE_AUTH,
            "AUTH",
            session_id=session_id,
            turn_id=turn_id,
            payload={"username": username, "password": password},
        ),
        log_protocol=log_protocol,
    )
    if is_terminal(response, log_protocol, on_connection_close, on_protocol_error):
        return

    # JOIN -> JOIN_ACK
    response = await send_and_receive(
        conn,
        stream_id,
        pdu.Datagram(
            pdu.MSG_TYPE_JOIN,
            "JOIN",
            session_id=session_id,
            turn_id=turn_id,
            payload={"team": team, "requested_role": role, "players": players},
        ),
        log_protocol=log_protocol,
    )
    if is_terminal(response, log_protocol, on_connection_close, on_protocol_error):
        return

    assigned_role = response.payload.get('assigned_role', pdu.ROLE_NONE)
    session_id = response.session_id
    turn_id = response.turn_id

    # Wait for the opponent roster. This only arrives after both clients join.
    roster_update = await wait_for(conn, pdu.MSG_TYPE_ROSTER_UPDATE, log_protocol=log_protocol)
    if is_terminal(roster_update, log_protocol, on_connection_close, on_protocol_error):
        return

    await send_datagram(
        conn,
        stream_id,
        pdu.Datagram(
            pdu.MSG_TYPE_READY,
            "READY",
            session_id=session_id,
            turn_id=turn_id,
            role=assigned_role,
            payload={"ready": True},
        ),
    )
    # inital game update 
    # this currently doesnt match the DFA
    # TODO: Need to note in the README or Update the DFA to reflect that
    # after both clients send READY, the server will send an initial GAME_UPDATE to both clients with the 
    # starting game state, and then the turn_id will increment from there for each turn,
    game_update = await wait_for(conn, pdu.MSG_TYPE_GAME_UPDATE, log_protocol=log_protocol)
    if on_game_update and game_update.mtype == pdu.MSG_TYPE_GAME_UPDATE:
        on_game_update(game_update.payload)
    if is_terminal(game_update, log_protocol, on_connection_close, on_protocol_error):
        return

    completed_turns = 0
    while completed_turns < turns:
        turn_id = game_update.turn_id
        if action_selector:
            if play_mode == "manual":
                selected_action = await asyncio.to_thread(action_selector, assigned_role, game_update.payload, players, play_mode)
            else:
                selected_action = action_selector(assigned_role, game_update.payload, players, play_mode)
            if play_mode == "auto" and auto_delay > 0:
                await asyncio.sleep(auto_delay)
        elif play_mode == "manual":
            selected_action = await asyncio.to_thread(prompt_action, assigned_role, game_update.payload, action)
        else:
            selected_action = select_action(assigned_role, game_update.payload, action)
            if auto_delay > 0:
                await asyncio.sleep(auto_delay)
        selected_player = select_player(assigned_role, game_update.payload, players)

        response = await send_and_receive(
            conn,
            stream_id,
            pdu.Datagram(
                pdu.MSG_TYPE_PLAY_ACTION,
                "PLAY_ACTION",
                session_id=session_id,
                turn_id=turn_id,
                role=assigned_role,
                payload={"action_type": selected_action, "player_id": selected_player},
            ),
            log_protocol=log_protocol,
        )
        if is_terminal(response, log_protocol, on_connection_close, on_protocol_error):
            return

        if response.mtype != pdu.MSG_TYPE_ACTION_ACK:
            if log_protocol:
                print('[cli] expected ACTION_ACK but received:')
                print(format_datagram(response))
            return

        game_update = await wait_for(conn, pdu.MSG_TYPE_GAME_UPDATE, label='resolved GAME_UPDATE', log_protocol=log_protocol)
        if on_game_update and game_update.mtype == pdu.MSG_TYPE_GAME_UPDATE:
            on_game_update(game_update.payload)
        if on_game_over and game_update.mtype == pdu.MSG_TYPE_GAME_OVER:
            on_game_over(game_update.payload)
        if is_terminal(game_update, log_protocol, on_connection_close, on_protocol_error):
            return
        completed_turns += 1

    if log_protocol:
        print('[cli] completed requested turn limit;')
    if conn.close:
        conn.close()


# helper function to send a datagram on the selected QUIC stream
async def send_datagram(conn:PhanatworkQuicConnection, stream_id:int, datagram:pdu.Datagram, end_stream:bool = False):
    qs = QuicStreamEvent(stream_id, datagram.to_bytes(), end_stream)
    await conn.send(qs)

# helper function to send a datagram and wait for a response
async def send_and_receive(conn: PhanatworkQuicConnection, stream_id: int, datagram: pdu.Datagram, log_protocol: bool = True):
    await send_datagram(conn, stream_id, datagram)
    response = await receive_datagram(conn)
    if log_protocol:
        print_received(response)
    return response


# helper functin to receive a datagram and handle an error by 
# updating the datagram to be an error datagram instead of raising an exception
# this follows my DFA design of transitioning to an error state on an error
async def receive_datagram(conn:PhanatworkQuicConnection):
    message:QuicStreamEvent = await conn.receive()

    # handling the case where the client closes the connection without sending a close frame, 
    # which can happen if the client process is killed or crashes or becomes idle in a timeout
    if message.end_stream and not message.data:
        close_reason = message.close_reason
        if close_reason is None:
            close_reason = pdu.CLOSE_ERROR
        close_text = message.close_text or "Connection closed"
        return pdu.Datagram(
            pdu.MSG_TYPE_CLOSE,
            close_text,
            payload={
                "close_reason": close_reason,
                "close_text": close_text,
            },
        )

    try:
        return pdu.Datagram.from_bytes(message.data)
    except pdu.PduError as exc:
        return pdu.Datagram(
            pdu.MSG_TYPE_ERROR,
            exc.text,
            payload={"error_code": exc.code, "error_text": exc.text},
        )

# replaces receive_until to be more general
async def wait_for(conn: PhanatworkQuicConnection, expected_type: int, label: Optional[str] = None, log_protocol: bool = True):
    expected_name = label or pdu.msg_type_name(expected_type)
    if log_protocol:
        print(f'[cli] waiting for {expected_name}')

    while True:
        datagram = await receive_datagram(conn)
        if log_protocol:
            print_received(datagram)
        if datagram.mtype in [expected_type, pdu.MSG_TYPE_ERROR, pdu.MSG_TYPE_CLOSE, pdu.MSG_TYPE_GAME_OVER]:
            return datagram
        if log_protocol:
            print('[cli] unexpected message while waiting; continuing')

# helper function to check if a recieved datagram should kill the client
def is_terminal(datagram: pdu.Datagram, log_protocol: bool = True, on_connection_close = None, on_protocol_error = None):
    if datagram.mtype in TERMINAL_MESSAGE_TYPES:
        if datagram.mtype == pdu.MSG_TYPE_ERROR:
            error_text = datagram.payload.get("error_text", datagram.msg)
            if on_protocol_error:
                on_protocol_error(error_text)
            elif not log_protocol:
                print(f"Game connection error: {error_text}")
        elif datagram.mtype == pdu.MSG_TYPE_CLOSE:
            close_text = datagram.payload.get("close_text", datagram.msg)
            if on_connection_close:
                on_connection_close(close_text)
            elif not log_protocol:
                print(f"Connection closed: {close_text}")
        if log_protocol:
            print('[cli] stopping client protocol because the peer sent a terminal message')
        return True
    return False

# helper function to pretty print a datagram payload for easier debugging
def print_received(datagram: pdu.Datagram):
    print(f'[cli] got {pdu.msg_type_name(datagram.mtype)}: {datagram.msg}')
    if datagram.payload:
        print(format_datagram(datagram))

# formatting a datagram for prettier prenting
def format_datagram(datagram: pdu.Datagram):
    visible = {
        "version": f"{datagram.version_major}.{datagram.version_minor}",
        "type": pdu.msg_type_name(datagram.mtype),
        "session_id": datagram.session_id,
        "turn_id": datagram.turn_id,
        "role": pdu.role_name(datagram.role),
        "message": datagram.msg,
        "payload": datagram.payload,
    }
    return json.dumps(visible, indent=2, sort_keys=True)


# helper function to select a legal dummy action based on the role assigned by the server
# and the current game update.  This is still dummy data, but it is no longer just one
# hardcoded client message.
# TODO: tie this in to be dynamic based on 'user' input or application input, or a config file
def select_action(assigned_role:int, game_update:dict, requested_action:int):
    if requested_action != 0:
        return requested_action
    if assigned_role == game_update.get('offense_role'):
        return pdu.ACTION_BAT_SWING
    if assigned_role == game_update.get('defense_role'):
        return pdu.ACTION_PITCH_FASTBALL
    return 0

# helper function to select the dummy player id to send for the current action.
# This is also hardcoded for now, but it selects the player based on the assigned role and the game update info
def select_player(assigned_role:int, game_update:dict, players:list = None):
    if assigned_role == game_update.get('offense_role'):
        return game_update.get('batter_id', first_player_id(players, pdu.POS_CATCHER)) or 1
    if assigned_role == game_update.get('defense_role'):
        return game_update.get('pitcher_id', first_player_id(players, pdu.POS_PITCHER)) or 1
    return first_player_id(players, pdu.POS_UNKNOWN)

# helper function to select the first player with the requested position from the roster
def first_player_id(players:list = None, position:int = pdu.POS_UNKNOWN):
    if not players:
        return 1
    for player in players:
        if int(player.get("position", pdu.POS_UNKNOWN)) == position:
            return int(player.get("player_id", 1))
    return int(players[0].get("player_id", 1))

# manual CLI prompt for choosing an available action on a turn
def prompt_action(assigned_role:int, game_update:dict, requested_action:int):
    if requested_action != 0:
        return requested_action
    if assigned_role == game_update.get('offense_role'):
        options = [
            ("swing", pdu.ACTION_BAT_SWING),
            ("take", pdu.ACTION_BAT_TAKE),
            ("bunt", pdu.ACTION_BAT_BUNT),
        ]
    elif assigned_role == game_update.get('defense_role'):
        options = [
            ("fastball", pdu.ACTION_PITCH_FASTBALL),
            ("curveball", pdu.ACTION_PITCH_CURVEBALL),
            ("changeup", pdu.ACTION_PITCH_CHANGEUP),
        ]
    else:
        return 0

    print_game_state(game_update)
    print("Available actions:")
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option[0]}")
    while True:
        selected = input("Choose action: ").strip().lower()
        for index, option in enumerate(options, start=1):
            if selected == str(index) or selected == option[0]:
                return option[1]
        print("Invalid action")

# show the current game state in a small CLI-friendly format
def print_game_state(game_update:dict):
    half = "top" if game_update.get('half_inning') == 0 else "bottom"
    print("\nGame state")
    print(f"  inning: {half} {game_update.get('inning')}  outs: {game_update.get('outs')}  count: {game_update.get('balls')}-{game_update.get('strikes')}")
    print(f"  score: AWAY {game_update.get('away_score')} - HOME {game_update.get('home_score')}")
    print(f"  last play: {game_update.get('result_text')}\n")

# hardcoded helper function to generate a default player list for a team, since the client needs to send a player list on join
# TODO: Expand this to be more dynamic and not hardcoded, and to include more player info and stats as needed
# planning to allow pulling from a config file
def default_players(team_name):
    return [
        {
            "player_id": 1,
            "player_name": team_name + " Player 1",
            "lineup_slot": 1,
            "position": pdu.POS_CATCHER,
            "player_status": pdu.PLAYER_ACTIVE,
            "stats": [
                {"stat_id": pdu.STAT_BATTING_AVG_X1000, "scale": 3, "stat_value": 275},
                {"stat_id": pdu.STAT_ON_BASE_X1000, "scale": 3, "stat_value": 340},
            ],
        },
        {
            "player_id": 2,
            "player_name": team_name + " Player 2",
            "lineup_slot": 2,
            "position": pdu.POS_FIRST_BASE,
            "player_status": pdu.PLAYER_ACTIVE,
            "stats": [
                {"stat_id": pdu.STAT_BATTING_AVG_X1000, "scale": 3, "stat_value": 250},
            ],
        },
        {
            "player_id": 3,
            "player_name": team_name + " Pitcher",
            "lineup_slot": 0,
            "position": pdu.POS_PITCHER,
            "player_status": pdu.PLAYER_ACTIVE,
            "stats": [
                {"stat_id": pdu.STAT_ERA_X100, "scale": 2, "stat_value": 375},
            ],
        },
    ]
