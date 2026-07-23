# -*- coding: utf-8 -*-
"""Pytest fixtures shared across the suite."""

from __future__ import annotations

import random

import pytest

import pipeline

_SEED = 1337


@pytest.fixture(autouse=True)
def _deterministic_rng() -> None:
    """Seed all engine randomness before every test so the suite is stable."""
    random.seed(_SEED)
    pipeline.seed_rng(_SEED)
