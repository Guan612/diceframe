# DiceFrame 安全公网联机方案

## 目标

普通 GM 不应为了分享一局游戏而购买域名、理解证书链或把 DiceFrame 的 HTTP 端口直接暴露到公网。本方案把公网接入分为三档，并保证接入方式故障时不影响本地游戏和存档。

## 为什么不能把自签证书作为默认方案

自签证书可以加密，但陌生玩家的浏览器并不信任签发者。要求每位玩家安装根证书不仅体验差，也会扩大根证书私钥泄露后的风险。因此它只适合 GM 自己完全控制的设备，不作为分享链接方案。

## 入口选择原则

这些入口是并列选项，不由 DiceFrame 强制排序。用户在“分享链接地址”中明确填写的 HTTPS 地址优先级最高；启动某个隧道插件时可以临时接管该地址，停止后必须恢复原值。任何新增方案都不得自动关闭、改写或阻断 SakuraFrp、其他 FRP 服务、命名 Cloudflare Tunnel 和用户自建的 HTTPS 反向代理。

### 1. 无公网 IP、无域名：Cloudflare Quick Tunnel 或第三方 HTTPS 穿透

对于几十分钟到几小时的小局，现有 Cloudflare 快速隧道可以继续作为正式联机入口：免账号、免域名，启动后直接得到 `https://xxx.trycloudflare.com` 地址。界面保留非阻断提示，说明地址会在重启后变化、官方不提供 SLA，并且官方当前注明 Quick Tunnel 不支持 SSE；如果实时回合更新异常，玩家可以刷新页面，GM 也可以改用其他入口。

SakuraFrp、其他 FRP/内网穿透服务只要最终提供浏览器信任的 HTTPS 地址，也属于同一档正式入口。DiceFrame 只保存最终分享地址，不绑定服务商。

官方说明：[Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)

### 2. 可选入口：Tailscale Funnel

用户只需要 Tailscale 账号，不需要购买域名。Funnel 提供 `*.ts.net` 公网地址、受信任的 HTTPS 证书和加密隧道，并允许没有安装 Tailscale 的玩家访问。

- 优点：无需端口映射；真实 IP 不直接暴露；支持普通长连接；DiceFrame 中心服务器不承担游戏流量。
- 限制：依赖 Tailscale 控制面、`*.ts.net` 和境外 Funnel 中继；Funnel 仍标记为 beta，并有带宽与端口限制。
- 中国大陆可用性：没有足够依据认定它在全国被统一封锁，但不同运营商和地区的 DNS、控制面或中继可达性可能波动，所以不把它设为国内用户的默认推荐。应先用手机流量实际打开一次再发给玩家。
- 产品落地：以后可新增独立的 `tailscale-funnel` 工具插件，检测 CLI、引导一次授权、启动/停止 Funnel；它仍是用户主动选择的入口，不覆盖既有穿透配置。

官方说明：[Tailscale Funnel](https://tailscale.com/kb/1223/funnel)

### 3. 有公网 IP：公网 IP 证书 + 本地 HTTPS

Let’s Encrypt 已正式支持 IPv4 和 IPv6 地址证书，因此有真实公网 IP、能映射 80/443 的用户可以不购买域名，直接用“公网 IP + 受信任证书 + 本地反向代理”提供 HTTPS。IP 地址证书有效期为 160 小时，必须由 ACME 客户端全自动续期；不能把手工续期作为普通用户方案。

DiceFrame 后续可提供本地 HTTPS 边缘进程，申请 IP 地址证书并反向代理到 `127.0.0.1:18000`；路由器只映射 80/443，应用端口继续只监听本机或内网。若无法映射 80/443，就继续使用 Cloudflare、SakuraFrp 或其他穿透入口。

不再规划由中心服务器分配 DiceFrame 官方动态子域名：即使中心不转发游戏流量，用户内容仍会出现在官方域名体系下，可能带来内容滥用和域名连带风险。公网 IP 证书只能由用户主动启用；检测到已经填写的外部 HTTPS 地址时，不自动申请证书、不改端口、不替换分享地址。官方说明：[Let’s Encrypt IP 地址证书](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability.html)

### 4. 已有域名：命名 Cloudflare Tunnel 或 Caddy

- Cloudflare Tunnel：用户的域名托管在 Cloudflare 时，使用命名隧道；无需开放入站端口。
- Caddy：公网 IP 和 80/443 可用时，用自动 HTTPS 反向代理 DiceFrame。

官方说明：[Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/)、[Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)

## 无论使用哪一种公网入口，都必须保留的应用安全

- 公网分享前强制设置管理密码；管理会话和玩家身份分离。
- 分享链接使用高熵房间标识，不把管理令牌放进 URL。
- 登录、房间密码、创建角色、上传和模型调用分别限速。
- 正确处理反向代理的可信来源；只有显式配置的代理才能提供真实客户端 IP。
- Cookie 使用 `Secure`、`HttpOnly`、`SameSite`；HTTPS 页面拒绝回退 HTTP。
- 设置页检测到非本机 HTTP 访问时显示明确警告，但不阻断局域网离线玩法。
- 中心服务器或隧道故障不得影响本地地址、存档、规则和插件。

## 实施顺序

1. 当前版本：Quick Tunnel 保留为短局入口，显示非阻断的地址变化、SSE 和稳定性提示；完整支持用户填写 SakuraFrp 等外部 HTTPS 地址。
2. 下一阶段：评估 `tailscale-funnel` 插件和公网 IP 证书边缘进程，两者都必须由用户主动启用。
3. 中心服务器不上线动态游戏子域名，也不接管现有穿透配置。
4. 有足够预算和明确容量后，再评估独立、可关闭的会合信令；不在低配中心服务器上自建全量中继。
