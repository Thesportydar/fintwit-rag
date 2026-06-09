import pytest

from src.vector_store import TweetFilters


def test_tweet_filters_from_dict_builds_expected_values():
    filters = TweetFilters.from_dict(
        {
            "year": "2025",
            "month": 6,
            "session": "pre",
            "user_handles": ["uno", "dos"],
            "is_retweet": "true",
        }
    )

    assert filters.year == 2025
    assert filters.month == 6
    assert filters.session == "pre"
    assert filters.user_handles == ["uno", "dos"]
    assert filters.is_retweet is True


def test_tweet_filters_rejects_non_object_payload():
    with pytest.raises(ValueError, match="filters debe ser un objeto JSON"):
        TweetFilters.from_dict(["not", "a", "dict"])
