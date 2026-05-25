# Cherry-picking the upstream To-do PRs onto a live HA

Two open PRs together give you native Alexa shopping-list → HA `todo` sync:

- HA core: https://github.com/home-assistant/core/pull/171136
- `aioamazondevices` library: https://github.com/chemelli74/aioamazondevices/pull/839

Both depend on each other. Until they merge, you can run them locally on top of your existing HA's `alexa_devices` config entry.

## Tested on

- HA `2026.5.1`, Python 3.14
- `aioamazondevices` PR head: `lonlazer/add_todo_lists` (commit `63f3020`)
- HA core PR head: `lonlazer/alexa_devices_todo_lists` (commit `c4584f9`)
- HA running as a Kubernetes pod with `/config` on a PVC

## Steps

### 1. Pin the library to the PR branch via the manifest

Pull the alexa_devices integration files from PR #171136 head into a local dir:

```sh
mkdir -p /tmp/alexa_devices_pr && cd /tmp/alexa_devices_pr
for url in $(gh api "repos/lonlazer/core/contents/homeassistant/components/alexa_devices?ref=c4584f9d7a10d4c3556160e90b71031642faad61" --jq '.[].download_url'); do
  curl -sS -o "$(basename "$url")" "$url"
done
```

Modify `manifest.json` to require the PR branch of `aioamazondevices` and add the mandatory `version` key for custom_components:

```diff
-  "requirements": ["aioamazondevices==13.7.0"]
+  "requirements": ["aioamazondevices @ git+https://github.com/lonlazer/aioamazondevices.git@lonlazer/add_todo_lists"],
+  "version": "0.0.1-pr171136"
```

### 2. Patch `todo.py` to re-sync after each mutation

PR #171136 wires up `on_todo_event` subscribers but never starts the HTTP/2 push client that emits those events. Until that lands, every create/update/delete must explicitly refresh:

```python
# in async_create_todo_item, after the API call:
await self._coordinator.sync_todo_list_items()
self._coordinator.async_update_listeners()

# in async_delete_todo_items, after the loop:
await self._coordinator.sync_todo_list_items()
self._coordinator.async_update_listeners()

# in async_update_todo_item, at the end:
if has_completed_changed or has_summary_changed:
    await self._coordinator.sync_todo_list_items()
    self._coordinator.async_update_listeners()
```

### 3. Push to the HA pod

```sh
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant -o jsonpath='{.items[0].metadata.name}')

# Stage the integration override
kubectl exec -n home-automation $POD -- mkdir -p /config/custom_components/alexa_devices/
kubectl cp /tmp/alexa_devices_pr/. home-automation/$POD:/config/custom_components/alexa_devices/

# Pre-install the library so the first import has it before HA's pip-install completes
kubectl exec -n home-automation $POD -- pip install --force-reinstall --no-deps \
  "git+https://github.com/lonlazer/aioamazondevices.git@lonlazer/add_todo_lists"

# Restart the pod
kubectl delete pod -n home-automation $POD
```

### 4. Verify

After HA comes back up, two new entities should exist on the same config entry that already drives your Echo devices:

- `todo.<your_account_email>` — shopping list
- `todo.<your_account_email>_2` — to-do list

Adding/completing/deleting items via the HA UI or `todo.add_item` service should propagate to the Alexa app within a couple of seconds.

## Rollback

```sh
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n home-automation $POD -- rm -rf /config/custom_components/alexa_devices
kubectl delete pod -n home-automation $POD
```

HA falls back to the bundled `alexa_devices` (device control still works; no `todo` entities).
