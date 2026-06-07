import asyncio
import io
import random
import struct
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import List

import pdu
import phanatwork_server
from phanatwork_quic import PhanatworkQuicConnection, QuicStreamEvent
from phanatwork_state import PhanatworkServerState
from baseball_simulator.simple_baseball import OneOutBaseballRules, SimpleBaseballRules, AlwaysOutOneOutRules
from phanatwork_client import default_players

# abstrac test case results for easy reporting and debugging
@dataclass
class TestCaseResult:
    category: str
    name: str
    passed: bool
    details: str = ""

# create a fake client to simulate a QUIC connection and capture the messages sent
# by the server in response to test inputs, without needing a real network connection or client implementation. 
@dataclass
class TestPeer:
    session: object
    sent: List[pdu.Datagram] = field(default_factory=list)


class FakeConn:
    def __init__(self, inbound_events):
        self.inbound = asyncio.Queue()
        for event in inbound_events:
            self.inbound.put_nowait(event)
        self.sent = []
        self.closed = False

    async def receive(self):
        return await self.inbound.get()

    async def send(self, event):
        self.sent.append(event)

    def close(self):
        self.closed = True

# make the actual fake client
async def make_peer(state: PhanatworkServerState) -> TestPeer:
    peer = TestPeer(session=None)

    async def send_pdu(datagram: pdu.Datagram):
        peer.sent.append(datagram)

    peer.session = state.register_client(send_pdu)
    return peer

# helper functions to send specific PDUs to the server

async def send_hello(state, peer, name="Player"):
    await state.handle_pdu(peer.session, pdu.Datagram(
        pdu.MSG_TYPE_HELLO,
        "HELLO",
        payload={"name": name, "requested_major": 1, "requested_minor": 0, "option_flags": 0},
    ))


async def send_auth(state, peer, username="player", password="password"):
    await state.handle_pdu(peer.session, pdu.Datagram(
        pdu.MSG_TYPE_AUTH,
        "AUTH",
        session_id=peer.session.session_id,
        turn_id=state.turn_id,
        payload={"username": username, "password": password},
    ))


async def send_join(state, peer, team, role):
    await state.handle_pdu(peer.session, pdu.Datagram(
        pdu.MSG_TYPE_JOIN,
        "JOIN",
        session_id=peer.session.session_id,
        turn_id=state.turn_id,
        payload={"team": team, "requested_role": role, "players": default_players(team)},
    ))


async def send_ready(state, peer):
    await state.handle_pdu(peer.session, pdu.Datagram(
        pdu.MSG_TYPE_READY,
        "READY",
        session_id=peer.session.session_id,
        turn_id=state.turn_id,
        role=peer.session.role,
        payload={"ready": True},
    ))


async def send_action(state, peer, action_type, player_id=1, turn_id=None):
    await state.handle_pdu(peer.session, pdu.Datagram(
        pdu.MSG_TYPE_PLAY_ACTION,
        "PLAY_ACTION",
        session_id=peer.session.session_id,
        turn_id=state.turn_id if turn_id is None else turn_id,
        role=peer.session.role,
        payload={"action_type": action_type, "player_id": player_id},
    ))

# helper function to setup the server and
# get it to a state where two clients have joined and the match is ready to start, 
async def setup_joined_match():
    state = PhanatworkServerState(log_protocol=False)
    home = await make_peer(state)
    away = await make_peer(state)

    await send_hello(state, home, "Home")
    await send_auth(state, home, "home", "password")
    await send_join(state, home, "Home Team", pdu.ROLE_HOME)

    await send_hello(state, away, "Away")
    await send_auth(state, away, "away", "password")
    await send_join(state, away, "Away Team", pdu.ROLE_AWAY)

    return state, home, away

# helper function to setup the server and get it to a state where two clients have joined and both have sent ready, 
async def setup_ready_match():
    state, home, away = await setup_joined_match()
    clear_all(home, away)
    await send_ready(state, home)
    await send_ready(state, away)
    return state, home, away

# helper function to clear the sent messages for one or more peers
def clear_all(*peers):
    for peer in peers:
        peer.sent.clear()

