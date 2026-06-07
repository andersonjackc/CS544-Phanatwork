import argparse
import asyncio

import pdu
import phanatwork_server
import quic_engine
from baseball_simulator.config import load_client_config, convert_players, role_from_string, action_name
from baseball_simulator.simple_baseball import load_rules
import random

# configuring the Phanatwork server with the selected ruleset
# this option shows that the protocol is not handling the specific
# baseball game rules, just the message processing, since different 
# implementations could have different rules
def host_mode(args):
    print(r"""
        ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗ █████╗ ████████╗██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗
        ██╔══██╗██║  ██║██╔══██╗████╗  ██║██╔══██╗╚══██╔══╝██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝
        ██████╔╝███████║███████║██╔██╗ ██║███████║   ██║   ██║ █╗ ██║██║   ██║██████╔╝█████╔╝ 
        ██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║██╔══██║   ██║   ██║███╗██║██║   ██║██╔══██╗██╔═██╗ 
        ██║     ██║  ██║██║  ██║██║ ╚████║██║  ██║   ██║   ╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗
        ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝   ╚═╝    ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
    """)
    game_logic = load_rules(args.rule_set, args.seed)
    phanatwork_server.configure_server_state(game_logic, log_protocol=True)

    server_config = quic_engine.build_server_quic_config(args.cert_file, args.key_file)
    asyncio.run(quic_engine.run_server(args.listen, args.port, server_config, log_protocol=True))

# joining an existing hosted game, can be configured based on a config file as input
def join_mode(args):
    client_config = load_client_config(args.config_file)
    server_address = args.server or client_config.get("server", "localhost")
    server_port = args.port or int(client_config.get("port", 4433))
    cert_file = args.cert_file or client_config.get("cert_file", "./certs/quic_certificate.pem")
    team = args.team or client_config.get("team", "Team")

    scope = {
        "name": args.name or client_config.get("name", "Player"),
        "team": team,
        "role": role_from_string(args.role or client_config.get("role", "either")),
        "username": args.username or client_config.get("username", "player"),
        "password": args.password or client_config.get("password", "password"),
        "turns": args.turns if args.turns is not None else int(client_config.get("turns", 9999)),
        "play_mode": args.play_mode or client_config.get("play_mode", "manual"),
        "auto_delay": args.auto_delay if args.auto_delay is not None else float(client_config.get("auto_delay", 0.25)),
        "players": convert_players(client_config.get("players"), team),
        "log_protocol": False,
        "action_selector": select_baseball_action,
        "on_game_update": print_game_update,
        "on_game_over": print_game_over,
        "on_connection_close": print_connection_close,
        "on_protocol_error": print_protocol_error,
    }

    print(f"Joining baseball game as {scope['name']} / {team}")
    config = quic_engine.build_client_quic_config(cert_file)
    asyncio.run(quic_engine.run_client(server_address, server_port, config, scope))

# helper function to nicely print the information relevant to the game
def print_game_update(game_update):
    half = "Top" if game_update.get("half_inning") == 0 else "Bottom"
    away_team = game_update.get("away_team", "Away")
    home_team = game_update.get("home_team", "Home")
    batter_name = game_update.get("batter_name", f"Batter #{game_update.get('batter_id')}")
    pitcher_name = game_update.get("pitcher_name", f"Pitcher #{game_update.get('pitcher_id')}")
    print("\nGame update")
    print(f"  {half} {game_update.get('inning')} | Outs: {game_update.get('outs')} | Count: {game_update.get('balls')}-{game_update.get('strikes')}")
    print(f"  Score: {away_team} {game_update.get('away_score')} - {home_team} {game_update.get('home_score')}")
    print(f"  Hits: {away_team} {game_update.get('away_hits')} - {home_team} {game_update.get('home_hits')}")
    print(f"  Errors: {away_team} {game_update.get('away_errors')} - {home_team} {game_update.get('home_errors')}")
    print(f"  Batter: {batter_name} | Pitcher: {pitcher_name}")
    print(f"  {game_update.get('result_text')}")

