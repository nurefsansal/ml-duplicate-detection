from backend.services.feature_service import (
    email_similarity_score,
    normalize_email_for_similarity,
    phone_similarity_score,
)


def test_email_similarity_non_zero_but_not_too_high_for_partial_username_match() -> None:
    score = email_similarity_score("zehra@gmail.com", "zehrabagis@gmail.com")
    assert score > 0.0
    assert score < 0.85


def test_phone_similarity_non_zero_but_not_exact_for_similar_numbers() -> None:
    score = phone_similarity_score("054463982", "054362862")
    assert score > 0.0
    assert score < 0.85


def test_phone_similarity_is_exact_for_same_number() -> None:
    assert phone_similarity_score("054463982", "054463982") == 1.0


def test_gmail_plus_dot_variations_normalize_to_exact_match() -> None:
    left = normalize_email_for_similarity("do.ga+bagis@gmail.com")
    right = normalize_email_for_similarity("doga@gmail.com")
    assert left == right
    assert email_similarity_score("do.ga+bagis@gmail.com", "doga@gmail.com") == 1.0