# helper function to get the last message for easy test case reading
def last_message(peer: TestPeer):
    assert peer.sent, "expected the server to send a response"
    return peer.sent[-1]

# helper function to assert that the last message sent by the server is an error with a specific error code, for easy test case reading
def assert_error(peer: TestPeer, expected_code: int):
    msg = last_message(peer)
    assert msg.mtype == pdu.MSG_TYPE_ERROR, f"expected ERROR, got {pdu.msg_type_name(msg.mtype)}"
    actual_code = msg.payload.get("error_code")
    assert actual_code == expected_code, f"expected {pdu.error_name(expected_code)}, got {pdu.error_name(actual_code)}"

# helper function to assert that the last message sent by the server is of a specific type, for easy test case reading.
#  Returns the message for further assertions if needed.
def assert_last_type(peer: TestPeer, expected_type: int):
    msg = last_message(peer)
    assert msg.mtype == expected_type, f"expectd {pdu.msg_type_name(expected_type)}, got {pdu.msg_type_name(msg.mtype)}"
    return msg

# helper function to assert that at least one message sent by the server is of a specific type, for easy test case reading. 
def assert_contains_type(peer: TestPeer, expected_type: int):
    seen = [msg.mtype for msg in peer.sent]
    assert expected_type in seen, (
        f"expected to see {pdu.msg_type_name(expected_type)}, "
        f"got {[pdu.msg_type_name(mtype) for mtype in seen]}"
    )


#START OF TEST TEST CASES

# DFA Validation tests
# Tests for valid sequences of messages that should be accepted by the server and cause
#  expected state transitions and responses.

# test that the server properly goes through HELLO -> AUTH -> JOIN with valid inputs, 
# and that the assigned role is correct based on the requested role and server state
async def test_valid_hello_auth_join_sequence():
    state = PhanatworkServerState(log_protocol=False)
    peer = await make_peer(state)

    await send_hello(state, peer, "Solo")
    assert_last_type(peer, pdu.MSG_TYPE_HELLO_ACK)
    assert peer.session.setup_state == "WAIT_AUTH"

    await send_auth(state, peer, "solo", "password")
    assert_last_type(peer, pdu.MSG_TYPE_AUTH_RESULT)
    assert peer.session.setup_state == "WAIT_JOIN"

    await send_join(state, peer, "Solo Team", pdu.ROLE_HOME)
    join_ack = assert_last_type(peer, pdu.MSG_TYPE_JOIN_ACK)
    assert join_ack.payload.get("assigned_role") == pdu.ROLE_HOME
    assert peer.session.setup_state == "SETUP_COMPLETE"
    assert state.role_to_session[pdu.ROLE_HOME] == peer.session.session_id

# test that two clients can successfully join and that both receive the expected roster update message 
# with the correct info about both players and their assigned roles
async def test_valid_two_clients_join_triggers_roster_update():
    state, home, away = await setup_joined_match()

    assert state.main_state == "WAIT_READY"
    assert home.session.role == pdu.ROLE_HOME
    assert away.session.role == pdu.ROLE_AWAY
    assert_contains_type(home, pdu.MSG_TYPE_ROSTER_UPDATE)
    assert_contains_type(away, pdu.MSG_TYPE_ROSTER_UPDATE)

# verify that the server is in the right state when the clients btoh send ready
async def test_valid_ready_sequence_triggers_initial_game_update():
    state, home, away = await setup_ready_match()

    assert state.main_state == "WAIT_BOTH_ACTIONS"
    assert home.session.ready is True
    assert away.session.ready is True
    assert_contains_type(home, pdu.MSG_TYPE_GAME_UPDATE)
    assert_contains_type(away, pdu.MSG_TYPE_GAME_UPDATE)

    game_update = last_message(away)
    assert game_update.payload.get("offense_role") == pdu.ROLE_AWAY
    assert game_update.payload.get("defense_role") == pdu.ROLE_HOME



