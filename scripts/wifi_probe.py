"""Read this computer's actual WiFi association, independently of Internet reachability.

No network credentials, MAC addresses, or nearby-network scans are collected.
Errors are unknown evidence, never interpreted as a disconnection.
"""
from dataclasses import dataclass
import ctypes
import os
import platform
import re
import shutil
import subprocess


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Connection:
    interface: str
    ssid: str | None


@dataclass(frozen=True)
class Snapshot:
    connections: tuple[Connection, ...]
    adapter_count: int


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10, env={**os.environ, 'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeError(f'Unable to query WiFi using {args[0]}: {type(exc).__name__}') from exc
    if result.returncode:
        raise ProbeError(f'{args[0]} could not read WiFi state (exit {result.returncode}). Check OS permissions.')
    return result.stdout


def split_nmcli(line):
    """nmcli -t escapes colons and backslashes, including inside SSIDs."""
    parts, current, escaped = [], '', False
    for char in line:
        if escaped:
            current += char
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            parts.append(current)
            current = ''
        else:
            current += char
    if escaped:
        current += '\\'
    return parts+[current]


def linux_snapshot(run=command):
    if not shutil.which('nmcli') and run is command:
        raise ProbeError('Linux WiFi monitoring requires NetworkManager/nmcli. This machine has no supported WiFi reader.')
    devices = run(['nmcli', '--terse', '--escape', 'yes', '--fields', 'DEVICE,TYPE,STATE', 'device', 'status'])
    connections, adapters = [], 0
    for line in devices.splitlines():
        fields = split_nmcli(line)
        if len(fields) < 3 or fields[1] not in ('wifi', '802-11-wireless'):
            continue
        interface, _, state = fields[:3]
        adapters += 1
        if state.startswith('connected'):
            networks = run(['nmcli', '--terse', '--escape', 'yes', '--fields', 'IN-USE,SSID', 'device', 'wifi', 'list', '--rescan', 'no', 'ifname', interface])
            active = [split_nmcli(row) for row in networks.splitlines() if split_nmcli(row)[0] == '*']
            if not active:
                # Association is known; the SSID may be hidden/restricted.
                connections.append(Connection(interface, None))
            else:
                connections.append(Connection(interface, active[0][1] or None))
        elif state not in ('disconnected', 'unavailable', 'unmanaged'):
            raise ProbeError('WiFi association is changing; waiting for a stable OS observation.')
        elif state == 'unmanaged':
            raise ProbeError('The WiFi interface is not managed by NetworkManager; its state is unknown.')
    if not adapters:
        raise ProbeError('No WiFi adapter was found. Run this on your physical WiFi-connected computer.')
    return Snapshot(tuple(sorted(connections, key=lambda c: c.interface)), adapters)


def mac_interfaces(output):
    interfaces = []
    for block in output.split('\n\n'):
        if re.search(r'Hardware Port:\s*(Wi-Fi|AirPort)\s*$', block, re.MULTILINE):
            match = re.search(r'^Device:\s*(\S+)', block, re.MULTILINE)
            if match:
                interfaces.append(match[1])
    return interfaces


def mac_snapshot(run=command):
    interfaces = mac_interfaces(run(['/usr/sbin/networksetup', '-listallhardwareports']))
    if not interfaces:
        raise ProbeError('No WiFi interface was found on this Mac.')
    connections = []
    for interface in interfaces:
        link = run(['/sbin/ifconfig', interface])
        match = re.search(r'^\s*status:\s*(active|inactive)\s*$', link, re.MULTILINE)
        if not match:
            raise ProbeError('macOS did not provide a reliable WiFi link state.')
        if match[1] == 'inactive':
            continue
        # macOS can redact SSIDs. An active WiFi link is still observable.
        try:
            info = run(['/usr/sbin/networksetup', '-getairportnetwork', interface])
            ssid_match = re.search(r'^Current (?:Wi-Fi|AirPort) Network:\s*(.+)$', info, re.MULTILINE)
            ssid = ssid_match[1].strip() if ssid_match else None
            if ssid in ('<redacted>', '<private>'):
                ssid = None
        except ProbeError:
            ssid = None
        connections.append(Connection(interface, ssid))
    return Snapshot(tuple(connections), len(interfaces))


def windows_snapshot():
    """Native WLAN API avoids parsing localized `netsh` output."""
    from ctypes import wintypes as w
    class GUID(ctypes.Structure):
        _fields_ = [('a', w.DWORD), ('b', w.WORD), ('c', w.WORD), ('d', w.BYTE*8)]
    class Interface(ctypes.Structure):
        _fields_ = [('guid', GUID), ('description', w.WCHAR*256), ('state', w.DWORD)]
    class InterfaceList(ctypes.Structure):
        _fields_ = [('count', w.DWORD), ('index', w.DWORD), ('items', Interface*1)]
    class SSID(ctypes.Structure):
        _fields_ = [('length', w.ULONG), ('bytes', w.BYTE*32)]
    class Association(ctypes.Structure):
        _fields_ = [('ssid', SSID), ('bss_type', w.DWORD), ('bssid', w.BYTE*6), ('phy_type', w.DWORD), ('phy_index', w.ULONG), ('quality', w.ULONG), ('rx', w.ULONG), ('tx', w.ULONG)]
    class Security(ctypes.Structure):
        _fields_ = [('enabled', w.BOOL), ('enterprise', w.BOOL), ('auth', w.DWORD), ('cipher', w.DWORD)]
    class Attributes(ctypes.Structure):
        _fields_ = [('state', w.DWORD), ('mode', w.DWORD), ('profile', w.WCHAR*256), ('association', Association), ('security', Security)]
    dll = ctypes.WinDLL('wlanapi.dll')
    dll.WlanOpenHandle.argtypes = [w.DWORD, ctypes.c_void_p, ctypes.POINTER(w.DWORD), ctypes.POINTER(w.HANDLE)]
    dll.WlanOpenHandle.restype = w.DWORD
    dll.WlanEnumInterfaces.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    dll.WlanEnumInterfaces.restype = w.DWORD
    dll.WlanQueryInterface.argtypes = [w.HANDLE, ctypes.POINTER(GUID), w.DWORD, ctypes.c_void_p, ctypes.POINTER(w.DWORD), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.DWORD)]
    dll.WlanQueryInterface.restype = w.DWORD
    dll.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    dll.WlanCloseHandle.argtypes = [w.HANDLE, ctypes.c_void_p]
    handle, version, memory = w.HANDLE(), w.DWORD(), ctypes.c_void_p()
    code = dll.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle))
    if code:
        raise ProbeError(f'Windows WLAN service is unavailable (code {code}).')
    try:
        code = dll.WlanEnumInterfaces(handle, None, ctypes.byref(memory))
        if code:
            raise ProbeError(f'Windows could not list WiFi interfaces (code {code}).')
        header = ctypes.cast(memory, ctypes.POINTER(InterfaceList)).contents
        if not header.count:
            raise ProbeError('No WiFi adapter was found on this Windows computer.')
        if header.count > 64:
            raise ProbeError('Windows returned an invalid interface list.')
        items = (Interface*header.count).from_address(memory.value+InterfaceList.items.offset)
        connections = []
        for interface in items:
            if interface.state == 1:  # wlan_interface_state_connected
                size, data, value_type = w.DWORD(), ctypes.c_void_p(), w.DWORD()
                code = dll.WlanQueryInterface(handle, ctypes.byref(interface.guid), 7, None, ctypes.byref(size), ctypes.byref(data), ctypes.byref(value_type))
                if code:
                    raise ProbeError(f'Windows WiFi information is restricted (code {code}). Enable Location access for desktop apps in Windows privacy settings, then retry.')
                try:
                    if size.value < ctypes.sizeof(Attributes):
                        raise ProbeError('Windows returned incomplete WiFi association data.')
                    attrs = ctypes.cast(data, ctypes.POINTER(Attributes)).contents
                    length = attrs.association.ssid.length
                    if length > 32:
                        raise ProbeError('Windows returned an invalid SSID length.')
                    ssid = bytes(attrs.association.ssid.bytes[:length]).decode('utf-8', 'replace') or None
                    connections.append(Connection(interface.description, ssid))
                finally:
                    dll.WlanFreeMemory(data)
            elif interface.state not in (0, 4):  # radio not ready or disconnected
                raise ProbeError('Windows WiFi is connecting/disconnecting; waiting for a stable observation.')
        return Snapshot(tuple(sorted(connections, key=lambda c: c.interface)), header.count)
    finally:
        if memory:
            dll.WlanFreeMemory(memory)
        dll.WlanCloseHandle(handle, None)


def probe():
    system = platform.system()
    if system == 'Windows':
        return windows_snapshot()
    if system == 'Darwin':
        return mac_snapshot()
    if system == 'Linux':
        return linux_snapshot()
    raise ProbeError(f'WiFi monitoring is not implemented for {system}.')
