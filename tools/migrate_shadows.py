#!/usr/bin/env python3
"""Migrate shadow profile configuration from .env to shadows.toml.

Usage:
    python3 tools/migrate_shadows.py

Reads SPOT_SHADOW_* and FUTURES_SHADOW_* variables from .env and writes
shadows.toml in the repo root.  The script never modifies .env; instead it
prints the lines/patterns you should remove manually.

Safe to re-run: exits with an error if shadows.toml already exists.
"""
import os
import sys

# Ensure the repo root is on the path so bot.shadows_config is importable.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from bot import shadows_config  # noqa: E402  (after sys.path tweak)


def _main() -> None:
    if os.path.exists(shadows_config.SHADOWS_PATH):
        print(f"ERROR: {shadows_config.SHADOWS_PATH} already exists.")
        print("Delete it first if you want to re-run this migration.")
        sys.exit(1)

    # Load .env
    try:
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(_REPO_ROOT, ".env"))
    except ImportError:
        # Fallback: parse .env manually (key=value, no shell expansion)
        env = {}
        env_file = os.path.join(_REPO_ROOT, ".env")
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
        except FileNotFoundError:
            pass

    # -------------------------------------------------------------------------
    # Spot shadows
    # -------------------------------------------------------------------------
    spot_profiles_raw = env.get("SPOT_SHADOW_PROFILES", "")
    spot_profiles = [p.strip().upper() for p in spot_profiles_raw.split(",") if p.strip()]

    # Env suffix → (toml_key, cast)
    SPOT_SUFFIX_MAP = {
        "PAIRS":                  ("pairs",                  "list"),
        "INTERVAL":               ("interval",               str),
        "TYPE":                   ("type",                   lambda v: v.lower()),
        "RSI_OVERSOLD":           ("rsi_oversold",           int),
        "RSI_OVERBOUGHT":         ("rsi_overbought",         int),
        "RSI_PERIOD":             ("rsi_period",             int),
        "EMA_GAP_PCT":            ("ema_gap_pct",            float),
        "TRAILING_STOP_PCT":      ("trailing_stop_pct",      float),
        "PROFIT_FLOOR_PCT":       ("profit_floor_pct",       float),
        "TAKE_PROFIT_PCT":        ("take_profit_pct",        float),
        "MIN_EXIT_PROFIT_PCT":    ("min_exit_profit_pct",    float),
        "TIME_STOP_DAYS":         ("time_stop_days",         float),
        "STOP_COOLDOWN_CANDLES":  ("stop_cooldown_candles",  int),
        "REENTRY_DROP_PCT":       ("reentry_drop_pct",       float),
        "PARTIAL_CLOSE_PCT":      ("partial_close_pct",      float),
        "PARTIAL_CLOSE_TRAIL_PCT":("partial_close_trail_pct",float),
        "HARD_STOP_PCT":          ("hard_stop_pct",          float),
        "POSITION_SIZE_PCT":      ("position_size_pct",      float),
        "DCA_DROP_PCT":           ("dca_drop_pct",           float),
        "DCA_SIZE_PCT":           ("dca_size_pct",           float),
        "DCA_MAX":                ("dca_max",                int),
        "DCA_STEP_PCT":           ("dca_step_pct",           float),
        "VOLUME_FILTER_PERIOD":   ("volume_filter_period",   int),
        "VOLUME_FILTER_MULT":     ("volume_filter_mult",     float),
        "BALANCE":                ("balance",                float),
        "GRID_SPACING":           ("grid_spacing",           float),
        "GRID_LEVELS":            ("grid_levels",            int),
    }

    spot_data: dict = {}
    env_lines_to_remove: list[str] = []

    if spot_profiles:
        spot_data["profiles"] = spot_profiles
        env_lines_to_remove.append("SPOT_SHADOW_PROFILES=...")

    for name in spot_profiles:
        section: dict = {}
        prefix = f"SPOT_SHADOW_{name}_"
        for suffix, (toml_key, cast) in SPOT_SUFFIX_MAP.items():
            env_key = f"{prefix}{suffix}"
            val = env.get(env_key)
            if val is None:
                continue
            env_lines_to_remove.append(env_key)
            if cast == "list":
                section[toml_key] = [p.strip().upper() for p in val.split(",") if p.strip()]
            else:
                try:
                    section[toml_key] = cast(val)
                except (ValueError, TypeError) as e:
                    print(f"  WARNING: could not convert {env_key}={val!r}: {e} — skipping")
        if section:
            spot_data[name] = section

    # -------------------------------------------------------------------------
    # Futures shadows
    # -------------------------------------------------------------------------
    fut_profiles_raw = env.get("FUTURES_SHADOW_PROFILES", "")
    fut_profiles = [p.strip().upper() for p in fut_profiles_raw.split(",") if p.strip()]

    FUTURES_SUFFIX_MAP = {
        "SYMBOLS":          ("symbols",          "list"),
        "LEVERAGE":         ("leverage",         int),
        "POSITION_SIZE_PCT":("position_size_pct",float),
        "MAX_FUNDING_RATE": ("max_funding_rate", float),
        "TAKE_PROFIT_PCT":  ("take_profit_pct",  float),
        "TRAILING_STOP_PCT":("trailing_stop_pct",float),
        "PROFIT_FLOOR_PCT": ("profit_floor_pct", float),
        "DCA_DROP_PCT":     ("dca_drop_pct",     float),
        "DCA_SIZE_PCT":     ("dca_size_pct",     float),
        "RSI_OVERSOLD":     ("rsi_oversold",     int),
        "RSI_OVERBOUGHT":   ("rsi_overbought",   int),
        "RSI_PERIOD":       ("rsi_period",       int),
        "EMA_GAP_PCT":      ("ema_gap_pct",      float),
        "BALANCE":          ("balance",          float),
    }

    fut_data: dict = {}

    if fut_profiles:
        fut_data["profiles"] = fut_profiles
        env_lines_to_remove.append("FUTURES_SHADOW_PROFILES=...")

    for name in fut_profiles:
        section = {}
        prefix = f"FUTURES_SHADOW_{name}_"
        for suffix, (toml_key, cast) in FUTURES_SUFFIX_MAP.items():
            env_key = f"{prefix}{suffix}"
            val = env.get(env_key)
            if val is None:
                continue
            env_lines_to_remove.append(env_key)
            if cast == "list":
                section[toml_key] = [s.strip().upper() for s in val.split(",") if s.strip()]
            else:
                try:
                    section[toml_key] = cast(val)
                except (ValueError, TypeError) as e:
                    print(f"  WARNING: could not convert {env_key}={val!r}: {e} — skipping")
        if section:
            fut_data[name] = section

    # -------------------------------------------------------------------------
    # Build output dict and write
    # -------------------------------------------------------------------------
    data: dict = {}
    if spot_data:
        data["spot"] = spot_data
    if fut_data:
        data["futures"] = fut_data

    if not data:
        print("No shadow profiles found in .env (SPOT_SHADOW_PROFILES and FUTURES_SHADOW_PROFILES are empty).")
        print(f"Nothing written to {shadows_config.SHADOWS_PATH}.")
        sys.exit(0)

    shadows_config.save(data)
    print(f"Written: {shadows_config.SHADOWS_PATH}")
    print()

    if spot_profiles:
        print(f"Spot profiles migrated: {', '.join(spot_profiles)}")
    if fut_profiles:
        print(f"Futures profiles migrated: {', '.join(fut_profiles)}")
    print()

    print("The following .env keys/patterns are now redundant and can be removed:")
    for key in env_lines_to_remove:
        print(f"  {key}")
    print()
    print("NOTE: .env has NOT been modified.  Remove those lines manually once you")
    print("      have verified that shadows.toml looks correct.")


if __name__ == "__main__":
    _main()
