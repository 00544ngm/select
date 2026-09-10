from app.domain.market_evidence import classify_market_results, derive_market_level
from app.domain.stickiness import EvidenceLevel


def _item(title: str, url: str) -> dict[str, str]:
    return {"title": title, "url": url, "price": "$9", "rating": "", "review_count": "", "image": ""}


def test_title_overlap_never_derives_e2_or_e3():
    results = [_item("Electric Salt Pepper Grinder with Oil Sprayer", "https://walmart.com/ip/1")]
    assert derive_market_level(results, matched_count=1, bundle_count=0) == EvidenceLevel.E1
    results.append(_item("Salt Pepper Grinder Oil Sprayer Bundle Kit", "https://walmart.com/ip/2"))
    assert derive_market_level(results, matched_count=2, bundle_count=2) == EvidenceLevel.E1


def test_requires_both_term_groups_and_deduplicates_urls():
    record = classify_market_results(
        [
            _item("Electric Salt Pepper Grinder", "https://walmart.com/ip/1"),
            _item("Electric Salt Pepper Grinder with Oil Sprayer", "https://walmart.com/ip/2"),
            _item("Electric Salt Pepper Grinder with Oil Sprayer", "https://walmart.com/ip/2"),
        ],
        ["electric salt pepper grinder"],
        ["oil sprayer"],
        query="electric salt pepper grinder oil sprayer",
        verified_at="2026-07-29T00:00:00+00:00",
    )

    assert record.level == EvidenceLevel.E1
    assert record.records[0].source_type == "candidate_discovery"
    assert record.matched_count == 1
    assert len(record.raw_results) == 2
    assert record.verified_at == "2026-07-29T00:00:00+00:00"


def test_unrelated_results_are_e0():
    record = classify_market_results(
        [_item("Kitchen Scissors", "https://walmart.com/ip/3")],
        ["electric salt pepper grinder"],
        ["oil sprayer"],
        query="electric salt pepper grinder oil sprayer",
    )
    assert record.level == EvidenceLevel.E0
    assert record.matched_count == 0
