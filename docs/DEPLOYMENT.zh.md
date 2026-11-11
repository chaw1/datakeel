# 小团队部署：认证代理之后的可信实例

[English](DEPLOYMENT.md) · [身份与访问](IDENTITY_ACCESS.zh.md) · [数据生产流程](PRODUCTION.zh.md)

Datakeel 是面向可信安装的单实例平台。应用负责服务端操作人角色、受控动作审批与审计，但**不做**
部署级身份认证、TLS 终结或多租户隔离。本指南给出把同一个实例开放给小团队的支持边界：应用保持
回环绑定，前面放一个负责认证的反向代理。这是部署配方，不是架构变更。

## 信任模型

| 层 | 职责 |
| --- | --- |
| 反向代理 | TLS、认证每个人、剥离客户端自带的 `X-Datakeel-Actor`、注入认证后的主体 |
| 应用 | 从 `X-Datakeel-Actor` 选择操作人、服务端角色范围、审批门、审计与回执 |
| 数据库 / 对象存储 | 各自的凭证与网络隔离；HTTP 角色检查不替代数据库认证 |

默认值已经是回环：`datakeel api` 绑定 `127.0.0.1:8765`，`datakeel mcp` 绑定 `127.0.0.1:8766`。
保持默认，不要传 `--host 0.0.0.0`；确需改绑定时，用防火墙保证只有代理能访问该端口。

实例零登记用户时保持本机单人体验：所有请求以 `local` 全范围行事。登记用户后切换到角色检查
模式，未知或停用的操作人只能读、不能修改业务对象。角色、范围与写入口矩阵见
[身份与访问](IDENTITY_ACCESS.zh.md)。

## 两种支持模式

**模式 A——认证后的共享操作人。** 保持零登记用户。代理认证每个团队成员后转发，应用继续以
`local` 行事。授权完全在部署层；应用审计记 `local`，按人归因只存在于代理日志。适合彼此互信、
只需要网络访问控制的小团队。

**模式 B——登记的按人操作人。** 每人登记一个应用用户并绑定角色。代理认证每个人并把其主体
注入 `X-Datakeel-Actor`，应用在每次写入、签批和执行时检查该操作人的服务端范围。

模式 B 与自带 Web UI 兼容：签批/执行请求体可以写旧别名 `local`，服务端接受别名并以请求头的
有效身份签署，审计记录的是注入的真实主体。API 与 CLI 客户端显式携带自己的操作人。注入值必须
与登记用户 ID 完全一致；未登记的值是未知操作人（登记后只读）。

## 配方一：Caddy + oauth2-proxy（OIDC）

oauth2-proxy 与应用同机部署（回环或私有网络），对接你的身份提供方，只负责认证；Caddy 终结
TLS 并转发：

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

Caddyfile：

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

`header_up -X-Datakeel-Actor` 先删掉客户端带来的任何值，下一行再注入认证主体。未认证请求
到不了应用。`X-Auth-Request-User` 的具体取值取决于 IdP 的声明（通常是 preferred username），
先验证一次，再按该值登记应用用户 ID。

## 配方二：nginx + oauth2-proxy

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

`proxy_set_header X-Datakeel-Actor $auth_user` 会覆盖客户端自带的同名头，不会继承。

## 配方三：Caddy basic auth（无 IdP）

没有身份提供方的极小团队可以让 Caddy 直接认证。用 `caddy hash-password` 生成口令哈希，
只保存哈希：

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

零登记用户时这是模式 A（只做认证）；给 `alice`、`bob` 登记角色即为模式 B。basic auth 没有
会话吊销和 MFA，有 IdP 时优先配方一。

## 登记操作人与角色

1. 通过代理访问实例，以首位管理员身份认证。
2. 用 Web UI、CLI 或 `manage_users` 动作登记用户。首位未显式指定角色的用户自动持有
   `administrator`。
3. 绑定角色模板（`administrator`、`project_manager`、`annotator`、`reviewer`、`acceptance`）
   或自定义角色；范围只能来自已注册动作。角色变更本身是需要签批的受控动作。
4. 模式 B 中用户 ID 必须等于代理注入的主体值。

归档用户后其下一次请求即失去写权限；归档最后一人不会恢复匿名写。

## 验收清单

邀请团队之前，对部署后的代理域名逐条验证：

1. **未认证访问被拒。** `curl -i https://datakeel.example.org/api/datasets` 返回代理的
   401/跳转，绝不返回应用数据。
2. **伪造 actor 头被剥离。** 以低权限用户认证后，对其角色禁止的写入口（如 `POST /api/datasets`）
   发 `curl -H "X-Datakeel-Actor: administrator" ...`，应用必须拒绝；有效操作人是注入主体，
   不是伪造值。
3. **直连端口不通。** 从另一台机器 `curl http://HOST:8765/` 必须失败（回环绑定或防火墙）。
4. **角色吊销即时生效。** 经签批计划归档或改角色后，该用户下一次请求即反映变化。
5. **审计记录真实签批人。** 模式 B 下通过 Web UI 签批并执行一个可逆计划，回执与审计记录
   注入的主体。
6. **MCP 不对外。** MCP SSE 端口保持回环，除非接受同样的代理处理；stdio MCP 是本机可信进程。

## 边界与运维

- worker、非生产 CLI 和直接数据库访问仍是应用主机上的本机可信进程，本指南不把它们变成
  网络服务。
- PostgreSQL 凭证与对象存储访问另行配置，代理不保护它们；使用专用数据库角色，数据库不接
  公网。
- 用 `DATAKEEL_HOME` 指定持久数据目录并备份；SQLite 版本化备份与恢复见
  [数据库维护](DATABASE_MAINTENANCE.md)。
- 多租户隔离、应用级登录和企业身份联邦按架构决策不在范围内；一个实例服务一个可信团队。
- 容量数字是实测工作点，不是部署承诺；见[容量](CAPACITY.md)，承诺 SLO 前在目标硬件复测。
