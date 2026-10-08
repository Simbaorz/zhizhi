# Zhizhi Test Portal

Optional test-host application. Enterprise integrations continue to authenticate users in their
own host and call the existing Agent API with trusted `tenant_code` context.

Portal owns only test accounts, opaque browser sessions, account scope bindings and a conversation
directory in `portal.database_file`. Full messages, attachments and runs remain in the Agent
backend. Its platform connection executes SELECT only; it never creates or migrates platform tables.
The Portal database must be separate from the platform database.

Copy `conf/portal.example.yml` to `conf/portal.yml`. `platform_config_file` references the local
database and RSA password-transport settings already used by Admin, without copying credentials.
A separate infrastructure YAML with a SELECT-only database account and a mounted RSA key can be
used for isolated deployments. As with other settings, environment overrides take precedence.
Portal uses local configuration; point this infrastructure reference at the actual platform DB.

```bash
CONFIG_SOURCE=local CONFIG_FILE=conf/portal.yml uv run zhizhi-portal-api --host 127.0.0.1 --port 8003
```

Set `PROJECT_HOME` to the repository root when running from another directory. The root
`scripts/start-local.sh` also starts Portal and Portal Admin and prepares the non-secret local
Portal configuration from the example if missing.

- Portal Admin: enabled platform Super Admin accounts sign in using their existing passwords.
  Status, super-admin membership and token version are checked on every request.
- Users: administrators create test accounts and assign explicit tenant-root or arbitrary-depth
  organization scopes. Disabling an account or revoking a scope takes effect on subsequent requests.
- Browser callers send only a scope binding ID or conversation ID. Portal derives `tenant_code`,
  organization ID and the stable account principal ID; callers cannot override identity in chat bodies.
- Each conversation belongs to one account and one bound scope. Rename, archive, restore and
  paginated directory operations are supported. Archived conversations cannot execute new turns.
- Separate HttpOnly user/admin cookies and CSRF tokens protect writes. Passwords use the existing
  RSA-OAEP browser transport and PBKDF2 hashing. New passwords require 12–256 characters; password
  changes/reset invalidate all existing user sessions.
- Scope lookup walks the actual organization tree; no province/city levels or business-specific roles
  are encoded. Resource entitlements and execution bindings remain owned by the main Admin.

Deploy Web and Portal's `/api` on the same origin. Portal Admin can be a separate origin with its
own `/api` proxy to Portal. Keep the Agent API reachable only by Portal and trusted enterprise
hosts/gateways; otherwise browsers could bypass Portal authorization. Use secure cookies over
HTTPS. This optional identity system is for tests, not a production enterprise identity provider.

Tests use isolated disposable databases and an injected fake upstream. They do not read local
deployment configuration, create platform users or grant access to existing tenants.
