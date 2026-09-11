"""Padded positions provably cannot influence sequence-model output (CLAUDE.md §4).

Padding artifacts leaking signal is one of the named technical challenges
(PROJECT_KNOWLEDGE.md §11.7). A model that quietly consumed its padding would
produce plausible-looking numbers that depend on how many CDMs an event happened
to have — an easy silent failure. These tests prove the property empirically
rather than asserting it in a comment:

  1. Perturbing padded positions to arbitrary values leaves predictions bitwise
     identical — including with extreme and NaN-adjacent values.
  2. The same event predicts identically regardless of how much padding surrounds
     it (different max_len).
  3. Reordering padded slots changes nothing.
  4. Real (unmasked) positions DO change predictions — so test 1 is not passing
     merely because the model ignores its input entirely.
  5. Standardisation statistics are computed over real timesteps only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import torch

from kelvins_conformal import features as feat
from kelvins_conformal.config import load_config
from kelvins_conformal.models.sequence import SequenceRegressor, set_torch_seed


@pytest.fixture(scope="module")
def model():
    set_torch_seed(0)
    m = SequenceRegressor(n_features=4, hidden_size=16, num_layers=1, dropout=0.0, cell="gru")
    m.eval()
    return m


def _batch(seed: int = 0, n: int = 6, max_len: int = 8, n_features: int = 4):
    """A padded batch with varied true lengths."""
    rng = np.random.default_rng(seed)
    lengths = rng.integers(1, max_len + 1, size=n)
    X = np.full((n, max_len, n_features), feat.PAD_VALUE, dtype=np.float32)
    for i, ln in enumerate(lengths):
        X[i, :ln, :] = rng.normal(size=(ln, n_features)).astype(np.float32)
    return X, lengths.astype(np.int64)


def _predict(model, X, lengths):
    with torch.no_grad():
        return model(torch.from_numpy(X).float(), torch.from_numpy(lengths).long()).numpy()


# --- 1. perturbing padding changes nothing -----------------------------------
@pytest.mark.parametrize("fill", [0.0, 1.0, -1e6, 1e6, 12345.678, -999.0])
def test_perturbing_padded_positions_does_not_change_predictions(model, fill):
    X, lengths = _batch()
    base = _predict(model, X, lengths)

    tampered = X.copy()
    for i, ln in enumerate(lengths):
        tampered[i, ln:, :] = fill
    after = _predict(model, tampered, lengths)

    np.testing.assert_array_equal(base, after)


def test_random_garbage_in_padding_does_not_change_predictions(model):
    X, lengths = _batch(seed=3)
    base = _predict(model, X, lengths)

    rng = np.random.default_rng(99)
    tampered = X.copy()
    for i, ln in enumerate(lengths):
        tampered[i, ln:, :] = rng.normal(scale=1e4, size=(X.shape[1] - ln, X.shape[2]))
    after = _predict(model, tampered, lengths)

    np.testing.assert_array_equal(base, after)


# --- 2. amount of padding is irrelevant --------------------------------------
def test_prediction_is_invariant_to_padding_width(model):
    """The same event, padded to different widths, must predict identically."""
    rng = np.random.default_rng(7)
    true_len = 5
    core = rng.normal(size=(true_len, 4)).astype(np.float32)

    preds = []
    for max_len in (5, 8, 16):
        X = np.full((1, max_len, 4), feat.PAD_VALUE, dtype=np.float32)
        X[0, :true_len, :] = core
        preds.append(_predict(model, X, np.array([true_len], dtype=np.int64))[0])

    assert preds[0] == pytest.approx(preds[1], abs=1e-6)
    assert preds[1] == pytest.approx(preds[2], abs=1e-6)


# --- 3. padding order is irrelevant ------------------------------------------
def test_shuffling_padded_slots_changes_nothing(model):
    X, lengths = _batch(seed=11)
    base = _predict(model, X, lengths)

    tampered = X.copy()
    rng = np.random.default_rng(5)
    for i, ln in enumerate(lengths):
        pad_block = tampered[i, ln:, :]
        if len(pad_block) > 1:
            tampered[i, ln:, :] = pad_block[rng.permutation(len(pad_block))]
    np.testing.assert_array_equal(base, _predict(model, tampered, lengths))


# --- 4. the model is not simply ignoring its input ---------------------------
def test_perturbing_real_positions_does_change_predictions(model):
    """Guards against a vacuous pass of the tests above."""
    X, lengths = _batch(seed=13)
    base = _predict(model, X, lengths)

    tampered = X.copy()
    for i, ln in enumerate(lengths):
        tampered[i, :ln, :] += 5.0
    after = _predict(model, tampered, lengths)

    assert not np.allclose(base, after), "predictions ignore real timesteps too"


def test_length_one_sequences_are_handled(model):
    X = np.full((3, 6, 4), feat.PAD_VALUE, dtype=np.float32)
    rng = np.random.default_rng(1)
    X[:, 0, :] = rng.normal(size=(3, 4))
    preds = _predict(model, X, np.array([1, 1, 1], dtype=np.int64))
    assert np.all(np.isfinite(preds))


# --- 5. standardisation ignores padding --------------------------------------
def test_standardisation_uses_real_timesteps_only():
    X, lengths = _batch(seed=17, n=20, max_len=10, n_features=4)
    mask = np.zeros(X.shape[:2], dtype=bool)
    for i, ln in enumerate(lengths):
        mask[i, :ln] = True

    mean, std = feat.standardise(X, mask)

    # Recompute by hand over unmasked entries only.
    real = np.concatenate([X[i, : lengths[i], :] for i in range(len(X))])
    np.testing.assert_allclose(mean, real.mean(axis=0), rtol=1e-6)
    # The sentinel is far outside the real range; if it had leaked in, the mean
    # would be dragged toward -999.
    assert np.all(np.abs(mean) < 10.0)


def test_apply_standardisation_keeps_padding_at_sentinel():
    X, lengths = _batch(seed=19)
    mask = np.zeros(X.shape[:2], dtype=bool)
    for i, ln in enumerate(lengths):
        mask[i, :ln] = True
    mean, std = feat.standardise(X, mask)
    out = feat.apply_standardisation(X, mask, mean, std)
    assert np.all(out[~mask] == feat.PAD_VALUE)


def test_built_sequence_tensors_mask_matches_lengths():
    """The builder's mask and lengths must agree, or masking is meaningless."""
    cfg = load_config()
    rng = np.random.default_rng(0)
    from kelvins_conformal.data import COLUMNS_103

    rows = []
    for e in range(25):
        n_cdms = int(rng.integers(1, 6))
        times = np.sort(rng.uniform(2.0, 6.5, size=n_cdms))[::-1]
        for i, t in enumerate(times):
            row = {c: float(rng.normal()) for c in COLUMNS_103}
            row.update({
                "event_id": e, "time_to_tca": float(t), "risk": float(rng.normal(-12, 4)),
                "mission_id": int(e % 3), "event_uid": f"train_{e}", "split": "train",
                "cdm_index": i, "n_cdms": n_cdms, "target_log_risk": -8.0,
                "target_time_to_tca": 0.5, "is_high_risk": False,
            })
            rows.append(row)
    events = pd.DataFrame(rows)

    st = feat.build_sequence_tensors(events, cfg, split="train")
    for i in range(len(st)):
        assert st.mask[i].sum() == st.lengths[i]
        assert st.mask[i, : st.lengths[i]].all()
        assert not st.mask[i, st.lengths[i] :].any()
