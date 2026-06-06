import json
import struct

# message type constant defines, from the protocol spec doc
MSG_TYPE_HELLO           = 0x0001
MSG_TYPE_HELLO_ACK       = 0x0002
MSG_TYPE_AUTH            = 0x0003
MSG_TYPE_AUTH_RESULT     = 0x0004
MSG_TYPE_JOIN            = 0x0005
MSG_TYPE_JOIN_ACK        = 0x0006
MSG_TYPE_ROSTER_UPDATE   = 0x0007
MSG_TYPE_READY           = 0x0008

MSG_TYPE_PLAY_ACTION     = 0x0010
MSG_TYPE_ACTION_ACK      = 0x0011
MSG_TYPE_GAME_UPDATE     = 0x0012
MSG_TYPE_GAME_OVER       = 0x0013

MSG_TYPE_ERROR           = 0x00F0
MSG_TYPE_CLOSE           = 0x00F1

ROLE_NONE = 0
ROLE_HOME = 1
ROLE_AWAY = 2

STATUS_FAILURE = 0
STATUS_SUCCESS = 1

ERR_MALFORMED_PDU = 1
ERR_UNSUPPORTED_VERSION = 2
ERR_AUTH_FAILED = 3
ERR_INVALID_STATE = 4
ERR_INVALID_ROLE = 5
ERR_DUPLICATE_ACTION = 6
ERR_STALE_TURN = 7
ERR_PAYLOAD_TOO_LARGE = 8

CLOSE_NORMAL = 0
CLOSE_ERROR = 1
CLOSE_TIMEOUT = 2

ACTION_PITCH_FASTBALL = 1
ACTION_PITCH_CURVEBALL = 2
ACTION_PITCH_CHANGEUP = 3
ACTION_BAT_SWING = 16
ACTION_BAT_TAKE = 17
ACTION_BAT_BUNT = 18

OFFENSE_ACTIONS = [
    ACTION_BAT_SWING,
    ACTION_BAT_TAKE,
    ACTION_BAT_BUNT,
]

DEFENSE_ACTIONS = [
    ACTION_PITCH_FASTBALL,
    ACTION_PITCH_CURVEBALL,
    ACTION_PITCH_CHANGEUP,
]

#  Stats / Position / Status defines
STAT_BATTING_AVG_X1000 = 1
STAT_ON_BASE_X1000 = 2
STAT_SLUGGING_X1000 = 3
STAT_ERA_X100 = 4
STAT_WAR_X10 = 5

POS_UNKNOWN = 0
POS_PITCHER = 1
POS_CATCHER = 2
POS_FIRST_BASE = 3
POS_SECOND_BASE = 4
POS_THIRD_BASE = 5
POS_SHORTSTOP = 6
POS_LEFT_FIELD = 7
POS_CENTER_FIELD = 8
POS_RIGHT_FIELD = 9
POS_DESIGNATED_HITTER = 10

PLAYER_ACTIVE = 1
PLAYER_BENCH = 2
PLAYER_BULLPEN = 3
PLAYER_UNAVAILABLE = 4

PHAN_HEADER_LEN_V1_0 = 20
PHAN_MAX_PAYLOAD_V1_0 = 2048
SUPPORTED_MAJOR = 1
SUPPORTED_MINOR = 0
PHAN_NAME_LEN = 32
PHAN_TEXT_LEN = 64
PHAN_MAX_PLAYERS = 26
PHAN_PLAYER_STAT_SLOTS = 8

# ! = network byte order, big endiann
# B = unsigned char    = uint8_t  (for version_major)
# B = unsigned char    = uint8_t  (for version_minor)
# H = unsigned short   = uint16_t (for msg_type)
# H = unsigned short   = uint16_t (for flags)
# I = unsigned int     = uint32_t (for session_id)
# I = unsigned int     = uint32_t (for turn_id)
# H = unsigned short   = uint16_t (for header length)
# I = unsigned int     = uint32_t (for payload length)
_HEADER_STRUCT = struct.Struct("!BBHHIIHI")

