from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

SCHEDULE_REPLACEMENT = base64.b64decode("ZGVmIF9zY2hlZHVsZV9kYXkoCiAgICAqLAogICAgY2F2aXRpZXM6IGxpc3RbX0Nhdml0eV0sCiAgICBkZW1hbmRzOiBsaXN0W19EZW1hbmRdLAogICAgc2V0dGluZ3M6IENhdml0eVBsYW5TZXR0aW5ncywKICAgIG1vbGRfY2FwYWNpdHk6IGRpY3Rbc3RyLCBpbnRdLAogICAgY2FzaW5nX2NhcGFjaXR5OiBkaWN0W3N0ciwgaW50XSwKKSAtPiBsaXN0W19Vbml0QWxsb2NhdGlvbl06CiAgICAiIiJQbGFuIGZpeGVkIGZhY3Rvcnkgc2hpZnRzLgoKICAgIERBWSBpcyAwNzowMC0xOTowMCBhbmQgTklHSFQgaXMgMTk6MDAtMDc6MDAuIEVuYWJsZWQKICAgIHdpbmRvd3MgYXJlIGRlcml2ZWQgZnJvbSB0aGUgc3RvcmVkIGRheS9uaWdodCBtaW51dGUgdmFsdWVzOgogICAgNzIwLzcyMCA9IGFsbCBzaGlmdHMsIDcyMC8wID0gZGF5IG9ubHksIDAvNzIwID0gbmlnaHQgb25seS4KCiAgICBUaGUgc2FtZSB0eXJlIHJldXNlcyB0aGUgc2FtZSBvdmVuIGluIHRoZSBuZXh0IGVuYWJsZWQgc2hpZnQKICAgIHdoZW5ldmVyIHBvc3NpYmxlLgogICAgIiIiCiAgICBzdGF0ZXMgPSBbCiAgICAgICAgX0Nhdml0eSgqKmFzZGljdChjYXZpdHkpKQogICAgICAgIGZvciBjYXZpdHkgaW4gY2F2aXRpZXMKICAgICAgICBpZiBfY2F2aXR5X29wZXJhdGlvbmFsX3N0YXR1cyhjYXZpdHkpCiAgICAgICAgPT0gIkFWQUlMQUJMRSAvIEZSRUUiCiAgICBdCiAgICBzdGF0ZXMuc29ydCgKICAgICAgICBrZXk9bGFtYmRhIGNhdml0eTogKAogICAgICAgICAgICBfbm9ybV9saW5lKGNhdml0eS5saW5lX25hbWUpLAogICAgICAgICAgICBjYXZpdHkuY2F2aXR5X25vLAogICAgICAgICAgICBjYXZpdHkuY2F2aXR5X2lkLAogICAgICAgICkKICAgICkKCiAgICBtb2xkX2ludGVydmFsczogZGljdFsKICAgICAgICBzdHIsCiAgICAgICAgbGlzdFt0dXBsZVtpbnQsIGludF1dLAogICAgXSA9IGRlZmF1bHRkaWN0KGxpc3QpCiAgICBjYXNpbmdfaW50ZXJ2YWxzOiBkaWN0WwogICAgICAgIHN0ciwKICAgICAgICBsaXN0W3R1cGxlW2ludCwgaW50XV0sCiAgICBdID0gZGVmYXVsdGRpY3QobGlzdCkKICAgIGFsbG9jYXRpb25zOiBsaXN0W19Vbml0QWxsb2NhdGlvbl0gPSBbXQoKICAgIGFjdGl2ZV9kZW1hbmRzID0gWwogICAgICAgIGRlbWFuZAogICAgICAgIGZvciBkZW1hbmQgaW4gZGVtYW5kcwogICAgICAgIGlmIGRlbWFuZC5yZW1haW5pbmdfcXR5ID4gMAogICAgXQogICAgYWN0aXZlX2RlbWFuZHMuc29ydChrZXk9X2RlbWFuZF9zb3J0X2tleSkKCiAgICBkYXlfZW5hYmxlZCA9IGludChzZXR0aW5ncy5kYXlfc2hpZnRfbWludXRlcykgPiAwCiAgICBuaWdodF9lbmFibGVkID0gaW50KHNldHRpbmdzLm5pZ2h0X3NoaWZ0X21pbnV0ZXMpID4gMAoKICAgIHNoaWZ0X3dpbmRvd3M6IGxpc3RbdHVwbGVbc3RyLCBpbnQsIGludF1dID0gW10KICAgIGlmIGRheV9lbmFibGVkOgogICAgICAgIHNoaWZ0X3dpbmRvd3MuYXBwZW5kKCgiREFZIiwgMCwgNzIwKSkKICAgIGlmIG5pZ2h0X2VuYWJsZWQ6CiAgICAgICAgc2hpZnRfd2luZG93cy5hcHBlbmQoKCJOSUdIVCIsIDcyMCwgMTQ0MCkpCgogICAgZm9yIHNoaWZ0X25hbWUsIHNoaWZ0X3N0YXJ0LCBzaGlmdF9lbmQgaW4gc2hpZnRfd2luZG93czoKICAgICAgICBpZiBub3QgYWN0aXZlX2RlbWFuZHM6CiAgICAgICAgICAgIGJyZWFrCgogICAgICAgIGZvciBjYXZpdHkgaW4gc3RhdGVzOgogICAgICAgICAgICBjYXZpdHkuY3Vyc29yID0gc2hpZnRfc3RhcnQKCiAgICAgICAgd2hpbGUgYWN0aXZlX2RlbWFuZHM6CiAgICAgICAgICAgIGJlc3Q6IHR1cGxlWwogICAgICAgICAgICAgICAgdHVwbGVbQW55LCAuLi5dLAogICAgICAgICAgICAgICAgX0Nhdml0eSwKICAgICAgICAgICAgICAgIF9EZW1hbmQsCiAgICAgICAgICAgICAgICBpbnQsCiAgICAgICAgICAgICAgICBpbnQsCiAgICAgICAgICAgIF0gfCBOb25lID0gTm9uZQoKICAgICAgICAgICAgZm9yIGNhdml0eSBpbiBzdGF0ZXM6CiAgICAgICAgICAgICAgICBpZiBjYXZpdHkuY3Vyc29yID49IHNoaWZ0X2VuZDoKICAgICAgICAgICAgICAgICAgICBjb250aW51ZQoKICAgICAgICAgICAgICAgIGZvciBwcmlvcml0eSwgZGVtYW5kIGluIGVudW1lcmF0ZShhY3RpdmVfZGVtYW5kcyk6CiAgICAgICAgICAgICAgICAgICAgaWYgZGVtYW5kLnJlbWFpbmluZ19xdHkgPD0gMDoKICAgICAgICAgICAgICAgICAgICAgICAgY29udGludWUKICAgICAgICAgICAgICAgICAgICBpZiBub3QgX2xpbmVfY29tcGF0aWJsZSgKICAgICAgICAgICAgICAgICAgICAgICAgY2F2aXR5LmxpbmVfbmFtZSwKICAgICAgICAgICAgICAgICAgICAgICAgZGVtYW5kLmxpbmVfbmFtZXMsCiAgICAgICAgICAgICAgICAgICAgKToKICAgICAgICAgICAgICAgICAgICAgICAgY29udGludWUKCiAgICAgICAgICAgICAgICAgICAgY2hhbmdlb3ZlciA9ICgKICAgICAgICAgICAgICAgICAgICAgICAgc2V0dGluZ3MuY2hhbmdlb3Zlcl9taW51dGVzCiAgICAgICAgICAgICAgICAgICAgICAgIGlmIGNhdml0eS5sYXN0X3NhcF9jb2RlCiAgICAgICAgICAgICAgICAgICAgICAgIGFuZCBjYXZpdHkubGFzdF9zYXBfY29kZSAhPSBkZW1hbmQuc2FwX2NvZGUKICAgICAgICAgICAgICAgICAgICAgICAgZWxzZSAwCiAgICAgICAgICAgICAgICAgICAgKQogICAgICAgICAgICAgICAgICAgIHJlcXVlc3RlZF9zdGFydCA9IG1heCgKICAgICAgICAgICAgICAgICAgICAgICAgc2hpZnRfc3RhcnQsCiAgICAgICAgICAgICAgICAgICAgICAgIGNhdml0eS5jdXJzb3IgKyBjaGFuZ2VvdmVyLAogICAgICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgICAgICBkdXJhdGlvbiA9IGRlbWFuZC5lZmZlY3RpdmVfY3ljbGVfbWludXRlcwogICAgICAgICAgICAgICAgICAgIG1vbGRfa2V5ID0gX25vcm1fcmVzb3VyY2UoZGVtYW5kLm1vbGRfdHlwZSkKICAgICAgICAgICAgICAgICAgICBjYXNpbmdfa2V5ID0gKAogICAgICAgICAgICAgICAgICAgICAgICBfbm9ybV9yZXNvdXJjZShkZW1hbmQuY2FzaW5nX3R5cGUpCiAgICAgICAgICAgICAgICAgICAgICAgIGlmIF9jYXNpbmdfcmVxdWlyZWQoZGVtYW5kLmNhc2luZ190eXBlKQogICAgICAgICAgICAgICAgICAgICAgICBlbHNlICIiCiAgICAgICAgICAgICAgICAgICAgKQoKICAgICAgICAgICAgICAgICAgICBzdGFydCA9IF9maW5kX3Jlc291cmNlX3N0YXJ0KAogICAgICAgICAgICAgICAgICAgICAgICByZXF1ZXN0ZWRfc3RhcnQ9cmVxdWVzdGVkX3N0YXJ0LAogICAgICAgICAgICAgICAgICAgICAgICBkdXJhdGlvbj1kdXJhdGlvbiwKICAgICAgICAgICAgICAgICAgICAgICAgdG90YWxfbWludXRlcz1zaGlmdF9lbmQsCiAgICAgICAgICAgICAgICAgICAgICAgIG1vbGRfa2V5PW1vbGRfa2V5LAogICAgICAgICAgICAgICAgICAgICAgICBtb2xkX2NhcGFjaXR5PW1vbGRfY2FwYWNpdHkuZ2V0KG1vbGRfa2V5LCAwKSwKICAgICAgICAgICAgICAgICAgICAgICAgbW9sZF9pbnRlcnZhbHM9bW9sZF9pbnRlcnZhbHMsCiAgICAgICAgICAgICAgICAgICAgICAgIGNhc2luZ19rZXk9Y2FzaW5nX2tleSwKICAgICAgICAgICAgICAgICAgICAgICAgY2FzaW5nX2NhcGFjaXR5PSgKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNhc2luZ19jYXBhY2l0eS5nZXQoY2FzaW5nX2tleSwgMCkKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGlmIGNhc2luZ19rZXkKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGVsc2UgMTAqKjkKICAgICAgICAgICAgICAgICAgICAgICAgKSwKICAgICAgICAgICAgICAgICAgICAgICAgY2FzaW5nX2ludGVydmFscz1jYXNpbmdfaW50ZXJ2YWxzLAogICAgICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgICAgICBpZiBzdGFydCBpcyBOb25lIG9yIHN0YXJ0IDwgc2hpZnRfc3RhcnQ6CiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCgogICAgICAgICAgICAgICAgICAgIGlmIGNhdml0eS5sYXN0X3NhcF9jb2RlID09IGRlbWFuZC5zYXBfY29kZToKICAgICAgICAgICAgICAgICAgICAgICAgcmV1c2VfcmFuayA9IDAKICAgICAgICAgICAgICAgICAgICBlbGlmIGNhdml0eS5sYXN0X3NhcF9jb2RlOgogICAgICAgICAgICAgICAgICAgICAgICByZXVzZV9yYW5rID0gMQogICAgICAgICAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICAgICAgICAgIHJldXNlX3JhbmsgPSAyCgogICAgICAgICAgICAgICAgICAgIGNhbmRpZGF0ZV9rZXkgPSAoCiAgICAgICAgICAgICAgICAgICAgICAgIHN0YXJ0LAogICAgICAgICAgICAgICAgICAgICAgICByZXVzZV9yYW5rLAogICAgICAgICAgICAgICAgICAgICAgICBwcmlvcml0eSwKICAgICAgICAgICAgICAgICAgICAgICAgX2RlbWFuZF9zb3J0X2tleShkZW1hbmQpLAogICAgICAgICAgICAgICAgICAgICAgICBfbm9ybV9saW5lKGNhdml0eS5saW5lX25hbWUpLAogICAgICAgICAgICAgICAgICAgICAgICBjYXZpdHkuY2F2aXR5X25vLAogICAgICAgICAgICAgICAgICAgICAgICBjYXZpdHkuY2F2aXR5X2lkLAogICAgICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgICAgICBjYW5kaWRhdGUgPSAoCiAgICAgICAgICAgICAgICAgICAgICAgIGNhbmRpZGF0ZV9rZXksCiAgICAgICAgICAgICAgICAgICAgICAgIGNhdml0eSwKICAgICAgICAgICAgICAgICAgICAgICAgZGVtYW5kLAogICAgICAgICAgICAgICAgICAgICAgICBzdGFydCwKICAgICAgICAgICAgICAgICAgICAgICAgY2hhbmdlb3ZlciwKICAgICAgICAgICAgICAgICAgICApCiAgICAgICAgICAgICAgICAgICAgaWYgYmVzdCBpcyBOb25lIG9yIGNhbmRpZGF0ZV9rZXkgPCBiZXN0WzBdOgogICAgICAgICAgICAgICAgICAgICAgICBiZXN0ID0gY2FuZGlkYXRlCgogICAgICAgICAgICBpZiBiZXN0IGlzIE5vbmU6CiAgICAgICAgICAgICAgICBicmVhawoKICAgICAgICAgICAgKAogICAgICAgICAgICAgICAgX2NhbmRpZGF0ZV9rZXksCiAgICAgICAgICAgICAgICBjYXZpdHksCiAgICAgICAgICAgICAgICBkZW1hbmQsCiAgICAgICAgICAgICAgICBzdGFydCwKICAgICAgICAgICAgICAgIF9jaGFuZ2VvdmVyLAogICAgICAgICAgICApID0gYmVzdAogICAgICAgICAgICBlbmQgPSBzdGFydCArIGRlbWFuZC5lZmZlY3RpdmVfY3ljbGVfbWludXRlcwoKICAgICAgICAgICAgaWYgZW5kID4gc2hpZnRfZW5kOgogICAgICAgICAgICAgICAgY2F2aXR5LmN1cnNvciA9IHNoaWZ0X2VuZAogICAgICAgICAgICAgICAgY29udGludWUKCiAgICAgICAgICAgIG1vbGRfa2V5ID0gX25vcm1fcmVzb3VyY2UoZGVtYW5kLm1vbGRfdHlwZSkKICAgICAgICAgICAgbW9sZF9pbnRlcnZhbHNbbW9sZF9rZXldLmFwcGVuZCgoc3RhcnQsIGVuZCkpCiAgICAgICAgICAgIGlmIF9jYXNpbmdfcmVxdWlyZWQoZGVtYW5kLmNhc2luZ190eXBlKToKICAgICAgICAgICAgICAgIGNhc2luZ19rZXkgPSBfbm9ybV9yZXNvdXJjZShkZW1hbmQuY2FzaW5nX3R5cGUpCiAgICAgICAgICAgICAgICBjYXNpbmdfaW50ZXJ2YWxzW2Nhc2luZ19rZXldLmFwcGVuZCgoc3RhcnQsIGVuZCkpCgogICAgICAgICAgICBhbGxvY2F0aW9ucy5hcHBlbmQoCiAgICAgICAgICAgICAgICBfVW5pdEFsbG9jYXRpb24oCiAgICAgICAgICAgICAgICAgICAgY2F2aXR5X2lkPWNhdml0eS5jYXZpdHlfaWQsCiAgICAgICAgICAgICAgICAgICAgbGluZV9uYW1lPWNhdml0eS5saW5lX25hbWUsCiAgICAgICAgICAgICAgICAgICAgY2F2aXR5X25vPWNhdml0eS5jYXZpdHlfbm8sCiAgICAgICAgICAgICAgICAgICAgb3Zlbl9ubz1jYXZpdHkub3Zlbl9ubywKICAgICAgICAgICAgICAgICAgICBzYXBfY29kZT1kZW1hbmQuc2FwX2NvZGUsCiAgICAgICAgICAgICAgICAgICAgc3RhcnRfbWludXRlPXN0YXJ0LAogICAgICAgICAgICAgICAgICAgIGVuZF9taW51dGU9ZW5kLAogICAgICAgICAgICAgICAgICAgIHNoaWZ0X25hbWU9c2hpZnRfbmFtZSwKICAgICAgICAgICAgICAgICAgICBkZW1hbmQ9ZGVtYW5kLAogICAgICAgICAgICAgICAgKQogICAgICAgICAgICApCiAgICAgICAgICAgIGNhdml0eS5jdXJzb3IgPSBlbmQKICAgICAgICAgICAgY2F2aXR5Lmxhc3Rfc2FwX2NvZGUgPSBkZW1hbmQuc2FwX2NvZGUKICAgICAgICAgICAgZGVtYW5kLnJlbWFpbmluZ19xdHkgLT0gMQoKICAgICAgICAgICAgYWN0aXZlX2RlbWFuZHMgPSBbCiAgICAgICAgICAgICAgICBpdGVtCiAgICAgICAgICAgICAgICBmb3IgaXRlbSBpbiBhY3RpdmVfZGVtYW5kcwogICAgICAgICAgICAgICAgaWYgaXRlbS5yZW1haW5pbmdfcXR5ID4gMAogICAgICAgICAgICBdCiAgICAgICAgICAgIGFjdGl2ZV9kZW1hbmRzLnNvcnQoa2V5PV9kZW1hbmRfc29ydF9rZXkpCgogICAgcmV0dXJuIGFsbG9jYXRpb25z").decode()
SELECTOR_BLOCK = base64.b64decode("ICAgICAgICBzZWxmLnNoaWZ0X3NlbGVjdG9yID0gUUNvbWJvQm94KCkKICAgICAgICBzZWxmLnNoaWZ0X3NlbGVjdG9yLmFkZEl0ZW0oCiAgICAgICAgICAgICJBTEwgU0hJRlRTICgwNzowMCAtIDA3OjAwKSIsCiAgICAgICAgICAgICJBTEwiLAogICAgICAgICkKICAgICAgICBzZWxmLnNoaWZ0X3NlbGVjdG9yLmFkZEl0ZW0oCiAgICAgICAgICAgICJEQVkgU0hJRlQgKDA3OjAwIC0gMTk6MDApIiwKICAgICAgICAgICAgIkRBWSIsCiAgICAgICAgKQogICAgICAgIHNlbGYuc2hpZnRfc2VsZWN0b3IuYWRkSXRlbSgKICAgICAgICAgICAgIk5JR0hUIFNISUZUICgxOTowMCAtIDA3OjAwKSIsCiAgICAgICAgICAgICJOSUdIVCIsCiAgICAgICAgKQogICAgICAgIHNlbGYuc2hpZnRfc2VsZWN0b3Iuc2V0TWluaW11bVdpZHRoKDIzMCkKICAgICAgICBzZWxmLnNoaWZ0X3NlbGVjdG9yLnNldFRvb2xUaXAoCiAgICAgICAgICAgICJTZWxlY3QgdGhlIGZpeGVkIGZhY3Rvcnkgc2hpZnQgdG8gZ2VuZXJhdGUuIgogICAgICAgICkKICAgICAgICBzZWxmLnNoaWZ0X3NlbGVjdG9yLmN1cnJlbnRJbmRleENoYW5nZWQuY29ubmVjdCgKICAgICAgICAgICAgc2VsZi5fb25fc2hpZnRfY2hhbmdlZAogICAgICAgICkKCg==").decode()
SETTINGS_METHODS = base64.b64decode("ICAgIGRlZiBfb25fc2hpZnRfY2hhbmdlZChzZWxmLCAqYXJncykgLT4gTm9uZToKICAgICAgICBRVGltZXIuc2luZ2xlU2hvdCgKICAgICAgICAgICAgMCwKICAgICAgICAgICAgc2VsZi5fcmVmcmVzaF9zZWxlY3RlZF9zaGlmdF9wcmV2aWV3LAogICAgICAgICkKCiAgICBkZWYgX3JlZnJlc2hfc2VsZWN0ZWRfc2hpZnRfcHJldmlldyhzZWxmKSAtPiBOb25lOgogICAgICAgIGlmIG5vdCBzZWxmLmlzVmlzaWJsZSgpOgogICAgICAgICAgICByZXR1cm4KCiAgICAgICAgdHJ5OgogICAgICAgICAgICBzZXR0aW5ncyA9IHNlbGYuX3NldHRpbmdzKCkKICAgICAgICAgICAgd2l0aCBnZXRfc2Vzc2lvbigpIGFzIHNlc3Npb246CiAgICAgICAgICAgICAgICByb3dzLCBzdW1tYXJ5LCBibG9ja2VkID0gZ2VuZXJhdGVfY2F2aXR5X3BsYW4oCiAgICAgICAgICAgICAgICAgICAgc2Vzc2lvbiwKICAgICAgICAgICAgICAgICAgICBzZXR0aW5ncz1zZXR0aW5ncywKICAgICAgICAgICAgICAgICkKCiAgICAgICAgICAgIHNlbGYuY3VycmVudF9ydW5faWQgPSBOb25lCiAgICAgICAgICAgIHNlbGYucHJldmlld19pc19zYXZlZCA9IEZhbHNlCiAgICAgICAgICAgIHNlbGYuX2FwcGx5X3Jlc3VsdChyb3dzLCBzdW1tYXJ5LCBibG9ja2VkKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZXhjOgogICAgICAgICAgICBRTWVzc2FnZUJveC5jcml0aWNhbCgKICAgICAgICAgICAgICAgIHNlbGYsCiAgICAgICAgICAgICAgICAiU2hpZnQgUGxhbiBSZWZyZXNoIiwKICAgICAgICAgICAgICAgIHN0cihleGMpLAogICAgICAgICAgICApCgogICAgZGVmIF9zZXR0aW5ncyhzZWxmKSAtPiBDYXZpdHlQbGFuU2V0dGluZ3M6CiAgICAgICAgcGxhbm5pbmdfZGF0ZSA9IHNlbGYucGxhbl9kYXRlLmRhdGUoKS50b1B5dGhvbigpCiAgICAgICAgaWYgbm90IGlzaW5zdGFuY2UocGxhbm5pbmdfZGF0ZSwgZGF0ZSk6CiAgICAgICAgICAgIHBsYW5uaW5nX2RhdGUgPSBkYXRlKAogICAgICAgICAgICAgICAgcGxhbm5pbmdfZGF0ZS55ZWFyLAogICAgICAgICAgICAgICAgcGxhbm5pbmdfZGF0ZS5tb250aCwKICAgICAgICAgICAgICAgIHBsYW5uaW5nX2RhdGUuZGF5LAogICAgICAgICAgICApCgogICAgICAgIHNoaWZ0X21vZGUgPSBzdHIoCiAgICAgICAgICAgIHNlbGYuc2hpZnRfc2VsZWN0b3IuY3VycmVudERhdGEoKSBvciAiQUxMIgogICAgICAgICkudXBwZXIoKQogICAgICAgIGlmIHNoaWZ0X21vZGUgbm90IGluIHsiQUxMIiwgIkRBWSIsICJOSUdIVCJ9OgogICAgICAgICAgICBzaGlmdF9tb2RlID0gIkFMTCIKCiAgICAgICAgZGF5X21pbnV0ZXMgPSA3MjAgaWYgc2hpZnRfbW9kZSBpbiB7IkFMTCIsICJEQVkifSBlbHNlIDAKICAgICAgICBuaWdodF9taW51dGVzID0gNzIwIGlmIHNoaWZ0X21vZGUgaW4geyJBTEwiLCAiTklHSFQifSBlbHNlIDAKCiAgICAgICAgcmV0dXJuIENhdml0eVBsYW5TZXR0aW5ncygKICAgICAgICAgICAgcGxhbm5pbmdfZGF0ZT1wbGFubmluZ19kYXRlLAogICAgICAgICAgICBkYXlfc2hpZnRfbWludXRlcz1kYXlfbWludXRlcywKICAgICAgICAgICAgbmlnaHRfc2hpZnRfbWludXRlcz1uaWdodF9taW51dGVzLAogICAgICAgICAgICBjaGFuZ2VvdmVyX21pbnV0ZXM9bWF4KAogICAgICAgICAgICAgICAgMCwKICAgICAgICAgICAgICAgIGludChzZWxmLmNoYW5nZW92ZXJfbWludXRlcy52YWx1ZSgpKSwKICAgICAgICAgICAgKSwKICAgICAgICApCgo=").decode()
SET_CONTROLS_METHOD = base64.b64decode("ICAgIGRlZiBfc2V0X3NoaWZ0X2NvbnRyb2xzKAogICAgICAgIHNlbGYsCiAgICAgICAgc2V0dGluZ3M6IENhdml0eVBsYW5TZXR0aW5ncywKICAgICkgLT4gTm9uZToKICAgICAgICBkYXlfZW5hYmxlZCA9IHNldHRpbmdzLmRheV9zaGlmdF9taW51dGVzID4gMAogICAgICAgIG5pZ2h0X2VuYWJsZWQgPSBzZXR0aW5ncy5uaWdodF9zaGlmdF9taW51dGVzID4gMAoKICAgICAgICBpZiBkYXlfZW5hYmxlZCBhbmQgbmlnaHRfZW5hYmxlZDoKICAgICAgICAgICAgc2hpZnRfbW9kZSA9ICJBTEwiCiAgICAgICAgZWxpZiBkYXlfZW5hYmxlZDoKICAgICAgICAgICAgc2hpZnRfbW9kZSA9ICJEQVkiCiAgICAgICAgZWxpZiBuaWdodF9lbmFibGVkOgogICAgICAgICAgICBzaGlmdF9tb2RlID0gIk5JR0hUIgogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHNoaWZ0X21vZGUgPSAiQUxMIgoKICAgICAgICBpbmRleCA9IHNlbGYuc2hpZnRfc2VsZWN0b3IuZmluZERhdGEoc2hpZnRfbW9kZSkKICAgICAgICBzZWxmLnNoaWZ0X3NlbGVjdG9yLmJsb2NrU2lnbmFscyhUcnVlKQogICAgICAgIHNlbGYuc2hpZnRfc2VsZWN0b3Iuc2V0Q3VycmVudEluZGV4KG1heCgwLCBpbmRleCkpCiAgICAgICAgc2VsZi5zaGlmdF9zZWxlY3Rvci5ibG9ja1NpZ25hbHMoRmFsc2UpCiAgICAgICAgc2VsZi5jaGFuZ2VvdmVyX21pbnV0ZXMuc2V0VmFsdWUoCiAgICAgICAgICAgIHNldHRpbmdzLmNoYW5nZW92ZXJfbWludXRlcwogICAgICAgICkKCg==").decode()


