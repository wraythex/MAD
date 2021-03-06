from flask import Response, url_for
import copy
from enum import IntEnum
import json
from io import BytesIO
from typing import Any, Dict, List, NoReturn, Tuple
from xml.sax.saxutils import escape
from mapadroid.data_manager.modules import MAPPINGS
from mapadroid.mad_apk import get_apk_status
from mapadroid.data_manager.modules.resource import USER_READABLE_ERRORS


class AutoConfIssues(IntEnum):
    no_ggl_login: int = 1
    origin_hopper_not_ready: int = 2
    auth_not_configured: int = 3
    pd_not_configured: int = 4
    rgc_not_configured: int = 5
    package_missing: int = 6


class AutoConfIssueGenerator(object):
    def __init__(self, db, data_manager, args, storage_obj):
        self.warnings: List[AutoConfIssues] = []
        self.critical: List[AutoConfIssues] = []
        sql = "SELECT count(*)\n" \
              "FROM `settings_pogoauth` ag\n" \
              "LEFT JOIN `settings_device` sd ON sd.`account_id` = ag.`account_id`\n" \
              "WHERE ag.`instance_id` = %s AND sd.`device_id` IS NULL"
        if db.autofetch_value(sql, (db.instance_id)) == 0 and not args.autoconfig_no_auth:
            self.warnings.append(AutoConfIssues.no_ggl_login)
        if not validate_hopper_ready(data_manager):
            self.critical.append(AutoConfIssues.origin_hopper_not_ready)
        if not data_manager.get_root_resource('auth'):
            self.warnings.append(AutoConfIssues.auth_not_configured)
        if not PDConfig(db, args, data_manager).configured:
            self.critical.append(AutoConfIssues.pd_not_configured)
        if not RGCConfig(db, args, data_manager).configured:
            self.critical.append(AutoConfIssues.rgc_not_configured)
        missing_packages = []
        for _, apkpackages in get_apk_status(storage_obj).items():
            for _, package in apkpackages.items():
                if package.version is None:
                    missing_packages.append(package)
        if missing_packages:
            self.critical.append(AutoConfIssues.package_missing)

    def get_headers(self) -> Dict:
        headers: Dict[str, int] = {
            'X-Critical': json.dumps([issue.value for issue in self.critical]),
            'X-Warnings': json.dumps([issue.value for issue in self.warnings])
        }
        return headers

    def get_issues(self) -> Tuple[List[str], List[str]]:
        issues_warning = []
        issues_critical = []
        # Warning messages
        if AutoConfIssues.no_ggl_login in self.warnings:
            link = url_for('settings_pogoauth')
            anchor = f"<a class=\"alert-link\" href=\"{link}\">PogoAuth</a>"
            issues_warning.append("No available Google logins for auto creation of devices. Configure through "
                                  f"{anchor}")
        if AutoConfIssues.auth_not_configured in self.warnings:
            link = url_for('settings_auth')
            anchor = f"<a class=\"alert-link\" href=\"{link}\">Auth</a>"
            issues_warning.append(f"No auth configured which is a potential security risk. Configure through {anchor}")
        # Critical messages
        if AutoConfIssues.origin_hopper_not_ready in self.critical:
            link = url_for('settings_walkers')
            anchor = f"<a class=\"alert-link\" href=\"{link}\">Walker</a>"
            issues_critical.append(f"No walkers configured. Configure through {anchor}")
        if AutoConfIssues.pd_not_configured in self.critical:
            link = url_for('autoconf_pd')
            anchor = f"<a class=\"alert-link\" href=\"{link}\">PogoDroid Configuration</a>"
            issues_critical.append(f"PogoDroid is not configured. Configure through {anchor}")
        if AutoConfIssues.rgc_not_configured in self.critical:
            link = url_for('autoconf_rgc')
            anchor = f"<a class=\"alert-link\" href=\"{link}\">RemoteGPSController Configuration</a>"
            issues_critical.append(f"RGC is not configured. Configure through {anchor}")
        if AutoConfIssues.package_missing in self.critical:
            link = url_for('mad_apks')
            anchor = f"<a class=\"alert-link\" href=\"{link}\">MADmin Packages</a>"
            issues_critical.append(f"Missing one or more required packages. Configure through {anchor}")
        return issues_warning, issues_critical

    def has_blockers(self) -> bool:
        return len(self.critical) > 0


