"""Truth table for the India + remote geographic scope filter (jobscope.core.geo)."""
from jobscope.core.model import Job, derive_remote_scope
from jobscope.core import geo


def _job(location="", is_remote=False):
    j = Job(title="Security Engineer", company="X", location=location, is_remote=is_remote)
    j.remote_scope = derive_remote_scope(location, "Security Engineer", is_remote)
    return j


def test_india_onsite_in_scope():
    assert geo.in_scope(_job("Bengaluru, India")) is True
    assert geo.in_scope(_job("Pune, Maharashtra, India")) is True
    assert geo.in_scope(_job("Mumbai, MH, IN")) is True
    assert geo.in_scope(_job("Gurugram, Haryana")) is True


def test_eligible_remote_in_scope():
    assert geo.in_scope(_job("Remote", is_remote=True)) is True            # global / unspecified
    assert geo.in_scope(_job("Remote - India", is_remote=True)) is True
    assert geo.in_scope(_job("Remote, IN", is_remote=True)) is True
    assert geo.in_scope(_job("Remote - APAC", is_remote=True)) is True
    assert geo.in_scope(_job("Remote - Asia", is_remote=True)) is True


def test_foreign_onsite_dropped():
    assert geo.in_scope(_job("London, UK")) is False
    assert geo.in_scope(_job("San Francisco, CA, US")) is False
    assert geo.in_scope(_job("Berlin, Germany")) is False
    assert geo.in_scope(_job("New York, NY")) is False
    assert geo.in_scope(_job("Boulder, CO")) is False
    assert geo.in_scope(_job("American Fork, UT")) is False
    assert geo.in_scope(_job("Cape Town, South Africa")) is False
    assert geo.in_scope(_job("Budapest, Hungary")) is False
    assert geo.in_scope(_job("Doha, Qatar")) is False


def test_ambiguous_state_codes():
    # TN / GA are both US and Indian state codes: a US city drops, an Indian city stays
    assert geo.in_scope(_job("Nashville, TN")) is False        # Tennessee, US
    assert geo.in_scope(_job("Atlanta, GA")) is False          # Georgia, US
    assert geo.in_scope(_job("Chennai, Tamil Nadu")) is True   # India (metro)


def test_india_word_boundary():
    # 'india' must match as a word, not as a prefix of 'Indianapolis'
    from jobscope.core.geo import _looks_indian
    assert _looks_indian("Indianapolis, Ohio") is False


def test_region_locked_remote_dropped():
    assert geo.in_scope(_job("Remote - US", is_remote=True)) is False
    assert geo.in_scope(_job("Remote (US)", is_remote=True)) is False
    assert geo.in_scope(_job("Remote in Ireland", is_remote=True)) is False
    assert geo.in_scope(_job("Remote - EMEA", is_remote=True)) is False
    assert geo.in_scope(_job("United States (Remote)", is_remote=True)) is False


def test_remote_naming_foreign_city_only_is_kept():
    # a remote role that merely names a foreign CITY (not a country) is treated as global
    j = Job(title="Security Engineer", company="X", location="Toronto", is_remote=True)
    j.remote_scope = "global"
    assert geo.in_scope(j) is True


def test_unknown_location_kept():
    assert geo.in_scope(_job("")) is True                                  # nothing to judge
    assert geo.in_scope(_job("Springfield")) is True                       # unknown city -> keep


def test_home_country_override():
    # switch the home country: a US role becomes in-scope, an India role drops out
    assert geo.in_scope(_job("Austin, Texas, US"), home="United States") is True
    assert geo.in_scope(_job("Bengaluru, India"), home="United States") is False