def replace_between(source, start_marker, end_marker, replacement):
    start = source.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Start marker not found: {start_marker}")
    end = source.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"End marker not found: {end_marker}")
    return source[:start] + replacement.rstrip() + "\n\n" + source[end:]


def patch_schedule_page(project_root: Path) -> None:
    target = project_root / "app" / "ui" / "schedule_page.py"
    source = target.read_text(encoding="utf-8-sig")

    if "self.shift_selector = QComboBox()" in source:
        print("Shift selector UI is already installed.")
        return

    if "from PySide6.QtCore import QDate, Qt, QTimer" not in source:
        old_import = "from PySide6.QtCore import QDate, Qt"
        if old_import not in source:
            raise RuntimeError("QtCore import was not found.")
        source = source.replace(
            old_import,
            "from PySide6.QtCore import QDate, Qt, QTimer",
            1,
        )

    start = source.find("        self.day_hours = QDoubleSpinBox()")
    end = source.find("        self.changeover_minutes = QSpinBox()", start)
    if start < 0 or end < 0:
        raise RuntimeError("Day/night hour selector block was not found.")
    source = source[:start] + SELECTOR_BLOCK + source[end:]

    old_controls = """        planning_controls.addWidget(
            QLabel("Day Shift")
        )
        planning_controls.addWidget(self.day_hours)
        planning_controls.addWidget(
            QLabel("Night Shift")
        )
        planning_controls.addWidget(
            self.night_hours
        )
"""
    new_controls = """        planning_controls.addWidget(
            QLabel("Shift")
        )
        planning_controls.addWidget(
            self.shift_selector
        )
"""
    if old_controls not in source:
        raise RuntimeError("Planning shift controls block was not found.")
    source = source.replace(old_controls, new_controls, 1)

    settings_start = source.find("    def _settings(self) -> CavityPlanSettings:")
    settings_end = source.find("    def _load_saved_or_preview(", settings_start)
    if settings_start < 0 or settings_end < 0:
        raise RuntimeError("_settings method boundaries were not found.")
    source = source[:settings_start] + SETTINGS_METHODS + source[settings_end:]

    controls_start = source.find("    def _set_shift_controls(")
    controls_end = source.find("    def _refresh_line_filter(", controls_start)
    if controls_start < 0 or controls_end < 0:
        raise RuntimeError("_set_shift_controls boundaries were not found.")
    source = source[:controls_start] + SET_CONTROLS_METHOD + source[controls_end:]

    old_ui_format = """    @staticmethod
    def _format_minute(value: int) -> str:
        minute = max(0, int(value))
        return (
            f"{minute // 60:02d}:"
            f"{minute % 60:02d}"
        )
"""
    new_ui_format = """    @staticmethod
    def _format_minute(value: int) -> str:
        minute = (420 + max(0, int(value))) % 1440
        return (
            f"{minute // 60:02d}:"
            f"{minute % 60:02d}"
        )
"""
    if old_ui_format not in source:
        raise RuntimeError("UI _format_minute method was not found.")
    source = source.replace(old_ui_format, new_ui_format, 1)

    old_subtitle = '            "time and cavity operating status."\n'
    new_subtitle = (
        '            "time and cavity operating status. Fixed shifts: "\n'
        '            "DAY 07:00-19:00 and NIGHT 19:00-07:00."\n'
    )
    if old_subtitle in source:
        source = source.replace(old_subtitle, new_subtitle, 1)

    if "self.day_hours" in source or "self.night_hours" in source:
        raise RuntimeError("Old day/night hour controls still have references.")

    target.write_text(source, encoding="utf-8")
    print(f"Updated: {target}")


