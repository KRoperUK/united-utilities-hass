# United Utilities for Home Assistant

Unofficial Home Assistant integration for **United Utilities**, the water and
wastewater company for North West England. It reads your account balance, next
payment, water meter readings and tariff prices through the same API as the
United Utilities mobile app, using the
[`united-utilities`](https://github.com/KRoperUK/united-utilities-py) library.

> Not affiliated with or endorsed by United Utilities. It uses a private app API
> that can change without notice. The United Utilities name and logo are
> trademarks of United Utilities and are used only to identify the service.

## Use cases

- Track water use on the **Energy dashboard**, priced with your real tariff.
- Get a reminder before a payment is taken, or when your balance changes.
- Know when the next meter reading is due, and notice when one is recorded.
- Keep an eye on your bills without opening the app.

## Supported accounts

There's no hardware: the integration connects to your United Utilities customer
account. It works with household accounts that are registered in the United
Utilities app and log in with an app PIN. One device is created per account.

| Account | Status |
| --- | --- |
| Metered household account, registered in the app | Supported and tested |
| Unmetered household account | Not tested. Balance and payments should work; the meter sensors stay unknown and the bill sensors may be unavailable. |
| Account not registered in the app | Not supported: register in the app first. |
| Business accounts | Not supported: the app API is for household customers. |

## What you get

One device per water account:

| Sensor | Example | Notes |
| --- | --- | --- |
| Meter reading | `1975 m³` | Latest recorded read. `total_increasing`, so it works on the Energy dashboard's water panel. Attributes: `reading_date`, `read_by` (`customer` or `united_utilities`). |
| Last reading date | `2026-11-21` | Diagnostic, disabled by default: the same date is the meter reading's `reading_date` attribute. |
| Next reading date | `2027-04-09` | When United Utilities next expects a reading. |
| Account balance | `£80.58` | Amount owed. |
| Next payment | `£51.78` | Next scheduled payment. |
| Next payment date | `2026-11-23` | |
| Water price | `£5.51/m³` | Fresh water + wastewater usage rate from your latest bill. Use it as the price entity for water in the Energy dashboard. Attributes: `water_per_m3`, `wastewater_per_m3`, `from_bill_dated`. |
| Standing charge | `£0.487/day` | Combined fixed charges from your latest bill. Attribute: `per_year`. |
| Last bill | `£76.51` | Latest itemised bill. Attributes: billing period, `usage_m3`, the usage and standing-charge split for fresh water and wastewater, and any discount. |

The integration is read-only: it has no actions, and it can't submit meter
readings or make payments.

### Prices from your bills

Tariffs aren't in the app's API, so the last three sensors come from your bill
PDFs. Each bill is downloaded once and read in memory; it's never stored,
because it includes your name, address and bank details. Payment-plan update
"bills" have no charges, so the integration looks back up to three bills for the
latest itemised one. A bill spanning 1 April uses the newer tariff.

Every bill is cross-checked: the line items must add up to the total, each
charge must equal quantity × rate, and the volume must match your meter
readings. If a bill doesn't add up, usually because United Utilities changed the
layout, the three bill sensors go **unavailable** rather than showing figures
that might be wrong. A **repair** under Settings → System → Repairs then says
what didn't match. The other sensors keep working.

## How data is updated

The integration polls United Utilities every **6 hours**. Each poll reads the
account details, meter readings, payment information and the bill list, reusing
the app login between polls. When the login has expired it logs in again once;
it never retries a rejected PIN.

Each bill PDF is downloaded once and then kept in memory until Home Assistant
restarts, so a poll normally downloads nothing new. A failed bill download keeps
the previous bill's prices and doesn't fail the poll.

To refresh sooner, run the `homeassistant.update_entity` action on any of the
integration's sensors. The data itself only changes when United Utilities
records something: a meter read (typically every few months), a bill or a
payment. This is billing data, not a live smart-meter feed.

If United Utilities can't be reached, the sensors go unavailable, Home Assistant
logs the outage once, and they come back on the next successful poll.

## Installation

### HACS (recommended)

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/KRoperUK/united-utilities-hass` as an **Integration**.
2. Install **United Utilities** and restart Home Assistant.

### Manual

Copy `custom_components/united_utilities` into your Home Assistant
`config/custom_components/` folder and restart.

Requires Home Assistant 2026.8 or newer.

## Setup

Your account must already be registered in the **United Utilities app**.

**Settings → Devices & services → Add integration → United Utilities**, then
enter:

- **Account number**: from your bill.
- **Postcode**: of the property on the account. It's used once to find your
  app customer ID (the same lookup the app's "register again" screen does) and
  is not stored.
- **App PIN**: the PIN you log in to the app with. This is not your website
  password.

The integration checks the details by logging in once before it creates the
entry. It has no options to configure afterwards.

> ⚠️ United Utilities locks the account for about an hour after **3 wrong
> attempts**. The integration never retries a rejected PIN: it stops polling
> and asks you to reauthenticate, and it won't try the old PIN again after a
> restart.

## Changing the PIN

- **Before it fails:** Settings → Devices & services → United Utilities → ⋮ →
  **Reconfigure**, then enter your postcode and new PIN.
- **After it fails:** if you change your PIN in the app, or register the app
  again, the next poll fails and Home Assistant shows a **Reauthenticate**
  prompt. Enter your postcode and current PIN there.

Both re-look up your customer ID, so they also fix things after the app has been
registered again. To use a different account number, add the integration again
rather than reconfiguring.

## Automation examples

Remind yourself the day before a payment is taken:

```yaml
alias: Water payment reminder
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: template
    value_template: >
      {{ states('sensor.united_utilities_next_payment_date')
         == ((now() + timedelta(days=1)).date() | string) }}
actions:
  - action: notify.notify
    data:
      message: >
        United Utilities will take
        £{{ states('sensor.united_utilities_next_payment') }} tomorrow.
mode: single
```

Get told when a new meter reading is recorded:

```yaml
alias: New water meter reading
triggers:
  - trigger: state
    entity_id: sensor.united_utilities_meter_reading
    not_from: [unknown, unavailable]
    not_to: [unknown, unavailable]
actions:
  - action: notify.notify
    data:
      message: >
        New water meter reading:
        {{ trigger.to_state.state }} m³
        (up {{ (trigger.to_state.state | float(0)
               - trigger.from_state.state | float(0)) | round(1) }} m³,
        read by {{ state_attr('sensor.united_utilities_meter_reading', 'read_by') }}).
mode: single
```

### Energy dashboard

Settings → Dashboards → Energy → **Water consumption** → add
`sensor.united_utilities_meter_reading`, and choose **Use an entity with current
price** with `sensor.united_utilities_water_price`. Because readings arrive every
few months, each reading's usage shows up as one block on the day it was
recorded.

## Known limitations

- **Not real time.** Readings change only when you or United Utilities record
  one, so daily or hourly water use isn't available.
- **App registration and PIN required.** Website-only accounts can't be used.
- **Lockout.** Three wrong PINs lock the account for about an hour, including in
  the app. The integration never retries a PIN, but a wrong PIN entered during
  setup, reauthentication or reconfiguration still counts.
- **Prices need an itemised bill.** The bill sensors stay unavailable until one
  is found within the latest three bills, and a tariff change shows up only
  once a bill on the new tariff arrives.
- **Bill layout changes.** Prices come from the bill PDF. If United Utilities
  changes the layout, the bill sensors go unavailable and a repair explains why
  until the integration is updated.
- **Unofficial API.** United Utilities can change it at any time, which may
  break the integration until it's updated.
- **One account per entry.** Add the integration again for each account.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| "No account matches that account number and postcode" | Check both against a recent bill. Spaces before or after the postcode don't matter. |
| "This account isn't registered in the United Utilities app yet" | Register in the app, then add the integration. |
| "The PIN was rejected" or a **Reauthenticate** prompt | Use the app PIN, not your website password. Check it by logging in to the app first, as each wrong PIN counts toward the lockout. |
| "United Utilities has locked this account" | Wait about an hour, then try once with the correct PIN. |
| Sensors are unavailable | United Utilities couldn't be reached. They come back on the next successful poll; check the logs for the error. |
| Water price, Standing charge and Last bill are unavailable, with a repair | Your latest bill didn't pass the consistency checks. Report the problems the repair lists (never the bill itself). |
| Water price, Standing charge and Last bill are unavailable, without a repair | No itemised bill was found in your latest three bills yet, or bills couldn't be downloaded. Wait for the next bill or poll. |
| The meter reading hasn't changed for months | Expected: it changes only when a reading is recorded. Submit one in the app to update it. |

If that doesn't help, enable debug logging for `custom_components.united_utilities`
and `united_utilities`, and include the integration's diagnostics download (it
contains no credentials, account number or meter serial) when
[opening an issue](https://github.com/KRoperUK/united-utilities-hass/issues).
Don't attach bills or unredacted logs.

## Removal

1. **Settings → Devices & services → United Utilities → ⋮ → Delete**.
2. If installed through HACS, remove it from HACS too and restart.

Deleting the entry removes the stored PIN, customer ID and account number from
Home Assistant. It doesn't change anything on your United Utilities account.

## License

MIT