# binary payload structures for v1.0 messages
# each of these match the payload formati
# that is specified in the spec.
# note that the JOIN and ROSTER_UPDATE
# have a special packing format of adding the 
# variable number of players and stats
_HELLO_STRUCT = struct.Struct("!32sBBI")
_HELLO_ACK_STRUCT = struct.Struct("!BBII")
_AUTH_STRUCT = struct.Struct("!32s32s")
_AUTH_RESULT_STRUCT = struct.Struct("!B64s")
_JOIN_PREFIX_STRUCT = struct.Struct("!B32sB")
_JOIN_ACK_STRUCT = struct.Struct("!BB64s")
_ROSTER_PREFIX_STRUCT = struct.Struct("!32sB")
_PLAYER_PREFIX_STRUCT = struct.Struct("!I32sBBBB")
_PLAYER_STAT_STRUCT = struct.Struct("!HBh")
_READY_STRUCT = struct.Struct("!B")
_PLAY_ACTION_STRUCT = struct.Struct("!BI")
_ACTION_ACK_STRUCT = struct.Struct("!B")
_GAME_UPDATE_STRUCT = struct.Struct("!IIIBBBBBBBBBBBBBBH64s")
_GAME_OVER_STRUCT = struct.Struct("!HHB64s")
_ERROR_STRUCT = struct.Struct("!H64s")
_CLOSE_STRUCT = struct.Struct("!H64s")

ROLE_NAMES = {
    ROLE_NONE: "NONE",
    ROLE_HOME: "HOME",
    ROLE_AWAY: "AWAY",
}

MSG_TYPE_NAMES = {
    MSG_TYPE_HELLO: "HELLO",
    MSG_TYPE_HELLO_ACK: "HELLO_ACK",
    MSG_TYPE_AUTH: "AUTH",
    MSG_TYPE_AUTH_RESULT: "AUTH_RESULT",
    MSG_TYPE_JOIN: "JOIN",
    MSG_TYPE_JOIN_ACK: "JOIN_ACK",
    MSG_TYPE_ROSTER_UPDATE: "ROSTER_UPDATE",
    MSG_TYPE_READY: "READY",
    MSG_TYPE_PLAY_ACTION: "PLAY_ACTION",
    MSG_TYPE_ACTION_ACK: "ACTION_ACK",
    MSG_TYPE_GAME_UPDATE: "GAME_UPDATE",
    MSG_TYPE_GAME_OVER: "GAME_OVER",
    MSG_TYPE_ERROR: "ERROR",
    MSG_TYPE_CLOSE: "CLOSE"
}

ERROR_NAMES = {
    ERR_MALFORMED_PDU: "MALFORMED_PDU",
    ERR_UNSUPPORTED_VERSION: "UNSUPPORTED_VERSION",
    ERR_AUTH_FAILED: "AUTH_FAILED",
    ERR_INVALID_STATE: "INVALID_STATE",
    ERR_INVALID_ROLE: "INVALID_ROLE",
    ERR_DUPLICATE_ACTION: "DUPLICATE_ACTION",
    ERR_STALE_TURN: "STALE_TURN",
    ERR_PAYLOAD_TOO_LARGE: "PAYLOAD_TOO_LARGE",
}

class PduError(Exception):
    def __init__(self, code:int, text:str):
        super().__init__(text)
        self.code = code
        self.text = text

