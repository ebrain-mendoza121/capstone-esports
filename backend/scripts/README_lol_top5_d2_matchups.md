# LoL Top-5 D2+ Matchups Generator

This script builds a CSV with the 5 best matchups for each champion using Riot Data Dragon and LoLalytics.

Install:
pip install -r requirements.txt

Run:
python lol_top5_d2_matchups.py

Test run:
python lol_top5_d2_matchups.py --champion-limit 10 --sleep 1.5 --out sample.csv

Notes:
- role is normalized to TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
- support from LoLalytics is exported as UTILITY
- rows are kept only if games_played > 1000 by default
- main role is inferred from the champion's default D2+ build page
