import asyncio
from typing import Coroutine,Dict
import json
from phanatwork_quic import PhanatworkQuicConnection, QuicStreamEvent
import pdu
from phanatwork_state import SERVER_STATE


# This is the main server protocol handler
# copied from the example class echo_server, but modified to have a loop for
# event handling, and to use the pdu module for message parsing and construction
async def phanatwork_server_proto(scope:Dict, conn:PhanatworkQuicConnection):
    async def send_pdu(datagram:pdu.Datagram):
        rsp_msg = datagram.to_bytes()
        rsp_evnt = QuicStreamEvent(scope["stream_id"], rsp_msg, False)
        await conn.send(rsp_evnt)
        
    session = SERVER_STATE.register_client(send_pdu)
        
    while not session.closed:
        message:QuicStreamEvent = await conn.receive()
                
        dgram_in = pdu.Datagram.from_bytes(message.data)
        await SERVER_STATE.handle_pdu(session, dgram_in)