class Datagram:
    def __init__(self, mtype: int, msg: str = "", session_id:int = 0,
                 turn_id:int = 0, role:int = ROLE_NONE, payload:dict = None,
                 version_major:int = SUPPORTED_MAJOR, version_minor:int = SUPPORTED_MINOR,
                 flags:int = 0, sz:int = 0):
        self.version_major = version_major
        self.version_minor = version_minor
        self.mtype = mtype
        self.flags = flags
        self.session_id = session_id
        self.turn_id = turn_id
        self.role = role
        self.msg = msg
        self.payload = payload or {}
        self.sz = len(self.msg)
        if sz:
            self.sz = sz

    def to_json(self):
        return json.dumps(self.__dict__)

    @staticmethod
    def from_json(json_str):
        return Datagram(**json.loads(json_str))

    # helper function to convert the payload dict to bytes for sending over the wire
    def payload_bytes(self):
        return pack_payload(self.mtype, self.payload, self.msg)

    def to_bytes(self):
        payload_bytes = self.payload_bytes()
        payload_len = len(payload_bytes)

        # enforce max payload size for the protocol version, and raise an error if exceeded
        if payload_len > PHAN_MAX_PAYLOAD_V1_0:
            raise PduError(ERR_PAYLOAD_TOO_LARGE, "Payload too large")
        
        # pack the header fields into bytes using the struct to 
        # ensure correct byte order and field sizes, then concatenate with the payload bytes
        header = _HEADER_STRUCT.pack(
            self.version_major,
            self.version_minor,
            self.mtype,
            self.flags,
            self.session_id,
            self.turn_id,
            PHAN_HEADER_LEN_V1_0,
            payload_len,
        )
        return header + payload_bytes

    @staticmethod
    def from_bytes(raw_bytes):
        if len(raw_bytes) < PHAN_HEADER_LEN_V1_0:
            raise PduError(ERR_MALFORMED_PDU, "PDU header is too short")

        # unpacking the header from the raw bytes
        version_major, version_minor, mtype, flags, session_id, turn_id, header_len, payload_len = _HEADER_STRUCT.unpack(raw_bytes[:PHAN_HEADER_LEN_V1_0])

        # error handle the various conditions that could indicate a malformed or unsupported PDU
        if version_major != SUPPORTED_MAJOR:
            raise PduError(ERR_UNSUPPORTED_VERSION, "Unsupported protocol major version")
        if header_len < PHAN_HEADER_LEN_V1_0:
            raise PduError(ERR_MALFORMED_PDU, "Invalid header length")
        if payload_len > PHAN_MAX_PAYLOAD_V1_0:
            raise PduError(ERR_PAYLOAD_TOO_LARGE, "Payload too large")
        if len(raw_bytes) < header_len + payload_len:
            raise PduError(ERR_MALFORMED_PDU, "PDU payload is incomplete")

        # extract the payload bytes based on the header length and payload length, 
        # and decode it according to the message type
        payload_start = header_len
        payload_end = payload_start + payload_len
        payload, msg, role = unpack_payload(mtype, raw_bytes[payload_start:payload_end])

        return Datagram(
            mtype,
            msg,
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            payload=payload,
            version_major=version_major,
            version_minor=version_minor,
            flags=flags,
            sz=payload_len,
        )

# pack the payload dict into byte structs according to the message type
# this ensures that the payload is formatted correctly according to the spec
# and that the packets are generic so that any client can interpret them as long as they follow the spec, \
# without needing to understand the internal structure of the payload dict
def pack_payload(mtype:int, payload:dict, msg:str = ""):
    if mtype == MSG_TYPE_HELLO:
        return _HELLO_STRUCT.pack(
            pack_text(payload.get("name", "player"), PHAN_NAME_LEN),
            int(payload.get("requested_major", SUPPORTED_MAJOR)),
            int(payload.get("requested_minor", SUPPORTED_MINOR)),
            int(payload.get("option_flags", 0)),
        )
    if mtype == MSG_TYPE_HELLO_ACK:
        return _HELLO_ACK_STRUCT.pack(
            int(payload.get("accepted_major", SUPPORTED_MAJOR)),
            int(payload.get("accepted_minor", SUPPORTED_MINOR)),
            int(payload.get("accepted_options", 0)),
            int(payload.get("session_id", 0)),
        )
    if mtype == MSG_TYPE_AUTH:
        return _AUTH_STRUCT.pack(
            pack_text(payload.get("username", ""), PHAN_NAME_LEN),
            pack_text(payload.get("password", ""), PHAN_NAME_LEN),
        )
    if mtype == MSG_TYPE_AUTH_RESULT:
        return _AUTH_RESULT_STRUCT.pack(
            int(payload.get("status", STATUS_FAILURE)),
            pack_text(payload.get("message", msg), PHAN_TEXT_LEN),
        )
    if mtype == MSG_TYPE_JOIN:
        # JOIN has a special packing format due to the variable number of
        # players and stats.  It looops through the players in the 
        # payload and packs each one according to the spec, then concatenates them together
        players = payload.get("players", [])[:PHAN_MAX_PLAYERS]
        team_name = payload.get("team", payload.get("team_name", "Team"))
        data = _JOIN_PREFIX_STRUCT.pack(
            int(payload.get("requested_role", ROLE_NONE)),
            pack_text(team_name, PHAN_NAME_LEN),
            len(players),
        )
        for player in players:
            data += pack_player(player)
        return data
    if mtype == MSG_TYPE_JOIN_ACK:
        return _JOIN_ACK_STRUCT.pack(
            int(payload.get("status", STATUS_FAILURE)),
            int(payload.get("assigned_role", ROLE_NONE)),
            pack_text(payload.get("message", msg), PHAN_TEXT_LEN),
        )
    if mtype == MSG_TYPE_ROSTER_UPDATE:
        # similar to JOIN, the ROSTER_UPDATE has a variable number of players and 
        # stats, so it loops through and packs each one
        players = payload.get("players", [])[:PHAN_MAX_PLAYERS]
        team_name = payload.get("team", payload.get("team_name", "Team"))
        data = _ROSTER_PREFIX_STRUCT.pack(
            pack_text(team_name, PHAN_NAME_LEN),
            len(players),
        )
        for player in players:
            data += pack_player(player)
        return data
    if mtype == MSG_TYPE_READY:
        return _READY_STRUCT.pack(1 if payload.get("ready", True) else 0)
    if mtype == MSG_TYPE_PLAY_ACTION:
        return _PLAY_ACTION_STRUCT.pack(
            int(payload.get("action_type", 0)),
            int(payload.get("player_id", 0)),
        )
    if mtype == MSG_TYPE_ACTION_ACK:
        return _ACTION_ACK_STRUCT.pack(int(payload.get("status", STATUS_FAILURE)))
    if mtype == MSG_TYPE_GAME_UPDATE:
        return _GAME_UPDATE_STRUCT.pack(
            int(payload.get("event_id", 0)),
            int(payload.get("batter_id", 0)),
            int(payload.get("pitcher_id", 0)),
            int(payload.get("inning", 1)),
            int(payload.get("half_inning", 0)),
            int(payload.get("outs", 0)),
            int(payload.get("balls", 0)),
            int(payload.get("strikes", 0)),
            int(payload.get("bases", 0)),
            int(payload.get("offense_role", ROLE_NONE)),
            int(payload.get("defense_role", ROLE_NONE)),
            int(payload.get("home_score", 0)),
            int(payload.get("home_hits", 0)),
            int(payload.get("home_errors", 0)),
            int(payload.get("away_score", 0)),
            int(payload.get("away_hits", 0)),
            int(payload.get("away_errors", 0)),
            int(payload.get("result_code", 0)),
            pack_text(payload.get("result_text", msg), PHAN_TEXT_LEN),
        )
    if mtype == MSG_TYPE_GAME_OVER:
        return _GAME_OVER_STRUCT.pack(
            int(payload.get("home_score", 0)),
            int(payload.get("away_score", 0)),
            int(payload.get("winning_role", ROLE_NONE)),
            pack_text(payload.get("final_text", msg), PHAN_TEXT_LEN),
        )
    if mtype == MSG_TYPE_ERROR:
        return _ERROR_STRUCT.pack(
            int(payload.get("error_code", ERR_MALFORMED_PDU)),
            pack_text(payload.get("error_text", msg), PHAN_TEXT_LEN),
        )
    if mtype == MSG_TYPE_CLOSE:
        return _CLOSE_STRUCT.pack(
            int(payload.get("close_reason", CLOSE_NORMAL)),
            pack_text(payload.get("close_text", msg), PHAN_TEXT_LEN),
        )
    return b""