def patch_service(project_root: Path) -> None:
    target = project_root / "app" / "services" / "cavity_daily_plan_service.py"
    source = target.read_text(encoding="utf-8-sig")

    source = replace_between(
        source,
        "def _schedule_day(",
        "def _find_resource_start(",
        SCHEDULE_REPLACEMENT,
    )

    old_group = """            if (
                current
                and (
                    current[-1].sap_code
                    != unit.sap_code
                    or current[-1].end_minute
                    != unit.start_minute
                )
            ):"""
    new_group = """            if (
                current
                and current[-1].sap_code
                != unit.sap_code
            ):"""
    if old_group in source:
        source = source.replace(old_group, new_group, 1)

    old_schedule = """            schedule_text = (
                f"{_format_minute(start)}-"
                f"{_format_minute(end)} "
                f"({shift_name})"
            )"""
    new_schedule = """            day_units = [
                unit
                for unit in group
                if unit.shift_name == "DAY"
            ]
            night_units = [
                unit
                for unit in group
                if unit.shift_name == "NIGHT"
            ]
            schedule_parts: list[str] = []
            if day_units:
                schedule_parts.append(
                    "DAY "
                    f"{_format_minute(day_units[0].start_minute)}-"
                    f"{_format_minute(day_units[-1].end_minute)}"
                )
            if night_units:
                schedule_parts.append(
                    "NIGHT "
                    f"{_format_minute(night_units[0].start_minute)}-"
                    f"{_format_minute(night_units[-1].end_minute)}"
                )
            schedule_text = "; ".join(schedule_parts)"""
    if old_schedule in source:
        source = source.replace(old_schedule, new_schedule, 1)

    old_format = """def _format_minute(value: int) -> str:
    minute = max(0, int(value))
    hours = minute // 60
    minutes = minute % 60
    return f"{hours:02d}:{minutes:02d}"
"""
    new_format = """def _format_minute(value: int) -> str:
    minute = (420 + max(0, int(value))) % 1440
    hours = minute // 60
    minutes = minute % 60
    return f"{hours:02d}:{minutes:02d}"
"""
    if old_format in source:
        source = source.replace(old_format, new_format, 1)
    elif "minute = (420 + max(0, int(value))) % 1440" not in source:
        raise RuntimeError("Service _format_minute function was not found.")

    target.write_text(source, encoding="utf-8")
    print(f"Updated: {target}")


def main():
    project_root = Path.cwd()
    schedule_target = project_root / "app" / "ui" / "schedule_page.py"
    service_target = project_root / "app" / "services" / "cavity_daily_plan_service.py"
    if not schedule_target.exists() or not service_target.exists():
        raise SystemExit("Run this installer from the MPPS project root.")

    backup_dir = project_root / "backups" / "code_backups" / "local_snapshots"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for target in (schedule_target, service_target):
        backup = backup_dir / f"{target.stem}_before_shift_selector_{stamp}.py"
        backup.write_text(target.read_text(encoding="utf-8-sig"), encoding="utf-8")
        print(f"Backup: {backup}")

    patch_schedule_page(project_root)
    patch_service(project_root)
    print("Fixed shift selector update applied.")


if __name__ == "__main__":
    main()