def validate_hopper_ready(data_manager):
    walkers = data_manager.get_root_resource('walker')
    if len(walkers) == 0:
        return Response(status=400, response='No walkers configured')
    return True


def origin_generator(data_manager, dbc, *args, **kwargs):
    origin = kwargs.get('OriginBase', None)
    walker_id = kwargs.get('walker', None)
    pool_id = kwargs.get('pool', None)
    device = MAPPINGS['device'](data_manager)
    is_ready = validate_hopper_ready(data_manager)
    if not is_ready:
        return is_ready
    if origin is None:
        return Response(status=400, response='Please specify an Origin Prefix')
    last_id_sql = "SELECT `last_id` FROM `origin_hopper` WHERE `origin` = %s"
    last_id = dbc.autofetch_value(last_id_sql, (origin,))
    if last_id is None:
        last_id = 0
    walkers = data_manager.get_root_resource('walker')
    if walker_id is not None:
        try:
            walker_id = int(walker_id)
            walkers[walker_id]
        except KeyError:
            return Response(404, response='Walker ID not found')
        except ValueError:
            return Response(status=404, response='Walker must be an integer')
    else:
        walker_id = next(iter(walkers))
    device['walker'] = walker_id
    if pool_id is not None:
        pools = data_manager.get_root_resource('devicepool')
        try:
            pool_id = int(pool_id)
            pools[pool_id]
        except KeyError:
            return Response(404, response='Walker ID not found')
        except ValueError:
            return Response(status=404, response='Walker must be an integer')
        device['pool'] = pool_id
    next_id = last_id + 1
    data = {
        'origin': origin,
        'last_id': next_id,
    }
    origin = '%s%03d' % (origin, next_id,)
    dbc.autoexec_insert('origin_hopper', data, optype="ON DUPLICATE")
    device['walker'] = walker_id
    device['origin'] = origin
    device.save()
    return (device['origin'], device.identifier)


class AutoConfIssue(Exception):
    def __init__(self, issues):
        super().__init__()
        self.issues = issues


class AutoConfigCreator:
    origin_field: str = None

    def __init__(self, db, args, data_manager):
        self._db = db
        self._args = args
        self._data_manager = data_manager
        self.contents: dict[str, Any] = {}
        self.configured: bool = False
        self.load_config()

    def delete(self):
        del_info = {
            "name": self.source,
            "instance_id": self._db.instance_id
        }
        self._db.autoexec_delete('autoconfig_file', del_info)

    def generate_config(self, origin: str) -> str:
        origin_config = self.get_config()
        origin_config[self.origin_field] = origin
        conv_xml = ["<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\" ?>", "<map>"]
        for _, sect_conf in self.sections.items():
            for key, elem in sect_conf.items():
                if key not in origin_config:
                    continue
                elem_type = "string"
                value = escape(str(origin_config[key]))
                if elem['expected'] == bool:
                    elem_type = "boolean"
                xml_elem = "<{} name=\"{}\"".format(elem_type, key)
                if elem['expected'] == bool:
                    xml_elem += " value=\"{}\" />".format(value)
                else:
                    xml_elem += ">{}</{}>".format(value, elem_type)
                conv_xml.append('    {}'.format(xml_elem))
        conv_xml.append('</map>')
        return BytesIO('\n'.join(conv_xml).encode('utf-8'))

    def get_config(self) -> dict:
        tmp_config: dict = copy.copy(self.contents)
        try:
            auth = self._data_manager.get_resource('auth', tmp_config['mad_auth'])
            del tmp_config['mad_auth']
            tmp_config['auth_username'] = auth['username']
            tmp_config['auth_password'] = auth['password']
            tmp_config['switch_enable_auth_header'] = True
        except KeyError:
            tmp_config['switch_enable_auth_header'] = False
            tmp_config['auth_username'] = ""
            tmp_config['auth_password'] = ""
        return tmp_config

    def load_config(self) -> NoReturn:
        sql = "SELECT `data`\n"\
              "FROM `autoconfig_file`\n"\
              "WHERE `name` = %s AND `instance_id` = %s"
        try:
            db_conf = self._db.autofetch_value(sql, (self.source, self._db.instance_id))
            if db_conf:
                self.contents = json.loads(db_conf)
                self.configured = True
            else:
                self.contents = {}
        except json.decoder.JSONDecodeError:
            self.contents = {}
        for _, sect_conf in self.sections.items():
            for key, elem in sect_conf.items():
                if key not in self.contents:
                    self.contents[key] = elem['default']
                    continue

    def save_config(self, user_vals: dict) -> NoReturn:
        self.validate(user_vals)
        save = {
            "name": self.source,
            "data": json.dumps(self.contents),
            "instance_id": self._db.instance_id
        }
        self._db.autoexec_insert("autoconfig_file", save, optype="ON DUPLICATE")

    def validate(self, user_vals: dict) -> bool:
        processed = []
        missing: List[str] = []
        invalid: List[str] = []
        for section, sect_conf in self.sections.items():
            for key, elem in sect_conf.items():
                processed.append(key)
                if elem['required'] and key not in user_vals:
                    if key not in self.contents:
                        missing.append(key)
                    continue
                if elem['required'] and user_vals[key] in [None, ""]:
                    if key not in self.contents:
                        missing.append(key)
                        continue
                try:
                    check_func = elem['expected']
                    if elem['expected'] == 'bool':
                        if user_vals[key] not in [True, False]:
                            invalid.append((key, USER_READABLE_ERRORS[bool]))
                    self.contents[key] = check_func(user_vals[key])
                except KeyError:
                    if key not in self.contents:
                        self.contents[key] = elem['default'] if elem['default'] not in ['None', None] else ""
                except (TypeError, ValueError):
                    invalid.append((key, USER_READABLE_ERRORS[check_func]))
        unknown = set(list(user_vals.keys())) - set(processed)
        try:
            invalid_dest = ['127.0.0.1', '0.0.0.0']
            for dest in invalid_dest:
                if dest in self.contents[self.host_field]:
                    invalid.append((self.host_field, "Routable address from outside the server"))
        except KeyError:
            pass
        issues = {}
        if missing:
            issues['missing'] = missing
        if invalid:
            issues['invalid'] = invalid
        if unknown:
            issues['unknown'] = unknown
        if issues:
            raise AutoConfIssue(issues)
        return True


