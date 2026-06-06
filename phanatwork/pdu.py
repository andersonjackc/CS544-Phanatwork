
import json

# message type constant defines, from the protocol spec doc
MSG_TYPE_HELLO           = 0x0001
MSG_TYPE_HELLO_ACK       = 0x0002
MSG_TYPE_AUTH            = 0x0003
MSG_TYPE_AUTH_ACK        = 0x0004
MSG_TYPE_JOIN            = 0x0005
MSG_TYPE_JOIN_ACK        = 0x0006
MSG_TYPE_ROSTER_UPDATE   = 0x0007
MSG_TYPE_READY           = 0x0008

# dummy message types for testing
MSG_TYPE_ECHO            = 0x0FFF
MSG_TYPE_ECHO_ACK        = 0x00FF

MSG_TYPE_PLAY_ACTION     = 0x0010
MSG_TYPE_PLAY_ACTION_ACK = 0x0011
MSG_TYPE_GAME_UPDATE     = 0x0012
MSG_TYPE_GAME_OVER       = 0x0013

MSG_TYPE_ERROR           = 0x00F0
MSG_TYPE_CLOSE           = 0x00F1

ROLE_NONE = 0
ROLE_HOME = 1
ROLE_AWAY = 2

ROLE_NAMES = {
    ROLE_NONE: "NONE",
    ROLE_HOME: "HOME",
    ROLE_AWAY: "AWAY",
}

MSG_TYPE_NAMES = {
    MSG_TYPE_HELLO: "HELLO",
    MSG_TYPE_HELLO_ACK: "HELLO_ACK",
    MSG_TYPE_AUTH: "AUTH",
    MSG_TYPE_AUTH_ACK: "AUTH_ACK",
    MSG_TYPE_JOIN: "JOIN",
    MSG_TYPE_JOIN_ACK: "JOIN_ACK",
    MSG_TYPE_ROSTER_UPDATE: "ROSTER_UPDATE",
    MSG_TYPE_READY: "READY",
    MSG_TYPE_ECHO: "ECHO",
    MSG_TYPE_ECHO_ACK: "ECHO_ACK",
    MSG_TYPE_PLAY_ACTION: "PLAY_ACTION",
    MSG_TYPE_PLAY_ACTION_ACK: "PLAY_ACTION_ACK",
    MSG_TYPE_GAME_UPDATE: "GAME_UPDATE",
    MSG_TYPE_GAME_OVER: "GAME_OVER",
    MSG_TYPE_ERROR: "ERROR",
    MSG_TYPE_CLOSE: "CLOSE"
}

class Datagram:
    def __init__(self, mtype: int, msg: str = "", session_id:int = 0,
                 turn_id:int = 0, role:int = ROLE_NONE, payload:dict = None,
                 version_major:int = 1, version_minor:int = 0, sz:int = 0):
        self.version_major = version_major
        self.version_minor = version_minor
        self.mtype = mtype
        self.session_id = session_id
        self.turn_id = turn_id
        self.role = role
        self.msg = msg
        self.payload = payload or {}
        self.sz = len(self.msg)
        
    def to_json(self):
        return json.dumps(self.__dict__)    
    
    @staticmethod
    def from_json(json_str):
        return Datagram(**json.loads(json_str))
    
    def to_bytes(self):
        return json.dumps(self.__dict__).encode('utf-8')
    
    @staticmethod
    def from_bytes(json_bytes):
        return Datagram(**json.loads(json_bytes.decode('utf-8')))    


def msg_type_name(mtype:int):
    return MSG_TYPE_NAMES.get(mtype, f"UNKNOWN({mtype})")


def role_name(role:int):
    return ROLE_NAMES.get(role, f"UNKNOWN({role})")
