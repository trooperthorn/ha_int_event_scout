# Notifications

## Payload shape

`event_scout.send_alerts` builds one Companion app notification per active
deadline alert and sends it through the notify service configured in the
hub's options (`notify_service`):

```yaml
title: "Vendor deadline in 14 days: Old Settler's Music Festival"
message: "Deadline 2027-01-15 (estimated). Booth fee $150. Tap to open."
data:
  tag: event_scout_<uid>_deadline_14
  channel: Event Scout
  importance: high
  url: <vendor app url>
  actions:
    - action: URI
      title: Open application
      uri: <vendor app url>
    - action: EVENT_SCOUT_ADD_CAL
      title: Add to calendar
    - action: EVENT_SCOUT_DISMISS
      title: Dismiss
  action_data:
    uid: <uid>
    tag: <tag>
```

`tag` is `event_scout_<uid>_<alert_kind>_<days>`, so a repeat notification
for the same alert replaces the previous one instead of stacking.
`alert_kind` is one of `reconnaissance`, `deadline`, or `opens`.

## Actions

Event Scout listens for the core `mobile_app_notification_action` event in
`async_setup_entry` (`custom_components/event_scout/__init__.py`):

- **EVENT_SCOUT_DISMISS**: records `action_data.tag` as dismissed in the
  integration's store. The next coordinator refresh drops that specific
  alert from `ScoutData.deadlines`, so it will not be re-sent.
- **EVENT_SCOUT_ADD_CAL**: looks up `action_data.uid` in the current event
  list and calls `calendar.create_event` on the calendar entity named by the
  `target_calendar` option. If no target calendar is configured, the action
  is a no-op; set `target_calendar` in the hub's options first.

## Digests

`event_scout.get_digest` (response-only) and `event_scout.send_digest` both
take `period` (`daily` or `weekly`) and an optional `categories` filter, and
build the same structured payload: a list of events, a list of deadline
alerts, and a rendered markdown summary. `send_digest` sends the markdown
through the configured notify service; `get_digest` returns the structured
data for an automation or template to use directly.

## Blueprints

- `blueprints/automation/event_scout/daily_digest.yaml`: calls
  `event_scout.send_digest` with `period: daily` at a configured time.
- `blueprints/automation/event_scout/weekly_digest.yaml`: same, with
  `period: weekly`, gated to a chosen weekday.
- `blueprints/automation/event_scout/vendor_alert_actions.yaml`: triggers on
  the Vendor Deadlines calendar's `start` event and calls
  `event_scout.send_alerts`, so every alert on that calendar reaches the
  notify service without a custom trigger.
