import os
import json
import random
import math
from typing import Dict, List, Tuple, Any, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Global data structures
CONTINENTS = []
POSITIONS = []
CONTINENT_LEVEL_COMPS = {}
NATIONS_BY_CONTINENT = {}
NATION_FOLDERS = {}
NATION_COMPS = {}
NATION_TEAMS = {}
COMP_TEAMS = {}
COMP_NAME_LOOKUP = {}
COMP_FORMAT = {}
COMP_TIER = {}

CURRENT_SEASON = 0
TEAM_HISTORY = {}
LEAGUE_HISTORY = []
CUP_HISTORY = []
TEAM_ID_MAP = {}

# Cache for team ratings
_RATING_CACHE = {}


def _load_json(path: str, default: Any = None) -> Any:
    """Load JSON file with error handling."""
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {path}: {e}")
        return default


def _slug(s: str) -> str:
    """Convert string to slug format."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def load_root_data() -> None:
    """Load continent and position data."""
    global CONTINENTS, POSITIONS
    continents_path = os.path.join(DATA_DIR, "continents.json")
    positions_path = os.path.join(DATA_DIR, "positions.json")
    CONTINENTS = _load_json(continents_path, [])
    POSITIONS = _load_json(positions_path, [])


def load_continent(cont_folder_name: str) -> None:
    """Load all data for a continent."""
    continent_dir = os.path.join(DATA_DIR, cont_folder_name)
    if not os.path.isdir(continent_dir):
        return

    nations_path = os.path.join(continent_dir, "nations.json")
    comps_path = os.path.join(continent_dir, "comps.json")

    nations = _load_json(nations_path, [])
    comps = _load_json(comps_path, [])

    NATIONS_BY_CONTINENT[cont_folder_name] = nations
    CONTINENT_LEVEL_COMPS[cont_folder_name] = comps

    # Build nation name lookup
    nation_name_by_id = {}
    for n in nations:
        nid = n.get("nationId")
        cid = n.get("continentId")
        nation_name_by_id[(cid, nid)] = n.get("nationName", f"Nation {nid}")

    # Load nation-level competitions and teams
    for entry in os.scandir(continent_dir):
        if not entry.is_dir() or entry.name.lower() in ("nations",):
            continue

        nation_folder = entry.name
        nation_path = entry.path

        nation_comps_path = os.path.join(nation_path, "comps.json")
        nation_teams_path = os.path.join(nation_path, "teams.json")

        nation_comps = _load_json(nation_comps_path, [])
        nation_teams_raw = _load_json(nation_teams_path, {})

        NATION_COMPS[nation_path] = nation_comps
        NATION_TEAMS[nation_path] = nation_teams_raw

        # Match nation folder to nation ID
        folder_slug = _slug(nation_folder)
        matched_nation_id = None
        matched_cont_id = None

        for n in nations:
            if _slug(n.get("nationName", "")) == folder_slug:
                matched_nation_id = n.get("nationId")
                matched_cont_id = n.get("continentId")
                break

        if matched_nation_id is not None:
            NATION_FOLDERS[(cont_folder_name, matched_nation_id)] = nation_folder

        # Process competitions
        for comp in nation_comps:
            comp_id = comp.get("compId")
            nation_id = comp.get("nationId")
            comp_format = comp.get("format")
            COMP_FORMAT[comp_id] = comp_format
            COMP_TIER[comp_id] = comp.get("tier", 99)

            if comp_format == 0:  # League
                comp_key_str = str(comp_id)
                teams_list = nation_teams_raw.get(comp_key_str, [])
                if teams_list:
                    COMP_TEAMS[comp_id] = teams_list
                    for t in teams_list:
                        tid = t.get("teamId")
                        if tid is not None:
                            TEAM_ID_MAP[tid] = t
            elif comp_format == 1:  # Cup
                all_teams = []
                for v in nation_teams_raw.values():
                    all_teams.extend(v)
                if all_teams:
                    COMP_TEAMS[comp_id] = all_teams
                    for t in all_teams:
                        tid = t.get("teamId")
                        if tid is not None and tid not in TEAM_ID_MAP:
                            TEAM_ID_MAP[tid] = t

            if comp_format in (0, 1):
                nation_name = nation_name_by_id.get(
                    (matched_cont_id, matched_nation_id),
                    f"Nation {nation_id}"
                )
                comp_name = comp.get("compName", f"Comp {comp_id}")
                COMP_NAME_LOOKUP[comp_id] = f"{comp_name} ({nation_name})"

    # Load continental competitions
    for comp in comps:
        comp_id = comp.get("compId")
        if comp_id is None:
            continue
        
        comp_format = comp.get("format")
        COMP_FORMAT[comp_id] = comp_format
        COMP_TIER[comp_id] = comp.get("tier", 99)
        
        if comp_format == 5:  # Continental competition
            # Qualify teams from domestic leagues
            qualified_teams = qualify_teams_for_continental(comp_id, cont_folder_name)
            if qualified_teams:
                COMP_TEAMS[comp_id] = qualified_teams
                for t in qualified_teams:
                    tid = t.get("teamId")
                    if tid is not None and tid not in TEAM_ID_MAP:
                        TEAM_ID_MAP[tid] = t
        
        comp_name = comp.get("compName", f"Comp {comp_id}")
        COMP_NAME_LOOKUP[comp_id] = f"{comp_name}"


def qualify_teams_for_continental(comp_id: int, cont_folder: str) -> List[Dict]:
    """Qualify teams for continental competitions based on league performance."""
    if not LEAGUE_HISTORY:
        return []
    
    last_season = LEAGUE_HISTORY[-1]
    tier = COMP_TIER.get(comp_id, 1)
    
    # Determine how many teams to qualify based on tier
    if tier == 1:  # Champions League equivalent
        teams_per_league = 4
    elif tier == 2:  # Europa League equivalent
        teams_per_league = 3
    elif tier == 3:  # Conference League equivalent
        teams_per_league = 2
    else:
        teams_per_league = 2
    
    qualified = []
    
    # Get all domestic leagues from this continent
    for (cf, nid), folder in NATION_FOLDERS.items():
        if cf != cont_folder:
            continue
        
        nation_path = os.path.join(DATA_DIR, cf, folder)
        comps = NATION_COMPS.get(nation_path, [])
        
        for comp in comps:
            cid = comp.get("compId")
            if COMP_FORMAT.get(cid) != 0:  # Only leagues
                continue
            
            if cid not in last_season:
                continue
            
            table = last_season[cid].get("table", [])
            
            # Qualify top N teams
            for i in range(min(teams_per_league, len(table))):
                team_id = table[i].get("teamId")
                if team_id in TEAM_ID_MAP:
                    team_copy = dict(TEAM_ID_MAP[team_id])
                    qualified.append(team_copy)
    
    return qualified


def init_team_history() -> None:
    """Initialize history tracking for all teams."""
    for tid, t in TEAM_ID_MAP.items():
        if tid not in TEAM_HISTORY:
            TEAM_HISTORY[tid] = {
                "name": t.get("teamName", ""),
                "records": [],
                "ratings": []
            }


def load_world() -> None:
    """Load all world data."""
    load_root_data()
    for entry in os.scandir(DATA_DIR):
        if entry.is_dir():
            load_continent(entry.name)
    init_team_history()


def _poisson_sample(lam: float) -> int:
    """Sample from Poisson distribution."""
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


def _build_fixtures(team_list: List[Dict]) -> List[Tuple[int, int]]:
    """Build round-robin fixtures."""
    n = len(team_list)
    fixtures = []
    for i in range(n):
        for j in range(n):
            if i != j:
                fixtures.append((i, j))
    return fixtures


def _team_rating(t: Dict) -> float:
    """Calculate team rating with caching."""
    tid = t.get("teamId")
    
    # Check cache
    cache_key = (
        tid,
        t.get("attack", 50),
        t.get("midfield", 50),
        t.get("defense", 50),
        t.get("goalkeeping", 50)
    )
    
    if cache_key in _RATING_CACHE:
        return _RATING_CACHE[cache_key]
    
    atk = t.get("attack", 50)
    mid = t.get("midfield", 50)
    dfn = t.get("defense", 50)
    gk = t.get("goalkeeping", 50)
    
    rating = 0.35 * atk + 0.35 * mid + 0.2 * dfn + 0.1 * gk
    _RATING_CACHE[cache_key] = rating
    
    return rating


def _simulate_match(home: Dict, away: Dict, force_winner: bool = False) -> Tuple[int, int]:
    """Simulate a match between two teams."""
    r_home = _team_rating(home)
    r_away = _team_rating(away)

    rating_diff = (r_home - r_away) / 9.0
    rating_factor_home = 1.0 + rating_diff
    rating_factor_away = 1.0 - rating_diff

    rating_factor_home = max(0.4, min(1.8, rating_factor_home))
    rating_factor_away = max(0.4, min(1.8, rating_factor_away))

    culture_home = home.get("culture", 50)
    culture_away = away.get("culture", 50)
    culture_term = (culture_home - culture_away) / 200.0
    HOME_ADV = 1.08 + culture_term
    HOME_ADV = max(1.02, min(1.25, HOME_ADV))

    BASE_LAMBDA = 1.45
    lam_home = BASE_LAMBDA * rating_factor_home * HOME_ADV
    lam_away = BASE_LAMBDA * rating_factor_away

    lam_home = max(0.2, min(3.4, lam_home))
    lam_away = max(0.1, min(3.0, lam_away))

    goals_home = _poisson_sample(lam_home)
    goals_away = _poisson_sample(lam_away)

    # Force winner for cup matches
    if force_winner and goals_home == goals_away:
        if random.random() < 0.5:
            goals_home += 1
        else:
            goals_away += 1

    return goals_home, goals_away


def simSeason(team_stats_by_key: Dict[int, List[Dict]]) -> Dict[int, Dict]:
    """Simulate a full season of leagues."""
    all_results = {}
    
    for key, teams in team_stats_by_key.items():
        teams = [dict(t) for t in teams]

        table = {}
        for i, t in enumerate(teams):
            table[i] = {
                "teamId": t.get("teamId", i),
                "teamName": t.get("teamName", f"Team {i}"),
                "played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "gf": 0,
                "ga": 0,
                "gd": 0,
                "points": 0,
                "reputationFactor": t.get("reputationFactor", 0)
            }

        fixtures = _build_fixtures(teams)
        match_results = []

        for home_idx, away_idx in fixtures:
            home = teams[home_idx]
            away = teams[away_idx]

            goals_home, goals_away = _simulate_match(home, away, force_winner=False)

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

        sorted_table = sorted(
            table.values(),
            key=lambda r: (-r["points"], -r["gd"], -r["gf"], -r.get("reputationFactor", 0))
        )

        all_results[key] = {
            "fixtures": match_results,
            "table": sorted_table
        }

    return all_results


def simCups(cup_stats_by_key: Dict[int, List[Dict]], league_results: Dict[int, Dict]) -> Dict[int, Dict]:
    """Simulate cup competitions with knockout format."""
    def is_power_of_two(x):
        return x > 0 and (x & (x - 1)) == 0

    league_seed_info = {}
    for comp_id, res in league_results.items():
        tier = COMP_TIER.get(comp_id, 99)
        table = res.get("table", [])
        for pos, row in enumerate(table, start=1):
            tid = row.get("teamId")
            league_seed_info[tid] = (tier, pos)

    all_results = {}
    for key, teams in cup_stats_by_key.items():
        teams = [dict(t) for t in teams]
        n = len(teams)
        if not teams:
            all_results[key] = {"rounds": [], "winner": None}
            continue

        rounds = []

        seed_indices = list(range(n))
        seed_indices.sort(
            key=lambda i: league_seed_info.get(
                teams[i].get("teamId"),
                (999, 999)
            )
        )

        if not is_power_of_two(n):
            target = 1
            while target * 2 <= n:
                target *= 2
            num_elim = n - target
            num_q_teams = 2 * num_elim

            q_candidates = seed_indices[-num_q_teams:]
            main_seeds = seed_indices[:-num_q_teams]

            random.shuffle(q_candidates)

            q_matches = []
            winners = []
            for i in range(0, len(q_candidates), 2):
                a = q_candidates[i]
                b = q_candidates[i + 1]
                home = teams[a]
                away = teams[b]
                gh, ga = _simulate_match(home, away, force_winner=True)
                if gh > ga:
                    w = a
                else:
                    w = b
                winners.append(w)
                q_matches.append({
                    "home_team": home.get("teamName", ""),
                    "away_team": away.get("teamName", ""),
                    "home_goals": gh,
                    "away_goals": ga,
                    "winner": teams[w].get("teamName", "")
                })

            rounds.append({
                "round_name": "Qualifying Round",
                "matches": q_matches
            })

            current_indices = main_seeds + winners
        else:
            current_indices = seed_indices

        while len(current_indices) > 1:
            random.shuffle(current_indices)
            next_round_indices = []
            pairs = []

            if len(current_indices) % 2 == 1:
                bye = current_indices.pop()
                next_round_indices.append(bye)

            while current_indices:
                a = current_indices.pop()
                b = current_indices.pop()
                pairs.append((a, b))

            size = len(pairs) * 2 + len(next_round_indices)
            if size == 2:
                round_name = "Final"
            elif size == 4:
                round_name = "Semi-finals"
            elif size == 8:
                round_name = "Quarter-finals"
            elif size == 16:
                round_name = "Round of 16"
            elif size == 32:
                round_name = "Round of 32"
            else:
                round_name = f"Round of {size}"

            matches = []
            for home_idx, away_idx in pairs:
                home = teams[home_idx]
                away = teams[away_idx]
                gh, ga = _simulate_match(home, away, force_winner=True)
                if gh > ga:
                    w = home_idx
                else:
                    w = away_idx
                next_round_indices.append(w)
                matches.append({
                    "home_team": home.get("teamName", ""),
                    "away_team": away.get("teamName", ""),
                    "home_goals": gh,
                    "away_goals": ga,
                    "winner": teams[w].get("teamName", "")
                })

            rounds.append({
                "round_name": round_name,
                "matches": matches
            })
            current_indices = next_round_indices

        winner_name = teams[current_indices[0]].get("teamName", "") if current_indices else None
        all_results[key] = {
            "rounds": rounds,
            "winner": winner_name
        }

    return all_results


def simContinental(continental_comps: Dict[int, List[Dict]], league_results: Dict[int, Dict]) -> Dict[int, Dict]:
    """Simulate continental competitions (Champions League style)."""
    all_results = {}
    
    for comp_id, teams in continental_comps.items():
        if not teams or len(teams) < 8:
            all_results[comp_id] = {"rounds": [], "winner": None}
            continue
        
        teams = [dict(t) for t in teams]
        
        # Group stage
        num_groups = len(teams) // 4
        groups = {}
        
        # Seed teams
        teams_sorted = sorted(teams, key=lambda t: t.get("reputationFactor", 0), reverse=True)
        
        for i in range(num_groups):
            groups[i] = []
        
        # Distribute teams across groups (seeded)
        for i, team in enumerate(teams_sorted):
            group_idx = i % num_groups
            groups[group_idx].append(team)
        
        group_results = []
        knockout_qualifiers = []
        
        for group_idx, group_teams in groups.items():
            # Simulate group matches
            group_table = {}
            for i, t in enumerate(group_teams):
                group_table[i] = {
                    "teamId": t.get("teamId"),
                    "teamName": t.get("teamName", ""),
                    "played": 0,
                    "wins": 0,
                    "draws": 0,
                    "losses": 0,
                    "gf": 0,
                    "ga": 0,
                    "gd": 0,
                    "points": 0
                }
            
            # Everyone plays everyone twice
            for i in range(len(group_teams)):
                for j in range(len(group_teams)):
                    if i == j:
                        continue
                    
                    home = group_teams[i]
                    away = group_teams[j]
                    gh, ga = _simulate_match(home, away, force_winner=False)
                    
                    group_table[i]["played"] += 1
                    group_table[j]["played"] += 1
                    group_table[i]["gf"] += gh
                    group_table[i]["ga"] += ga
                    group_table[j]["gf"] += ga
                    group_table[j]["ga"] += gh
                    
                    if gh > ga:
                        group_table[i]["wins"] += 1
                        group_table[j]["losses"] += 1
                        group_table[i]["points"] += 3
                    elif ga > gh:
                        group_table[j]["wins"] += 1
                        group_table[i]["losses"] += 1
                        group_table[j]["points"] += 3
                    else:
                        group_table[i]["draws"] += 1
                        group_table[j]["draws"] += 1
                        group_table[i]["points"] += 1
                        group_table[j]["points"] += 1
            
            for i in group_table:
                group_table[i]["gd"] = group_table[i]["gf"] - group_table[i]["ga"]
            
            sorted_group = sorted(
                group_table.values(),
                key=lambda r: (-r["points"], -r["gd"], -r["gf"])
            )
            
            group_results.append({
                "group_name": f"Group {chr(65 + group_idx)}",
                "table": sorted_group
            })
            
            # Top 2 qualify
            for row in sorted_group[:2]:
                tid = row["teamId"]
                for t in teams:
                    if t.get("teamId") == tid:
                        knockout_qualifiers.append(t)
                        break
        
        # Knockout stage
        knockout_rounds = []
        current_teams = knockout_qualifiers
        
        while len(current_teams) > 1:
            random.shuffle(current_teams)
            next_round = []
            matches = []
            
            for i in range(0, len(current_teams), 2):
                if i + 1 >= len(current_teams):
                    next_round.append(current_teams[i])
                    continue
                
                home = current_teams[i]
                away = current_teams[i + 1]
                gh, ga = _simulate_match(home, away, force_winner=True)
                
                if gh > ga:
                    winner = home
                else:
                    winner = away
                
                next_round.append(winner)
                matches.append({
                    "home_team": home.get("teamName", ""),
                    "away_team": away.get("teamName", ""),
                    "home_goals": gh,
                    "away_goals": ga,
                    "winner": winner.get("teamName", "")
                })
            
            size = len(current_teams)
            if size == 2:
                round_name = "Final"
            elif size == 4:
                round_name = "Semi-finals"
            elif size == 8:
                round_name = "Quarter-finals"
            elif size == 16:
                round_name = "Round of 16"
            else:
                round_name = f"Round of {size}"
            
            knockout_rounds.append({
                "round_name": round_name,
                "matches": matches
            })
            
            current_teams = next_round
        
        winner_name = current_teams[0].get("teamName", "") if current_teams else None
        
        all_results[comp_id] = {
            "groups": group_results,
            "rounds": knockout_rounds,
            "winner": winner_name
        }
    
    return all_results


def displayResults(sim_results: Dict[int, Dict], comp_keys: Optional[List[int]] = None, 
                   show_fixtures: bool = False, show_table: bool = True) -> None:
    """Display league results."""
    if comp_keys is None:
        keys = list(sim_results.keys())
    elif isinstance(comp_keys, (list, tuple, set)):
        keys = list(comp_keys)
    else:
        keys = [comp_keys]

    for ck in keys:
        if ck not in sim_results:
            print(f"\n--- Competition {ck} not found in results ---")
            continue

        data = sim_results[ck]
        fixtures = data.get("fixtures", [])
        table = data.get("table", [])

        comp_name = COMP_NAME_LOOKUP.get(ck, f"Competition {ck}")

        print("\n" + "=" * 60)
        print(f" COMPETITION: {comp_name}")
        print("=" * 60)

        if show_fixtures:
            print("\n--- MATCH RESULTS ---")
            for mr in fixtures:
                print(
                    f"{mr['home_team'][:18]} {mr['home_goals']:>2}-"
                    f"{mr['away_goals']:<2} {mr['away_team'][:18]}"
                )

        if show_table:
            print("\n--- FINAL TABLE ---")
            header = (
                f"{'Pos':>3} {'Team':<25} {'P':>2} {'W':>2} "
                f"{'D':>2} {'L':>2} {'GF':>3} {'GA':>3} {'GD':>4} {'Pts':>4}"
            )
            print(header)
            for pos, row in enumerate(table, start=1):
                print(
                    f"{pos:>3} {row['teamName']:<25} {row.get('played',0):>2} "
                    f"{row.get('wins',0):>2} {row.get('draws',0):>2} {row.get('losses',0):>2} "
                    f"{row.get('gf',0):>3} {row.get('ga',0):>3} {row.get('gd',0):>4} {row.get('points',0):>4}"
                )

        print("=" * 60)


def displayCupResults(cup_results: Dict[int, Dict]) -> None:
    """Display cup competition results."""
    for ck, data in cup_results.items():
        comp_name = COMP_NAME_LOOKUP.get(ck, f"Competition {ck}")
        print("\n" + "=" * 60)
        print(f" CUP: {comp_name}")
        print("=" * 60)
        for rnd in data.get("rounds", []):
            print(f"\n{rnd['round_name']}")
            for m in rnd["matches"]:
                print(
                    f"{m['home_team'][:18]} {m['home_goals']:>2}-"
                    f"{m['away_goals']:<2} {m['away_team'][:18]}  -> {m['winner']}"
                )
        winner = data.get("winner")
        if winner:
            print(f"\nWinner: {winner}")
        print("=" * 60)


def displayContinentalResults(continental_results: Dict[int, Dict]) -> None:
    """Display continental competition results."""
    for ck, data in continental_results.items():
        comp_name = COMP_NAME_LOOKUP.get(ck, f"Competition {ck}")
        print("\n" + "=" * 60)
        print(f" CONTINENTAL: {comp_name}")
        print("=" * 60)
        
        # Group stage
        for group in data.get("groups", []):
            print(f"\n{group['group_name']}")
            print(f"{'Team':<25} {'P':>2} {'W':>2} {'D':>2} {'L':>2} {'GF':>3} {'GA':>3} {'GD':>4} {'Pts':>4}")
            for row in group["table"]:
                print(
                    f"{row['teamName']:<25} {row['played']:>2} {row['wins']:>2} "
                    f"{row['draws']:>2} {row['losses']:>2} {row['gf']:>3} {row['ga']:>3} "
                    f"{row['gd']:>4} {row['points']:>4}"
                )
        
        # Knockout stage
        for rnd in data.get("rounds", []):
            print(f"\n{rnd['round_name']}")
            for m in rnd["matches"]:
                print(
                    f"{m['home_team'][:18]} {m['home_goals']:>2}-"
                    f"{m['away_goals']:<2} {m['away_team'][:18]}  -> {m['winner']}"
                )
        
        winner = data.get("winner")
        if winner:
            print(f"\nWinner: {winner}")
        print("=" * 60)


def record_history(league_results: Dict[int, Dict], cup_results: Dict[int, Dict], 
                   continental_results: Dict[int, Dict]) -> None:
    """Record season history for all competitions."""
    season = CURRENT_SEASON + 1

    # League records
    for comp_id, data in league_results.items():
        table = data.get("table", [])
        comp_name = COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
        for pos, row in enumerate(table, start=1):
            tid = row.get("teamId")
            if tid not in TEAM_HISTORY:
                continue
            TEAM_HISTORY[tid]["records"].append({
                "season": season,
                "type": "league",
                "compId": comp_id,
                "compName": comp_name,
                "position": pos,
                "played": row.get("played", 0),
                "points": row.get("points", 0),
                "gd": row.get("gd", 0)
            })

    # Cup records
    for comp_id, data in cup_results.items():
        rounds = data.get("rounds", [])
        if not rounds:
            continue
        winner_name = data.get("winner")
        comp_name = COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")

        team_best_round = {}
        for rnd in rounds:
            rname = rnd.get("round_name", "")
            for m in rnd.get("matches", []):
                ht = m.get("home_team")
                at = m.get("away_team")
                for tn in (ht, at):
                    if not tn:
                        continue
                    tid = None
                    for t_id, t_obj in TEAM_ID_MAP.items():
                        if t_obj.get("teamName") == tn:
                            tid = t_id
                            break
                    if tid is None:
                        continue
                    team_best_round[tid] = rname

        for tid, rname in team_best_round.items():
            if tid not in TEAM_HISTORY:
                continue
            tname = TEAM_ID_MAP[tid].get("teamName", "")
            TEAM_HISTORY[tid]["records"].append({
                "season": season,
                "type": "cup",
                "compId": comp_id,
                "compName": comp_name,
                "best_round": rname,
                "winner": (tname == winner_name)
            })
    
    # Continental records
    for comp_id, data in continental_results.items():
        winner_name = data.get("winner")
        comp_name = COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
        
        # Group stage participants
        for group in data.get("groups", []):
            for row in group["table"]:
                tid = row.get("teamId")
                if tid in TEAM_HISTORY:
                    pos_in_group = group["table"].index(row) + 1
                    qualified = pos_in_group <= 2
                    TEAM_HISTORY[tid]["records"].append({
                        "season": season,
                        "type": "continental",
                        "compId": comp_id,
                        "compName": comp_name,
                        "stage": "Group Stage",
                        "qualified": qualified,
                        "winner": False
                    })
        
        # Knockout stage
        team_best_round = {}
        for rnd in data.get("rounds", []):
            rname = rnd.get("round_name", "")
            for m in rnd.get("matches", []):
                for tn in (m.get("home_team"), m.get("away_team")):
                    if not tn:
                        continue
                    tid = None
                    for t_id, t_obj in TEAM_ID_MAP.items():
                        if t_obj.get("teamName") == tn:
                            tid = t_id
                            break
                    if tid:
                        team_best_round[tid] = rname
        
        for tid, rname in team_best_round.items():
            if tid not in TEAM_HISTORY:
                continue
            tname = TEAM_ID_MAP[tid].get("teamName", "")
            is_winner = (tname == winner_name)
            
            # Update or add knockout record
            existing = [r for r in TEAM_HISTORY[tid]["records"] 
                       if r.get("season") == season and r.get("compId") == comp_id]
            if existing:
                existing[0]["stage"] = rname
                existing[0]["winner"] = is_winner
            else:
                TEAM_HISTORY[tid]["records"].append({
                    "season": season,
                    "type": "continental",
                    "compId": comp_id,
                    "compName": comp_name,
                    "stage": rname,
                    "winner": is_winner
                })


def adjust_team_ratings_after_season(league_results: Dict[int, Dict]) -> Dict[str, Dict]:
    """
    Adjust team ratings based on league performance, development rate, and finances.
    Now properly based on performance vs expected finish.
    """
    change_report = {}
    season = CURRENT_SEASON + 1

    for comp_id, data in league_results.items():
        if comp_id not in COMP_TEAMS:
            continue
        teams = COMP_TEAMS[comp_id]
        if not teams:
            continue

        # Calculate expected positions based on team strength
        strength_sorted = sorted(
            teams,
            key=lambda t: (
                t.get("attack", 50) + t.get("midfield", 50) + 
                t.get("defense", 50) + t.get("goalkeeping", 50)
            ),
            reverse=True
        )
        expected_pos = {t.get("teamId"): i + 1 for i, t in enumerate(strength_sorted)}
        
        table = data.get("table", [])
        finish_pos = {row.get("teamId"): i + 1 for i, row in enumerate(table)}
        n = max(len(teams), 1)

        for t in teams:
            tid = t.get("teamId")
            fp = finish_pos.get(tid, n)
            ep = expected_pos.get(tid, n)

            # Performance factor: positive if overperformed, negative if underperformed
            pos_diff = ep - fp
            performance_factor = pos_diff / float(max(1, n - 1))

            # Development rate factor (0 to 1 scale)
            dev = t.get("devRate", 5) / 10.0

            # Financial factor (0 to 1 scale)
            fin_norm = t.get("financial", 50) / 100.0

            # Base rating change calculation
            # Performance: -1.0 to 1.0, dev: -0.5 to 0.5, fin: -0.5 to 0.5
            base_change = (
                8.0 * performance_factor +      # Main driver: -8 to +8
                3.0 * (dev - 0.5) +              # Dev rate: -1.5 to +1.5
                2.0 * (fin_norm - 0.5)           # Finance: -1.0 to +1.0
            )

            # Random factor
            random_factor = random.uniform(-2.0, 2.0)
            total_change = base_change + random_factor

            # Rare dramatic changes
            if random.random() < 0.02:
                total_change *= random.uniform(1.5, 2.0)

            # Clamp total change
            total_change = max(-10.0, min(10.0, total_change))
            base_delta = int(round(total_change))

            # Apply to attack, midfield, defense with slight variation
            deltas = {}
            for key in ("attack", "midfield", "defense"):
                old = t.get(key, 50)
                attr_variation = random.randint(-1, 1)
                final_delta = base_delta + attr_variation
                final_delta = max(-10, min(10, final_delta))
                new_val = int(max(50, min(99, old + final_delta)))
                t[key] = new_val
                deltas[key] = new_val - old

            # Goalkeeping: less frequent changes
            gk_old = t.get("goalkeeping", 50)
            if random.random() < 0.20:
                gk_delta = int(base_delta * 0.7 + random.randint(-2, 2))
                gk_delta = max(-8, min(8, gk_delta))
                gk_new = int(max(50, min(99, gk_old + gk_delta)))
            else:
                gk_new = gk_old
            
            t["goalkeeping"] = gk_new
            deltas["goalkeeping"] = gk_new - gk_old

            # Financial changes based on league position
            old_finance = t.get("financial", 50)
            
            # Prize money effect (better finish = more money)
            prize_factor = (n - fp + 1) / n  # 0 to 1, higher for better positions
            prize_money_change = int(prize_factor * 10)
            
            # Performance bonus/penalty
            fin_perf_change = int(performance_factor * 5)
            
            # Random variation
            fin_random = random.randint(-3, 3)
            
            # Total financial change
            fin_delta = prize_money_change + fin_perf_change + fin_random
            
            # Rare takeover event (huge financial boost)
            takeover = False
            if random.random() < 0.015:  # 1.5% chance
                boost = random.randint(20, 40)
                fin_delta += boost
                takeover = True
            
            fin_delta = max(-20, min(30, fin_delta))
            new_finance = int(max(20, min(100, old_finance + fin_delta)))
            t["financial"] = new_finance

            # Reputation changes (slower than ratings)
            old_rep = t.get("reputationFactor", 50)
            rep_delta = int(performance_factor * 3 + random.uniform(-1.5, 1.5))
            rep_delta = max(-8, min(8, rep_delta))
            new_rep = int(max(40, min(100, old_rep + rep_delta)))
            t["reputationFactor"] = new_rep

            # Record ratings in history
            if tid in TEAM_HISTORY:
                ratings_list = TEAM_HISTORY[tid].get("ratings", [])
                if not ratings_list or ratings_list[-1].get("season") != season:
                    ratings_list.append({
                        "season": season,
                        "attack": t.get("attack", 50),
                        "midfield": t.get("midfield", 50),
                        "defense": t.get("defense", 50),
                        "goalkeeping": t.get("goalkeeping", 50),
                        "financial": new_finance,
                        "reputation": new_rep
                    })
                    TEAM_HISTORY[tid]["ratings"] = ratings_list

            change_report[t.get("teamName")] = {
                "deltas": deltas,
                "final_pos": fp,
                "expected_pos": ep,
                "comp_id": comp_id,
                "finance_delta": new_finance - old_finance,
                "reputation_delta": new_rep - old_rep,
                "takeover": takeover
            }

    return change_report


def print_change_report(change_report: Dict[str, Dict]) -> None:
    """Print rating changes after season."""
    print("\n================= RATING CHANGES AFTER SEASON =================")
    grouped = {}
    for name, info in change_report.items():
        comp_id = info["comp_id"]
        if comp_id not in grouped:
            grouped[comp_id] = []
        grouped[comp_id].append((name, info))

    for comp_id, entries in grouped.items():
        comp_name = COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
        print(f"\n{comp_name}")
        entries_sorted = sorted(entries, key=lambda x: x[1]["final_pos"])
        for name, info in entries_sorted:
            d = info["deltas"]
            takeover_str = " (TAKEOVER)" if info.get("takeover") else ""
            exp_str = f" [Exp: {info['expected_pos']}]" if info['final_pos'] != info['expected_pos'] else ""
            print(
                f"{name:<25} Pos {info['final_pos']:>2}{exp_str} | "
                f"ATT {d['attack']:>+2} MID {d['midfield']:>+2} DEF {d['defense']:>+2} GK {d['goalkeeping']:>+2} | "
                f"FIN {info['finance_delta']:>+3}{takeover_str}"
            )

    print("\n================================================================\n")


def get_season_statistics(league_results: Dict[int, Dict], cup_results: Dict[int, Dict],
                          continental_results: Dict[int, Dict]) -> Dict[str, Any]:
    """Calculate statistics for the completed season."""
    stats = {
        "top_scorer": {"team": "", "goals": 0},
        "most_improved": {"team": "", "change": 0},
        "biggest_surprise": {"team": "", "diff": 0},
        "champions": [],
        "relegated": [],
        "promoted": []
    }
    
    # Find champions from each league
    for comp_id, data in league_results.items():
        table = data.get("table", [])
        if table:
            comp_name = COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
            stats["champions"].append({
                "competition": comp_name,
                "team": table[0]["teamName"],
                "points": table[0]["points"]
            })
    
    # Find cup winners
    for comp_id, data in cup_results.items():
        winner = data.get("winner")
        if winner:
            comp_name = COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
            stats["champions"].append({
                "competition": comp_name,
                "team": winner,
                "points": None
            })
    
    # Find continental winners
    for comp_id, data in continental_results.items():
        winner = data.get("winner")
        if winner:
            comp_name = COMP_NAME_LOOKUP.get(comp_id, f"Competition {comp_id}")
            stats["champions"].append({
                "competition": comp_name,
                "team": winner,
                "points": None
            })
    
    return stats


def export_season_results(filename: str = "season_export.json") -> None:
    """Export current season results to JSON file."""
    export_data = {
        "season": CURRENT_SEASON,
        "league_history": LEAGUE_HISTORY,
        "cup_history": CUP_HISTORY,
        "team_history": TEAM_HISTORY,
        "team_data": TEAM_ID_MAP
    }
    
    export_path = os.path.join(BASE_DIR, filename)
    try:
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)
        print(f"\n✓ Season data exported to {filename}")
    except IOError as e:
        print(f"\n✗ Failed to export: {e}")


def import_season_results(filename: str = "season_export.json") -> bool:
    """Import season results from JSON file."""
    global CURRENT_SEASON, LEAGUE_HISTORY, CUP_HISTORY, TEAM_HISTORY, TEAM_ID_MAP
    
    import_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(import_path):
        print(f"\n✗ File not found: {filename}")
        return False
    
    try:
        with open(import_path, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        CURRENT_SEASON = import_data.get("season", 0)
        LEAGUE_HISTORY = import_data.get("league_history", [])
        CUP_HISTORY = import_data.get("cup_history", [])
        TEAM_HISTORY = import_data.get("team_history", {})
        
        # Merge team data (update existing teams with imported data)
        imported_teams = import_data.get("team_data", {})
        for tid_str, team_data in imported_teams.items():
            tid = int(tid_str)
            if tid in TEAM_ID_MAP:
                TEAM_ID_MAP[tid].update(team_data)
        
        print(f"\n✓ Season data imported from {filename}")
        print(f"  Current season: {CURRENT_SEASON}")
        print(f"  Seasons in history: {len(LEAGUE_HISTORY)}")
        return True
    except (json.JSONDecodeError, IOError, ValueError) as e:
        print(f"\n✗ Failed to import: {e}")
        return False


def run_season(show_fixtures: bool = False, show_table: bool = True, 
               run_cups: bool = True, run_continental: bool = True) -> Tuple[Dict, Dict, Dict, Dict]:
    """Run a complete season simulation."""
    global CURRENT_SEASON, LEAGUE_HISTORY, CUP_HISTORY, _RATING_CACHE

    # Clear rating cache at start of season
    _RATING_CACHE.clear()

    # Prepare competition inputs
    league_input = {cid: teams for cid, teams in COMP_TEAMS.items() if COMP_FORMAT.get(cid) == 0}
    cup_input = {cid: teams for cid, teams in COMP_TEAMS.items() if COMP_FORMAT.get(cid) == 1}
    continental_input = {cid: teams for cid, teams in COMP_TEAMS.items() if COMP_FORMAT.get(cid) == 5}

    # Simulate leagues
    league_results = simSeason(league_input)
    if show_table or show_fixtures:
        displayResults(league_results, show_fixtures=show_fixtures, show_table=show_table)

    # Simulate cups
    if run_cups and cup_input:
        cup_results = simCups(cup_input, league_results)
        displayCupResults(cup_results)
    else:
        cup_results = {}

    # Simulate continental competitions
    if run_continental and continental_input:
        continental_results = simContinental(continental_input, league_results)
        displayContinentalResults(continental_results)
    else:
        continental_results = {}

    # Adjust ratings
    change_report = adjust_team_ratings_after_season(league_results)
    print_change_report(change_report)

    # Record history
    record_history(league_results, cup_results, continental_results)

    # Increment season
    CURRENT_SEASON += 1
    LEAGUE_HISTORY.append(league_results)
    CUP_HISTORY.append(cup_results)

    # Get statistics
    season_stats = get_season_statistics(league_results, cup_results, continental_results)

    return league_results, cup_results, continental_results, season_stats


def main():
    load_world()
    if not COMP_TEAMS:
        print("No competitions found.")
        return
    run_season(show_fixtures=False, show_table=True, run_cups=True, run_continental=True)


if __name__ == "__main__":
    main()