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

    new_stream_id = conn.new_stream()

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_HELLO,
        "HELLO",
        payload={"name": name, "requested_major": 1, "requested_minor": 0, "option_flags": 0},
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)
    dgram_resp = await receive_datagram(conn)
    print('[cli] got message: ', dgram_resp.msg)
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR:
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
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)
    dgram_resp = await receive_datagram(conn)
    print('[cli] got message: ', dgram_resp.msg)
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR:
        return

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_JOIN,
        "JOIN",
        session_id=session_id,
        turn_id=turn_id,
        payload={"team": team, "requested_role": role, "players": default_players(team)},
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)
    dgram_resp = await receive_datagram(conn)
    print('[cli] got message: ', dgram_resp.msg)
    if dgram_resp.mtype == pdu.MSG_TYPE_ERROR:
        return

    assigned_role = dgram_resp.payload.get('assigned_role', pdu.ROLE_NONE)
    session_id = dgram_resp.session_id
    turn_id = dgram_resp.turn_id

    print('[cli] waiting for ROSTER_UPDATE')
    dgram_resp = await receive_until(conn, pdu.MSG_TYPE_ROSTER_UPDATE)
    print('[cli] got message: ', dgram_resp.msg)
    print('[cli] msg as json: ', dgram_resp.to_json())

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_READY,
        "READY",
        session_id=session_id,
        turn_id=turn_id,
        role=assigned_role,
        payload={"ready": True},
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)

    print('[cli] waiting for GAME_UPDATE')
    dgram_resp = await receive_until(conn, pdu.MSG_TYPE_GAME_UPDATE)
    print('[cli] got message: ', dgram_resp.msg)
    print('[cli] msg as json: ', dgram_resp.to_json())
    turn_id = dgram_resp.turn_id

    # currently hardcoding an action / game update / close
    # for testing, but it will be expanded to be more dynamic
    # TODO: Add continuous handling based on the "game" / server_state flow
    if action == 0:
        if assigned_role == dgram_resp.payload.get('offense_role'):
            action = pdu.ACTION_BAT_SWING
        else:
            action = pdu.ACTION_PITCH_FASTBALL

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_PLAY_ACTION,
        "PLAY_ACTION",
        session_id=session_id,
        turn_id=turn_id,
        role=assigned_role,
        payload={"action_type": action, "player_id": 1},
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)
    dgram_resp = await receive_datagram(conn)
    print('[cli] got message: ', dgram_resp.msg)
    print('[cli] msg as json: ', dgram_resp.to_json())
    
    if dgram_resp.mtype == pdu.MSG_TYPE_ACTION_ACK:
        print('[cli] waiting for resolved GAME_UPDATE')
        dgram_resp = await receive_until(conn, pdu.MSG_TYPE_GAME_UPDATE)
        print('[cli] got message: ', dgram_resp.msg)
        print('[cli] msg as json: ', dgram_resp.to_json())
        turn_id = dgram_resp.turn_id

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_CLOSE,
        "CLOSE",
        session_id=session_id,
        turn_id=turn_id,
        role=assigned_role,
        payload={"close_reason": pdu.CLOSE_NORMAL, "close_text": "Client complete"},
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), True)
    await conn.send(qs)
    #END CLIENT HERE


# helper functin to receive a datagram and handle an error by 
# updating the datagram to be an error datagram instead of raising an exception
# this follows my DFA design of transitioning to an error state on an error
async def receive_datagram(conn:PhanatworkQuicConnection):
    message:QuicStreamEvent = await conn.receive()
    try:
        return pdu.Datagram.from_bytes(message.data)
    except pdu.PduError as exc:
        return pdu.Datagram(
            pdu.MSG_TYPE_ERROR,
            exc.text,
            payload={"error_code": exc.code, "error_text": exc.text},
        )

# helper function to continuously receive datagrams until one with the expected type is received,
# while printing out any other received datagrams along the way
# This should never really occur but we dont want to ignore an unexpected datagram, and it 
# is  useful for debugging to see if we get any unexpected messages before the one we are waiting for
async def receive_until(conn:PhanatworkQuicConnection, expected_type:int):
    while True:
        datagram = await receive_datagram(conn)
        if datagram.mtype == expected_type or datagram.mtype == pdu.MSG_TYPE_ERROR:
            return datagram
        print('[cli] got unexpected message: ', datagram.msg)
        print('[cli] msg as json: ', datagram.to_json())


# hardcoded helper function to generate a default player list for a team, since the client needs to send a player list on join
# TODO: Expand this to be more dynamic and not hardcoded, and to include more player info and stats as needed
# planning to allow pulling from a config file
def default_players(team_name):
    return [
        {"player_id": 1, "player_name": team_name + " Player 1", "lineup_slot": 1, "position": 1, "player_status": 1, "stats": []}
    ]
