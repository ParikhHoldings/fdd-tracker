from fdd_tracker.services.diff_engine import categorize_changes, change_ratio


def test_categorize_changes_detects_expected_categories():
    old = "Initial franchise fee is $35,000. No litigation."
    new = "Initial franchise fee is $45,000. Litigation disclosed in Item 3."
    categories = categorize_changes(old, new)
    assert "fees" in categories
    assert "litigation" in categories


def test_change_ratio_has_signal_when_text_changes():
    old = "Royalty is 6%."
    new = "Royalty is 8%."
    assert change_ratio(old, new) > 0.0
