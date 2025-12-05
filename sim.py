import os
import json
import random
import math

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

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


def _load_json(path, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _slug(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def load_root_data():
    global CONTINENTS, POSITIONS
    continents_path = os.path.join(DATA_DIR, "continents.json")
    positions_path = os.path.join(DATA_DIR, "positions.json")
    CONTINENTS = _load_json(continents_path, [])
    POSITIONS = _load_json(positions_path, [])


def load_continent(cont_folder_name: str):
    continent_dir = os.path.join(DATA_DIR, cont_folder_name)
    if not os.path.isdir(continent_dir):
        return

    nations_path = os.path.join(continent_dir, "nations.json")
    comps_path = os.path.join(continent_dir, "comps.json")

    nations = _load_json(nations_path, [])
    comps = _load_json(comps_path, [])

    NATIONS_BY_CONTINENT[cont_folder_name] = nations
    CONTINENT_LEVEL_COMPS[cont_folder_name] = comps

    nation_name_by_id = {}
    for n in nations:
        nid = n.get("nationId")
        cid = n.get("continentId")
        nation_name_by_id[(cid, nid)] = n.get("nationName", f"Nation {nid}")

    for entry in os.scandir(continent_dir):
        if not entry.is_dir():
            continue

        nation_folder = entry.name
        nation_path = entry.path

        if nation_folder.lower() in ("nations",):
            continue

        nation_comps_path = os.path.join(nation_path, "comps.json")
        nation_teams_path = os.path.join(nation_path, "teams.json")

        nation_comps = _load_json(nation_comps_path, [])
        nation_teams_raw = _load_json(nation_teams_path, {})

        NATION_COMPS[nation_path] = nation_comps
        NATION_TEAMS[nation_path] = nation_teams_raw

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

        for comp in nation_comps:
            comp_id = comp.get("compId")
            nation_id = comp.get("nationId")
            comp_format = comp.get("format")
            COMP_FORMAT[comp_id] = comp_format
            COMP_TIER[comp_id] = comp.get("tier", 99)

            if comp_format == 0:
                comp_key_str = str(comp_id)
                teams_list = nation_teams_raw.get(comp_key_str, [])
                if not teams_list:
                    continue
                COMP_TEAMS[comp_id] = teams_list
                for t in teams_list:
                    tid = t.get("teamId")
                    if tid is not None:
                        TEAM_ID_MAP[tid] = t
            elif comp_format == 1:
                all_teams = []
                for v in nation_teams_raw.values():
                    all_teams.extend(v)
                if not all_teams:
                    continue
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


def init_team_history():
    for tid, t in TEAM_ID_MAP.items():
        if tid not in TEAM_HISTORY:
            TEAM_HISTORY[tid] = {
                "name": t.get("teamName", ""),
                "records": [],
                "ratings": []
            }


def load_world():
    load_root_data()
    for entry in os.scandir(DATA_DIR):
        if entry.is_dir():
            load_continent(entry.name)
    init_team_history()


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


def _team_rating(t):
    atk = t.get("attack", 50)
    mid = t.get("midfield", 50)
    dfn = t.get("defense", 50)
    gk = t.get("goalkeeping", 50)
    return 0.35 * atk + 0.35 * mid + 0.2 * dfn + 0.1 * gk


def _simulate_match(home, away):
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

    if goals_home == goals_away:
        if random.random() < 0.5:
            goals_home += 1
        else:
            goals_away += 1

    return goals_home, goals_away


def simSeason(team_stats_by_key):
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

            goals_home, goals_away = _simulate_match(home, away)

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


def simCups(cup_stats_by_key, league_results):
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
                gh, ga = _simulate_match(home, away)
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
                gh, ga = _simulate_match(home, away)
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


def displayResults(sim_results, comp_keys=None, show_fixtures=False, show_table=True):
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


def displayCupResults(cup_results):
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


def record_history(league_results, cup_results):
    season = CURRENT_SEASON + 1

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


def adjust_team_ratings_after_season(sim_results):
    change_report = {}

    season = CURRENT_SEASON + 1

    for comp_id, data in sim_results.items():
        if comp_id not in COMP_TEAMS:
            continue
        teams = COMP_TEAMS[comp_id]
        if not teams:
            continue

        strength_sorted = sorted(
            teams,
            key=lambda t: t.get("attack", 50)
            + t.get("midfield", 50)
            + t.get("defense", 50)
            + t.get("goalkeeping", 50),
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

            pos_diff = ep - fp
            pos_factor = pos_diff / float(max(1, n - 1))

            dev = t.get("devRate", 5) / 10.0
            fin_norm = t.get("financial", 50) / 100.0
            rep_norm = t.get("reputationFactor", 50) / 100.0

            mean_delta = (
                6.0 * pos_factor
                + 1.5 * (dev - 0.5)
                + 1.0 * (fin_norm - 0.5)
                + 0.8 * (rep_norm - 0.5)
            )

            noise = random.uniform(-2.0, 2.0)
            raw_delta = mean_delta + noise

            if random.random() < 0.03:
                raw_delta *= random.uniform(1.8, 2.5)

            raw_delta = max(-8.0, min(8.0, raw_delta))
            base_delta_int = int(round(raw_delta))

            deltas = {}

            for key in ("attack", "midfield", "defense"):
                old = t.get(key, 50)
                attr_noise = random.randint(-1, 1)
                final_delta = base_delta_int + attr_noise
                if final_delta > 8:
                    final_delta = 8
                if final_delta < -8:
                    final_delta = -8
                new_val = int(max(50, min(99, old + final_delta)))
                t[key] = new_val
                deltas[key] = new_val - old

            gk_old = t.get("goalkeeping", 50)
            if random.random() < 0.18:
                if base_delta_int > 0:
                    sign = 1 if random.random() < 0.8 else -1
                elif base_delta_int < 0:
                    sign = -1 if random.random() < 0.8 else 1
                else:
                    sign = 1 if random.random() < 0.5 else -1
                magnitude = random.randint(2, 6)
                gk_delta = sign * magnitude
                if gk_delta > 10:
                    gk_delta = 10
                if gk_delta < -10:
                    gk_delta = -10
                gk_new = int(max(50, min(99, gk_old + gk_delta)))
            else:
                gk_delta = 0
                gk_new = gk_old

            t["goalkeeping"] = gk_new
            deltas["goalkeeping"] = gk_new - gk_old

            old_finance = t.get("financial", 50)
            old_rep = t.get("reputationFactor", 50)

            fin_delta = int(round(8.0 * pos_factor + random.uniform(-3.0, 3.0)))
            fin_delta = max(-15, min(15, fin_delta))
            new_finance = int(max(0, min(100, old_finance + fin_delta)))

            rep_delta = int(round(4.0 * pos_factor + random.uniform(-2.0, 2.0)))
            rep_delta = max(-10, min(10, rep_delta))
            new_rep = int(max(0, min(100, old_rep + rep_delta)))

            takeover = False
            if random.random() < 0.01:
                boost = random.randint(15, 35)
                new_finance = int(min(100, new_finance + boost))
                takeover = True

            t["financial"] = new_finance
            t["reputationFactor"] = new_rep

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
                "final_pos": finish_pos.get(tid, n),
                "comp_id": comp_id,
                "finance_delta": new_finance - old_finance,
                "reputation_delta": new_rep - old_rep,
                "takeover": takeover
            }

    return change_report


def print_change_report(change_report):
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
            print(
                f"{name:<25} "
                f"ATT {d['attack']:>+2} | "
                f"MID {d['midfield']:>+2} | "
                f"DEF {d['defense']:>+2} | "
                f"GK {d['goalkeeping']:>+2}{takeover_str}"
            )

    print("\n================================================================\n")


def run_season(show_fixtures=False, show_table=True, run_cups=True):
    global CURRENT_SEASON, LEAGUE_HISTORY, CUP_HISTORY

    league_input = {cid: teams for cid, teams in COMP_TEAMS.items() if COMP_FORMAT.get(cid) == 0}
    cup_input = {cid: teams for cid, teams in COMP_TEAMS.items() if COMP_FORMAT.get(cid) == 1}

    league_results = simSeason(league_input)
    if show_table or show_fixtures:
        displayResults(league_results, show_fixtures=show_fixtures, show_table=show_table)

    if run_cups and cup_input:
        cup_results = simCups(cup_input, league_results)
        displayCupResults(cup_results)
    else:
        cup_results = {}

    change_report = adjust_team_ratings_after_season(league_results)
    print_change_report(change_report)

    record_history(league_results, cup_results)

    CURRENT_SEASON += 1
    LEAGUE_HISTORY.append(league_results)
    CUP_HISTORY.append(cup_results)

    return league_results, cup_results, change_report


def main():
    load_world()
    if not COMP_TEAMS:
        print("No competitions found.")
        return
    run_season(show_fixtures=False, show_table=True, run_cups=True)


if __name__ == "__main__":
    main()
