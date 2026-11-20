"""Flow-decomposition forecaster for GTA VI trophy earn rates.

A rate changes for exactly two reasons: new players get tracked (they
arrive holding almost nothing, so every rate is diluted), and players
who were already tracked keep playing (so earners accumulate). This
program measures the two flows separately from the gaps between page
refreshes and then replays them forward to the target.

From the distinct page states (reads that repeat the previous read are
the same refresh and are dropped) it builds, per trophy, two numbers:

  * uptake  -- of the players who joined between two refreshes, the
    share who already held the trophy at the next refresh. Estimated
    from every interval, weighted by how many players the interval
    added, and shrunk toward the page-wide uptake for the trophy's
    tier, because one interval's small counts lie.
  * grind   -- earners gained per hour per thousand tracked players
    during intervals when the tracked crowd barely grew: the pure
    progression flow of the existing crowd. Also tier-shrunk.

The forecast then needs the crowd size at the target: players are
fitted on a log-hours clock and walked forward from the last count.
Earners at the target are the last earners, plus uptake applied to the
new crowd (discounted, since the newest joiners have had less time to
earn than the average joiner the uptake was measured on), plus grind
accumulated over the horizon on the average crowd. Divide, clamp, and
put a spread on the logit scale that widens with the horizon, with
the disagreement between intervals, and for trophies whose earner
count is still small.

When the history holds a single distinct state, no flow can be
measured. The program then falls back to a dilution prior: the next
refresh mostly adds fresh players, medians sag by an amount that
grows with the horizon and with rarity, and the spread stays broad.

Standard library only, fully deterministic. Every *.in in the input
directory produces a *.out in the output directory.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SRC = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
DST = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

ZS = (-1.644854, -0.674490, 0.0, 0.674490, 1.644854)
TIER_PRIOR_UPTAKE = {"platinum": 0.15, "gold": 0.30, "silver": 0.45, "bronze": 0.55}


def lg(pct):
    p = min(99.99, max(0.01, pct)) / 100.0
    return math.log(p / (1.0 - p))


def inv(lg_value):
    if lg_value >= 0:
        return 100.0 / (1.0 + math.exp(-lg_value))
    e = math.exp(lg_value)
    return 100.0 * e / (1.0 + e)


def q4(x):
    v = math.floor(x * 10000.0 + 0.5) / 10000.0
    return int(v) if v == int(v) else v


def stamp(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def page_states(case):
    states = []
    prev = None
    for read in case["history"]:
        key = (read["players_tracked"], tuple(read["rates"]))
        if key == prev:
            continue
        prev = key
        states.append(read)
    return states


def earners_of(read, idx):
    rate = read["rates"][idx]
    if rate is None:
        return None
    return rate / 100.0 * read["players_tracked"]


def measure_flows(case, states):
    """Per trophy: (uptake, grind per hour per 1000 players, scatter)."""
    n = len(case["trophies"])
    intervals = []
    for a, b in zip(states, states[1:]):
        hours = max((stamp(b["at"]) - stamp(a["at"])).total_seconds() / 3600.0, 0.05)
        joined = b["players_tracked"] - a["players_tracked"]
        intervals.append((a, b, hours, joined))
    # Pass one: grind, from the quiet intervals where the crowd barely
    # grew, so almost every gained earner is an old player progressing.
    grind_num = [0.0] * n
    grind_den = [0.0] * n
    for a, b, hours, joined in intervals:
        if joined > max(10.0, 0.02 * a["players_tracked"]):
            continue
        for i in range(n):
            ea = earners_of(a, i)
            eb = earners_of(b, i)
            if ea is None or eb is None:
                continue
            grind_num[i] += eb - ea
            grind_den[i] += hours * a["players_tracked"] / 1000.0
    grinds = []
    for i, tr in enumerate(case["trophies"]):
        last_rate = states[-1]["rates"][i] or 0.0
        grind_prior = 0.02 * last_rate  # per hour per 1000 players, scaled by level
        g = ((grind_num[i] + grind_prior * 30.0) / (grind_den[i] + 30.0)
             if grind_den[i] > 0 else grind_prior)
        grinds.append(max(g, 0.0))
    # Pass two: uptake, from the busy intervals, after subtracting the
    # earners the old crowd's grind already explains -- otherwise the
    # joiners get credited for progress they never made.
    up_num = [0.0] * n
    up_den = [0.0] * n
    moves = [[] for _ in range(n)]
    for a, b, hours, joined in intervals:
        for i in range(n):
            ea = earners_of(a, i)
            eb = earners_of(b, i)
            if ea is None or eb is None:
                continue
            gained = eb - ea
            moves[i].append(gained)
            if joined >= 25:
                explained = grinds[i] * hours * a["players_tracked"] / 1000.0
                up_num[i] += gained - explained
                up_den[i] += joined
    flows = []
    for i, tr in enumerate(case["trophies"]):
        prior = TIER_PRIOR_UPTAKE.get(tr["tier"], 0.5)
        # Shrinkage: 400 joiners of evidence before the measured uptake
        # outweighs the tier prior.
        uptake = (up_num[i] + prior * 400.0) / (up_den[i] + 400.0) if up_den[i] > 0 else prior
        uptake = min(max(uptake, 0.0), 1.0)
        grind = grinds[i]
        if len(moves[i]) >= 2:
            mean_move = sum(moves[i]) / len(moves[i])
            scatter = math.sqrt(sum((m - mean_move) ** 2 for m in moves[i]) / len(moves[i]))
        else:
            scatter = 0.0
        flows.append((uptake, grind, scatter))
    return flows


def players_at_target(case, states):
    t0 = stamp(states[0]["at"])
    xs = [math.log1p((stamp(r["at"]) - t0).total_seconds() / 3600.0) for r in states]
    ys = [math.log(max(r["players_tracked"], 1)) for r in states]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx > 1e-12 else 0.0
    x_t = math.log1p((stamp(case["target"]) - t0).total_seconds() / 3600.0)
    # Arrivals bend: a crowd that doubled every few hours at launch does
    # not keep that pace for a week, so the extrapolation leg walks at a
    # damped slope and the total growth is capped at a factor of 12.
    walked = ys[-1] + 0.7 * slope * (x_t - xs[-1])
    cap = ys[-1] + math.log(12.0)
    return math.exp(min(walked, cap)), slope


def flow_forecast(case, states):
    flows = measure_flows(case, states)
    p_target, _ = players_at_target(case, states)
    last = states[-1]
    p_last = last["players_tracked"]
    horizon_h = case["horizon_minutes"] / 60.0
    joined = max(p_target - p_last, 0.0)
    crowd_avg = 0.5 * (p_target + p_last)
    out = []
    for i, tr in enumerate(case["trophies"]):
        uptake, grind, scatter = flows[i]
        e_last = earners_of(last, i) or 0.0
        # Joiners counted at 65% of the measured uptake: the measured
        # figure belongs to joiners who had a full interval to play.
        e_target = (e_last
                    + 0.65 * uptake * joined
                    + grind * horizon_h * crowd_avg / 1000.0)
        rate = min(99.99, max(0.01, 100.0 * e_target / p_target))
        sigma = (0.34
                 + 0.16 * math.sqrt(horizon_h / 24.0)
                 + 0.30 * scatter / max(e_last, 25.0)
                 + 0.70 / math.sqrt(max(e_last, 1.0)))
        out.append((tr["id"], lg(rate), min(max(sigma, 0.24), 2.3)))
    return out


def prior_forecast(case, states):
    days = case["horizon_minutes"] / 1440.0
    last = states[-1]
    players = max(last["players_tracked"], 1)
    out = []
    for i, tr in enumerate(case["trophies"]):
        rate = last["rates"][i] or 0.0
        earners = rate * players / 100.0
        sag = (0.25 + 0.85 * (1.0 - rate / 100.0)) * math.log1p(1.8 * days)
        sigma = 0.58 + 0.5 * math.sqrt(days) + 0.55 / math.sqrt(max(earners, 1.0))
        out.append((tr["id"], lg(rate) - sag, min(sigma, 2.5)))
    return out


def forecast(case):
    states = page_states(case)
    if not states:
        raise ValueError("empty history")
    span_h = (stamp(states[-1]["at"]) - stamp(states[0]["at"])).total_seconds() / 3600.0
    if len(states) < 2 or span_h < 1.0:
        centred = prior_forecast(case, states)
    else:
        centred = flow_forecast(case, states)
    return {"trophies": [
        {"id": tid, "q": sorted(q4(inv(c + z * s)) for z in ZS)}
        for tid, c, s in centred]}


def main():
    DST.mkdir(parents=True, exist_ok=True)
    for path in sorted(SRC.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(forecast(case), separators=(",", ":")) + "\n"
        (DST / (path.stem + ".out")).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
