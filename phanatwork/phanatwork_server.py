import asyncio
from typing import Coroutine,Dict
import json
from phanatwork_quic import PhanatworkQuicConnection, QuicStreamEvent
import pdu
from phanatwork_state import SERVER_STATE


# This is the main server protocol handler
# copied from the example class echo_server, but modified to have a loop for
# event handling, and to use the pdu module for mesage parsing and construction
async def phanatwork_server_proto(scope:Dict, conn:PhanatworkQuicConnection):
    async def send_pdu(datagram:pdu.Datagram):
        rsp_msg = datagram.to_bytes()
        rsp_evnt = QuicStreamEvent(scope["stream_id"], rsp_msg, False)
        await conn.send(rsp_evnt)

    session = SERVER_STATE.register_client(send_pdu)

    try:
        while not session.closed:
            message:QuicStreamEvent = await conn.receive()
            if message.end_stream and not message.data:
                break

            try:
                dgram_in = pdu.Datagram.from_bytes(message.data)
            except pdu.PduError as exc:
                await SERVER_STATE.send_error(session, exc.code, exc.text)
                continue

            await SERVER_STATE.handle_pdu(session, dgram_in)
    finally:
        # handle cleaning up the session on exit, 
        # whether from a clean close or an exception
        # a clean close should not get here, but if the client crashes or 
        # disconnects without sending a close frame, we want to make sure we 
        # clean up the session and free the assigned role
        if not session.closed:
            await SERVER_STATE.handle_close(session)
        if conn.close:
            conn.close()
