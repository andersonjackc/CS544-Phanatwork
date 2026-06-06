from typing import Dict
import json
from phanatwork_quic import PhanatworkQuicConnection, QuicStreamEvent
import pdu


# main client protocol setup
# Currently hardcoded, goes through the motions of HELLO, JOIN, READY, and then sends a ECHO message
# this is just dummy code to test the quic connection and having 2 async clients and server running together
# need to add AUTH as well as the remaining message types.
async def phanatwork_client_proto(scope:Dict, conn:PhanatworkQuicConnection):
    
    #START CLIENT HERE
    print('[cli] starting Phanatwork client')
    name = scope.get('name', 'Player')
    team = scope.get('team', 'Team')
    role = scope.get('role', pdu.ROLE_NONE)
    echo_message = scope.get('message', 'This is a Phanatwork ECHO message')
    
    new_stream_id = conn.new_stream()

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_HELLO,
        "HELLO",
        payload={"name": name, "requested_major": 1, "requested_minor": 0},
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)
    message:QuicStreamEvent = await conn.receive()
    dgram_resp = pdu.Datagram.from_bytes(message.data)
    print('[cli] got message: ', dgram_resp.msg)

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_JOIN,
        "JOIN",
        session_id=dgram_resp.session_id,
        turn_id=dgram_resp.turn_id,
        payload={"team": team, "requested_role": role},
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)
    message:QuicStreamEvent = await conn.receive()
    dgram_resp = pdu.Datagram.from_bytes(message.data)
    print('[cli] got message: ', dgram_resp.msg)
    assigned_role = dgram_resp.payload.get('assigned_role', pdu.ROLE_NONE)
    session_id = dgram_resp.session_id
    turn_id = dgram_resp.turn_id

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_READY,
        "READY",
        session_id=session_id,
        turn_id=turn_id,
        role=assigned_role,
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)

    print('[cli] waiting for START')
    message:QuicStreamEvent = await conn.receive()
    dgram_resp = pdu.Datagram.from_bytes(message.data)
    print('[cli] got message: ', dgram_resp.msg)
    print('[cli] msg as json: ', dgram_resp.to_json())

    datagram = pdu.Datagram(
        pdu.MSG_TYPE_ECHO,
        echo_message,
        session_id=session_id,
        turn_id=turn_id,
        role=assigned_role,
    )
    qs = QuicStreamEvent(new_stream_id, datagram.to_bytes(), False)
    await conn.send(qs)
    message:QuicStreamEvent = await conn.receive()
    dgram_resp = pdu.Datagram.from_bytes(message.data)
    print('[cli] got message: ', dgram_resp.msg)
    print('[cli] msg as json: ', dgram_resp.to_json())
    #END CLIENT HERE
