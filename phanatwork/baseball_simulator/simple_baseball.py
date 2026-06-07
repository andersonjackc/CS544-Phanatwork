import random

import pdu

# baseball rules to use in the app running phanatwork

class SimpleBaseballRules:
    def __init__(self, innings:int = 3, outs_per_half:int = 3, seed:int = None):
        self.innings = innings
        self.outs_per_half = outs_per_half
        self.seed = seed
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.event_id = 1
        self.inning = 1
        self.half_inning = 0
        self.outs = 0
        self.balls = 0
        self.strikes = 0
        self.bases = 0
        self.home_score = 0
        self.home_hits = 0
        self.home_errors = 0
        self.away_score = 0
        self.away_hits = 0
        self.away_errors = 0
        self.offense_role = pdu.ROLE_AWAY
        self.defense_role = pdu.ROLE_HOME
        self.game_over = False
        self.last_result_code = 0
        self.last_result_text = ""
        self.batter_id = 0
        self.pitcher_id = 0
        self.batting_orders = {pdu.ROLE_HOME: [], pdu.ROLE_AWAY: []}
        self.batting_order_index = {pdu.ROLE_HOME: 0, pdu.ROLE_AWAY: 0}
        self.pitchers = {pdu.ROLE_HOME: 0, pdu.ROLE_AWAY: 0}


    # configure each team's batting order from the roster sent through the protocol.
    def configure_roster(self, role:int, players:list):
        active_players = [
            player for player in players or []
            if int(player.get("player_status", pdu.PLAYER_ACTIVE)) == pdu.PLAYER_ACTIVE
        ]

        lineup_players = [
            player for player in active_players
            if int(player.get("lineup_slot", 0)) > 0
        ]
        lineup_players.sort(key=lambda player: int(player.get("lineup_slot", 0)))

        if lineup_players:
            self.batting_orders[role] = [int(player.get("player_id", 1)) for player in lineup_players]
        else:
            self.batting_orders[role] = [int(player.get("player_id", 1)) for player in active_players]

        self.batting_order_index[role] = 0

        for player in active_players:
            if int(player.get("position", pdu.POS_UNKNOWN)) == pdu.POS_PITCHER:
                self.pitchers[role] = int(player.get("player_id", 0))
                break
        else:
            if active_players:
                self.pitchers[role] = int(active_players[0].get("player_id", 0))

    def initialize_matchup_from_rosters(self):
        self.batter_id = self.current_batter_id(self.offense_role)
        self.pitcher_id = self.current_pitcher_id(self.defense_role)

    def current_batter_id(self, role:int):
        order = self.batting_orders.get(role, [])
        if not order:
            return self.batter_id or 1
        return order[self.batting_order_index.get(role, 0) % len(order)]

    def current_pitcher_id(self, role:int):
        return self.pitchers.get(role, self.pitcher_id) or self.pitcher_id or 0

    def advance_batter(self, role:int):
        order = self.batting_orders.get(role, [])
        if order:
            self.batting_order_index[role] = (self.batting_order_index.get(role, 0) + 1) % len(order)

    def current_update(self, result_text:str = None, result_code:int = None, batter_id:int = None, pitcher_id:int = None):
        return {
            "event_id": self.event_id,
            "batter_id": self.batter_id if batter_id is None else batter_id,
            "pitcher_id": self.pitcher_id if pitcher_id is None else pitcher_id,
            "inning": self.inning,
            "half_inning": self.half_inning,
            "outs": self.outs,
            "balls": self.balls,
            "strikes": self.strikes,
            "bases": self.bases,
            "offense_role": self.offense_role,
            "defense_role": self.defense_role,
            "home_score": self.home_score,
            "home_hits": self.home_hits,
            "home_errors": self.home_errors,
            "away_score": self.away_score,
            "away_hits": self.away_hits,
            "away_errors": self.away_errors,
            "result_code": self.last_result_code if result_code is None else result_code,
            "result_text": self.last_result_text if result_text is None else result_text,
        }

    # main funtion to resolve the play based on the input actions
    # i made them all be rng based, but the functionality to tie into the
    # players stats is available
    def resolve_play(self, offense_action:dict, defense_action:dict):
        batting_role = self.offense_role
        self.batter_id = self.current_batter_id(batting_role)
        self.pitcher_id = int(defense_action.get('player_id', self.current_pitcher_id(self.defense_role)))
        action_text = self.describe_actions(offense_action, defense_action)
        roll = self.rng.randint(1, 100)

        if int(offense_action.get('action_type', 0)) == pdu.ACTION_BAT_TAKE:
            result_text = self.resolve_take(roll, action_text)
        elif int(offense_action.get('action_type', 0)) == pdu.ACTION_BAT_BUNT:
            result_text = self.resolve_bunt(roll, action_text)
        else:
            result_text = self.resolve_swing(roll, action_text)

        # A completed plate appearance resets the count to 0-0 and should replace the batter
        # Advance the batting-order index for the team that was batting before any side switch.
        if self.balls == 0 and self.strikes == 0:
            self.advance_batter(batting_role)

        if self.outs >= self.outs_per_half:
            self.advance_half_inning()

        self.batter_id = self.current_batter_id(self.offense_role)
        self.pitcher_id = self.current_pitcher_id(self.defense_role)
        self.event_id += 1
        self.last_result_code = 0
        self.last_result_text = result_text
        return self.current_update(result_text, 0, self.batter_id, self.pitcher_id)

    def resolve_take(self, roll:int, action_text:str):
        if roll <= 55:
            self.balls += 1
            if self.balls >= 4:
                self.walk_runner()
                self.balls = 0
                self.strikes = 0
                return f"{action_text}: walk"
            return f"{action_text}: ball {self.balls}"
        self.strikes += 1
        if self.strikes >= 3:
            self.record_out()
            self.balls = 0
            self.strikes = 0
            return f"{action_text}: strikeout looking"
        return f"{action_text}: called strike {self.strikes}"

    def resolve_bunt(self, roll:int, action_text:str):
        if roll <= 10:
            self.balls = 0
            self.strikes = 0
            self.add_hit(1)
            return f"{action_text}: bunt single"
        if roll <= 28:
            return self.record_foul(action_text, "bunt foul")
        self.balls = 0
        self.strikes = 0
        self.record_out()
        return f"{action_text}: bunt out"

    def resolve_swing(self, roll:int, action_text:str):
        if roll <= 16:
            self.balls = 0
            self.strikes = 0
            self.add_hit(1)
            return f"{action_text}: single"
        if roll <= 23:
            self.balls = 0
            self.strikes = 0
            self.add_hit(2)
            return f"{action_text}: double"
        if roll <= 26:
            self.balls = 0
            self.strikes = 0
            self.add_hit(3)
            return f"{action_text}: triple"
        if roll <= 30:
            self.balls = 0
            self.strikes = 0
            self.add_hit(4)
            return f"{action_text}: home run"
        if roll <= 48:
            return self.record_foul(action_text, "foul ball")
        self.balls = 0
        self.strikes = 0
        self.record_out()
        return f"{action_text}: out"

    def record_foul(self, action_text:str, label:str):
        if self.strikes < 2:
            self.strikes += 1
            return f"{action_text}: {label}, strike {self.strikes}"
        return f"{action_text}: {label}, count stays {self.balls}-{self.strikes}"

    # helper function to update the number of hits
    def add_hit(self, bases:int):
        if self.offense_role == pdu.ROLE_HOME:
            self.home_hits += 1
        else:
            self.away_hits += 1
        self.advance_runners(bases)

    # hleper to update the bases and score when a hit or walk happens
    def advance_runners(self, bases:int):
        scored = 0
        for base_index in [2, 1, 0]:
            if self.bases & (1 << base_index):
                self.bases &= ~(1 << base_index)
                new_base = base_index + bases
                if new_base >= 3:
                    scored += 1
                else:
                    self.bases |= (1 << new_base)
        if bases >= 4:
            scored += 1
        else:
            self.bases |= (1 << (bases - 1))
        self.add_runs(scored)

    # update the bases when a walk occurs
    def walk_runner(self):
        if self.bases == 7:
            self.add_runs(1)
        elif self.bases & 1 and self.bases & 2:
            self.bases |= 4
        elif self.bases & 1:
            self.bases |= 2
        self.bases |= 1

    # add the runs to the relevant team
    def add_runs(self, runs:int):
        if self.offense_role == pdu.ROLE_HOME:
            self.home_score += runs
        else:
            self.away_score += runs

    def record_out(self):
        self.outs += 1

    # perform teh relevant updates for when the inning switches sides
    def advance_half_inning(self):
        self.outs = 0
        self.balls = 0
        self.strikes = 0
        self.bases = 0
        if self.half_inning == 0:
            self.half_inning = 1
            self.offense_role = pdu.ROLE_HOME
            self.defense_role = pdu.ROLE_AWAY
        else:
            self.half_inning = 0
            self.inning += 1
            self.offense_role = pdu.ROLE_AWAY
            self.defense_role = pdu.ROLE_HOME
        if self.inning > self.innings:
            self.game_over = True

    # currently only handle the game_over scenario after the predetermined
    # number of innings, however, different rules could be easily added
    # by adding another derivation off of SimpleBaseballRules
    def winning_role(self):
        if self.home_score > self.away_score:
            return pdu.ROLE_HOME
        if self.away_score > self.home_score:
            return pdu.ROLE_AWAY
        return pdu.ROLE_NONE

    def final_text(self, home_team:str = "HOME", away_team:str = "AWAY"):
        if self.winning_role() == pdu.ROLE_HOME:
            return f"Game over: {home_team} wins {self.home_score}-{self.away_score}"
        if self.winning_role() == pdu.ROLE_AWAY:
            return f"Game over: {away_team} wins {self.away_score}-{self.home_score}"
        return f"Game over: {home_team} and {away_team} tie {self.home_score}-{self.away_score}"

    def describe_actions(self, offense_action:dict, defense_action:dict):
        return f"offense={action_name(offense_action.get('action_type'))} defense={action_name(defense_action.get('action_type'))}"

