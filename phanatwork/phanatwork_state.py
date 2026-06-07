from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict

import pdu
from baseball_simulator.simple_baseball import SimpleBaseballRules


SendPdu = Callable[[pdu.Datagram], Awaitable[None]]

# this controls the server state and DFA logic for protocol handling
# currently minimal implementation with enough of the spec to test
# setup, auth, joining, ready, action handling, and cleanup
@dataclass
class ClientSession:
    session_id: int
    send_pdu: SendPdu
    role: int = pdu.ROLE_NONE
    name: str = ""
    username: str = ""
    team: str = ""
    players: list = field(default_factory=list)
    setup_state: str = "SETUP_START"
    ready: bool = False
    closed: bool = False


class PhanatworkServerState:
    # setting up the initial server state, with session tracking and role assignment
    def __init__(self, game_logic = None, log_protocol: bool = True):
        self.game_logic = game_logic or SimpleBaseballRules() # defaulting to the normal rules for ease of testing
        self.log_protocol = log_protocol
        self.next_session_id = 1
        self.clients: Dict[int, ClientSession] = {}
        self.role_to_session: Dict[int, int] = {}
        self.game_logic.reset()
        self.turn_id = 1
        self.event_id = 1
        self.main_state = "SETUP"
        self.offense_role = self.game_logic.offense_role
        self.defense_role = self.game_logic.defense_role
        self.actions: Dict[int, dict] = {}

    # on new client connection, register them and create a session for them,
    # returning the session object for use in the protocol handler loop
    def register_client(self, send_pdu: SendPdu) -> ClientSession:
        session_id = self.next_session_id
        self.next_session_id += 1
        session = ClientSession(session_id, send_pdu)
        self.clients[session_id] = session
        if self.log_protocol:
            print(f"[svr] registered session {session_id}")
        return session

    # main server protocol handler, called from the server loop,
    # which dispatches to the appropriate handler function based on message type
    async def handle_pdu(self, session: ClientSession, datagram: pdu.Datagram):
        if self.log_protocol:
            print(f"[svr] session {session.session_id} received {pdu.msg_type_name(datagram.mtype)}")

        if datagram.mtype != pdu.MSG_TYPE_HELLO:
            if datagram.session_id != session.session_id:
                await self.send_error(session, pdu.ERR_INVALID_STATE, "Invalid session id")
                return
            if datagram.turn_id not in [0, self.turn_id]:
                await self.send_error(session, pdu.ERR_STALE_TURN, "Stale turn id")
                return

        if datagram.mtype == pdu.MSG_TYPE_HELLO:
            await self.handle_hello(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_AUTH:
            await self.handle_auth(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_JOIN:
            await self.handle_join(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_READY:
            await self.handle_ready(session, datagram)
        elif datagram.mtype == pdu.MSG_TYPE_PLAY_ACTION:
            await self.handle_play_action(session, datagram)
        else:
            await self.send_error(session, pdu.ERR_INVALID_STATE, "Unexpected message type")

    # the following are the individual message handlers for each message type,
    # which implement the protocol logic and state transitions

    # hello handler checks the requested version and responds with a HELLO_ACK
    async def handle_hello(self, session: ClientSession, datagram: pdu.Datagram):
        if session.setup_state != "SETUP_START":
            await self.send_error(session, pdu.ERR_INVALID_STATE, "HELLO received in invalid state")
            return

        requested_major = int(datagram.payload.get("requested_major", datagram.version_major))
        requested_minor = int(datagram.payload.get("requested_minor", datagram.version_minor))
        if requested_major != pdu.SUPPORTED_MAJOR:
            await self.send_error(session, pdu.ERR_UNSUPPORTED_VERSION, "Unsupported protocol version")
            return

        session.name = datagram.payload.get("name", "player")[:32]
        session.setup_state = "WAIT_AUTH"
        accepted_minor = min(requested_minor, pdu.SUPPORTED_MINOR)
        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_HELLO_ACK,
            "HELLO accepted",
            session_id=session.session_id,
            turn_id=self.turn_id,
            payload={"accepted_major": pdu.SUPPORTED_MAJOR, "accepted_minor": accepted_minor, "accepted_options": 0},
        ))

    # auth handler currently just passes through the username and password and accepts any non-empty values,
    # TODO: Implement a more "real" auth method with a user "database" (dict lookup for current purposes)
    async def handle_auth(self, session: ClientSession, datagram: pdu.Datagram):
        if session.setup_state != "WAIT_AUTH":
            await self.send_error(session, pdu.ERR_INVALID_STATE, "AUTH received before HELLO")
            return

        username = datagram.payload.get("username", session.name)
        password = datagram.payload.get("password", "")
        if username == "" or password == "":
            await self.send_error(session, pdu.ERR_AUTH_FAILED, "AUTH failed")
            return

        session.username = username[:32]
        session.setup_state = "WAIT_JOIN"
        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_AUTH_RESULT,
            "Login accepted",
            session_id=session.session_id,
            turn_id=self.turn_id,
            payload={"status": pdu.STATUS_SUCCESS, "message": "Login accepted"},
        ))

    # then assigns a role based on the requested role and availability,
    # and responds with a JOIN_ACK with the assigned role, or an error
    async def handle_join(self, session: ClientSession, datagram: pdu.Datagram):
        if session.setup_state != "WAIT_JOIN":
            await self.send_error(session, pdu.ERR_INVALID_STATE, "JOIN received before AUTH")
            return

        requested_role = int(datagram.payload.get("requested_role", pdu.ROLE_NONE))
        assigned_role = self.assign_role(requested_role)

        if assigned_role == pdu.ROLE_NONE:
            await self.send_error(session, pdu.ERR_INVALID_ROLE, "No role available")
            return

        session.role = assigned_role
        session.team = datagram.payload.get("team", "Team")[:32]
        session.players = datagram.payload.get("players", [])[:26]
        session.setup_state = "SETUP_COMPLETE"
        self.role_to_session[assigned_role] = session.session_id

        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_JOIN_ACK,
            f"Joined as {pdu.role_name(assigned_role)}",
            session_id=session.session_id,
            turn_id=self.turn_id,
            role=assigned_role,
            payload={"status": pdu.STATUS_SUCCESS, "assigned_role": assigned_role, "message": "Joined"},
        ))

        if self.both_clients_joined():
            self.main_state = "WAIT_READY"
            await self.broadcast_roster_update()

    # ready handler checks that join was done, then marks the session as ready,
    # and if both clients are ready, broadcasts a GAME_UPDATE to both clients to start the
    async def handle_ready(self, session: ClientSession, datagram: pdu.Datagram):
        if self.main_state != "WAIT_READY" or session.setup_state != "SETUP_COMPLETE":
            await self.send_error(session, pdu.ERR_INVALID_STATE, "READY received before both clients joined")
            return

        session.ready = bool(datagram.payload.get("ready", True))
        if self.log_protocol:
            print(f"[svr] session {session.session_id} is READY")

        if self.both_clients_ready():
            self.main_state = "WAIT_BOTH_ACTIONS"
            await self.broadcast_game_update("Both clients are ready. Send PLAY_ACTION.", 0)

    # play action handler checks that the message is valid for the current state and role,
    # then stores the action and responds with an ACTION_ACK, and if both clients have sent
    # their actions, resolves the turn and broadcasts a GAME_UPDATE with the result
    async def handle_play_action(self, session: ClientSession, datagram: pdu.Datagram):
        if self.main_state not in ["WAIT_BOTH_ACTIONS", "WAIT_OFFENSE", "WAIT_DEFENSE"]:
            await self.send_error(session, pdu.ERR_INVALID_STATE, "PLAY_ACTION received in invalid state")
            return
        if session.role not in [self.offense_role, self.defense_role]:
            await self.send_error(session, pdu.ERR_INVALID_ROLE, "Role is not active for this turn")
            return
        if session.role in self.actions:
            await self.send_error(session, pdu.ERR_DUPLICATE_ACTION, "Duplicate action for this turn")
            return

        action_type = int(datagram.payload.get("action_type", 0))
        if not self.action_valid_for_role(session.role, action_type):
            await self.send_error(session, pdu.ERR_INVALID_ROLE, "Action is not valid for this role")
            return

        self.actions[session.role] = datagram.payload
        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_ACTION_ACK,
            "ACTION accepted",
            session_id=session.session_id,
            turn_id=self.turn_id,
            role=session.role,
            payload={"status": pdu.STATUS_SUCCESS},
        ))

        if self.offense_role in self.actions and self.defense_role in self.actions:
            self.main_state = "RESOLVE_TURN"
            await self.resolve_turn()
        elif session.role == self.offense_role:
            self.main_state = "WAIT_DEFENSE"
        else:
            self.main_state = "WAIT_OFFENSE"

    # close handler marks the session as closed and frees the assigned role
    async def handle_close(self, session: ClientSession, datagram: pdu.Datagram = None):
        await self.broadcast_close(session, "Opponent disconnected")
        session.closed = True
        self.cleanup_session(session)
        if self.log_protocol:
            print(f"[svr] session {session.session_id} closed")

    # error handler sends an ERROR message back to the client with a spec error code
    async def send_error(self, session: ClientSession, error_code:int, text: str):
        await session.send_pdu(pdu.Datagram(
            pdu.MSG_TYPE_ERROR,
            text,
            session_id=session.session_id,
            turn_id=self.turn_id,
            role=session.role,
            payload={"error_code": error_code, "error_text": text},
        ))

    # send CLOSE to the remaining peer when one side leaves the match
    async def broadcast_close(self, closed_session: ClientSession, text: str):
        for session in list(self.clients.values()):
            if session.session_id != closed_session.session_id and not session.closed:
                await session.send_pdu(pdu.Datagram(
                    pdu.MSG_TYPE_CLOSE,
                    text,
                    session_id=session.session_id,
                    turn_id=self.turn_id,
                    role=session.role,
                    payload={"close_reason": pdu.CLOSE_ERROR, "close_text": text},
                ))

    # broadcast a roster update to both clients when they have both joined, with their opponent's info
    async def broadcast_roster_update(self):
        home = self.clients[self.role_to_session[pdu.ROLE_HOME]]
        away = self.clients[self.role_to_session[pdu.ROLE_AWAY]]
        if self.log_protocol:
            print("[svr] both clients joined; sending ROSTER_UPDATE")

        for session in [home, away]:
            opponent = away if session.role == pdu.ROLE_HOME else home
            await session.send_pdu(pdu.Datagram(
                pdu.MSG_TYPE_ROSTER_UPDATE,
                "Opponent roster update",
                session_id=session.session_id,
                turn_id=self.turn_id,
                role=session.role,
                payload={
                    "team": opponent.team,
                    "player_count": len(opponent.players),
                    "players": opponent.players,
                    "opponent_role": opponent.role,
                },
            ))

    # sends current game state to both clients
    async def broadcast_game_update(self, result_text:str, result_code:int, batter_id:int = 1, pitcher_id:int = 3, payload:dict = None):
        home = self.clients.get(self.role_to_session.get(pdu.ROLE_HOME))
        away = self.clients.get(self.role_to_session.get(pdu.ROLE_AWAY))
        if not home or not away:
            return

        update_payload = payload or self.game_logic.current_update(result_text, result_code, batter_id, pitcher_id)
        self.offense_role = int(update_payload.get("offense_role", self.offense_role))
        self.defense_role = int(update_payload.get("defense_role", self.defense_role))
        if self.log_protocol:
            print("[svr] sending GAME_UPDATE")
        for session in [home, away]:
            await session.send_pdu(pdu.Datagram(
                pdu.MSG_TYPE_GAME_UPDATE,
                result_text,
                session_id=session.session_id,
                turn_id=self.turn_id,
                role=session.role,
                payload=update_payload,
            ))

    # resolves the turn by calling the injected game logic, then clears the actions and increments the turn id
    async def resolve_turn(self):
        offense_action = self.actions.get(self.offense_role, {})
        defense_action = self.actions.get(self.defense_role, {})
        update_payload = self.game_logic.resolve_play(offense_action, defense_action)
        result_text = update_payload.get("result_text", "Resolved turn")
        self.event_id = int(update_payload.get("event_id", self.event_id))
        self.offense_role = int(update_payload.get("offense_role", self.offense_role))
        self.defense_role = int(update_payload.get("defense_role", self.defense_role))
        self.actions.clear()
        self.turn_id += 1
        if self.game_logic.game_over:
            self.main_state = "GAME_OVER"
            await self.broadcast_game_over()
            return
        self.main_state = "WAIT_BOTH_ACTIONS"
        await self.broadcast_game_update(result_text, 0, payload=update_payload)

    # sends GAME_OVER to both clients when the injected game logic decides that the game is complete
    async def broadcast_game_over(self):
        home = self.clients.get(self.role_to_session.get(pdu.ROLE_HOME))
        away = self.clients.get(self.role_to_session.get(pdu.ROLE_AWAY))
        if not home or not away:
            return
        final_text = self.game_logic.final_text()
        if self.log_protocol:
            print("[svr] sending GAME_OVER")
        for session in [home, away]:
            await session.send_pdu(pdu.Datagram(
                pdu.MSG_TYPE_GAME_OVER,
                final_text,
                session_id=session.session_id,
                turn_id=self.turn_id,
                role=session.role,
                payload={
                    "home_score": self.game_logic.home_score,
                    "away_score": self.game_logic.away_score,
                    "winning_role": self.game_logic.winning_role(),
                    "final_text": final_text,
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

    # helper function to check if the action is valid for the current role
    def action_valid_for_role(self, role:int, action_type:int):
        if role == self.offense_role:
            return action_type in pdu.OFFENSE_ACTIONS
        if role == self.defense_role:
            return action_type in pdu.DEFENSE_ACTIONS
        return False

    # once a CLEAN message is received or a client disconnects, this function cleans up the session and 
    # frees the role for another client to join
    def cleanup_session(self, session: ClientSession):
        if self.role_to_session.get(session.role) == session.session_id:
            self.role_to_session.pop(session.role)
        self.actions.pop(session.role, None)
        self.clients.pop(session.session_id, None)
        session.role = pdu.ROLE_NONE
        session.ready = False
        if not self.role_to_session:
            self.reset_match_state()
    
    # resets the match state to the initial values,
    # ready for a new match to be set up once both clients have left or sent CLEAN
    def reset_match_state(self):
        self.game_logic.reset()
        self.turn_id = 1
        self.event_id = 1
        self.main_state = "SETUP"
        self.offense_role = self.game_logic.offense_role
        self.defense_role = self.game_logic.defense_role
        self.actions.clear()

    # helper function to check if both clients have joined
    def both_clients_joined(self):
        return pdu.ROLE_HOME in self.role_to_session and pdu.ROLE_AWAY in self.role_to_session

    # helper function to check if both clients are ready
    def both_clients_ready(self):
        if not self.both_clients_joined():
            return False
        home = self.clients[self.role_to_session[pdu.ROLE_HOME]]
        away = self.clients[self.role_to_session[pdu.ROLE_AWAY]]
        return home.ready and away.ready


SERVER_STATE = PhanatworkServerState()
