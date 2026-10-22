"""Pure replay engine. All timestamps are UTC; no network or database side effects."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class Evidence:
    event_id: str
    device_id: str
    session_id: str
    location_id: str
    kind: str
    timestamp: datetime

@dataclass
class Period:
    location_id: str
    start: datetime
    end: datetime
    confidence: str
    ongoing: bool=False

def reconcile(events:list[Evidence], as_of:datetime, grace_seconds=300, stale_seconds=900)->list[Period]:
    """Replay in event-time order. Resolve concurrent buildings as uncertain/unknown.

    A missing stop is capped at last evidence + stale threshold. A brief
    disconnect at the SAME location is merged; no simultaneous time is counted
    twice. AP roaming must preserve the RADIUS accounting session identifier.
    """
    if as_of.tzinfo is None: raise ValueError('as_of must be timezone aware')
    if grace_seconds<0 or stale_seconds<=0: raise ValueError('Invalid reconciliation thresholds')
    ordered=sorted({e.event_id:e for e in events if e.timestamp<=as_of}.values(),key=lambda e:(e.timestamp,{'start':0,'interim':1,'outage':2,'stop':3}.get(e.kind,4),e.event_id))
    active={}; intervals=[]
    def finish(key,end,confidence,ongoing=False):
        state=active.pop(key,None)
        if state:
            start,last,location=state
            capped=min(end,last+timedelta(seconds=stale_seconds),as_of)
            if capped>start: intervals.append(Period(location,start,capped,confidence if capped==end else 'stale_signal',ongoing and capped==as_of))
    for e in ordered:
        if e.timestamp.tzinfo is None: raise ValueError('Event timestamp must be timezone aware')
        key=(e.device_id,e.session_id)
        # Expire sessions before processing a new signal; an outage never extends evidence.
        for k,s in list(active.items()):
            if s[1]+timedelta(seconds=stale_seconds)<e.timestamp: finish(k,s[1]+timedelta(seconds=stale_seconds),'stale_signal')
        if e.kind in ('start','interim'):
            if key in active and active[key][2]!=e.location_id: finish(key,e.timestamp,'network_detected')
            if key not in active: active[key]=(e.timestamp,e.timestamp,e.location_id)
            else: active[key]=(active[key][0],e.timestamp,e.location_id)
        elif e.kind=='stop': finish(key,e.timestamp,'network_detected' if key in active else 'incomplete')
        elif e.kind=='outage':
            for k in list(active): finish(k,e.timestamp,'outage_uncertain')
    for key in list(active): finish(key,as_of,'network_detected',True)
    if not intervals:return []
    boundaries=sorted({t for p in intervals for t in (p.start,p.end)})
    pieces=[]
    for start,end in zip(boundaries,boundaries[1:]):
        covering=[p for p in intervals if p.start<=start and p.end>=end]
        locations={p.location_id for p in covering}
        if not locations:continue
        location=next(iter(locations)) if len(locations)==1 else 'unknown'
        confidence='conflicting_locations' if len(locations)>1 else ('network_detected' if any(p.confidence=='network_detected' for p in covering) else covering[0].confidence)
        current=Period(location,start,end,confidence,any(p.ongoing for p in covering) and end==as_of)
        if pieces and pieces[-1].location_id==location and pieces[-1].confidence==confidence and (start-pieces[-1].end).total_seconds()<=grace_seconds:
            previous_end=pieces[-1].end
            pieces[-1].end=end;pieces[-1].ongoing=current.ongoing
            if start>previous_end:pieces[-1].confidence='grace_merged'
        else:pieces.append(current)
    # Explicit transit/unknown gaps inside the observed day, never overnight.
    result=[]
    for p in pieces:
        if result and result[-1].end<p.start and result[-1].end.date()==p.start.date():
            result.append(Period('unknown',result[-1].end,p.start,'unknown_transit'))
        result.append(p)
    return result

def clipped_seconds(start,end,window_start,window_end):
    return max(0,int((min(end,window_end)-max(start,window_start)).total_seconds()))
