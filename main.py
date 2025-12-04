import random
import json
import math

TEAM_STATS = []
POSITION_STATS = []
NATION_STATS = []
NATION_LOOKUP = []

TEAM_FILE = "teams.json"
POSITION_FILE = "positions.json"
NATION_FILE = "nations.json"

class Player:
    def __init__(self, pos, nation):
        self.pos = pos
        self.overall = max(random.normalvariate(0.5, 0.1), 0) * 10 + 60
        self.potential = max(random.normalvariate(0.5, 0.1) * 30 + 70, self.overall + 5)
        self.nationId = nation
        self.age = 16
        self.history = []
        self.teamId = None
        self.reputation = 0
        self.setStats()
        self.checkValue()

    def setStats(self):
        team = random.choice(TEAM_STATS[self.nationId])
        self.teamId = team['teamId']
        self.reputation = max(random.normalvariate(0.5, 0.1), 0) * team['reputationFactor']//2 + 25

    def checkValue(self):
        _PERFECT_TARGET = 300000.0
        _PERFECT_REP = 100.0
        _PERFECT_AGE_FACTOR = 1.35
        _BASE_SCALE = _PERFECT_TARGET / ((1 + _PERFECT_REP / 150) * _PERFECT_AGE_FACTOR)
        _ABILITY_EXPONENT = 11.926591021447322

        ca = self.overall
        pa = self.potential
        age = self.age
        rep = self.reputation

        pa_weight = max(0.2, min(0.8, 1 - (age - 16) / 20))
        ca_weight = 1 - pa_weight

        ability_score = (pa * pa_weight) + (ca * ca_weight)
        rep_multiplier = 1 + (rep / 150)

        if age < 20:
            age_factor = 1.35
        elif age < 24:
            age_factor = 1.15
        elif age < 29:
            age_factor = 1.0
        elif age < 32:
            age_factor = 0.7
        else:
            age_factor = 0.45

        value = _BASE_SCALE * ((ability_score / 100) ** _ABILITY_EXPONENT) * rep_multiplier * age_factor
        self.value = round(value, 2)

    def add_history(self, season_summary, league_won):
        season_no = len(self.history) + 1
        entry = {"season": season_no}
        entry.update(season_summary)
        entry["league_won"] = bool(league_won)
        self.history.append(entry)

    def show_history(self):
        print(self.history)

def _poisson_sample(lam):
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1

def _build_fixtures(team_list):
    n = len(team_list)
    fixtures = []
    for i in range(n):
        for j in range(n):
            if i != j:
                fixtures.append((i, j))
    return fixtures

def displayResults(sim_results, nation_keys=None, show_fixtures=True, show_table=True):
    if nation_keys is None:
        keys = list(sim_results.keys())
    elif isinstance(nation_keys, (list, tuple, set)):
        keys = list(nation_keys)
    else:
        keys = [nation_keys]

    for nk in keys:
        if nk not in sim_results:
            print(f"\n--- Nation {nk} not found in results ---")
            continue

        data = sim_results[nk]
        fixtures = data.get("fixtures", [])
        table = data.get("table", [])

        nation_name = NATION_LOOKUP.get(nk, f"Nation {nk}")

        print("\n" + "=" * 60)
        print(f" NATION / LEAGUE: {nation_name}")
        print("=" * 60)

        if show_fixtures:
            print("\n--- MATCH RESULTS ---")
            for mr in fixtures:
                print(f"{mr['home_team'][:18]} {mr['home_goals']:>2}-{mr['away_goals']:<2} {mr['away_team'][:18]}")

        if show_table:
            print("\n--- FINAL TABLE ---")
            header = f"{'Pos':>3} {'Team':<25} {'P':>2} {'W':>2} {'D':>2} {'L':>2} {'GF':>3} {'GA':>3} {'GD':>4} {'Pts':>4}"
            print(header)
            for pos, row in enumerate(table, start=1):
                print(f"{pos:>3} {row['teamName']:<25} {row.get('played',0):>2} "
                        f"{row.get('wins',0):>2} {row.get('draws',0):>2} {row.get('losses',0):>2} "
                        f"{row.get('gf',0):>3} {row.get('ga',0):>3} {row.get('gd',0):>4} {row.get('points',0):>4}")

        print("=" * 60)

