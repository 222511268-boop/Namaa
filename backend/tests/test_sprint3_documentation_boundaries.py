"""Additional requirement boundaries. All records here are constructed; no live AI/provider claims."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import get_settings
from app.models import Role
from app.routers.reports import _safe
from app.schemas import PlantFactorUpdate
from app.services.ai import facts_hash
from app.services.analysis import heat_context
from app.services.audit import _clean
from app.services.heat import LstStats
from app.services.overview import default_filters
from app.services.water import ScheduleError, validate_schedule
from tests.test_sprint3_heat import _lst, _site


def test_csv_formula_prefixes_preserve_numbers_and_normal_text():
    for prefix in ('=', '+', '-', '@', '\t', '\r'):
        assert _safe(prefix+'value') == "'"+prefix+'value'
    assert _safe(-12) == -12
    assert _safe('Namaa') == 'Namaa'
    assert _safe(None) == ''


def test_audit_secret_removal_recurses_through_lists():
    dirty = {"safe": [{"api_key": "secret", "count": 3}], "password": "secret", "cookie": "secret"}
    assert _clean(dirty) == {"safe": [{"count": 3}]}


def test_plant_factor_inclusive_limits_and_outside_values():
    for factor in (0.05,1.2):
        assert PlantFactorUpdate(factor=factor,source_note='Documented assumption').factor == factor
    for factor in (0.0499,1.2001):
        with pytest.raises(ValidationError):
            PlantFactorUpdate(factor=factor,source_note='Documented assumption')


def test_schedule_volume_exact_limit_and_above():
    # Minimal session double isolates validation arithmetic from persistence.
    db=SimpleNamespace(scalars=lambda _: [])
    site=SimpleNamespace(id='constructed',irrigated_area_m2=100,area_m2=200)
    data=dict(start_date=date(2026,1,1),end_date=date(2026,1,2),weekdays=[1],litres_per_day=10000)
    validate_schedule(db,site,data)
    with pytest.raises(ScheduleError,match='100 mm'):
        validate_schedule(db,site,data|{'litres_per_day':10000.01})


def test_schedule_adjacent_day_allowed_shared_day_rejected():
    other=SimpleNamespace(id='old',start_date=date(2026,1,1),end_date=date(2026,1,10))
    db=SimpleNamespace(scalars=lambda _: [other])
    site=SimpleNamespace(id='constructed',irrigated_area_m2=100,area_m2=200)
    data=dict(start_date=date(2026,1,11),end_date=date(2026,1,15),weekdays=[1],litres_per_day=100)
    validate_schedule(db,site,data)
    with pytest.raises(ScheduleError,match='overlaps'):
        validate_schedule(db,site,data|{'start_date':date(2026,1,10)})


def test_clear_pixel_half_is_usable_below_half_or_no_temperature_is_not():
    assert LstStats(30,35,50,100,100).usable
    assert not LstStats(30,35,49,100,100).usable
    assert not LstStats(None,35,50,100,100).usable
    assert not LstStats(None,None,0,0,0).usable


def test_one_day_overview_filter_has_one_day_inclusive_window():
    f=default_filters(104,date(2026,11,5),date(2026,11,5))
    assert (f.end_dt-f.start_dt).days == 1
    assert f.key() == 'district=104;start=2026-11-05;end=2026-11-05'
    assert (default_filters(end=date(2026,11,5)).end-default_filters(end=date(2026,11,5)).start).days == 89


def test_ai_cache_hash_changes_with_facts_prompt_and_model():
    facts=[{'id':'count','value':3}]
    a=facts_hash(facts,'v1','modelA')
    assert a == facts_hash(facts,'v1','modelA')
    assert a != facts_hash([{'id':'count','value':4}],'v1','modelA')
    assert a != facts_hash(facts,'v2','modelA')
    assert a != facts_hash(facts,'v1','modelB')


def test_heat_exact_age_and_minimum_ranking_sites(as_role,db):
    manager=as_role(Role.manager)
    sites=[_site(manager,f'Constructed boundary site {i}',46.60+i*0.01) for i in range(3)]
    today=date.today()
    cutoff=today-timedelta(days=get_settings().heat_max_age_days)
    for i,s in enumerate(sites[:2]):
        _lst(db,s['id'],cutoff,40+i)
    db.commit()
    assert heat_context(db,today) == {}  # two sites insufficient
    _lst(db,sites[2]['id'],cutoff,42)
    db.commit()
    assert len(heat_context(db,today)) == 3  # three sites at day 120 included
    assert heat_context(db,today+timedelta(days=1)) == {}  # day 121 excluded