# verify that the game play loop goes into the proper states during actions
async def test_valid_complete_turn_resolves_and_increments_turn():
    state, home, away = await setup_ready_match()
    starting_turn = state.turn_id
    clear_all(home, away)

    await send_action(state, away, pdu.ACTION_BAT_SWING, player_id=1)
    assert_last_type(away, pdu.MSG_TYPE_ACTION_ACK)
    assert state.main_state == "WAIT_DEFENSE"
    assert state.turn_id == starting_turn

    await send_action(state, home, pdu.ACTION_PITCH_FASTBALL, player_id=3)
    assert_contains_type(home, pdu.MSG_TYPE_ACTION_ACK)
    assert_last_type(home, pdu.MSG_TYPE_GAME_UPDATE)
    assert_last_type(away, pdu.MSG_TYPE_GAME_UPDATE)
    assert state.main_state == "WAIT_BOTH_ACTIONS"
    assert state.turn_id == starting_turn + 1
    assert state.actions == {}

# verify that the server can use a different injected game rule set without changing the protocol handler
async def test_valid_injected_one_out_rules_advance_half_inning():
    state = PhanatworkServerState(AlwaysOutOneOutRules(innings=2), log_protocol=False)
    home = await make_peer(state)
    away = await make_peer(state)

    await send_hello(state, home, "Home")
    await send_auth(state, home, "home", "password")
    await send_join(state, home, "Home Team", pdu.ROLE_HOME)

    await send_hello(state, away, "Away")
    await send_auth(state, away, "away", "password")
    await send_join(state, away, "Away Team", pdu.ROLE_AWAY)

    clear_all(home, away)
    await send_ready(state, home)
    await send_ready(state, away)
    clear_all(home, away)

    await send_action(state, away, pdu.ACTION_BAT_SWING, player_id=1)
    await send_action(state, home, pdu.ACTION_PITCH_FASTBALL, player_id=3)

    game_update = last_message(away)
    assert game_update.mtype == pdu.MSG_TYPE_GAME_UPDATE
    assert game_update.payload.get("half_inning") == 1
    assert game_update.payload.get("offense_role") == pdu.ROLE_HOME
    assert game_update.payload.get("defense_role") == pdu.ROLE_AWAY


# verify that auth now rejects a known user with the wrong password
async def test_auth_wrong_password_is_rejected():
    state = PhanatworkServerState(log_protocol=False)
    peer = await make_peer(state)

    await send_hello(state, peer, "Bad Login")
    peer.sent.clear()
    await send_auth(state, peer, "home", "wrong-password")

    assert_error(peer, pdu.ERR_AUTH_FAILED)
    assert peer.session.setup_state == "WAIT_AUTH"

# verify that a client cannot send a protocol CLOSE, because CLOSE is server initiated only
# adding this as I initially, incorrectly, had the client be able to send it, which does not match the DFA
async def test_client_close_pdu_is_rejected():
    state, home, away = await setup_ready_match()
    clear_all(home, away)

    await state.handle_pdu(home.session, pdu.Datagram(
        pdu.MSG_TYPE_CLOSE,
        "CLOSE",
        session_id=home.session.session_id,
        turn_id=state.turn_id,
        role=home.session.role,
        payload={"close_reason": pdu.CLOSE_NORMAL, "close_text": "leaving"},
    ))

    assert_error(home, pdu.ERR_INVALID_STATE)
    assert away.sent == []
    assert home.session.closed is False

# verify that the server sends CLOSE to the remaining peer when a client connection disappears
async def test_transport_disconnect_notifies_opponent_with_server_close():
    state, home, away = await setup_ready_match()
    clear_all(home, away)

    await state.handle_close(home.session)

    assert_last_type(away, pdu.MSG_TYPE_CLOSE)
    assert home.sent == []
    assert home.session.closed is True


# DFA Invalid Tests
# Test that incorrect packets or out of order packets are rejected with the proper error

# test AUTH before HELLO
async def test_auth_before_hello():
    state = PhanatworkServerState(log_protocol=False)
    peer = await make_peer(state)
    await send_auth(state, peer)
    assert_error(peer, pdu.ERR_INVALID_STATE)

# test JOIN before AUTH
async def test_join_before_auth():
    state = PhanatworkServerState(log_protocol=False)
    peer = await make_peer(state)
    await send_hello(state, peer)
    peer.sent.clear()
    await send_join(state, peer, "Bad Team", pdu.ROLE_HOME)
    assert_error(peer, pdu.ERR_INVALID_STATE)

