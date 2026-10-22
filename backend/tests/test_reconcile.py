from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import pytest
from app.reconcile import Evidence,reconcile,clipped_seconds

T=datetime(2026,10,22,12,tzinfo=timezone.utc)
def e(n,kind,minute,device='phone',session='one',location='hospital'):
    return Evidence(str(n),device,session,location,kind,T+timedelta(minutes=minute))
def detected(periods):return sum((p.end-p.start).total_seconds() for p in periods if p.location_id!='unknown')
def test_start_stop_exact():
    p=reconcile([e(1,'start',0),e(2,'interim',10),e(3,'stop',20)],T+timedelta(hours=1))
    assert detected(p)==1200 and not p[0].ongoing
def test_duplicate_is_idempotent():
    events=[e(1,'start',0),e(2,'stop',10)]
    assert reconcile(events+events,T+timedelta(hours=1))==reconcile(events,T+timedelta(hours=1))
def test_out_of_order_uses_source_timestamp():
    events=[e(3,'stop',20),e(1,'start',0),e(2,'interim',10)]
    assert detected(reconcile(events,T+timedelta(hours=1)))==1200
def test_multiple_devices_are_union_not_sum():
    events=[e(1,'start',0),e(2,'start',5,device='tablet'),e(3,'stop',12),e(4,'stop',18,device='tablet')]
    assert detected(reconcile(events,T+timedelta(hours=1)))==18*60
def test_brief_reconnection_merged():
    p=reconcile([e(1,'start',0),e(2,'stop',10),e(3,'start',12,session='two'),e(4,'stop',20,session='two')],T+timedelta(hours=1))
    assert len(p)==1 and detected(p)==1200 and p[0].confidence=='grace_merged'
def test_long_gap_is_unknown_transit():
    p=reconcile([e(1,'start',0),e(2,'stop',10),e(3,'start',30,session='two',location='office'),e(4,'stop',40,session='two',location='office')],T+timedelta(hours=1))
    assert len(p)==3 and p[1].location_id=='unknown' and detected(p)==1200
def test_missed_stop_capped_and_stale():
    p=reconcile([e(1,'start',0)],T+timedelta(hours=8))
    assert detected(p)==900 and p[0].confidence=='stale_signal' and not p[0].ongoing
def test_fresh_open_session():
    p=reconcile([e(1,'start',0)],T+timedelta(minutes=5))
    assert detected(p)==300 and p[0].ongoing
def test_conflicting_buildings_are_uncertain_not_double_counted():
    p=reconcile([e(1,'start',0),e(2,'start',5,device='tablet',location='office'),e(3,'stop',12),e(4,'stop',15,device='tablet',location='office')],T+timedelta(hours=1))
    assert any(x.confidence=='conflicting_locations' for x in p)
    assert sum((x.end-x.start).total_seconds() for x in p)==900
    assert detected(p)==480
def test_roam_to_new_building_closes_old_location():
    p=reconcile([e(1,'start',0),e(2,'interim',10,location='office'),e(3,'stop',20,location='office')],T+timedelta(hours=1))
    assert [x.location_id for x in p]==['hospital','office'] and detected(p)==1200
def test_orphan_stop_does_not_invent_attendance():
    assert reconcile([e(1,'stop',0)],T+timedelta(hours=1))==[]
def test_orphan_interim_is_incomplete_start_boundary():
    p=reconcile([e(1,'interim',10),e(2,'stop',20)],T+timedelta(hours=1))
    assert p[0].start==T+timedelta(minutes=10)
def test_future_events_not_processed():
    assert reconcile([e(1,'start',10)],T)==[]
def test_outage_caps_all_device_sessions():
    p=reconcile([e(1,'start',0),e(2,'outage',5)],T+timedelta(hours=1))
    assert detected(p)==300 and p[0].confidence=='outage_uncertain'
def test_timezone_offset_is_required():
    with pytest.raises(ValueError):reconcile([],datetime(2026,10,22))
def test_dst_day_duration_is_elapsed_utc():
    tz=ZoneInfo('America/New_York');start=datetime(2026,11,1,0,tzinfo=tz).astimezone(timezone.utc);end=datetime(2026,11,2,0,tzinfo=tz).astimezone(timezone.utc)
    assert clipped_seconds(start,end,start,end)==25*3600
def test_half_open_clipping_at_midnight():
    assert clipped_seconds(T,T+timedelta(hours=8),T+timedelta(hours=8),T+timedelta(hours=24))==0
def test_all_output_periods_are_disjoint():
    p=reconcile([e(1,'start',0),e(2,'start',2,device='tablet'),e(3,'stop',7),e(4,'stop',12,device='tablet'),e(5,'start',40,session='two')],T+timedelta(hours=1))
    assert all(a.end<=b.start for a,b in zip(p,p[1:]))
