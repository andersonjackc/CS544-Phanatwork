# CS544-Phanatwork
Repository to hold the final project for Drexel's CS544.  

This is a QUIC based protocol to validate the messages sent between clients and a server, where the clients are playing a baseball game.  It is not application specific, as the protocol itself is simply validating the message types.

This repo contains the main v1.0 Phanatwork protocol client/server implementation as well as a simple baseball simulator.

Phanatwork is a stateful protocol utilizing QUIC transport, and has binary PDUs, so a client implemented in another language that follows the specifications would be able to communicate with the server as well.

## Implemented Features
- QUIC-based client/server comms
- Binary PDUs for both headers and all payloads
- Versioned protocol header
- DFA State validation on the server side
- Full Client setup sequence of HELLO -> AUTH -> JOIN -> ROSTER_UPDATE -> READY
- Full Gameplay loop of GAME_UPDATE -> PLAY_ACTION -> ACTION_ACK -> GAME_UPDATE (looping until GAME_OVER)
- CLOSE / ERROR handling
- Role assignment on the server side
- Basic authentication handling (hardcoded username and password, but the ability to tie in more sophisticated methods is there)
- Modified QUIC's default idle timeout from 1 minute to 5 minutes for easier testing and playing
- Session ID and Turn ID implementation so that the server can always ensure the correct actor is communicating at the right time
- Multiple play modes
    - Manual for playing as yourself, selecting the actions
    - Auto for simulating a game, or playing against a bot
- Set up ability for injecting game rules into the server setup for resolving the play, allowing dynamic rules
    - This also demonstrates the protocol being implementation independent.
- Configured Autotesting
    - DFA Validation pass and error tests
    - Malformed PDU tests
    - small fuzz testing


# Main File Summaries

`pdu.py` defines the Phanatwork binary message types. It contains the message/role/action/error constants and binary struct definitions. It also contains the serialization and deserialization methods.  Base version adapted from the class QUIC example.

`phanatwork_server.py` contains the server protocol loop that gets QUIC stream data, parses the PDUs, and passes the information onto the state machine.

`phanatwork_state.py` contains the server's state machine and is where the DFA validation logic occurs. It tracks the various client sessions, assigned roles, and the submitted actions.

`phanatwork_client.py` contains the client protocol sequence.  It sends the setup PDUs to the server, waits for responses from the server, and submits the actions during the gameplay loop.

`quic_engine.py` was adapted from the class example and slightly modified.  Handles the Phanatwork scope, different close connection implementation, and updated the default idle timeout.  It was also modified to be able to handle multiple clients.

`phanatwork.py` is a script designed to interact directly with the protocol with no direct gameplay rules required.  It is NOT the application layer baseball simulator, but a way to debug and interact with the Phanatwork message types directly.

`test_phanatwork_protocol.py` contains all of the automated tests of Phanatwork.  It provides DFA Validation, malformed PDU testing, and some simple fuzz testing.

`baseball_simulator/simple_baseball.py` contains the application layer rules of the baseball game.  It is completely separate from the protocol itself to show that the protocol is not tied to the game itself.

`baseball_app.py` is the main game simulator using Phanatwork as its transport protocol.  It imports the `simple_baseball.py` rules and then resolves the play of the actual game loop.  It shows no Phanatwork specific information, simply the CLI gameplay itself.  It allows for importing configuration files for ease of use.  The config file includes the server address, port number, display name, username, password, team name, role, play mode (auto/manual), delay (amount of time between moves for auto mode), turns (number of allowed turns before the game is forced to stop), and player dictionary. It can be configured to utilize different rulesets from `simple_baseball.py` on the server side, such as the normal rules but with only 3 innings for ease of testing, a "one-out" version that reduces the number of outs per half-inning from 3 to 1, and a shortened game of just 1 inning.  There is also a test "AlwaysOut" ruleset that is used for deterministic testing.

# Requirements
Phanatwork is developed using Python 3.10.18 and the ```aioquic``` package.  Other similar Python versions will most likely work but 3.10.18 is what I used for testing and development.

