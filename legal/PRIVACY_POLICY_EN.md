# DiceFrame Privacy Policy

Last updated: August 11, 2026  
Effective date: August 11, 2026  
Version: 1.0

This Policy explains data handling by the local DiceFrame application, the public plugin index, and DiceFrame Hub. DiceFrame is self-hosted software, so actual processing depends on the deployer’s providers, plugins, network exposure, and sharing choices.

**Optional usage statistics are off by default. A periodic heartbeat begins only after a user actively enables the switch and confirms. Refusal or withdrawal does not restrict local features. Plugin installation events, likes, and ratings are user-requested Hub interactions and are described separately.**

## 1. Who controls data

The person or organization controlling a DiceFrame device or server determines processing of local games, accounts, shared links, and server logs. For DiceFrame Hub at `api.diceframe.com`, the DiceFrame project maintainers are responsible for processing they actually operate. DiceFrame is an open-source collaboration and does not represent model providers, plugin authors, GitHub, Cloudflare, NapCat, or other platforms.

Privacy or deletion requests may be raised through [GitHub Issues](https://github.com/diceframe/diceframe/issues). Do not include installation tokens, API keys, access passwords, private chats, or full saves in a public Issue; maintainers can provide a safer follow-up method when verification is needed.

## 2. Data stored locally

DiceFrame commonly stores games, characters, lorebooks, rules, scenes, maps, conversation and processing logs; settings, plugin data, themes, caches, and update state; model and bot credentials; and Hub identity and preference data under the deployer-controlled `data` directory. Installation does not automatically upload this content to maintainers. Removing the application may not remove a host-mounted data directory.

## 3. Network processing

### Model providers

When AI generation is requested, DiceFrame sends the prompt and game context needed for that request to the provider configured by the user. Provider retention and use are governed by that provider and any proxy selected by the deployer.

### GitHub, updates, announcements, and repositories

Update checks, announcements, repository views, and plugin downloads request GitHub, mirrors, or author-configured hosts. Those servers can ordinarily observe IP address, time, User-Agent, and request path and process them under their own policies.

Browsing the public DiceFrame Hub catalog does not create an installation identity, although coarse network identifiers may be processed for security and abuse prevention.

### Installation events, likes, ratings, and reports

The first Hub action requiring identity creates a random installation ID and local token. Hub stores a one-way token digest and does not request a name, email, or DiceFrame save. Depending on the action, DiceFrame may send plugin ID and version, artifact hash, random event ID, install outcome, like state, 1–5 star rating, preset rating tags, report reason code, and a coarse network digest made with a periodically rotated key. These fields support deduplication, requested interactions, aggregate counts, and abuse prevention.

These actions are triggered by the user and are separate from the optional heartbeat switch. Clearing Hub identity requests deletion of the installation and linked interactions and removes the local token; retry is required if Hub is offline.

### Optional heartbeat

The optional heartbeat is off by default. After active opt-in, DiceFrame sends approximately every six hours: application version, coarse platform (Windows, macOS, Linux, or unknown), a Hub time bucket, and a pseudonymous installation ID. It does not include game text, characters, lorebooks, plugin lists, model settings, keys, passwords, private chats, or log content. It can be disabled under Settings → Advanced → DiceFrame Hub and privacy, stopping new local heartbeats immediately.

### Plugins, bots, tunnels, and public rooms

Independent plugins, chat bots, reverse proxies, tunnels, and publicly shared rooms may process additional data. Deployers must review permissions and third-party policies and inform affected players.

## 4. Purposes and retention

Data is processed only as needed to run local games and user-selected model calls; provide updates, announcements, catalog, installs, likes, ratings, and reports; prevent duplicates and abuse; and, after opt-in, understand version and platform distribution.

Local data remains until the deployer removes or replaces it. Current Hub defaults retain raw download and heartbeat events for no more than 30 days, clear coarse network digests from reports after 30 days, and remove installation identities after 24 months of inactivity. De-identified aggregate statistics may be retained longer. Likes, ratings, install state, and unresolved reports generally remain until the related action or identity is deleted or the service no longer needs them. Legal, security, backup, or dispute requirements may require limited extensions.

## 5. Sharing, international transfer, and choices

Maintainers do not sell DiceFrame game content or Hub identities. Data is shared only to provide a user-selected function, comply with law, or protect security and legal rights. GitHub, model providers, mirrors, and tunnel services may operate in other countries; the deployer is responsible for assessing the services it selects.

Users can keep heartbeat off or withdraw consent, clear Hub identity, remove local data, stop using a provider or plugin, and request access, correction, deletion, or restriction for Hub data. Verification may require the installation token still held locally. A new identity is created only if a later install, like, rating, or report requires one.

## 6. Security, children, and changes

DiceFrame restricts local token file permissions and requires HTTPS for non-local Hub connections. Hub stores token digests, rotates network-digest keys, rate-limits requests, minimizes fields, and exposes deletion. No local or internet system is perfectly secure; use strong passwords, HTTPS, current releases, trusted plugins, and backups.

DiceFrame is intended for users with full legal capacity. Minors should use it with guardian supervision. Deployers should not knowingly collect sensitive information from children under 14 through Hub or public rooms.

Material changes to purposes, data types, or sharing will update the version and trigger a new in-app confirmation. If translations conflict, the Simplified Chinese version controls.
