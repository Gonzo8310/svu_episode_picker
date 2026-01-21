#!/usr/bin/env python3
"""
svu_picker.py
 
Simple prompt-driven SVU episode picker.
 
Usage examples:
  # pick 3 episodes from S2E1 to S6E20 using local CSV
  python svu_picker.py --range "S2E1>S6E20" --data episodes.csv
 
  # show details for a specific episode title
  python svu_picker.py --details "Repression" --data episodes.csv
 
CSV columns (header required):
season,episode,title,air_date,imdb_id,imdb_rating,features_george_huang,heavy_finn_munch,heavy_trial,one_sentence_plot,one_sentence_reason
 
Boolean columns can be '1'/'0' or 'True'/'False'.
 
If you don't have a CSV, edit SAMPLE_EPISODES below and run without --data.
"""
import csv
import argparse
import sys
import json
from datetime import datetime
from typing import List, Dict, Optional
import textwrap
import random
import os
import requests
 
# ---------- CONFIG ----------
OMDB_API_KEY = os.getenv("OMDB_API_KEY")  # set if you want live lookups
MAX_SEASONS_ALLOWED = (1, 12)  # global allowed seasons (1-12)
MIN_IMDB_RATING = 8.0
DEFAULT_NUM_RESULTS = 3
# ----------------------------
 
SAMPLE_EPISODES = [
    # minimal example rows; expand or provide a CSV file for full runs
    {
        "season": 2, "episode": 21, "title": "Scourge", "air_date": "2001-05-11",
        "imdb_id": "tt0629728", "imdb_rating": 8.5,
        "features_george_huang": True, "heavy_finn_munch": False, "heavy_trial": False,
        "one_sentence_plot": "The SVU hunts a sadistic serial killer whose crimes escalate in brutality and psychological complexity.",
        "one_sentence_reason": "A tense, profiler-driven episode where George Huang’s insights meaningfully shape the investigation."
    },
    {
        "season": 3, "episode": 1, "title": "Repression", "air_date": "2001-09-28",
        "imdb_id": "tt0629715", "imdb_rating": 8.2,
        "features_george_huang": True, "heavy_finn_munch": False, "heavy_trial": False,
        "one_sentence_plot": "A rape case hinges on repressed childhood memories, raising doubts about truth, trauma, and memory.",
        "one_sentence_reason": "Classic Huang-focused psychology episode with moral ambiguity and no trial-heavy payoff."
    },
    {
        "season": 3, "episode": 2, "title": "Wrath", "air_date": "2001-10-05",
        "imdb_id": "tt0629756", "imdb_rating": 8.3,
        "features_george_huang": True, "heavy_finn_munch": False, "heavy_trial": False,
        "one_sentence_plot": "A killer seeks revenge against people tied to Benson’s past cases, turning SVU’s history against them.",
        "one_sentence_reason": "High emotional stakes, strong profiling, and relentless momentum without courtroom drag."
    },
    # add more sample rows if you like...
]
 
# ---------- Helpers ----------
def parse_range(range_str: str):
    """Parse 'SxEy>SxEy' into integer ranges: (s1,e1,s2,e2)"""
    try:
        left, right = range_str.split(">")
        def se_to_tuple(s):
            s = s.strip().upper()
            if not (s.startswith("S") and "E" in s):
                raise ValueError
            s_idx = int(s[1:s.index("E")])
            e_idx = int(s[s.index("E")+1:])
            return s_idx, e_idx
        s1, e1 = se_to_tuple(left)
        s2, e2 = se_to_tuple(right)
        if (s2 < s1) or (s2 == s1 and e2 < e1):
            raise ValueError("Range end must be >= range start.")
        return (s1, e1, s2, e2)
    except Exception as ex:
        raise argparse.ArgumentTypeError(f"Invalid range format: '{range_str}'. Expected 'SxEy>SxEy'") from ex
 