class RGCConfig(AutoConfigCreator):
    host_field = "websocket_uri"
    origin_field = "websocket_origin"
    source = "rgc"
    sections = {
        "Socket": {
            "websocket_uri": {
                "title": "Websocket URI to connect to",
                "type": str,
                "expected": str,
                "default": "ws://",
                "summary": None,
                "required": True
            },
            "mad_auth": {
                "title": "Basic Authentication",
                "type": "authselect",
                "expected": int,
                "default": None,
                "summary": "Authentication credentials to use when performing basic auth",
                "required": False,
            },
            "websocket_origin": {
                "hidden": True,
                "title": "Websocket Origin",
                "type": str,
                "expected": str,
                "default": "",
                "summary": "Origin field of the header. This can be used as an identifier. Alphanumeric only.",
                "required": True
            },
            "switch_enable_auth_header": {
                "hidden": True,
                "title": "Enable Basic Auth header",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "For additional security, some servers may ask for basic auth to be sent with each "
                           "request for authorization. Keep in mind: if the connection is not secured via TLS (wss), "
                           "anyone could read the password.",
                "required": False
            },
            "auth_username": {
                "hidden": True,
                "title": "Username",
                "type": str,
                "expected": str,
                "default": "",
                "summary": None,
                "required": False
            },
            "auth_password": {
                "hidden": True,
                "title": "Password",
                "type": str,
                "expected": str,
                "default": "",
                "summary": None,
                "required": False
            }
        },
        "Rooted Devices": {
            "reset_google_play_services": {
                "title": "Reset GMS data",
                "type": "bool",
                "expected": bool,
                "enabled": False,
                "default": False,
                "summary": "Disabled for now...<br>"
                           "Resets Google Play Services data.<br>"
                           "This will STOP Google Play Services. Executed upon service start.<br>"
                           "Any apps relying on GMS will need to be restarted.<br>"
                           "Helps against rubberbanding.",
                "required": False
            },
            "oom_adj_override": {
                "title": "Override OOM value",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "Overrides the oom_adj value to reduce the possibility of the process being killed when "
                           "the system runs out of memory.",
                "required": False
            }
        },
        "Location": {
            "reset_agps_continuously": {
                "title": "Reset AGPS data continuously",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Resets the AGPS data with every location update",
                "required": False
            },
            "reset_agps_once": {
                "title": "Reset AGPS data once",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Resets AGPS data once at startup of services",
                "required": False
            },
            "use_mock_location": {
                "title": "Use Android Mock location",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "Requires RGC to be set as Mocking app in developer options",
                "required": False
            },
            "suspended_mocking": {
                "title": "Suspended mocking",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "May help against rubberbanding / location smoothing",
                "required": False
            },
            "location_overwrite_method": {
                "title": "location_overwrite_method",
                "type": "option",
                "values": ["Minimal", "Common", "Indirect"],
                "expected": str,
                "default": "Minimal",
                "summary": "Defines how many providers are overwritten (also known as indirect mocking). Minimal "
                           "(only GPS), Common (GPS, Network, Passive)",
                "required": False
            },
            "overwrite_fused": {
                "title": "Overwrite fused",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Also overwrite fused provider",
                "required": False
            },
        },
        "General": {
            "boot_startup": {
                "title": "Start on boot",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "Start app on boot",
                "required": False
            },
            "boot_delay": {
                "title": "Start RGC delayed by X seconds",
                "type": int,
                "expected": int,
                "default": 40,
                "summary": "Start app on boot",
                "required": False
            },
            "autostart_services": {
                "title": "Start services on appstart",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "Automatically start the services when the app is opened",
                "required": False
            }
        }
    }

    def load_config(self) -> NoReturn:
        super().load_config()
        if self.contents['websocket_uri'] in ['ws://', '']:
            self.contents['websocket_uri'] = 'ws://{}:{}'.format(self._args.ws_ip, self._args.ws_port)
        auths = self._data_manager.get_root_resource('auth')
        if auths:
            self.sections['Socket']['mad_auth']['required'] = True


