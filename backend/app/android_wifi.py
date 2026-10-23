"""Parse only explicit Medflow markers from an Android automation export.

No locale-dependent log date parsing and no unrelated log text is retained.
Epoch milliseconds come from the phone clock, not an authoritative controller.
"""
from datetime import datetime, timezone
import re
import uuid

MARKER = re.compile(r'MEDFLOW\|(connected|disconnected)\|([0-9]{13})(?![0-9])')


def parse_android_log(content: str, device_id: str, account_scope: str):
    matches = list(MARKER.finditer(content))
    if not matches:
        raise ValueError('No Medflow WiFi entries found. Use MEDFLOW|connected|{system_time_ms} and MEDFLOW|disconnected|{system_time_ms} in the two Android Log Event actions.')
    if content.count('MEDFLOW|') != len(matches):
        raise ValueError('A Medflow entry is malformed. Insert System time (ms) using MacroDroid Magic Text so the timestamp is an expanded 13-digit number.')
    if len(matches) > 1000:
        raise ValueError('Import up to 1,000 WiFi observations at a time')
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'android-wifi:{account_scope}:{device_id}'))
    rows = {}
    for match in matches:
        kind, millis = match.groups()
        stamp = datetime.fromtimestamp(int(millis)/1000, timezone.utc)
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f'android-wifi:{account_scope}:{device_id}:{kind}:{millis}'))
        rows[identifier] = {
            'id': identifier,
            'run_id': run_id,
            'device_id': device_id,
            'observed_at': stamp,
            'event_type': kind,
            'source': 'android_macrodroid_test',
            'note': 'Imported phone-reported WiFi event; timestamp is from the phone clock.',
        }
    return sorted(rows.values(), key=lambda row: (row['observed_at'], row['id']))