The python packages that were utilized are defined in the `requirements.txt` file and can be installed by running:
```python -m pip install -r requirements.txt```

# Certificates
Since Phanatwork is built upon QUIC, it needs certificates and private keys for TLS to work.  I utilized the `gencert.sh` script from the example project, and it has its own `README.md` that was provided in the example project.  I also have pushed the development certificate so regeneration should not be necessary until June of 2027.

## Running Phanatwork
The client and server can be run using the main UI baseball game app and a debugging script.  Both are detailed below, but the main script to run, use, and grade against is the `baseball_app.py` version.

You will need three terminals to run the Phanatwork example.  One to run the server, and then one for each client.

# Running the Server
You can run the server in a few different ways.  

To run the baseball game simulator version of the server, you can do either of the following.

```python baseball_app.py host``` will run the baseball simulator using all the default values.  So `localhost` for the server address, `4433` for the port number, the default cert path locations, the default normal baseball game ruleset, and no seed for reproducible game outcomes (that is, allowing for as random of a game outcome as possible).

It could also be run as
```python baseball_app.py host --listen localhost --port 4433 --cert-file ./certs/quic_certificate.pem --key-file ./certs/quic_private_key.pem --rule-set standard --seed 1234```

The rule-set argument can be any of "standard", "short", "one-out" and the seed argument can be omitted to allow for random games.

To run the Phanatwork protocol debugger version of the server, you can do either of the following.  This server is not much different from the baseball game simulator, as both still log what is occurring on the server side, but it does not run the game logic.

```python phanatwork.py server``` will run the debug server version with all of the default values for the server address, port number, cert path, and key path.

```python phanatwork.py server --listen localhost --port 4433 --cert-file ./certs/quic_certificate.pem --key-file ./certs/quic_private_key.pem``` will allow you to customize the address, port number and cert/key locations.

# Running the Client.
Similar to the server, you can run the client in a few ways.
```python baseball_app.py join``` will join an existing server using all of the default parameters.  That is localhost for address, 4433 for port number, the same cert file path as the default for the server, Team for team name, Player for display name, "either" for desired role, player for username, password for password, 9999 for number of turns, manual for the play mode, and 0.25 seconds for the delay between auto actions.

You can also pass all of these parameters in via the command line.
```python baseball_app.py join  --server localhost --port 4433 --cert-file ./certs/quic_certificate.pem --name Jack --team Phillies --role home --username home --password password --play-mode manual --turns 9999```

The easiest way to run it is by importing a config file in the following way:
```python baseball_app.py join --config-file path/to/config.json```
and some pre-configured configs have been provided in the `configs` folder.  A non-default path to the certificate would still be required via the CLI.

You can also interact directly with Phanatwork and see the deserialized payload datagrams for easier debugging.  A default instance can be run with:
```python phanatwork.py client```
which will default all of the server address, port number, cert path, display name, team name, role, username, password, play mode, and number of turns to their defaults.

Each of those can also be passed in as a CLI argument in the following way:
```python phanatwork.py client --server localhost --port 4433 --cert-file ./certs/quic_certificate.pem --name Player --team Team --role either --username player --password password --play-mode auto --turns 3```

# Game Flow
Once the server has been kicked off and both clients have gone through the HELLO -> AUTH -> JOIN process, the game begins. 

In manual mode, a prompt appears for the user to select their action.  Currently a minimal list of pitches / offense options.  Once the server has received the action from both users, it resolves the play via the predefined ruleset, and returns the new game state information to the users.  The users then get prompted for their next action.  This loop continues until the game ends.

The auto mode is nearly identical, except for an auto user is more like a bot.  It does not prompt for any input after the game begins, and randomly chooses an action to send to the server.  

You can have any combination of users, such as both manual, both auto, or one of each.

# Error Handling
Currently errors cause the Phanatwork protocol to send a terminal message to the clients.  Some errors are technically recoverable by design, such as an authentication issue for example, but development focus was directed at PDU implementation and DFA state validation.

