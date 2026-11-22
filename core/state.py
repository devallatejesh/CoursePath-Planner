"""Session helpers: the active dataset bundle and the objects built from it."""

from __future__ import annotations

import streamlit as st

from .datasets import build_catalog, build_market, fingerprint, has_errors, load_defaults, validate

PLANNER_KEYS = {
    "orch": None,
    "objective": None,
    "plan": None,
    "issues": [],
    "trace": [],
    "blocked": set(),
    "last_diff": None,
    "approved": False,
    "versions": [],
    "roadmap_skills": None,
}


@st.cache_data(show_spinner=False)
def _defaults():
    return load_defaults()


def reset_planner():
    for k, v in PLANNER_KEYS.items():
        st.session_state[k] = v.copy() if hasattr(v, "copy") else v


def activate(frames: dict) -> dict:
    """Validate and, if there are no errors, make ``frames`` the active data."""
    report = validate(frames)
    if has_errors(report):
        return report
    ss = st.session_state
    ss.frames = {k: v.copy() for k, v in frames.items()}
    ss.catalog = build_catalog(frames)
    ss.market = build_market(frames)
    ss.data_key = fingerprint(frames)
    ss.data_is_default = ss.data_key == fingerprint(_defaults())
    reset_planner()
    return report


def init():
    ss = st.session_state
    if "frames" not in ss:
        activate({k: v.copy() for k, v in _defaults().items()})
    for k, v in PLANNER_KEYS.items():
        ss.setdefault(k, v)


def refresh_defaults():
    """Call after the permanent defaults change on disk."""
    _defaults.clear()


def default_frames() -> dict:
    return {k: v.copy() for k, v in _defaults().items()}


def data_badge() -> str:
    ss = st.session_state
    return ":green-badge[default data]" if ss.get("data_is_default") else f":orange-badge[custom data · {ss.get('data_key', '')[:6]}]"
