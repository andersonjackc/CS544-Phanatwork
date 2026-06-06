from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

import pdu


SendPdu = Callable[[pdu.Datagram], Awaitable[None]]

# this controls the server state and DFA logic for protocol handling
# currently minimal implementation with only enough to test basic
# quic connection and message parsing, but will be expanded to have the 
# full DFA states
@dataclass
class ClientSession:
    session_id: int
    send_pdu: SendPdu
    role: int = pdu.ROLE_NONE
    name: str = ""
    team: str = ""
    hello_done: bool = False
    join_done: bool = False
    ready: bool = False
    text_done: bool = False
    closed: bool = False


class PhanatworkServerState:
    # setting up the initial server state, with session tracking and role assignment
    def __init__(self):
        self.next_session_id = 1
        self.clients: Dict[int, ClientSession] = {}
        self.role_to_session: Dict[int, int] = {}
        self.turn_id = 1

    # on new client connection, register them and create a session for them,
    # returning the session object for use in the protocol handler loop
    def register_client(self, send_pdu: SendPdu) -> ClientSession:
        session_id = self.next_session_id
        self.next_session_id += 1
        session = ClientSession(session_id, send_pdu)
        self.clients[session_id] = session
        print(f"[svr] registered session {session_id}")
        return session

    # main server protocol handler, called from the server loop, 
    # which dispatches to the appropriate handler function based on message type
    async def handle_pdu(self, session: ClientSession, datagram: pdu.Datagram):
        print(f"[svr] session {session.session_id} received {pdu.msg_type_name(datagram.mtype)}")

        if datagram.mtype == pdu.MSG_TYPE_HELLO:
            await self.handle_hello(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_JOIN:
            await self.handle_join(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_READY:
            await self.handle_ready(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_ECHO:
            await self.handle_echo(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_CLOSE:
            await self.handle_close(session)
        else:
            await self.send_error(session, "Unexpected message type")

    # the following are the individual message handlers for each message type, 
    # which implement the protocol logic and state transitions
    
    # hello handler just checks for a name in the payload and responds with a HELLO_ACK
    # need to add version checking and error handling for unsupported versions, 
    # but this is just a basic implementation for testing
    # TODO: add version checking and error handling for unsupported versions
    async def handle_hello(self, session: ClientSession, datagram: pdu.Datagram):
        session.name = datagram.payload.get("name", "player")
        session.hello_done = True
        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_HELLO_ACK,
            "HELLO accepted",
            session_id=session.session_id,
            turn_id=self.turn_id,
            payload={"accepted_major": 1, "accepted_minor": 0},
        ))


    # join handler checks that hello was done, 
    # then assigns a role based on the requested role and availability,
    # and responds with a JOIN_ACK with the assigned role, or an error
    # TODO: need to update main Datagram packing to be more consistent
    # with spec, currently just keeping very similar to the echo example
    async def handle_join(self, session: ClientSession, datagram: pdu.Datagram):
        if not session.hello_done:
            await self.send_error(session, "JOIN received before HELLO")
            return

        requested_role = int(datagram.payload.get("requested_role", pdu.ROLE_NONE))
        assigned_role = self.assign_role(requested_role)

        if assigned_role == pdu.ROLE_NONE:
            await self.send_error(session, "No role available")
            return

        session.role = assigned_role
        session.team = datagram.payload.get("team", "Team")
        session.join_done = True
        self.role_to_session[assigned_role] = session.session_id

        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_JOIN_ACK,
            f"Joined as {pdu.role_name(assigned_role)}",
            session_id=session.session_id,
            turn_id=self.turn_id,
            role=assigned_role,
            payload={"assigned_role": assigned_role},
        ))
    
    # ready handler checks that join was done, then marks the session as ready,
    # and if both clients are ready, broadcasts a GAME_UPDATE to both clients to start the
    async def handle_ready(self, session: ClientSession, datagram: pdu.Datagram):
        if not session.join_done:
            await self.send_error(session, "READY received before JOIN")
            return

        session.ready = True
        print(f"[svr] session {session.session_id} is READY")

        if self.both_clients_ready():
            await self.broadcast_game_update()

    # dummy message type for ECHO testing, not part of actual protcol
    # TODO: replace with real msg types
    async def handle_echo(self, session: ClientSession, datagram: pdu.Datagram):
        if not self.both_clients_ready():
            await self.send_error(session, "ECHO received before both clients are ready")
            return

        session.text_done = True
        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_ECHO_ACK,
            "SVR-ACK: " + datagram.msg,
            session_id=session.session_id,
            turn_id=self.turn_id,
            role=session.role,
        ))
        print(f"[svr] {pdu.role_name(session.role)} message: {datagram.msg}")

    # close handler just marks the session as closed, 
    # in a real implementation would also need to clean up state and 
    # notify the other client if one client disconnects
    # TODO: add cleanup and notification logic for client disconnects
    async def handle_close(self, session: ClientSession):
        session.closed = True
        print(f"[svr] session {session.session_id} closed")

    # error handler just sends an ERROR message back to the client with the error text
    # need to add more error handling and checking in the individual message handlers,
    # as well as tie in error codes from spec
    # TODO: add more error handling s well as tie in error codes from spec
    async def send_error(self, session: ClientSession, text: str):
        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_ERROR,
            text,
            session_id=session.session_id,
            turn_id=self.turn_id,
            role=session.role,
        ))

    # once both clients are ready, broadcast a GAME_UPDATE message to both clients to
    # start the game, currently just sends a message with the client and opponent info, 
    # but will need to be expanded
    # TODO: expand the GAME_UPDATE message to include the actual game state and 
    # logic for turns, actions, etc.
    async def broadcast_game_update(self):
        home = self.clients[self.role_to_session[pdu.ROLE_HOME]]
        away = self.clients[self.role_to_session[pdu.ROLE_AWAY]]
        print("[svr] both clients ready; sending GAME_UPDATE")

        for session in [home, away]:
            opponent = away if session.role == pdu.ROLE_HOME else home
            await session.send_pdu(pdu.Datagram(
                pdu.MSG_TYPE_GAME_UPDATE,
                "Both clients are ready. You may send ECHO.",
                session_id=session.session_id,
                turn_id=self.turn_id,
                role=session.role,
                payload={
                    "your_role": session.role,
                    "your_team": session.team,
                    "opponent_role": opponent.role,
                    "opponent_team": opponent.team,
                },
            ))

    # simple role assignment logic based on requested role and availability
    def assign_role(self, requested_role:int):
        if requested_role in [pdu.ROLE_HOME, pdu.ROLE_AWAY]:
            if requested_role not in self.role_to_session:
                return requested_role

        if pdu.ROLE_HOME not in self.role_to_session:
            return pdu.ROLE_HOME
        if pdu.ROLE_AWAY not in self.role_to_session:
            return pdu.ROLE_AWAY
        return pdu.ROLE_NONE

    # helper function to check if both clients are ready
    def both_clients_ready(self):
        if pdu.ROLE_HOME not in self.role_to_session:
            return False
        if pdu.ROLE_AWAY not in self.role_to_session:
            return False
        home = self.clients[self.role_to_session[pdu.ROLE_HOME]]
        away = self.clients[self.role_to_session[pdu.ROLE_AWAY]]
        return home.ready and away.ready


SERVER_STATE = PhanatworkServerState()