# unpack the payload bytes into a Python dict according to the message type and
# the struct format from the spec.  This is the reverse of the pack_payload func
def unpack_payload(mtype:int, payload_bytes:bytes):
    if mtype == MSG_TYPE_HELLO:
        require_payload_len(payload_bytes, _HELLO_STRUCT.size, "HELLO")
        name, requested_major, requested_minor, option_flags = _HELLO_STRUCT.unpack(payload_bytes[:_HELLO_STRUCT.size])
        return {
            "name": unpack_text(name),
            "requested_major": requested_major,
            "requested_minor": requested_minor,
            "option_flags": option_flags,
        }, "HELLO", ROLE_NONE
    if mtype == MSG_TYPE_HELLO_ACK:
        require_payload_len(payload_bytes, _HELLO_ACK_STRUCT.size, "HELLO_ACK")
        accepted_major, accepted_minor, accepted_options, session_id = _HELLO_ACK_STRUCT.unpack(payload_bytes[:_HELLO_ACK_STRUCT.size])
        return {
            "accepted_major": accepted_major,
            "accepted_minor": accepted_minor,
            "accepted_options": accepted_options,
            "session_id": session_id,
        }, "HELLO accepted", ROLE_NONE
    if mtype == MSG_TYPE_AUTH:
        require_payload_len(payload_bytes, _AUTH_STRUCT.size, "AUTH")
        username, password = _AUTH_STRUCT.unpack(payload_bytes[:_AUTH_STRUCT.size])
        return {
            "username": unpack_text(username),
            "password": unpack_text(password),
        }, "AUTH", ROLE_NONE
    if mtype == MSG_TYPE_AUTH_RESULT:
        require_payload_len(payload_bytes, _AUTH_RESULT_STRUCT.size, "AUTH_RESULT")
        status, message = _AUTH_RESULT_STRUCT.unpack(payload_bytes[:_AUTH_RESULT_STRUCT.size])
        text = unpack_text(message)
        return {"status": status, "message": text}, text, ROLE_NONE
    if mtype == MSG_TYPE_JOIN:
        require_payload_len(payload_bytes, _JOIN_PREFIX_STRUCT.size, "JOIN")
        requested_role, team_name, player_count = _JOIN_PREFIX_STRUCT.unpack(payload_bytes[:_JOIN_PREFIX_STRUCT.size])
        players = unpack_players(payload_bytes[_JOIN_PREFIX_STRUCT.size:], player_count)
        return {
            "requested_role": requested_role,
            "team": unpack_text(team_name),
            "player_count": player_count,
            "players": players,
        }, "JOIN", ROLE_NONE
    if mtype == MSG_TYPE_JOIN_ACK:
        require_payload_len(payload_bytes, _JOIN_ACK_STRUCT.size, "JOIN_ACK")
        status, assigned_role, message = _JOIN_ACK_STRUCT.unpack(payload_bytes[:_JOIN_ACK_STRUCT.size])
        text = unpack_text(message)
        return {
            "status": status,
            "assigned_role": assigned_role,
            "message": text,
        }, text, assigned_role
    if mtype == MSG_TYPE_ROSTER_UPDATE:
        require_payload_len(payload_bytes, _ROSTER_PREFIX_STRUCT.size, "ROSTER_UPDATE")
        team_name, player_count = _ROSTER_PREFIX_STRUCT.unpack(payload_bytes[:_ROSTER_PREFIX_STRUCT.size])
        players = unpack_players(payload_bytes[_ROSTER_PREFIX_STRUCT.size:], player_count)
        return {
            "team": unpack_text(team_name),
            "player_count": player_count,
            "players": players,
        }, "Opponent roster update", ROLE_NONE
    if mtype == MSG_TYPE_READY:
        require_payload_len(payload_bytes, _READY_STRUCT.size, "READY")
        ready, = _READY_STRUCT.unpack(payload_bytes[:_READY_STRUCT.size])
        return {"ready": bool(ready)}, "READY", ROLE_NONE
    if mtype == MSG_TYPE_PLAY_ACTION:
        require_payload_len(payload_bytes, _PLAY_ACTION_STRUCT.size, "PLAY_ACTION")
        action_type, player_id = _PLAY_ACTION_STRUCT.unpack(payload_bytes[:_PLAY_ACTION_STRUCT.size])
        return {"action_type": action_type, "player_id": player_id}, "PLAY_ACTION", ROLE_NONE
    if mtype == MSG_TYPE_ACTION_ACK:
        require_payload_len(payload_bytes, _ACTION_ACK_STRUCT.size, "ACTION_ACK")
        status, = _ACTION_ACK_STRUCT.unpack(payload_bytes[:_ACTION_ACK_STRUCT.size])
        return {"status": status}, "ACTION accepted", ROLE_NONE
    if mtype == MSG_TYPE_GAME_UPDATE:
        require_payload_len(payload_bytes, _GAME_UPDATE_STRUCT.size, "GAME_UPDATE")
        values = _GAME_UPDATE_STRUCT.unpack(payload_bytes[:_GAME_UPDATE_STRUCT.size])
        result_text = unpack_text(values[18])
        return {
            "event_id": values[0],
            "batter_id": values[1],
            "pitcher_id": values[2],
            "inning": values[3],
            "half_inning": values[4],
            "outs": values[5],
            "balls": values[6],
            "strikes": values[7],
            "bases": values[8],
            "offense_role": values[9],
            "defense_role": values[10],
            "home_score": values[11],
            "home_hits": values[12],
            "home_errors": values[13],
            "away_score": values[14],
            "away_hits": values[15],
            "away_errors": values[16],
            "result_code": values[17],
            "result_text": result_text,
        }, result_text, ROLE_NONE
    if mtype == MSG_TYPE_GAME_OVER:
        require_payload_len(payload_bytes, _GAME_OVER_STRUCT.size, "GAME_OVER")
        home_score, away_score, winning_role, final_text = _GAME_OVER_STRUCT.unpack(payload_bytes[:_GAME_OVER_STRUCT.size])
        text = unpack_text(final_text)
        return {
            "home_score": home_score,
            "away_score": away_score,
            "winning_role": winning_role,
            "final_text": text,
        }, text, winning_role
    if mtype == MSG_TYPE_ERROR:
        require_payload_len(payload_bytes, _ERROR_STRUCT.size, "ERROR")
        error_code, error_text = _ERROR_STRUCT.unpack(payload_bytes[:_ERROR_STRUCT.size])
        text = unpack_text(error_text)
        return {"error_code": error_code, "error_text": text}, text, ROLE_NONE
    if mtype == MSG_TYPE_CLOSE:
        require_payload_len(payload_bytes, _CLOSE_STRUCT.size, "CLOSE")
        close_reason, close_text = _CLOSE_STRUCT.unpack(payload_bytes[:_CLOSE_STRUCT.size])
        text = unpack_text(close_text)
        return {"close_reason": close_reason, "close_text": text}, text, ROLE_NONE
    if len(payload_bytes) != 0:
        raise PduError(ERR_MALFORMED_PDU, "Unknown message type has non-empty payload")
    return {}, msg_type_name(mtype), ROLE_NONE

