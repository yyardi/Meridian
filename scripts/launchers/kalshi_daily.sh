#!/usr/bin/env bash
# kalshi_daily.sh -- every day, Kalshi's in-play books and prints for that ET day's NBA, NFL and
# college football games, beside the Polymarket stream tapes, so the two venues can be matched
# instant to instant all season (docs/math/cross-venue-inplay-football.md). One socket per league;
# a league with no game that day finds nothing and exits. Places nothing.
#
# Installed on prod's crontab 2026-10-19 (the operator: grab as much data as we can):
#   30 15 * * * sudo -n /opt/meridian/scripts/launchers/kalshi_daily.sh >> /opt/meridian/artifacts/reads/cron.log 2>&1
set -euo pipefail
L=$(dirname "$0")
D=$(TZ=America/New_York date +%y%b%d | tr '[:lower:]' '[:upper:]')   # 26OCT20: the tickers' date tag is the ET date
T=$(TZ=America/New_York date +%m%d)
# 15:30Z to 06:30Z: a noon-ET weekend kickoff through a 10:30 pm ET tip's final.
M=900
"$L/launch_kalshi_slate.sh" KXNBAGAME,KXNBASPREAD,KXNBATOTAL "$D" $M "nba-$T"
"$L/launch_kalshi_slate.sh" KXNFLGAME,KXNFLSPREAD,KXNFLTOTAL "$D" $M "nfl-$T"
"$L/launch_kalshi_slate.sh" KXNCAAFGAME,KXNCAAFSPREAD,KXNCAAFTOTAL "$D" $M "cfb-$T"
