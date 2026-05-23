# Alexa Shopping List Sync

A Home Assistant custom integration that bidirectionally syncs the Amazon Alexa shopping list with HA's native `todo` entity.

Built on [`alexapy`](https://pypi.org/project/alexapy/). HACS-installable.

## Features

- Single HA `todo.alexa_shopping_list` entity kept in sync with Alexa every 15 min
- Bidirectional: add, complete, delete in either direction
- Persists cookies in the config entry — survives HA restarts
- HA Repair flow + phone notification when Amazon invalidates the session (one-click reauth)
- MFA and captcha handled in the config flow
- Region-aware (defaults to `amazon.de`; works against `amazon.com`, `amazon.co.uk`, etc.)

## Install

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/nachtschatt3n/alexa-shopping-list-sync`, category **Integration**
2. Install, restart Home Assistant
3. **Settings → Devices & Services → Add Integration → "Alexa Shopping List Sync"**
4. Enter your Amazon email, password, region (default `amazon.de`)

### MFA — what to expect

The config flow branches based on what Amazon asks for on each login attempt:

| Amazon asks for… | Step shown | What you enter |
|---|---|---|
| Authenticator-app code (TOTP) | `mfa_app` | Current 6-digit code from your app |
| SMS / email code | `mfa_sms` | Code Amazon sent you |
| "Pick a 2FA delivery method" | `claimspicker` | The option number Amazon lists |
| "Pick an authentication method" | `authselect` | The option number Amazon lists |
| Captcha | `captcha` | Open the image URL, type what you see |

If you use an **authenticator app**, paste your TOTP shared secret into the optional field on the first screen. The integration then computes codes itself on each login, so you'll never see the MFA step again — including after Amazon expires your cookies. (Get the secret from the QR-code setup screen when you enrolled the authenticator, or re-enroll if you don't have it.)

If you use **SMS / email** 2FA, you'll have to type a fresh code every time Amazon decides to re-challenge you. The Repair flow notification helps catch this fast.

## Usage

Once configured, the entity appears as `todo.alexa_shopping_list`. Drop it onto a dashboard:

```yaml
type: todo-list
entity: todo.alexa_shopping_list
```

It exposes the standard todo services — `todo.add_item`, `todo.update_item`, `todo.remove_completed_items`, etc. — and every change is pushed to Alexa immediately.

### Attributes

| Attribute   | Description |
|-------------|-------------|
| `last_sync` | ISO timestamp of the last successful poll. Use this in alerts to detect stalled sync. |

### Stalled-sync alert (recommended)

Drop [`examples/automations/last_sync_stale.yaml`](examples/automations/last_sync_stale.yaml) into your automations to get a persistent notification + phone push when `last_sync` falls behind by more than an hour. This is the soak-monitor: if Amazon invalidates your cookies, you'll know within an hour instead of finding out next time you check the dashboard.

## When Amazon kicks you out

Amazon periodically invalidates the unofficial-API sessions `alexapy` uses. When that happens:

1. The coordinator surfaces `ConfigEntryAuthFailed`
2. HA shows a **Repair** card and fires a `persistent_notification` (which your HA Companion app turns into a phone push)
3. Click the card → enter your password → done

No need to remove and re-add the integration.

## Local development

```sh
make venv          # one-time: create .venv with dev deps
make test          # run unit tests
make test-cov      # with coverage report
make lint          # ruff check + format check
make dev           # throwaway HA on :8123 with this integration bind-mounted
make logs          # tail just our domain
make down          # stop the dev HA
```

Use a **secondary Amazon account** for the dev container — iteration can spam your real shopping list.

### Project layout

```
custom_components/alexa_shopping_list_sync/
├── __init__.py        # setup_entry / unload_entry
├── alexa_client.py    # alexapy wrapper + householdlists CRUD
├── config_flow.py     # user / mfa / captcha / reauth
├── const.py
├── coordinator.py     # DataUpdateCoordinator, 15 min default
├── exceptions.py
├── manifest.json
├── repairs.py
├── strings.json
├── todo.py            # TodoListEntity (the HA entity)
└── translations/{en,de}.json
```

### Tests

40 unit tests cover the client (parsing, transport, 401/403/409), the coordinator (auth-failure → `ConfigEntryAuthFailed`, transient errors → `UpdateFailed`, last_sync stamping), the config flow (happy, MFA, captcha, invalid auth, unknown error, duplicate-account abort, reauth), the todo entity (uid stability, all CRUD paths, missing-uid no-ops), and the repair flow. Coverage: **91 %**.

Integration tests (gated by `@pytest.mark.integration`) hit the real Alexa API. Copy `.env.example` to `.env`, fill in `ALEXA_EMAIL` / `ALEXA_PASSWORD` (and `ALEXA_OTP_SECRET` for TOTP-based 2FA), then `make test-int`. The live test adds a `__hass_test__<uuid>`-tagged item, verifies it round-trips, then deletes it — your real shopping list isn't touched.

## Known risks

- Amazon may break the API. Pin to a known-good `alexapy` version. Track upstream breakage in [`alexa_media_player`](https://github.com/alandtse/alexa_media_player) issues — they usually catch it first.
- Concurrent edit window is up to one poll interval (default 15 min). Last-write-wins.
- One config entry per Amazon account (no multi-account support in v0.1).

## License

MIT
