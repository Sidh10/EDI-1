"""Regression tests for the coverage-check form (DECISIONS.md 2026-09-21, methodological note).

Two questions, two forms, one definition each:
  * validity under shift  -> one-sided  (CI upper bound >= nominal)  meets_coverage_guarantee
  * exactness on exchangeable data -> two-sided (CI contains nominal) consistent_with_exact_coverage

E12's official-test ``valid=`` labels used CI containment (the E17 H1 error class). The
fix was inert on the real data (0 of 9 labels changed), so the regression tests below are
built on the one case where the two forms disagree: a CI lying wholly ABOVE nominal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kelvins_conformal.models import conformal_runner as R
from kelvins_conformal.robustness import consistent_with_exact_coverage, meets_coverage_guarantee

# --- the two primitives -------------------------------------------------------------


@pytest.mark.parametrize(("lo", "hi", "valid", "exact"), [
    (0.915, 0.937, True, False),    # wholly ABOVE nominal: the ONLY case the forms disagree
    (0.882, 0.908, True, True),     # contains nominal: both pass
    (0.844, 0.874, False, False),   # wholly BELOW nominal: both fail
    (0.880, 0.900, True, True),     # upper bound exactly at nominal: both pass (same edge)
])
def test_the_two_forms_agree_everywhere_except_wholly_above_nominal(lo, hi, valid, exact):
    assert meets_coverage_guarantee(lo, hi, 0.90) is valid
    assert consistent_with_exact_coverage(lo, hi, 0.90) is exact


@pytest.mark.parametrize("fn", [meets_coverage_guarantee, consistent_with_exact_coverage])
@pytest.mark.parametrize("args", [(0.9, 0.8, 0.9), (0.8, np.nan, 0.9), (0.8, 0.9, 1.0), (0.8, 0.9, 0.0)])
def test_primitives_fail_loud_on_malformed_input(fn, args):
    with pytest.raises(ValueError):
        fn(*args)


# --- e12_coverage_checks ------------------------------------------------------------


def _cov(rows) -> pd.DataFrame:
    """An E12 coverage table: (method, nominal, coverage, cp_lo, cp_hi) per row."""
    return pd.DataFrame([{"method": m, "nominal": n, "coverage_mean": c,
                          "cp_lo_mean": lo, "cp_hi_mean": hi} for m, n, c, lo, hi in rows])


def _table(official, self_test=(0.896, 0.883, 0.908), level=0.90):
    rows = [(m, level, *official) for m in R.E12_OFFICIAL_METHODS]
    rows.append((R.E12_SELFTEST_METHOD, level, *self_test))
    return _cov(rows)


def test_over_covering_official_arm_is_valid():
    """THE regression test. A conservative official-test arm meets the guarantee.

    Its CI [0.915, 0.937] lies wholly above 0.90. The containment bug labelled this
    invalid; the one-sided validity form labels it valid. Verified to FAIL with the bug
    reintroduced.
    """
    chk = R.e12_coverage_checks(_table(official=(0.926, 0.915, 0.937)), 0.90).set_index("method")
    for m in R.E12_OFFICIAL_METHODS:
        assert chk.loc[m, "question"] == R.VALIDITY_UNDER_SHIFT
        assert bool(chk.loc[m, "passes"]) is True, f"{m}: an over-covering arm must be VALID"


def test_self_test_arm_stays_two_sided():
    """Exactness is deliberately two-sided: over-coverage on exchangeable data IS a defect.

    The same CI that makes an official arm valid must make the self-test arm FAIL — which
    pins that the fix did not simply flip every check to one-sided.
    """
    chk = R.e12_coverage_checks(_table(official=(0.86, 0.85, 0.87), self_test=(0.926, 0.915, 0.937)),
                                0.90).set_index("method")
    assert chk.loc[R.E12_SELFTEST_METHOD, "question"] == R.EXACTNESS_ON_EXCHANGEABLE
    assert bool(chk.loc[R.E12_SELFTEST_METHOD, "passes"]) is False


def test_reproduces_the_published_e12_labels_at_90():
    """The committed E12 table's exact 90% values must reproduce the reported labels."""
    cov = _cov([
        ("E12_cqr_naive", 0.9, 0.8652514997692663, 0.8501879629419417, 0.8793192591534676),
        ("E12_cqr_weighted_rule", 0.9, 0.8592524227041993, 0.8439521071461943, 0.8735735985121792),
        ("E11ref_split_weighted_rule", 0.9, 0.8957083525611443, 0.8820700085187404, 0.9082654841323686),
        ("E12_cqr_selftest", 0.9, 0.8955890563930765, 0.8826283991929408, 0.9075698563174092),
    ])
    p = R.e12_coverage_checks(cov, 0.9).set_index("method")["passes"]
    assert (p["E12_cqr_naive"], p["E12_cqr_weighted_rule"],
            p["E11ref_split_weighted_rule"], p["E12_cqr_selftest"]) == (False, False, True, True)


def test_every_label_names_its_question_and_form():
    chk = R.e12_coverage_checks(_table(official=(0.86, 0.85, 0.87)), 0.90)
    assert set(chk["question"]) == {R.VALIDITY_UNDER_SHIFT, R.EXACTNESS_ON_EXCHANGEABLE}
    assert chk["form"].str.contains("one-sided").sum() == len(R.E12_OFFICIAL_METHODS)
    assert chk["form"].str.contains("two-sided").sum() == 1


def test_missing_row_fails_loud():
    cov = _table(official=(0.86, 0.85, 0.87))
    with pytest.raises(ValueError, match="expected exactly one"):
        R.e12_coverage_checks(cov[cov["method"] != "E12_cqr_naive"], 0.90)