# DFA Validation
The server checks the protocol state before accepting each message.

Examples of enforced state rules:

- A client cannot send `AUTH` before `HELLO`.
- A client cannot send `JOIN` before successful authentication.
- A client cannot send `READY` before both clients have joined.
- A client cannot send `PLAY_ACTION` before the game has started.
- A client cannot send a stale turn id.
- A client cannot send a duplicate action for the same turn.
- A client cannot send an offensive action while on defense.
- A client cannot send a defensive action while on offense.
- A third client cannot join once both home and away roles are filled.

This follows the DFA that was detailed in the specification document.

# Testing

The automated tests can be run by calling ```python test_phanatwork_protocol.py```

The testing utilizes fake peers to validate that the protocol is enforcing the DFA and correctly errors out on various malformed packet types.  Each test is detailed below in the output and an expected output would be as follows:

```
PHANATWORK PROTOCOL TEST SUMMARY
============================================================

DFA passing cases (6/6 passed)
------------------------------------------------------------
[PASS] HELLO -> AUTH -> JOIN succeeds                            
[PASS] Two clients joining triggers ROSTER_UPDATE                
[PASS] Both clients READY triggers initial GAME_UPDATE           
[PASS] Valid actions resolve a turn and increment turn_id        
[PASS] Injected one-out rules advance the half inning            
[PASS] Transport disconnect notifies opponent with server CLOSE  

DFA validation errors (9/9 passed)
------------------------------------------------------------
[PASS] AUTH before HELLO is rejected                             
[PASS] Wrong password is rejected                                
[PASS] JOIN before AUTH is rejected                              
[PASS] READY before both clients joined is rejected              
[PASS] PLAY_ACTION before READY is rejected                      
[PASS] Wrong action for current role is rejected                 
[PASS] Duplicate action in same turn is rejected                 
[PASS] Stale turn id is rejected                                 
[PASS] Client protocol CLOSE is rejected                         

Malformed PDU errors (4/4 passed)
------------------------------------------------------------
[PASS] Too-short PDU header returns MALFORMED_PDU                
[PASS] Unsupported major version returns UNSUPPORTED_VERSION     
[PASS] Oversized payload length returns PAYLOAD_TOO_LARGE        
[PASS] Incomplete payload returns MALFORMED_PDU                  

Fuzz testing (2/2 passed)
------------------------------------------------------------
[PASS] Random byte parser fuzzing is controlled                  
[PASS] Mutated valid PDU parser fuzzing is controlled            

============================================================
TOTAL: 21/21 passed
```

# Design Updates during Development

Some design updates I found to be required while developing Phanatwork are as follows:
- I determined that 1 minute for timing out while the user is idle is too short, as I frequently timed out during debugging.  This was updated to 5 minutes in the design document.
- I determined that the clients do not know all of the game information on the start of the gameplay, and needs an initial `GAME_UPDATE` message after both clients have sent their `READY` messages.  This has been added to the DFA as the transition action from `WAIT_READY` to `WAIT_BOTH_ACTIONS`.

# Development Simplifications
This project can be taken in several different directions, as there were some portions intentionally simplified.  They are as follows:
- The authentication method is extremely insecure, being a hardcoded plain-text "database".  This could be updated to a more sophisticated method relatively easily, but was not the point of the project.
- Baseball Game application level logic is overly simplified. The framework is implemented for more advanced functionality, such as outcomes based on the players statistics and further actions such as pickoffs or base stealing.
- While the server is concurrent, allowing multiple clients at a time, currently only one game can be played at any one time.
- The UI is all CLI based, but the framework is there for a more complex GUI to be developed, as Phanatwork is implementation independent.
- Error handling ends the client connection, but some errors should be recoverable.

# Final Note
This project was meant to focus on the protocol design, not a baseball game simulation.  The main focuses were:
- creating a client/server architecture using QUIC
- allowing for a configurable hostname and port number
- Stateful DFA validation
- Binary PDU serialization
- Automated testing