def get_play_minutes(player, team_dict, opp_dict):
    team_strength = (team_dict.get("attack",50) + team_dict.get("midfield",50) + team_dict.get("defense",50)) / 3.0
    opp_strength = (opp_dict.get("attack",50) + opp_dict.get("midfield",50) + opp_dict.get("defense",50)) / 3.0
    team_strength_norm = max(0.0, min(1.0, (team_strength - 50.0) / 50.0))
    opp_strength_norm = max(0.0, min(1.0, (opp_strength - 50.0) / 50.0))
    ability_norm = max(0.0, min(1.0, (player.overall - 50.0) / 40.0))

    base_start = 0.16 + 0.60 * ability_norm + 0.12 * team_strength_norm
    if ability_norm + 0.12 < team_strength_norm:
        base_start -= (team_strength_norm - ability_norm) * 0.8
    base_start += (1.0 - opp_strength_norm) * 0.12
    start_prob = max(0.0, min(0.95, base_start))

    if random.random() < start_prob:
        sub_out_chance = 0.10 + 0.22 * (1.0 - ability_norm) + 0.04 * (1.0 - opp_strength_norm)
        if random.random() < sub_out_chance:
            minutes = 60 + random.randint(-12,12)
            minutes = max(25, min(88, minutes))
            return minutes, "start", True
        return 90, "start", True

    sub_prob = 0.06 + 0.45 * ability_norm + (1.0 - opp_strength_norm) * 0.16
    if random.random() < sub_prob:
        minutes = random.randint(5, 70)
        minutes = max(5, min(85, minutes))
        return minutes, "sub", True

    return 0, "bench", False

def simSeason(team_stats_by_nation):
    all_results = {}
    for nation_key, teams in team_stats_by_nation.items():
        teams = [dict(t) for t in teams]
        table = {}
        for i, t in enumerate(teams):
            table[i] = {
                "teamId": t.get("teamId", i),
                "teamName": t.get("teamName", f"Team {i}"),
                "played": 0, "wins": 0, "draws": 0, "losses": 0,
                "gf": 0, "ga": 0, "gd": 0, "points": 0,
                "reputationFactor": t.get("reputationFactor", 0)
            }
        avg_attack = sum(t.get("attack", 50) for t in teams) / max(1, len(teams))
        avg_mid = sum(t.get("midfield", 50) for t in teams) / max(1, len(teams))
        avg_def = sum(t.get("defense", 50) for t in teams) / max(1, len(teams))
        avg_keeper = sum(t.get("goalkeeping", 50) for t in teams) / max(1, len(teams))
        BASE_LAMBDA = 1.15
        fixtures = _build_fixtures(teams)
        match_results = []
        for home_idx, away_idx in fixtures:
            home = teams[home_idx]
            away = teams[away_idx]
            home_attack_power = home.get("attack", 50) + 0.8 * home.get("midfield", 50)
            away_attack_power = away.get("attack", 50) + 0.8 * away.get("midfield", 50)
            home_def_power = home.get("defense", 50) + 0.6 * home.get("midfield", 50) + 0.9 * home.get("goalkeeping", 50)
            away_def_power = away.get("defense", 50) + 0.6 * away.get("midfield", 50) + 0.9 * away.get("goalkeeping", 50)
            off_den = (avg_attack + 0.8 * avg_mid)
            def_den = (avg_def + 0.6 * avg_mid + 0.9 * avg_keeper)
            home_off_factor = home_attack_power / max(0.01, off_den)
            away_off_factor = away_attack_power / max(0.01, off_den)
            home_def_factor = away_def_power / max(0.01, def_den)
            away_def_factor = home_def_power / max(0.01, def_den)
            culture_home = home.get("culture", 50)
            culture_away = away.get("culture", 50)
            culture_adv = culture_home - 0.4 * culture_away
            HOME_ADV = 1 + (culture_adv / 100)
            HOME_ADV = max(0.85, min(HOME_ADV, 1.6))
            lam_home = BASE_LAMBDA * home_off_factor / home_def_factor * HOME_ADV
            lam_away = BASE_LAMBDA * away_off_factor / away_def_factor
            lam_home = max(0.15, min(lam_home, 6.0))
            lam_away = max(0.05, min(lam_away, 6.0))
            goals_home = _poisson_sample(lam_home)
            goals_away = _poisson_sample(lam_away)
            table[home_idx]["played"] += 1
            table[away_idx]["played"] += 1
            table[home_idx]["gf"] += goals_home
            table[home_idx]["ga"] += goals_away
            table[away_idx]["gf"] += goals_away
            table[away_idx]["ga"] += goals_home
            if goals_home > goals_away:
                table[home_idx]["wins"] += 1
                table[away_idx]["losses"] += 1
                table[home_idx]["points"] += 3
            elif goals_home < goals_away:
                table[away_idx]["wins"] += 1
                table[home_idx]["losses"] += 1
                table[away_idx]["points"] += 3
            else:
                table[home_idx]["draws"] += 1
                table[away_idx]["draws"] += 1
                table[home_idx]["points"] += 1
                table[away_idx]["points"] += 1
            match_results.append({
                "home_idx": home_idx,
                "away_idx": away_idx,
                "home_team": table[home_idx]["teamName"],
                "away_team": table[away_idx]["teamName"],
                "home_goals": goals_home,
                "away_goals": goals_away
            })
        for i in table:
            table[i]["gd"] = table[i]["gf"] - table[i]["ga"]
        sorted_table = sorted(table.values(), key=lambda r: (
            -r["points"], -r["gd"], -r["gf"], -r.get("reputationFactor", 0)
        ))
        all_results[nation_key] = {
            "fixtures": match_results,
            "table": sorted_table
        }
    return all_results

