from app.domain.product_url import extract_product_id


def test_extracts_walmart_numeric_id():
    assert (
        extract_product_id("https://www.walmart.com/ip/Some-Scale/123456789")
        == "123456789"
    )


def test_extracts_amazon_asin_from_dp_path():
    assert extract_product_id("https://www.amazon.com/dp/B0FBWG9ZPT") == "B0FBWG9ZPT"


def test_returns_none_for_supported_url_without_product_id():
    assert extract_product_id("https://www.walmart.com/search?q=scale") is None
