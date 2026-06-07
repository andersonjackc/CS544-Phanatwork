from typing import Coroutine,Callable, Optional

# this was entirely copied from the example echo_quic.py example

class QuicStreamEvent():
    def __init__(self, stream_id, data, end_stream, close_reason = None, close_text = ""):
        self.stream_id = stream_id
        self.data = data
        self.end_stream = end_stream
        self.close_reason = close_reason
        self.close_text = close_text
        
class PhanatworkQuicConnection():
    def __init__(self, send:Coroutine[QuicStreamEvent, None, None], 
                 receive: Coroutine[None, None, QuicStreamEvent],
                 close:Optional[Callable[[], None]], 
                 new_stream:Optional[Callable[[], int]]):
        self.send = send
        self.receive = receive
        self.close = close
        self.new_stream = new_stream
