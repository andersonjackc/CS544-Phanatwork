import json

import pdu

# helper functions for loading from the config file

# helper function to load client config from a JSON file when provided
def load_client_config(config_file):
    if not config_file:
        return {}
    with open(config_file, "r", encoding="utf-8") as file:
        return json.load(file)

# helper function to normalize player config values into the enum constants used by the PDU layer
def convert_players(players, team_name):
    if not players:
        return None
    normalized_players = []
    for player in players:
        normalized_player = dict(player)
        normalized_player["player_id"] = int(normalized_player.get("player_id", len(normalized_players) + 1))
        normalized_player["player_name"] = normalized_player.get("player_name", team_name + " Player")
        normalized_player["lineup_slot"] = int(normalized_player.get("lineup_slot", 0))
        normalized_player["position"] = position_from_string(normalized_player.get("position", pdu.POS_UNKNOWN))
        normalized_player["player_status"] = player_status_from_string(normalized_player.get("player_status", pdu.PLAYER_ACTIVE))
        normalized_player["stats"] = convert_stats(normalized_player.get("stats", []))
        normalized_players.append(normalized_player)
    return normalized_players


# helper function to normalize player stat config values into the enum constants used by the PDU layer
def convert_stats(stats):
    normalized_stats = []
    for stat in stats:
        normalized_stat = dict(stat)
        normalized_stat["stat_id"] = stat_from_string(normalized_stat.get("stat_id", 0))
        normalized_stat["scale"] = int(normalized_stat.get("scale", 0))
        normalized_stat["stat_value"] = int(normalized_stat.get("stat_value", 0))
        normalized_stats.append(normalized_stat)
    return normalized_stats

# helper function to convert stat strings from JSON config to protocol constants
def stat_from_string(stat_name):
    if isinstance(stat_name, int):
        return stat_name
    value = str(stat_name).lower().replace(" ", "_").replace("-", "_")
    stat_map = {
        "batting_avg_x1000": pdu.STAT_BATTING_AVG_X1000,
        "batting_average_x1000": pdu.STAT_BATTING_AVG_X1000,
        "on_base_x1000": pdu.STAT_ON_BASE_X1000,
        "obp_x1000": pdu.STAT_ON_BASE_X1000,
        "slugging_x1000": pdu.STAT_SLUGGING_X1000,
        "slg_x1000": pdu.STAT_SLUGGING_X1000,
        "era_x100": pdu.STAT_ERA_X100,
        "war_x10": pdu.STAT_WAR_X10,
    }
    return stat_map.get(value, 0)

# helper function to convert player position strings from JSON config to protocol constants
def position_from_string(position_name):
    if isinstance(position_name, int):
        return position_name
    value = str(position_name).lower().replace(" ", "_").replace("-", "_")
    position_map = {
        "pitcher": pdu.POS_PITCHER,
        "catcher": pdu.POS_CATCHER,
        "first_base": pdu.POS_FIRST_BASE,
        "second_base": pdu.POS_SECOND_BASE,
        "third_base": pdu.POS_THIRD_BASE,
        "shortstop": pdu.POS_SHORTSTOP,
        "left_field": pdu.POS_LEFT_FIELD,
        "center_field": pdu.POS_CENTER_FIELD,
        "right_field": pdu.POS_RIGHT_FIELD,
        "designated_hitter": pdu.POS_DESIGNATED_HITTER,
        "dh": pdu.POS_DESIGNATED_HITTER,
    }
    return position_map.get(value, pdu.POS_UNKNOWN)

# helper function to convert player status strings from JSON config to protocol constants
def player_status_from_string(status_name):
    if isinstance(status_name, int):
        return status_name
    value = str(status_name).lower().replace(" ", "_").replace("-", "_")
    status_map = {
        "active": pdu.PLAYER_ACTIVE,
        "bench": pdu.PLAYER_BENCH,
        "bullpen": pdu.PLAYER_BULLPEN,
        "unavailable": pdu.PLAYER_UNAVAILABLE,
    }
    return status_map.get(value, pdu.PLAYER_ACTIVE)

# helper function to convert the action string from the command line argument to the 
# constant in the pdu file
def action_from_string(action_name):
    value = str(action_name).lower()
    if value == "fastball":
        return pdu.ACTION_PITCH_FASTBALL
    if value == "curveball":
        return pdu.ACTION_PITCH_CURVEBALL
    if value == "changeup":
        return pdu.ACTION_PITCH_CHANGEUP
    if value == "swing":
        return pdu.ACTION_BAT_SWING
    if value == "take":
        return pdu.ACTION_BAT_TAKE
    if value == "bunt":
        return pdu.ACTION_BAT_BUNT
    return 0

# helper function to convert the role string from the command line argument to the
# constant in the pdu file
def role_from_string(role_name):
    value = str(role_name).lower()
    if value == "home":
        return pdu.ROLE_HOME
    if value == "away":
        return pdu.ROLE_AWAY
    return pdu.ROLE_NONE

# helper to convert action type to string
def action_name(action_type:int):
    if action_type == pdu.ACTION_BAT_SWING:
        return "swing"
    if action_type == pdu.ACTION_BAT_TAKE:
        return "take"
    if action_type == pdu.ACTION_BAT_BUNT:
        return "bunt"
    if action_type == pdu.ACTION_PITCH_FASTBALL:
        return "fastball"
    if action_type == pdu.ACTION_PITCH_CURVEBALL:
        return "curveball"
    if action_type == pdu.ACTION_PITCH_CHANGEUP:
        return "changeup"
    return f"action-{action_type}"