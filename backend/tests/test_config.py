from datetime import timedelta
from backend.ingestion import config


def test_seeded_zips_are_dallas_county():
    assert config.SEEDED_ZIPS == ["75201", "75205", "75225", "75204", "75248"]


def test_dallas_is_the_only_active_county():
    assert config.COUNTIES_ACTIVE == ["dallas"]


def test_rentcast_budget_is_50():
    assert config.API_BUDGETS["rentcast"] == 50


def test_ttl_for_rentcast_markets_is_30_days():
    assert config.get_ttl("rentcast", "markets") == timedelta(days=30)


def test_ttl_for_unknown_endpoint_defaults_to_wildcard():
    assert config.get_ttl("census_acs", "any_endpoint") == timedelta(days=365)


def test_ttl_missing_source_returns_none():
    assert config.get_ttl("nope", "nope") is None