def simulatePlayerSeason(player, team_stats_by_nation):
    pos_lookup = { p.get("positionId", i): p for i, p in enumerate(POSITION_STATS) }
    pos_profile = None
    if isinstance(player.pos, int):
        pos_profile = pos_lookup.get(player.pos)
    else:
        for p in POSITION_STATS:
            if str(p.get("position", "")).lower() == str(player.pos).lower() or str(p.get("positionId")) == str(player.pos):
                pos_profile = p
                break
    if pos_profile is None:
        pos_profile = POSITION_STATS[0] if POSITION_STATS else {
            "scoring": 1, "assisting": 1, "passing": 1, "tackling": 1,
            "stopping": 0, "diving": 0, "dribbling": 1, "yellowcard": 1, "redcard": 0
        }
    nation_key = player.nationId
    if nation_key in team_stats_by_nation:
        teams_list = team_stats_by_nation[nation_key]
    elif str(nation_key) in team_stats_by_nation:
        teams_list = team_stats_by_nation[str(nation_key)]
    else:
        teams_list = next(iter(team_stats_by_nation.values()))
    team_index = None
    team_dict = None
    for idx, t in enumerate(teams_list):
        if t.get("teamId") == player.teamId:
            team_index = idx
            team_dict = t
            break
    if team_index is None:
        team_index = 0
        team_dict = teams_list[0]
    results = simSeason({nation_key: teams_list})
    nation_results = results.get(nation_key, {})
    fixtures = nation_results.get("fixtures", [])
    matches_stats = []
    totals = {
        "involved": 0, "played": 0, "goals": 0, "assists": 0, "dribbles": 0,
        "tackles": 0, "key_passes": 0, "yellow": 0, "red": 0,
        "passes_attempted": 0, "passes_completed": 0, "clean_sheets": 0, "minutes": 0
    }
    def _expected_contrib(team_goals, attr_weight, overall, team_off_factor):
        return team_goals * ((attr_weight / 100.0)) * (overall / 90.0) * team_off_factor
    team_attack = team_dict.get("attack", 50)
    team_mid = team_dict.get("midfield", 50)
    team_def = team_dict.get("defense", 50)
    team_keeper = team_dict.get("goalkeeping", 50)
    team_off_factor_global = max(0.4, (team_attack + 0.6 * team_mid) / 140.0)
    for f in fixtures:
        h_idx = f["home_idx"]
        a_idx = f["away_idx"]
        if h_idx != team_index and a_idx != team_index:
            continue
        totals["involved"] += 1
        is_home = (h_idx == team_index)
        team_goals = f["home_goals"] if is_home else f["away_goals"]
        opp_goals = f["away_goals"] if is_home else f["home_goals"]
        opp_idx = a_idx if is_home else h_idx
        opp_team_dict = teams_list[opp_idx]
        opp_attack = opp_team_dict.get("attack", 50)
        opp_mid = opp_team_dict.get("midfield", 50)
        opp_def = opp_team_dict.get("defense", 50)
        opp_keeper = opp_team_dict.get("goalkeeping", 50)
        opp_off_factor = max(0.4, (opp_attack + 0.6 * opp_mid) / 140.0)
        lam_goals = _expected_contrib(team_goals, pos_profile.get("scoring", 0), player.overall, team_off_factor_global)
        lam_assists = _expected_contrib(team_goals, pos_profile.get("assisting", 0), player.overall, team_off_factor_global)
        lam_dribbles = 0.6 * (pos_profile.get("dribbling", 0) / 10.0) * (player.overall / 80.0) * (team_attack / 80.0)
        lam_tackles = 0.6 * (pos_profile.get("tackling", 0) / 10.0) * (1.0 + (player.overall - 60)/80.0) * (opp_attack / 80.0)
        lam_keypasses = 0.4 * (pos_profile.get("passing", 0) / 10.0) * (player.overall / 85.0) * (team_mid / 75.0)
        lam_goals = max(0.01, lam_goals)
        lam_assists = max(0.0, lam_assists)
        lam_dribbles = max(0.0, lam_dribbles)
        lam_tackles = max(0.0, lam_tackles)
        lam_keypasses = max(0.0, lam_keypasses)
        minutes, play_role, played = get_play_minutes(player, team_dict, opp_team_dict)
        minutes_ratio = minutes / 90.0 if minutes > 0 else 0.0
        if not played or minutes == 0:
            goals_scored = 0
            assists_made = 0
            dribbles = 0
            tackles = 0
            key_passes = 0
            passes_attempted = 0
            passes_completed = 0
            pass_acc = 0
            yellow = 0
            red = 0
            clean_sheet = 0
        else:
            totals["played"] += 1
            totals["minutes"] += minutes
            lam_goals_m = lam_goals * minutes_ratio
            lam_assists_m = lam_assists * minutes_ratio
            lam_dribbles_m = lam_dribbles * minutes_ratio
            lam_tackles_m = lam_tackles * minutes_ratio
            lam_keypasses_m = lam_keypasses * minutes_ratio
            goals_scored = _poisson_sample(lam_goals_m) if lam_goals_m > 0.5 else (1 if random.random() < lam_goals_m else 0)
            assists_made = _poisson_sample(lam_assists_m) if lam_assists_m > 0.5 else (1 if random.random() < lam_assists_m else 0)
            dribbles = _poisson_sample(lam_dribbles_m) if lam_dribbles_m > 0.5 else (1 if random.random() < lam_dribbles_m else 0)
            tackles = _poisson_sample(lam_tackles_m) if lam_tackles_m > 0.5 else (1 if random.random() < lam_tackles_m else 0)
            key_passes = _poisson_sample(lam_keypasses_m) if lam_keypasses_m > 0.5 else (1 if random.random() < lam_keypasses_m else 0)
            pass_base = 40 + pos_profile.get("passing", 0) + (player.overall - 65) * 0.5 + (team_mid - 60) * 0.25
            pass_acc = max(25, min(99, int(round(random.normalvariate(pass_base, 6)))))
            passes_attempted = int(round(((pos_profile.get("passing", 0) + 5) * (0.7 + player.overall/160.0)) * minutes_ratio * (team_mid / 70.0)))
            passes_completed = int(round(passes_attempted * pass_acc / 100.0))
            yellow_prob = max(0.01, pos_profile.get("yellowcard", 1) / 40.0)
            red_prob = max(0.002, pos_profile.get("redcard", 0) / 200.0)
            yellow = 1 if random.random() < yellow_prob * (1.0 - (player.overall-50)/200.0) * minutes_ratio else 0
            red = 1 if random.random() < red_prob * (1.0 - (player.overall-50)/300.0) * minutes_ratio else 0
            if (pos_profile.get("stopping", 0) > 0 or pos_profile.get("diving", 0) > 0) and opp_goals == 0 and minutes >= 60:
                keeper_factor = team_keeper / max(1.0, opp_attack)
                if random.random() < min(0.95, 0.6 + keeper_factor * 0.4):
                    clean_sheet = 1
                else:
                    clean_sheet = 0
            else:
                clean_sheet = 0
        match_stat = {
            "home": f["home_team"],
            "away": f["away_team"],
            "is_home": is_home,
            "team_goals": team_goals,
            "opp_goals": opp_goals,
            "minutes": minutes,
            "role": play_role,
            "goals": goals_scored,
            "assists": assists_made,
            "dribbles": dribbles,
            "tackles": tackles,
            "key_passes": key_passes,
            "passes_attempted": passes_attempted,
            "passes_completed": passes_completed,
            "pass_acc": pass_acc,
            "yellow": yellow,
            "red": red,
            "clean_sheet": clean_sheet
        }
        totals["goals"] += goals_scored
        totals["assists"] += assists_made
        totals["dribbles"] += dribbles
        totals["tackles"] += tackles
        totals["key_passes"] += key_passes
        totals["passes_attempted"] += passes_attempted
        totals["passes_completed"] += passes_completed
        totals["yellow"] += yellow
        totals["red"] += red
        totals["clean_sheets"] += clean_sheet
        matches_stats.append(match_stat)
    player.age = player.age + 1
    dev = team_dict.get("devRate", 5)
    gap = max(0.0, player.potential - player.overall)
    if player.age <= 18:
        age_factor = 1.3
    elif player.age <= 21:
        age_factor = 1.05
    elif player.age <= 24:
        age_factor = 0.75
    elif player.age <= 29:
        age_factor = 0.45
    elif player.age <= 32:
        age_factor = 0.25
    else:
        age_factor = 0.08
    random_mult = random.uniform(0.9, 1.15)
    max_minutes = totals["involved"] * 90 if totals["involved"] > 0 else 1
    minutes_ratio = totals["minutes"] / max_minutes
    base_growth = dev * 0.05
    growth = base_growth * minutes_ratio * random_mult * age_factor
    growth = max(0.0, min(growth, gap))
    player.overall = round(max(1.0, min(player.potential, player.overall + growth)), 2)
    summary = {
        "matches_involved": totals["involved"],
        "matches_played": totals["played"],
        "minutes": totals["minutes"],
        "teamId": player.teamId,
        "teamName": team_dict.get("teamName"),
        "goals": totals["goals"],
        "assists": totals["assists"],
        "dribbles": totals["dribbles"],
        "tackles": totals["tackles"],
        "key_passes": totals["key_passes"],
        "passes_attempted": totals["passes_attempted"],
        "passes_completed": totals["passes_completed"],
        "pass_acc_avg": int(round(totals["passes_completed"] / totals["passes_attempted"] * 100)) if totals["passes_attempted"]>0 else 0,
        "yellow": totals["yellow"],
        "red": totals["red"],
        "clean_sheets": totals["clean_sheets"],
        "age": player.age,
        "new_overall": player.overall
    }
    league_table = nation_results.get("table", [])
    league_won = False
    if league_table:
        top = league_table[0]
        if top.get("teamId") == player.teamId:
            league_won = True
    player.add_history(summary, league_won)
    return {"matches": matches_stats, "summary": summary, "league_table": league_table}

