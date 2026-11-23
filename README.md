# United Utilities for Home Assistant

Unofficial Home Assistant integration for **United Utilities** (North West
England water). It reads your account balance, next payment and water meter
readings through the same API as the United Utilities mobile app, using the
[`united-utilities`](https://github.com/KRoperUK/united-utilities-py) library.

> Not affiliated with or endorsed by United Utilities. It uses a private app API
> that can change without notice. The United Utilities name and logo are
> trademarks of United Utilities and are used only to identify the service.

## What you get

One device per water account, polled every 6 hours:

| Sensor | Example | Notes |
| --- | --- | --- |
| Meter reading | `1975 m³` | Latest recorded read. `total_increasing`, so it works on the Energy dashboard's water panel. Attributes: `reading_date`, `read_by` (`customer` or `united_utilities`). |
| Last reading date | `2026-11-21` | |
| Next reading date | `2027-04-09` | When United Utilities next expects a reading. |
| Account balance | `£80.58` | Amount owed. |
| Next payment | `£51.78` | Next scheduled payment. |
| Next payment date | `2026-11-23` | |
| Water price | `£5.51/m³` | Fresh water + wastewater usage rate from your latest bill. Use it as the price entity for water in the Energy dashboard. Attributes: `water_per_m3`, `wastewater_per_m3`, `from_bill_dated`. |
| Standing charge | `£0.487/day` | Combined fixed charges from your latest bill. Attribute: `per_year`. |
| Last bill | `£76.51` | Latest itemised bill. Attributes: billing period, `usage_m3`, the usage and standing-charge split for fresh water and wastewater, and any discount. |

Meter readings only change when a read is recorded (by you in the app or by
United Utilities), typically every few months. This is billing data, not a live
smart-meter feed.

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

## Installation

### HACS (recommended)

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/KRoperUK/united-utilities-hass` as an **Integration**.
2. Install **United Utilities** and restart Home Assistant.

### Manual

Copy `custom_components/united_utilities` into your Home Assistant
`config/custom_components/` folder and restart.

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

> ⚠️ United Utilities locks the account for about an hour after **3 wrong
> attempts**. The integration never retries a rejected PIN: it stops polling
> and asks you to reauthenticate, and it won't try the old PIN again after a
> restart.

## Changing the PIN

If you change your PIN in the app, or register the app again, the next poll
fails and Home Assistant shows a **Reauthenticate** prompt. Enter your postcode
and current PIN there.

## Removal

1. **Settings → Devices & services → United Utilities → ⋮ → Delete**.
2. If installed through HACS, remove it from HACS too and restart.

## Troubleshooting

Enable debug logging for `custom_components.united_utilities` and
`united_utilities`, and include the integration's diagnostics download (it
contains no credentials, account number or meter serial) when opening an issue.

## License

MIT
