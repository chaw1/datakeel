# Small-team deployment behind an authenticating proxy

[中文](DEPLOYMENT.zh.md) · [Identity and access](IDENTITY_ACCESS.md) · [Production workflow](PRODUCTION.md)

Datakeel is a single-instance platform for a trusted installation. The application enforces
server-side operator roles, controlled-action approval and audit, but it does **not** implement
deployment-level authentication, TLS termination or multi-tenant isolation. This guide describes
the supported boundary for exposing one instance to a small team: an authenticating reverse proxy
in front of a loopback-bound application. It is a deployment recipe, not an architecture change.

## Trust model

| Layer | Responsibility |
| --- | --- |
| Reverse proxy | TLS, authenticating every human, stripping any client-supplied `X-Datakeel-Actor`, injecting the authenticated principal |
| Application | Operator selection from `X-Datakeel-Actor`, server-side role scopes, approval gates, audit, receipts |
| Database / object store | Their own credentials and network isolation; HTTP role checks do not replace database authentication |

Defaults are already loopback-only: `datakeel api` binds `127.0.0.1:8765` and `datakeel mcp`
binds `127.0.0.1:8766`. Keep these defaults. Do not pass `--host 0.0.0.0`; if a different bind
address is unavoidable, firewall the port so only the proxy can reach it.

With zero registered users the instance keeps the single-operator local experience: every request
acts as `local` with full scope. Registering users switches the instance to role-checked mode;
unknown or disabled operators can read but cannot modify business objects. See
[identity and access](IDENTITY_ACCESS.md) for roles, scopes and the write-entry matrix.

## Two supported modes

**Mode A — authenticated shared operator.** Keep zero registered users. The proxy authenticates
every team member and forwards to the application, which continues to act as `local`. Authorization
lives entirely at the deployment layer; application audit records `local`, and per-human attribution
exists only in proxy logs. Suitable for a small, mutually trusted team that wants network access
control without per-person application roles.

**Mode B — registered per-user operators.** Register one application user per human, with role
bindings. The proxy authenticates each person and injects their principal as `X-Datakeel-Actor`.
The application checks that operator's server-side scopes on every write, approval and execution.

Mode B is compatible with the bundled Web UI. Approval and execution request bodies may name the
legacy `local` actor; the server accepts it as an alias and signs with the effective header identity,
so the audit records the injected principal. API and CLI clients send their own operator explicitly.
The injected value must exactly match a registered user ID; an unregistered value is an unknown
operator (read-only after registration).

## Recipe 1: Caddy + oauth2-proxy (OIDC)

Run oauth2-proxy next to the application (loopback or a private network), pointing at your identity
provider. It only authenticates; Caddy serves TLS and forwards:

```
oauth2-proxy \
  --provider=oidc \
  --oidc-issuer-url=https://idp.example.org/realms/team \
  --client-id=datakeel --client-secret=REPLACE_ME \
  --cookie-secret=REPLACE_ME_32_BYTES_BASE64 \
  --http-address=127.0.0.1:4180 \
  --upstream=static://200 --reverse-proxy=true \
  --set-xauthrequest=true --email-domain=example.org
```

Caddyfile:

```
datakeel.example.org {
    forward_auth 127.0.0.1:4180 {
        uri /oauth2/auth
        copy_headers X-Auth-Request-User
    }
    reverse_proxy 127.0.0.1:8765 {
        header_up -X-Datakeel-Actor
        header_up X-Datakeel-Actor {http.request.header.X-Auth-Request-User}
    }
}
```

`header_up -X-Datakeel-Actor` removes whatever the client sent; the next line injects the
authenticated principal. Unauthenticated requests never reach the application. The exact
`X-Auth-Request-User` value depends on your IdP claims (typically the preferred username); verify
it once and register application user IDs to match.

## Recipe 2: nginx + oauth2-proxy

```nginx
server {
    listen 443 ssl;
    server_name datakeel.example.org;
    # ssl_certificate / ssl_certificate_key ...

    location /oauth2/ {
        proxy_pass http://127.0.0.1:4180;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
    }

    location / {
        auth_request /oauth2/auth;
        error_page 401 = /oauth2/sign_in;
        auth_request_set $auth_user $upstream_http_x_auth_request_user;
        proxy_set_header X-Datakeel-Actor $auth_user;
        proxy_pass http://127.0.0.1:8765;
    }
}
```

`proxy_set_header X-Datakeel-Actor $auth_user` replaces any client-supplied header. Keep nginx's
default `underscores_in_headers off` behavior irrelevant here: the actor header uses hyphens and is
always overwritten, never inherited.

## Recipe 3: Caddy basic auth (no IdP)

For a very small team without an identity provider, Caddy can authenticate directly. Generate
password hashes with `caddy hash-password` and store only the hashes:

```
datakeel.example.org {
    basicauth {
        alice REPLACE_WITH_BCRYPT_HASH
        bob   REPLACE_WITH_BCRYPT_HASH
    }
    reverse_proxy 127.0.0.1:8765 {
        header_up -X-Datakeel-Actor
        header_up X-Datakeel-Actor {http.auth.user.id}
    }
}
```

With zero registered users this is Mode A (authentication only). Register `alice` and `bob` with
roles to make it Mode B. Basic auth has no session revocation or MFA; prefer Recipe 1 when an IdP
is available.

## Registering operators and roles

1. Start the instance behind the proxy and authenticate as the first administrator.
2. Register users through the Web UI, CLI or `manage_users` action. The first registered user
   without explicit roles automatically holds `administrator`.
3. Bind role templates (`administrator`, `project_manager`, `annotator`, `reviewer`, `acceptance`)
   or custom roles whose scopes come only from registered actions. Role changes are themselves
   controlled actions requiring approval.
4. In Mode B, user IDs must equal the principal the proxy injects.

Archiving a user removes write access on the next request; archiving the last user does not restore
anonymous writes.

## Verification checklist

Run these against the deployed proxy hostname before inviting the team:

1. **Unauthenticated access is rejected.** `curl -i https://datakeel.example.org/api/datasets`
   returns the proxy's 401/redirect, never application data.
2. **Forged actor headers are stripped.** Authenticate as a low-privilege user, then
   `curl -H "X-Datakeel-Actor: administrator" ...` against a write entry their role forbids
   (for example `POST /api/datasets`). The application must reject it; the effective operator is
   the injected principal, not the forged value.
3. **Direct port access is impossible.** From another machine, `curl http://HOST:8765/` must fail
   (loopback bind or firewall).
4. **Role revocation takes effect.** Archive or re-role a user through an approved plan; their next
   request reflects the change.
5. **Audit names the real signer.** Approve and execute a reversible plan through the Web UI in
   Mode B; the receipt and audit record the injected principal.
6. **MCP is not exposed.** The MCP SSE port stays loopback-only unless it receives the same proxy
   treatment; stdio MCP runs as a local trusted process.

## Boundaries and operations

- Workers, the non-production CLI and direct database access remain local trusted processes on the
  application host. This guide does not make them network services.
- PostgreSQL credentials and object-store access are configured separately; the proxy does not
  protect them. Use a dedicated database role and keep the database off public networks.
- Set `DATAKEEL_HOME` to a persistent data directory and back it up; see
  [database maintenance](DATABASE_MAINTENANCE.md) for SQLite versioned backups and restore.
- Multi-tenant isolation, app-level login and enterprise identity federation remain out of scope by
  architecture. One instance serves one trusted team.
- Capacity numbers are observed operating points, not deployment guarantees; see
  [capacity](CAPACITY.md) and re-measure on your target hardware before committing to SLOs.