class PDConfig(AutoConfigCreator):
    host_field = "post_destination"
    origin_field = "post_origin"
    source = "pd"
    sections = {
        "MAD Backend": {
            "user_id": {
                "title": "Backend User",
                "type": str,
                "expected": str,
                "default": "",
                "summary": "Username for logging into the MAD backend",
                "required": True
            },
            "auth_token": {
                "title": "Backend Device Password",
                "type": str,
                "expected": str,
                "default": "",
                "summary": "Device password created in the MAD backend",
                "required": True
            },
        },
        "External Communication": {
            "switch_disable_external_communication": {
                "title": "Disable external communication",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Disables sending data to servers entirely.",
                "required": False
            },
            "post_timeout_ms_connect": {
                "title": "Connect timeout",
                "type": int,
                "expected": int,
                "default": 10000,
                "summary": "Time in ms until a timeout while connecting is triggered. 0 = no timeout, default 10000",
                "required": False
            },
            "post_timeout_ms_call": {
                "title": "Call timeout",
                "type": int,
                "expected": int,
                "default": 0,
                "summary": "Time in ms until a timeout for the entire call is triggered. Default 0 (no timeout). "
                           "Includes DNS resolving, redirects etc.",
                "required": False
            },
            "post_timeout_ms_read": {
                "title": "Read timeout",
                "type": int,
                "expected": int,
                "default": 10000,
                "summary": "Time in ms until a timeout for the read operation of the TCP socket and individual IO-ops "
                           " is triggered. Default 10000, 0 = no timeout.",
                "required": False
            },
            "post_timeout_ms_write": {
                "title": "Write timeout",
                "type": int,
                "expected": int,
                "default": 10000,
                "summary": "Time in ms until a timeout during IO write is triggered. Default 10000, 0 = no timeout.",
                "required": False
            },
            "switch_send_protos": {
                "title": "Send selected set of serialized data (json)",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "",
                "required": False
            },
            "post_aggregate_wait_ms": {
                "title": "Aggregation delay (serialized)",
                "type": int,
                "expected": int,
                "default": 500,
                "summary": "Time in ms until serialized protos are sent. Any protos received between the first proto "
                           "and the delay having passed will be aggregated in a POST. Default: 500ms",
                "required": False
            },
            "switch_gzip_post_data": {
                "title": "GZIP the serialized data that is to be posted.",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "",
                "required": False
            },
            "post_destination": {
                "title": "POST destination",
                "type": str,
                "expected": str,
                "default": "",
                "summary": "Destination to send data to",
                "required": True
            },
            "post_origin": {
                "hidden": True,
                "title": "POST Origin",
                "type": str,
                "expected": str,
                "default": "",
                "summary": "Origin field of the header. This can be used as an identifier. Alphanumeric only.",
                "required": True
            },
            "switch_send_raw_protos": {
                "title": "Send raw data (base64 encoded)",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "",
                "required": False
            },
            "post_raw_aggregate_wait_ms": {
                "title": "Aggregation delay (raw)",
                "type": int,
                "expected": int,
                "default": 500,
                "summary": "Time in ms until raw protos are sent. Any protos received between the first proto and the "
                           "delay having passed will be aggregated in a POST. Default: 500ms",
                "required": False
            },
            "switch_gzip_post_raw_data": {
                "title": "GZIP the raw data that is to be posted.",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "",
                "required": False
            },
            "post_destination_raw": {
                "title": "RAW POST Destination",
                "type": str,
                "expected": str,
                "default": "",
                "summary": "HTTP Endpoint to POST raw data to",
                "required": True
            },
            "switch_disable_last_sent": {
                "title": "Disable last sent notifications",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Disable display of notifications of the last timestamp data was sent at. Attempts are also "
                           " logged for debugging of connectivity issues.",
                "required": False
            },
            "switch_popup_last_sent": {
                "title": "Heads up notification",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Have a notification displayed as a heads-up notification every time data is sent",
                "required": False
            },
            "switch_enable_auth_header": {
                "hidden": True,
                "title": "Enable Basic Auth header",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "For additional security, some servers may ask for basic auth to be sent with each "
                           "request for authorization. Keep in mind: if the connection is not secured via TLS (wss), "
                           "anyone could read the password.",
                "required": False
            },
            "auth_username": {
                "hidden": True,
                "title": "Username",
                "type": str,
                "expected": str,
                "default": "",
                "summary": None,
                "required": False
            },
            "auth_password": {
                "hidden": True,
                "title": "Password",
                "type": str,
                "expected": str,
                "default": "",
                "summary": None,
                "required": False
            },
            "mad_auth": {
                "title": "Basic Authentication",
                "type": "authselect",
                "expected": int,
                "default": None,
                "summary": "Authentication credentials to use when performing basic auth",
                "required": False,
            },
        },
        "App": {
            "preference_inject_after_seconds": {
                "title": "Injection delay",
                "type": int,
                "expected": int,
                "default": 120,
                "summary": "Time in seconds to wait after a Pogo start to inject into the process. Default: 120s",
                "required": False
            },
            "toggle_injection_detection": {
                "title": "Injection detection",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "If you experience issues with injections/freezes/crashes, try this toggle which toggles "
                           "the detection method used.",
                "required": False
            },
            "disable_pogo_freeze_detection": {
                "title": "Disable Pogo freeze detection",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "If no data has been received for some time, a restart is automatically triggered.",
                "required": False
            },
            "default_mappging_mode": {
                "title": "Default to mapping mode",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "",
                "required": False
            },
            "switch_setenforce": {
                "title": "Patch SELinux",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Patches very few SELinux rules, require for Samsung Stock ROMs for example (generally "
                           "enforcing kernels)",
                "required": False
            },
            "full_daemon": {
                "title": "Full daemon mode",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "Automatically start app on boot (and watchdog if enabled)",
                "required": False
            },
            "boot_delay": {
                "title": "Start Pogodroid with a delay (seconds)",
                "type": int,
                "expected": int,
                "default": 30,
                "summary": "",
                "required": False
            },
            "switch_enable_oomadj": {
                "title": "Override OOM value",
                "type": "bool",
                "expected": bool,
                "default": True,
                "summary": "Enables OOM adjustments to reduce the 'risk' of Android killing the app.",
                "required": False
            },
            "switch_enable_mock_location_patch": {
                "title": "Make mock location providers useful",
                "type": "bool",
                "expected": bool,
                "default": False,
                "summary": "Test feature: Mock location patching",
                "required": False
            }
        }
    }

    def load_config(self) -> NoReturn:
        super().load_config()
        if self.contents['post_destination'] in ['http://', '']:
            self.contents['post_destination'] = 'http://{}:{}'.format(self._args.mitmreceiver_ip,
                                                                      self._args.mitmreceiver_port)
        auths = self._data_manager.get_root_resource('auth')
        if auths:
            self.sections['External Communication']['mad_auth']['required'] = True