# instance of simple baseball but changing the number of outs in the inning to 1
class OneOutBaseballRules(SimpleBaseballRules):
    def __init__(self, innings:int = 3, seed:int = None):
        super().__init__(innings=innings, outs_per_half=1, seed=seed)

# reducing the number of innings to just 1.
# lets it be a bit shorter for testing things out manually
# also shows that more than one change is possible
class ShortBaseballRules(SimpleBaseballRules):
    def __init__(self, seed:int = None):
        super().__init__(innings=1, outs_per_half=3, seed=seed)

# adding a new game mode that no matter the actions the result is an out.  This is useful for testing, as the
# other rules are based on randomness, so are nondeterministic.

class AlwaysOutOneOutRules(OneOutBaseballRules):
    def resolve_play(self, offense_action: dict, defense_action: dict):
        batting_role = self.offense_role
        self.batter_id = self.current_batter_id(batting_role)
        self.pitcher_id = int(defense_action.get("player_id", self.current_pitcher_id(self.defense_role)))

        self.balls = 0
        self.strikes = 0
        self.record_out()
        self.advance_batter(batting_role)

        result_text = "test forced out"

        if self.outs >= self.outs_per_half:
            self.advance_half_inning()

        self.batter_id = self.current_batter_id(self.offense_role)
        self.pitcher_id = self.current_pitcher_id(self.defense_role)
        self.event_id += 1
        self.last_result_code = 0
        self.last_result_text = result_text
        return self.current_update(result_text, 0, self.batter_id, self.pitcher_id)


# helper function to convert the enum to a string
def action_name(action_type):
    if action_type == pdu.ACTION_PITCH_FASTBALL:
        return "fastball"
    if action_type == pdu.ACTION_PITCH_CURVEBALL:
        return "curveball"
    if action_type == pdu.ACTION_PITCH_CHANGEUP:
        return "changeup"
    if action_type == pdu.ACTION_BAT_SWING:
        return "swing"
    if action_type == pdu.ACTION_BAT_TAKE:
        return "take"
    if action_type == pdu.ACTION_BAT_BUNT:
        return "bunt"
    return str(action_type)

# get the ruleset from the input string
def load_rules(rule_set:str = "standard", seed:int = None):
    if rule_set == "one-out":
        return OneOutBaseballRules(seed=seed)
    if rule_set == "short":
        return ShortBaseballRules(seed=seed)
    return SimpleBaseballRules(innings=3, outs_per_half=3, seed=seed)