def load_csv(path: str) -> List[Dict]:
    rows = []
    with open(path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(normalize_row(r))
    return rows
 
def normalize_row(r: Dict) -> Dict:
    def to_bool(v):
        if isinstance(v, bool): return v
        if v is None: return False
        s = str(v).strip().lower()
        return s in ("1","true","yes","y","t")
    def to_float(v):
        try: return float(v)
        except: return None
    return {
        "season": int(r.get("season") or 0),
        "episode": int(r.get("episode") or 0),
        "title": r.get("title") or r.get("name") or "",
        "air_date": r.get("air_date") or "",
        "imdb_id": r.get("imdb_id") or "",
        "imdb_rating": to_float(r.get("imdb_rating")),
        "features_george_huang": to_bool(r.get("features_george_huang")),
        "heavy_finn_munch": to_bool(r.get("heavy_finn_munch")),
        "heavy_trial": to_bool(r.get("heavy_trial")),
        "one_sentence_plot": r.get("one_sentence_plot") or "",
        "one_sentence_reason": r.get("one_sentence_reason") or ""
    }
 
def in_range(ep: Dict, s1,e1,s2,e2) -> bool:
    """Return True if episode falls in inclusive range S1E1..S2E2"""
    # linearize to absolute episode index: season*100 + episode
    v = ep["season"]*100 + ep["episode"]
    start = s1*100 + e1
    end = s2*100 + e2
    return start <= v <= end
 
def filter_episodes(episodes: List[Dict], rng, min_imdb=MIN_IMDB_RATING, allow_seasons=MAX_SEASONS_ALLOWED, exclude_seasons: Optional[List[int]]=None) -> List[Dict]:
    s1,e1,s2,e2 = rng
    ex_seasons = set(exclude_seasons or [])
    out = []
    for ep in episodes:
        if ex_seasons and ep["season"] in ex_seasons:
            continue
        if not in_range(ep, s1,e1,s2,e2):
            continue
        if not (allow_seasons[0] <= ep["season"] <= allow_seasons[1]):
            continue
        if not ep["features_george_huang"]:
            continue
        if ep["heavy_finn_munch"]:
            continue
        if ep["heavy_trial"]:
            continue
        if ep["imdb_rating"] is None or ep["imdb_rating"] < min_imdb:
            continue
        out.append(ep)
    return out
 
def rank_and_select(candidates: List[Dict], n=DEFAULT_NUM_RESULTS, seed=42) -> List[Dict]:
    """Sort by imdb_rating desc, then deterministic tie-break by title; return top n."""
    random.seed(seed)
    # stable sort
    candidates_sorted = sorted(candidates, key=lambda e: (-float(e.get("imdb_rating") or 0.0), e.get("title","")))
    return candidates_sorted[:n]
 
def format_episode(ep: Dict) -> str:
    tpl = (
        f"**{ep['title']}** (S{ep['season']}E{ep['episode']})\n"
        f"{ep['air_date']}\n"
        f"IMDb Rating: {ep['imdb_rating']}\n"
        f"{ep.get('one_sentence_plot','')}\n"
        f"{ep.get('one_sentence_reason','')}\n"
    )
    return tpl
 
def details_expand(ep: Dict) -> str:
    """
    Produce the 'Details' expansion: 4 plot bullets + 4 why bullets.
    If the CSV contains longer fields these will be used; otherwise, this function
    will heuristically expand the one_sentence fields into 4 bullets.
    """
    def expand_sentence_to_bullets(sentence: str, max_bullets=4):
        # trivial heuristic split by comma/and/then to create more sentences
        if not sentence:
            return ["(No detail available)"] * max_bullets
        parts = [p.strip() for p in sentence.replace(" and ", ", ").split(",") if p.strip()]
        # if too few parts, split into clauses of ~10 words
        if len(parts) < max_bullets:
            words = sentence.split()
            approx = max(1, len(words)//max_bullets)
            bullets = []
            for i in range(max_bullets):
                chunk = " ".join(words[i*approx:(i+1)*approx])
                if chunk:
                    bullets.append(chunk.strip())
            # pad
            while len(bullets) < max_bullets:
                bullets.append(bullets[-1])
            return bullets[:max_bullets]
        else:
            return parts[:max_bullets]
    plot_bullets = expand_sentence_to_bullets(ep.get("one_sentence_plot",""))
    reason_bullets = expand_sentence_to_bullets(ep.get("one_sentence_reason",""))
    out_lines = []
    out_lines.append(f"**{ep['title']}**\n**{ep['air_date']}**\n**IMDb Rating:** {ep['imdb_rating']}\n")
    out_lines.append("**Plot:**")
    for b in plot_bullets:
        out_lines.append(f"- {b}")
    out_lines.append("\n**Why it’s a great pick:**")
    for b in reason_bullets:
        out_lines.append(f"- {b}")
    return "\n".join(out_lines)
 
def fetch_imdb_rating_from_omdb(imdb_id: str) -> Optional[float]:
    """Optional: fetch rating using OMDb API if key available."""
    if not OMDB_API_KEY or not imdb_id:
        return None
    url = "http://www.omdbapi.com/"
    params = {"apikey": OMDB_API_KEY, "i": imdb_id}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()
        rating = data.get("imdbRating")
        if rating and rating != "N/A":
            return float(rating)
    except Exception as e:
        print(f"[warning] OMDb lookup failed for {imdb_id}: {e}", file=sys.stderr)
    return None
 
# ---------- CLI ----------
def main(argv=None):
    parser = argparse.ArgumentParser(description="SVU episode picker")
    parser.add_argument("--range", type=str, help="Range in the format 'SxEy>SxEy' (e.g. S2E1>S6E20)")
    parser.add_argument("--data", type=str, help="Path to CSV file with episode metadata (optional). If omitted, sample data is used.")
    parser.add_argument("--num", type=int, default=3, help="Number of episodes to return")
    parser.add_argument("--details", type=str, help="Title of episode to show expanded details for (e.g. 'Repression')")
    parser.add_argument("--exclude-seasons", type=str, help="Comma-separated seasons to exclude (e.g. 6)", default="")
    args = parser.parse_args(argv)
 
    # load episodes
    if args.data:
        episodes = load_csv(args.data)
    else:
        # use sample
        episodes = [normalize_row(r) for r in SAMPLE_EPISODES]
 
    # optional: refresh imdb ratings via OMDb if some rows lack them
    # (comment out if you don't want external calls)
    for ep in episodes:
        if (ep.get("imdb_rating") is None or ep.get("imdb_rating") < 0.1) and ep.get("imdb_id"):
            rating = fetch_imdb_rating_from_omdb(ep["imdb_id"])
            if rating:
                ep["imdb_rating"] = rating
 
    # handle details-only mode
    if args.details:
        title = args.details.strip()
        matched = [e for e in episodes if e["title"].lower() == title.lower()]
        if not matched:
            print(f"No episode found with title '{title}'.")
            sys.exit(1)
        print(details_expand(matched[0]))
        sys.exit(0)
 
    if not args.range:
        print("Please provide --range 'SxEy>SxEy' (e.g. S2E1>S6E20) or use --details.")
        sys.exit(1)
    rng = parse_range(args.range)
    exclude_seasons = []
    if args.exclude_seasons:
        exclude_seasons = [int(x) for x in args.exclude_seasons.split(",") if x.strip().isdigit()]
 
    # apply filters
    candidates = filter_episodes(episodes, rng, min_imdb=MIN_IMDB_RATING, allow_seasons=MAX_SEASONS_ALLOWED, exclude_seasons=exclude_seasons)
    if not candidates:
        print("No episodes matched your constraints in that range. Try expanding the range or check your dataset.")
        sys.exit(0)
 
    results = rank_and_select(candidates, n=args.num)
    for ep in results:
        print(format_episode(ep))
        print("---")
 
if __name__ == "__main__":
    main()