# helper to pack a specific player dict into the byte structs
# to be used in the JOIN and ROSTER_UPDATE messag's pack case, 
def pack_player(player:dict):
    stats = player.get("stats", [])[:PHAN_PLAYER_STAT_SLOTS]
    data = _PLAYER_PREFIX_STRUCT.pack(
        int(player.get("player_id", 0)),
        pack_text(player.get("player_name", "Player"), PHAN_NAME_LEN),
        int(player.get("lineup_slot", 0)),
        int(player.get("position", 0)),
        int(player.get("player_status", 1)),
        len(stats),
    )
    for stat in stats:
        data += _PLAYER_STAT_STRUCT.pack(
            int(stat.get("stat_id", 0)),
            int(stat.get("scale", 0)),
            int(stat.get("stat_value", 0)),
        )
    return data

# helper to unpack the variable number of players and stats in the JOIN and ROSTER_UPDATE messages
def unpack_players(payload_bytes:bytes, player_count:int):
    if player_count > PHAN_MAX_PLAYERS:
        raise PduError(ERR_MALFORMED_PDU, "Too many players in payload")

    offset = 0
    players = []
    for _ in range(player_count):
        if len(payload_bytes) < offset + _PLAYER_PREFIX_STRUCT.size:
            raise PduError(ERR_MALFORMED_PDU, "Player data is incomplete")
        player_id, player_name, lineup_slot, position, player_status, stat_count = _PLAYER_PREFIX_STRUCT.unpack(payload_bytes[offset:offset + _PLAYER_PREFIX_STRUCT.size])
        offset += _PLAYER_PREFIX_STRUCT.size
        if stat_count > PHAN_PLAYER_STAT_SLOTS:
            raise PduError(ERR_MALFORMED_PDU, "Too many stats in player payload")
        stats = []
        for _ in range(stat_count):
            if len(payload_bytes) < offset + _PLAYER_STAT_STRUCT.size:
                raise PduError(ERR_MALFORMED_PDU, "Player stat data is incomplete")
            stat_id, scale, stat_value = _PLAYER_STAT_STRUCT.unpack(payload_bytes[offset:offset + _PLAYER_STAT_STRUCT.size])
            offset += _PLAYER_STAT_STRUCT.size
            stats.append({"stat_id": stat_id, "scale": scale, "stat_value": stat_value})
        players.append({
            "player_id": player_id,
            "player_name": unpack_text(player_name),
            "lineup_slot": lineup_slot,
            "position": position,
            "player_status": player_status,
            "stats": stats,
        })
    if offset != len(payload_bytes):
        raise PduError(ERR_MALFORMED_PDU, "Extra player bytes in payload")
    return players

# pack a specific text field into a fixed byte size format with null paddng
def pack_text(text:str, size:int):
    encoded = str(text).encode('utf-8')[:size]
    return encoded + b'\x00' * (size - len(encoded))

# take a possibled padded text and decode it to UTF-8 text
def unpack_text(raw_text:bytes):
    return raw_text.split(b'\x00', 1)[0].decode('utf-8', errors='replace')


def require_payload_len(payload_bytes:bytes, expected:int, msg_name:str):
    if len(payload_bytes) < expected:
        raise PduError(ERR_MALFORMED_PDU, f"{msg_name} payload is too short")


def msg_type_name(mtype:int):
    return MSG_TYPE_NAMES.get(mtype, f"UNKNOWN({mtype})")


def role_name(role:int):
    return ROLE_NAMES.get(role, f"UNKNOWN({role})")


def error_name(error_code:int):
    return ERROR_NAMES.get(error_code, f"UNKNOWN({error_code})")
