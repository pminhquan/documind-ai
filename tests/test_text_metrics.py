"""CER/WER metric tests with hand-computed reference values."""

import pytest

from documind.evaluation.text_metrics import (
    edit_operations,
    error_rate,
    levenshtein_distance,
    micro_aggregate,
    normalize_text,
)


class TestLevenshtein:
    def test_classic_kitten_sitting(self):
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_empty_strings(self):
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "abc") == 3

    def test_identical(self):
        assert levenshtein_distance("same", "same") == 0


class TestNormalization:
    def test_default_casefolds_and_collapses(self):
        assert normalize_text("  HELLO   World \n") == "hello world"

    def test_case_sensitive_option(self):
        assert normalize_text("ABC abc", casefold=False) == "ABC abc"

    def test_preserve_whitespace_option(self):
        assert normalize_text("a  b", collapse_whitespace=False) == "a  b".casefold()


class TestCER:
    def test_hand_computed_kitten_sitting(self):
        # 3 edits / 6 reference chars ("kitten")
        result = error_rate("kitten", "sitting", unit="chars")
        assert result.edits == 3
        assert result.reference_length == 6
        assert result.error_rate == pytest.approx(3 / 6)

    def test_empty_reference_both_empty(self):
        result = error_rate("", "", unit="chars")
        assert result.error_rate == 0.0

    def test_empty_reference_nonempty_hypothesis(self):
        result = error_rate("", "abc", unit="chars")
        assert result.error_rate == 1.0

    def test_casefold_makes_identical(self):
        assert error_rate("TOTAL 9.57", "total 9.57", unit="chars").error_rate == 0.0
        assert error_rate("TOTAL", "total", unit="chars",
                          casefold=False).error_rate == 1.0

    def test_whitespace_collapse_prevents_false_errors(self):
        assert error_rate("A  B", "A B", unit="chars").error_rate == 0.0

    def test_invalid_unit_rejected(self):
        with pytest.raises(ValueError):
            error_rate("a", "a", unit="syllables")


class TestWER:
    def test_hand_computed(self):
        # "the cat sat" -> "the bat sat": one substitution / 3 words
        result = error_rate("the cat sat", "the bat sat", unit="words")
        assert result.edits == 1
        assert result.error_rate == pytest.approx(1 / 3)

    def test_word_insertion(self):
        result = error_rate("hello world", "hello big world", unit="words")
        assert result.edits == 1
        assert result.error_rate == pytest.approx(1 / 2)

    def test_empty_reference(self):
        assert error_rate("", "some words", unit="words").error_rate == 1.0
        assert error_rate("", "", unit="words").error_rate == 0.0


class TestEditOperations:
    def test_substitution(self):
        ops = edit_operations("cat", "bat")
        assert ops == [
            {"op": "substitute", "position": 0, "reference": "c", "hypothesis": "b"}
        ]

    def test_insert_and_delete(self):
        assert edit_operations("abc", "abxc") == [
            {"op": "insert", "position": 2, "reference": None, "hypothesis": "x"}
        ]
        assert edit_operations("abxc", "abc") == [
            {"op": "delete", "position": 2, "reference": "x", "hypothesis": None}
        ]

    def test_identical_has_no_operations(self):
        assert edit_operations("same", "same") == []


class TestAggregation:
    def test_micro_aggregate(self):
        results = [
            error_rate("abcd", "abxd", unit="chars"),   # 1 edit / 4
            error_rate("hi", "hi", unit="chars"),       # 0 / 2
        ]
        aggregate = micro_aggregate(results)
        assert aggregate["total_edits"] == 1
        assert aggregate["total_reference_units"] == 6
        assert aggregate["error_rate"] == pytest.approx(1 / 6)

    def test_aggregate_all_empty(self):
        aggregate = micro_aggregate([error_rate("", "", unit="chars")])
        assert aggregate["error_rate"] == 0.0