# test READY before both clients have joined and the server is in the WAIT_READY state
async def test_ready_before_both_joined():
    state = PhanatworkServerState(log_protocol=False)
    peer = await make_peer(state)
    await send_hello(state, peer)
    await send_auth(state, peer)
    await send_join(state, peer, "Lonely Team", pdu.ROLE_HOME)
    peer.sent.clear()
    await send_ready(state, peer)
    assert_error(peer, pdu.ERR_INVALID_STATE)

# test PLAY_ACTION before READY
async def test_play_action_before_ready():
    state, home, away = await setup_joined_match()
    clear_all(home, away)
    await send_action(state, away, pdu.ACTION_BAT_SWING)
    assert_error(away, pdu.ERR_INVALID_STATE)

# test that an invalid action for the assigned role is rejected with the proper error. 
async def test_wrong_action_for_role():
    state, home, away = await setup_ready_match()
    clear_all(home, away)
    # Away is offense in the current hardcoded game state, so a pitch is invalid for Away.
    await send_action(state, away, pdu.ACTION_PITCH_FASTBALL)
    assert_error(away, pdu.ERR_INVALID_ROLE)

# test that if a client tries to send two actions in the same turn, the second one is rejected with the proper error.
async def test_duplicate_action_same_turn():
    state, home, away = await setup_ready_match()
    clear_all(home, away)
    await send_action(state, away, pdu.ACTION_BAT_SWING)
    assert_last_type(away, pdu.MSG_TYPE_ACTION_ACK)
    away.sent.clear()
    await send_action(state, away, pdu.ACTION_BAT_TAKE)
    assert_error(away, pdu.ERR_DUPLICATE_ACTION)

# test that if a client tries to send an action with a turn_id that is too old, it is rejcted with the proper error.
async def test_stale_turn_id():
    state, home, away = await setup_ready_match()
    clear_all(home, away)
    await send_action(state, away, pdu.ACTION_BAT_SWING, turn_id=state.turn_id + 99)
    assert_error(away, pdu.ERR_STALE_TURN)


# Malformed Packet Tests

# helper function to run raw bytes through the server protocol handler and capture the responses, 
# for testing malformed packets and fuzzing
async def run_server_bytes(raw_bytes):
    """Run one raw byte string through the real server protocol handler."""
    stream_id = 0
    fake = FakeConn([
        QuicStreamEvent(stream_id, raw_bytes, False),
        QuicStreamEvent(stream_id, b"", True),
    ])
    old_state = phanatwork_server.SERVER_STATE
    phanatwork_server.SERVER_STATE = PhanatworkServerState(log_protocol=False)
    try:
        await phanatwork_server.phanatwork_server_proto({"stream_id": stream_id}, PhanatworkQuicConnection(
            fake.send,
            fake.receive,
            fake.close,
            None,
        ))
    finally:
        phanatwork_server.SERVER_STATE = old_state

    responses = []
    for event in fake.sent:
        responses.append(pdu.Datagram.from_bytes(event.data))
    return responses

# ensure we get at least one response and return it
async def run_server_bytes_expect_response(raw_bytes):
    responses = await run_server_bytes(raw_bytes)
    assert responses, "expected the server to send a response PDU"
    return responses[0]

# test that a short header that can't be parsed as a valid PDU is rejected with the proper error
async def test_short_header_malformed_pdu():
    response = await run_server_bytes_expect_response(b"short")
    assert response.mtype == pdu.MSG_TYPE_ERROR
    assert response.payload.get("error_code") == pdu.ERR_MALFORMED_PDU

# test that a header with an unsupported version is rejected with the proper error
async def test_unsupported_version_error():
    raw = pdu.Datagram(
        pdu.MSG_TYPE_HELLO,
        "HELLO",
        version_major=99,
        payload={"name": "Bad Version", "requested_major": 99, "requested_minor": 0, "option_flags": 0},
    ).to_bytes()
    response = await run_server_bytes_expect_response(raw)
    assert response.mtype == pdu.MSG_TYPE_ERROR
    assert response.payload.get("error_code") == pdu.ERR_UNSUPPORTED_VERSION