def displayPlayerSeason(res, player=None):
    s = res["summary"]
    matches = res.get("matches", [])
    table = res.get("league_table", [])

    minutes_total = sum(m.get("minutes", 0) for m in matches)
    played_matches = sum(1 for m in matches if m.get("minutes", 0) > 0)
    starts = sum(1 for m in matches if m.get("role") == "start" and m.get("minutes", 0) > 0)
    subs = sum(1 for m in matches if m.get("role") == "sub" and m.get("minutes", 0) > 0)
    bench = len(matches) - played_matches
    mp90 = minutes_total / 90.0 if minutes_total > 0 else 0.0

    value_display = None
    if player is not None:
        player.checkValue()
        value_display = player.value

    print("\n================ PLAYER SEASON SUMMARY ================")
    print(f"Team:         {s.get('teamName')} (ID {s.get('teamId')})")
    print(f"Age:          {s.get('age')}")
    print(f"Overall:      {s.get('new_overall')}")

    if value_display is not None:
        print(f"Transfer Value: €{value_display/1000:,.2f}M")

    print(f"Matches (involved): {len(matches)}  Played: {played_matches}  Starts: {starts}  Subs: {subs}  Bench: {bench}")
    print(f"Minutes total: {minutes_total}  Avg minutes/match (played): {(minutes_total/played_matches if played_matches>0 else 0):.1f}")
    print("-------------------------------------------------------")
    print(f"Goals:        {s.get('goals',0)}")
    print(f"Assists:      {s.get('assists',0)}")
    print(f"Dribbles:     {s.get('dribbles',0)}")
    print(f"Tackles:      {s.get('tackles',0)}")
    print(f"Key Passes:   {s.get('key_passes',0)}")
    print(f"Passes (C/A): {s.get('passes_completed',0)}/{s.get('passes_attempted',0)}  Pass Acc: {s.get('pass_acc_avg',0)}%")
    print(f"Yellows:      {s.get('yellow',0)}")
    print(f"Reds:         {s.get('red',0)}")
    print(f"Clean Sheets: {s.get('clean_sheets',0)}")
    print("-------------------------------------------------------")

    denom = mp90 if mp90 > 0 else 1.0
    print("Per 90 (minutes-based):")
    print(f"G/90:         {s.get('goals',0) / denom:.2f}")
    print(f"A/90:         {s.get('assists',0) / denom:.2f}")
    print(f"Dribbles/90:  {s.get('dribbles',0) / denom:.2f}")
    print(f"Tackles/90:   {s.get('tackles',0) / denom:.2f}")
    print(f"KeyP/90:      {s.get('key_passes',0) / denom:.2f}")
    print(f"Passes completed/90: {s.get('passes_completed',0) / denom:.1f}")
    print("=======================================================\n")

    if table:
        print("=================== LEAGUE TABLE ===================")
        header = f"{'Pos':>3} {'Team':<25} {'P':>2} {'W':>2} {'D':>2} {'L':>2} {'GF':>3} {'GA':>3} {'GD':>4} {'Pts':>4}"
        print(header)
        for pos, row in enumerate(table, start=1):
            print(f"{pos:>3} {row['teamName']:<25} {row.get('played',0):>2} "
                  f"{row.get('wins',0):>2} {row.get('draws',0):>2} {row.get('losses',0):>2} "
                  f"{row.get('gf',0):>3} {row.get('ga',0):>3} {row.get('gd',0):>4} {row.get('points',0):>4}")
        print("=====================================================\n")

def load_stats():
    global TEAM_STATS
    global POSITION_STATS
    global NATION_STATS
    global NATION_LOOKUP
    with open(TEAM_FILE, "r") as f:
        TEAM_STATS = json.load(f)
    with open(POSITION_FILE, "r") as f:
        POSITION_STATS = json.load(f)
    with open(NATION_FILE, "r") as f:
        NATION_STATS = json.load(f)
    NATION_LOOKUP = { n["nationId"]: n["nationName"] for n in NATION_STATS }

def main():
    load_stats()
    P = Player("0", "0")
    print(P.overall, P.potential)
    res = simulatePlayerSeason(P, TEAM_STATS)
    displayPlayerSeason(res, P)
    P.show_history()


if __name__ == "__main__":
    main()