# final game message summarizing the game
def print_game_over(game_over):
    away_team = game_over.get("away_team", "Away")
    home_team = game_over.get("home_team", "Home")
    print("\nGame over")
    print(f"  Final score: {away_team} {game_over.get('away_score')} - {home_team} {game_over.get('home_score')}")
    print(f"  {game_over.get('final_text')}")

# let the client know that the connection has been closed
def print_connection_close(close_text):
    print("\nConnection closed")
    print(f"  {close_text}")

# if there was a fatal error, tell the user
def print_protocol_error(error_text):
    print("\nGame connection error")
    print(f"  {error_text}")

# function to abstract how an action is selected, can either be automatically for "bot" mode or 
# in a prompt
def select_baseball_action(assigned_role:int, game_update:dict, players:list, play_mode:str):
    if play_mode == "auto":
        return select_auto_action(assigned_role, game_update)
    return prompt_baseball_action(assigned_role, game_update)

# auto action simply picks a random action
def select_auto_action(assigned_role:int, game_update:dict):
    if assigned_role == game_update.get("offense_role"):
        return random.choice(pdu.OFFENSE_ACTIONS)
    if assigned_role == game_update.get("defense_role"):
        return random.choice(pdu.DEFENSE_ACTIONS)
    return 0

# normal user level prompt for a action
def prompt_baseball_action(assigned_role:int, game_update:dict):
    if assigned_role == game_update.get("offense_role"):
        options = pdu.OFFENSE_ACTIONS
    elif assigned_role == game_update.get("defense_role"):
        options = pdu.DEFENSE_ACTIONS
    else:
        return 0

    print("\nChoose your play:")
    for index, action_type in enumerate(options, start=1):
        print(f"  {index}. {action_name(action_type)}")
    while True:
        selected = input("Action: ").strip().lower()
        for index, action_type in enumerate(options, start=1):
            if selected == str(index) or selected == action_name(action_type):
                return action_type
        print("Invalid action")


def parse_args():
    parser = argparse.ArgumentParser(description="Phanatwork baseball app")
    subparsers = parser.add_subparsers(dest="mode", help="Choose whether to host or join a baseball game", required=True)

    host_parser = subparsers.add_parser("host")
    host_parser.add_argument("-l", "--listen", default="localhost", help="Address to listen on")
    host_parser.add_argument("-p", "--port", type=int, default=4433, help="Port to listen on")
    host_parser.add_argument("-c", "--cert-file", default="./certs/quic_certificate.pem", help="Certificate file")
    host_parser.add_argument("-k", "--key-file", default="./certs/quic_private_key.pem", help="Private key file")
    host_parser.add_argument("--rule-set", default="standard", choices=["standard", "short", "one-out"], help="Baseball rule set")
    host_parser.add_argument("--seed", type=int, default=None, help="Random seed for repeatable games")

    join_parser = subparsers.add_parser("join")
    join_parser.add_argument("-s", "--server", default=None, help="Game host")
    join_parser.add_argument("-p", "--port", type=int, default=None, help="Game port")
    join_parser.add_argument("-c", "--cert-file", default=None, help="Certificate file")
    join_parser.add_argument("--config-file", default=None, help="JSON team/player config")
    join_parser.add_argument("-n", "--name", default=None, help="Display name")
    join_parser.add_argument("-t", "--team", default=None, help="Team name")
    join_parser.add_argument("-r", "--role", default=None, choices=["home", "away", "either"], help="Home, away, or either")
    join_parser.add_argument("-u", "--username", default=None, help="Username")
    join_parser.add_argument("--password", default=None, help="Password")
    join_parser.add_argument("--play-mode", default=None, choices=["manual", "auto"], help="Manual or automatic play")
    join_parser.add_argument("--auto-delay", type=float, default=None, help="Delay between automatic actions")
    join_parser.add_argument("--turns", type=int, default=None, help="Maximum number of turns to play before leaving")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.mode == "host":
        host_mode(args)
    elif args.mode == "join":
        join_mode(args)