# test that a header that claims a payload larger than the actual bytes is rejected with the proper error
async def test_payload_too_large_error():
    raw = struct.pack(
        "!BBHHIIHI",
        pdu.SUPPORTED_MAJOR,
        pdu.SUPPORTED_MINOR,
        pdu.MSG_TYPE_HELLO,
        0,
        0,
        0,
        pdu.PHAN_HEADER_LEN_V1_0,
        pdu.PHAN_MAX_PAYLOAD_V1_0 + 1,
    )
    response = await run_server_bytes_expect_response(raw)
    assert response.mtype == pdu.MSG_TYPE_ERROR
    assert response.payload.get("error_code") == pdu.ERR_PAYLOAD_TOO_LARGE

# test that a header that claims a certain payload length but doesn't actually include that many bytes is rejected with the proper error
async def test_incomplete_payload_error():
    payload = b"abc"
    raw = struct.pack(
        "!BBHHIIHI",
        pdu.SUPPORTED_MAJOR,
        pdu.SUPPORTED_MINOR,
        pdu.MSG_TYPE_AUTH,
        0,
        1,
        1,
        pdu.PHAN_HEADER_LEN_V1_0,
        64,
    ) + payload
    response = await run_server_bytes_expect_response(raw)
    assert response.mtype == pdu.MSG_TYPE_ERROR
    assert response.payload.get("error_code") == pdu.ERR_MALFORMED_PDU

# fuzz tests 

async def test_fuzz_random_bytes_parser_never_crashes():
    # seed the RNG for reproducibility in the testing.
    # Allows for reproducibility of the tests
    rng = random.Random(1234)
    allowed_error_codes = {
        pdu.ERR_MALFORMED_PDU,
        pdu.ERR_UNSUPPORTED_VERSION,
        pdu.ERR_PAYLOAD_TOO_LARGE,
    }
    # Run 250 iterations of random bytes through the parser, and check that it either returns a Datagram or raises a known PduError, but does not crash or raise unexpected exceptions.
    for _ in range(250):
        size = rng.randint(0, 3000)
        raw = bytes(rng.getrandbits(8) for _ in range(size))
        try:
            parsed = pdu.Datagram.from_bytes(raw)
            assert isinstance(parsed, pdu.Datagram)
        except pdu.PduError as exc:
            assert exc.code in allowed_error_codes, f"unexpected parser error code {exc.code}"

# start with valid pdsu and randomly change some bytes 
# check that the server either parses it as a datagram or raises a known PduError 
# but doesnt crash or raise a different error. 
async def test_fuzz_mutated_valid_pdus_parser_never_crashes():
    rng = random.Random(1234)
    seeds = [
        pdu.Datagram(pdu.MSG_TYPE_HELLO, "HELLO", payload={"name": "Fuzz", "requested_major": 1, "requested_minor": 0, "option_flags": 0}).to_bytes(),
        pdu.Datagram(pdu.MSG_TYPE_AUTH, "AUTH", session_id=1, turn_id=1, payload={"username": "u", "password": "p"}).to_bytes(),
        pdu.Datagram(pdu.MSG_TYPE_READY, "READY", session_id=1, turn_id=1, role=pdu.ROLE_HOME, payload={"ready": True}).to_bytes(),
        pdu.Datagram(pdu.MSG_TYPE_PLAY_ACTION, "PLAY_ACTION", session_id=1, turn_id=1, role=pdu.ROLE_AWAY, payload={"action_type": pdu.ACTION_BAT_SWING, "player_id": 1}).to_bytes(),
    ]
    allowed_error_codes = {
        pdu.ERR_MALFORMED_PDU,
        pdu.ERR_UNSUPPORTED_VERSION,
        pdu.ERR_PAYLOAD_TOO_LARGE,
    }

    for _ in range(150):
        raw = bytearray(rng.choice(seeds))
        change_count = rng.randint(1, 8)
        for _ in range(change_count):
            index = rng.randrange(len(raw))
            raw[index] = rng.getrandbits(8)

        try:
            parsed = pdu.Datagram.from_bytes(bytes(raw))
            assert isinstance(parsed, pdu.Datagram)
        except pdu.PduError as exc:
            assert exc.code in allowed_error_codes, f"unexpected parser error code {exc.code}"

