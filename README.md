# gta6-trophy-flow-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/berkahmuse/gta6-trophy-flow-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/berkahmuse/gta6-trophy-flow-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

An earn rate changes for exactly two reasons: new players get tracked (they arrive holding almost nothing, diluting every rate) and the already-tracked crowd keeps playing (earners accumulate). This forecaster measures the two flows separately from the gaps between Exophase page refreshes — an uptake share for joiners, estimated net of the old crowd's grind, and a grind rate from the quiet intervals — then replays both flows forward: the crowd size is walked to the target on a damped log-time fit, joiners contribute at a discounted uptake, and the existing crowd keeps grinding over the horizon. Spreads widen with interval disagreement and shrink as earner counts grow. With only one distinct page state there is no flow to measure, so a dilution prior with wide bands takes over.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=v3r3ap81&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
