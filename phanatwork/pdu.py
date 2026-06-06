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

PHAN_HEADER_LEN_V1_0 = 20
PHAN_MAX_PAYLOAD_V1_0 = 2048
SUPPORTED_MAJOR = 1
SUPPORTED_MINOR = 0

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
        wrapper = {
            "role": self.role,
            "msg": self.msg,
            "payload": self.payload,
        }
        return json.dumps(wrapper, separators=(",", ":")).encode('utf-8')

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
        # and attempt to decode as JSON
        # TODO: Convert the payload format to a struct like the header
        # so that it is more accurate to a real protocol
        payload_start = header_len
        payload_end = payload_start + payload_len
        try:
            wrapper = json.loads(raw_bytes[payload_start:payload_end].decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PduError(ERR_MALFORMED_PDU, "Payload is not valid JSON") from exc

        return Datagram(
            mtype,
            wrapper.get("msg", ""),
            session_id=session_id,
            turn_id=turn_id,
            role=wrapper.get("role", ROLE_NONE),
            payload=wrapper.get("payload", {}),
            version_major=version_major,
            version_minor=version_minor,
            flags=flags,
            sz=payload_len,
        )


def msg_type_name(mtype:int):
    return MSG_TYPE_NAMES.get(mtype, f"UNKNOWN({mtype})")


def role_name(role:int):
    return ROLE_NAMES.get(role, f"UNKNOWN({role})")


def error_name(error_code:int):
    return ERROR_NAMES.get(error_code, f"UNKNOWN({error_code})")