# list of all test cases to run, with categories and names for reporting
TESTS = [
    ("DFA passing cases", "HELLO -> AUTH -> JOIN succeeds", test_valid_hello_auth_join_sequence),
    ("DFA passing cases", "Two clients joining triggers ROSTER_UPDATE", test_valid_two_clients_join_triggers_roster_update),
    ("DFA passing cases", "Both clients READY triggers initial GAME_UPDATE", test_valid_ready_sequence_triggers_initial_game_update),
    ("DFA passing cases", "Valid actions resolve a turn and increment turn_id", test_valid_complete_turn_resolves_and_increments_turn),
    ("DFA passing cases", "Injected one-out rules advance the half inning", test_valid_injected_one_out_rules_advance_half_inning),
    ("DFA passing cases", "Transport disconnect notifies opponent with server CLOSE", test_transport_disconnect_notifies_opponent_with_server_close),

    ("DFA validation errors", "AUTH before HELLO is rejected", test_auth_before_hello),
    ("DFA validation errors", "Wrong password is rejected", test_auth_wrong_password_is_rejected),
    ("DFA validation errors", "JOIN before AUTH is rejected", test_join_before_auth),
    ("DFA validation errors", "READY before both clients joined is rejected", test_ready_before_both_joined),
    ("DFA validation errors", "PLAY_ACTION before READY is rejected", test_play_action_before_ready),
    ("DFA validation errors", "Wrong action for current role is rejected", test_wrong_action_for_role),
    ("DFA validation errors", "Duplicate action in same turn is rejected", test_duplicate_action_same_turn),
    ("DFA validation errors", "Stale turn id is rejected", test_stale_turn_id),
    ("DFA validation errors", "Client protocol CLOSE is rejected", test_client_close_pdu_is_rejected),

    ("Malformed PDU errors", "Too-short PDU header returns MALFORMED_PDU", test_short_header_malformed_pdu),
    ("Malformed PDU errors", "Unsupported major version returns UNSUPPORTED_VERSION", test_unsupported_version_error),
    ("Malformed PDU errors", "Oversized payload length returns PAYLOAD_TOO_LARGE", test_payload_too_large_error),
    ("Malformed PDU errors", "Incomplete payload returns MALFORMED_PDU", test_incomplete_payload_error),

    ("Fuzz testing", "Random byte parser fuzzing is controlled", test_fuzz_random_bytes_parser_never_crashes),
    ("Fuzz testing", "Mutated valid PDU parser fuzzing is controlled", test_fuzz_mutated_valid_pdus_parser_never_crashes),
]

# auto tester loop
async def run_all_tests():
    results = []
    for category, name, test_func in TESTS:
        test_output = io.StringIO()
        try:
            with redirect_stdout(test_output):
                await test_func()
            results.append(TestCaseResult(category, name, True))
        except AssertionError as exc:
            details = str(exc)
            if test_output.getvalue():
                details += "\n       Captured output:\n" + test_output.getvalue().rstrip()
            results.append(TestCaseResult(category, name, False, details))
        except Exception as exc:
            details = f"unexpected {type(exc).__name__}: {exc}"
            if test_output.getvalue():
                details += "\n       Captured output:\n" + test_output.getvalue().rstrip()
            results.append(TestCaseResult(category, name, False, details))
    return results

# print the output of the test cases
def print_summary(results):
    width = max(len(result.name) for result in results) + 2
    categories = []
    for result in results:
        if result.category not in categories:
            categories.append(result.category)

    print("\nPHANATWORK PROTOCOL TEST SUMMARY")
    print("=" * 60)
    for category in categories:
        category_results = [result for result in results if result.category == category]
        passed = sum(1 for result in category_results if result.passed)
        total = len(category_results)
        print(f"\n{category} ({passed}/{total} passed)")
        print("-" * 60)
        for result in category_results:
            mark = "PASS" if result.passed else "FAIL"
            print(f"[{mark}] {result.name:<{width}}")
            if result.details:
                print(f"       {result.details}")

    passed = sum(1 for result in results if result.passed)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"TOTAL: {passed}/{total} passed")


if __name__ == "__main__":
    print_summary(asyncio.run(run_all_tests()))
