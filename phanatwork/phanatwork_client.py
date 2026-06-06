from typing import Dict
import json
from phanatwork_quic import PhanatworkQuicConnection, QuicStreamEvent
import pdu


# main client protocol setup
# Goes through HELLO, AUTH, JOIN, ROSTER_UPDATE, READY, GAME_UPDATE,
# PLAY_ACTION, and CLOSE.
async def phanatwork_client_proto(scope:Dict, conn:PhanatworkQuicConnection):

    #START CLIENT HERE
    print('[cli] starting Phanatwork client')
    name = scope.get('name', 'Player')
    team = scope.get('team', 'Team')
    role = scope.get('role', pdu.ROLE_NONE)
    username = scope.get('username', name)
    password = scope.get('password', 'password')
    action = scope.get('action', 0)
    turns = scope.get('turns', 1)

    new_stream_id = conn.new_stream()

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_HELLO,
        "HELLO",
        payload={"name": name, "requested_major": 1, "requested_minor": 0, "option_flags": 0},
    )
    await send_datagram(conn, new_stream_id, datagram)
    dgram_resp = await receive_datagram(conn)
    print('[cli] got message: ', dgram_resp.msg)
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR or dgram_resp.mtype == pdu.MSG_TYPE_CLOSE:
        return

    session_id = dgram_resp.session_id
    turn_id = dgram_resp.turn_id

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_AUTH,
        "AUTH",
        session_id=session_id,
        turn_id=turn_id,
        payload={"username": username, "password": password},
    )
    await send_datagram(conn, new_stream_id, datagram)
    dgram_resp = await receive_datagram(conn)
    print('[cli] got message: ', dgram_resp.msg)
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR or dgram_resp.mtype == pdu.MSG_TYPE_CLOSE: 
        return

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_JOIN,
        "JOIN",
        session_id=session_id,
        turn_id=turn_id,
        payload={"team": team, "requested_role": role, "players": default_players(team)},
    )
    await send_datagram(conn, new_stream_id, datagram)
    dgram_resp = await receive_datagram(conn)
    print('[cli] got message: ', dgram_resp.msg)
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR or dgram_resp.mtype == pdu.MSG_TYPE_CLOSE:
        return

    assigned_role = dgram_resp.payload.get('assigned_role', pdu.ROLE_NONE)
    session_id = dgram_resp.session_id
    turn_id = dgram_resp.turn_id

    print('[cli] waiting for ROSTER_UPDATE')
    dgram_resp = await receive_until(conn, pdu.MSG_TYPE_ROSTER_UPDATE)
    print('[cli] got message: ', dgram_resp.msg)
    print('[cli] msg as json: ', dgram_resp.to_json())
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR or dgram_resp.mtype == pdu.MSG_TYPE_CLOSE:
        return

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_READY,
        "READY",
        session_id=session_id,
        turn_id=turn_id,
        role=assigned_role,
        payload={"ready": True},
    )
    await send_datagram(conn, new_stream_id, datagram)

    # inital game update 
    # this currently doesnt match the DFA
    # TODO: Need to note in the README or Update the DFA to reflect that
    # after both clients send READY, the server will send an initial GAME_UPDATE to both clients with the 
    # starting game state, and then the turn_id will increment from there for each turn,
    print('[cli] waiting for GAME_UPDATE')
    dgram_resp = await receive_until(conn, pdu.MSG_TYPE_GAME_UPDATE)
    print('[cli] got message: ', dgram_resp.msg)
    print('[cli] msg as json: ', dgram_resp.to_json())
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR or dgram_resp.mtype == pdu.MSG_TYPE_CLOSE:
        return

    completed_turns = 0
    while completed_turns < turns:
        turn_id = dgram_resp.turn_id
        selected_action = select_action(assigned_role, dgram_resp.payload, action)
        selected_player = select_player(assigned_role, dgram_resp.payload)

        datagram = pdu.Datagram(
            pdu.MSG_TYPE_PLAY_ACTION,
            "PLAY_ACTION",
            session_id=session_id,
            turn_id=turn_id,
            role=assigned_role,
            payload={"action_type": selected_action, "player_id": selected_player},
        )
        await send_datagram(conn, new_stream_id, datagram)
        dgram_resp = await receive_datagram(conn)
        print('[cli] got message: ', dgram_resp.msg)
        print('[cli] msg as json: ', dgram_resp.to_json())
        if dgram_resp.mtype == pdu.MSG_TYPE_ERROR or dgram_resp.mtype == pdu.MSG_TYPE_CLOSE:
            return

        if dgram_resp.mtype == pdu.MSG_TYPE_ACTION_ACK:
            print('[cli] waiting for resolved GAME_UPDATE')
            dgram_resp = await receive_until(conn, pdu.MSG_TYPE_GAME_UPDATE)
            print('[cli] got message: ', dgram_resp.msg)
            print('[cli] msg as json: ', dgram_resp.to_json())
            if dgram_resp.mtype == pdu.MSG_TYPE_ERROR or dgram_resp.mtype == pdu.MSG_TYPE_CLOSE:
                return
            turn_id = dgram_resp.turn_id
            completed_turns += 1

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_CLOSE,
        "CLOSE",
        session_id=session_id,
        turn_id=turn_id,
        role=assigned_role,
        payload={"close_reason": pdu.CLOSE_NORMAL, "close_text": "Client complete"},
    )
    await send_datagram(conn, new_stream_id, datagram, True)
    #END CLIENT HERE


# helper function to send a datagram on the selected QUIC stream
async def send_datagram(conn:PhanatworkQuicConnection, stream_id:int, datagram:pdu.Datagram, end_stream:bool = False):
    qs = QuicStreamEvent(stream_id, datagram.to_bytes(), end_stream)
    await conn.send(qs)

# helper functin to receive a datagram and handle an error by 
# updating the datagram to be an error datagram instead of raising an exception
# this follows my DFA design of transitioning to an error state on an error
async def receive_datagram(conn:PhanatworkQuicConnection):
    message:QuicStreamEvent = await conn.receive()

    # handling the case where the client closes the connection without sending a close frame, 
    # which can happen if the client process is killed or crashes or becomes idle in a deadlock
    if message.end_stream and not message.data:
        return pdu.Datagram(
            pdu.MSG_TYPE_CLOSE,
            "Connection closed",
            payload={
                "close_reason": pdu.CLOSE_ERROR,
                "close_text": "Connection closed",
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

# helper function to continuously receive datagrams until one with the expected type is received,
# or an error or close message as well.
# It will print out any other received datagrams along the way
# This should never really occur but we dont want to ignore an unexpected datagram, and it 
# is  useful for debugging to see if we get any unexpected messages before the one we are waiting for
async def receive_until(conn:PhanatworkQuicConnection, expected_type:int):
    while True:
        datagram = await receive_datagram(conn)
        if datagram.mtype in [expected_type, pdu.MSG_TYPE_ERROR, pdu.MSG_TYPE_CLOSE]:
            return datagram
        print('[cli] got unexpected message: ', datagram.msg)
        print('[cli] msg as json: ', datagram.to_json())


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
def select_player(assigned_role:int, game_update:dict):
    if assigned_role == game_update.get('offense_role'):
        return game_update.get('batter_id', 1) or 1
    if assigned_role == game_update.get('defense_role'):
        return game_update.get('pitcher_id', 1) or 1
    return 1

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
