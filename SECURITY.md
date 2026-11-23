# Security Policy

## Supported versions

This is a Home Assistant custom integration distributed via HACS. Security fixes
are made against the latest release only. Please update to the newest version
before reporting a suspected vulnerability.

## What this integration handles

The integration stores and uses sensitive data on your behalf:

- Your United Utilities app **customer ID** and **PIN**, and your **account number**.
- The short-lived **session token** returned by login (kept in memory only).

These are held in Home Assistant's config-entry storage. They are never logged,
and the diagnostics download is built from an allowlist that excludes them, along
with the meter serial number. A rejected PIN is never retried automatically:
United Utilities locks the account after three wrong PINs.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

Instead, report privately via GitHub's
[private vulnerability reporting](https://github.com/KRoperUK/united-utilities-hass/security/advisories/new)
("**Report a vulnerability**" on the repository's **Security** tab). This opens a
private advisory visible only to the maintainers.

Please include:

- A description of the issue and its impact.
- Steps to reproduce (or a proof of concept).
- The integration version and Home Assistant version.

You can expect an initial acknowledgement within a few days. Once a fix is
available it will be released and, where appropriate, a security advisory will be
published crediting the reporter (unless you prefer to remain anonymous).

## Scope

This policy covers the integration code in this repository. Vulnerabilities in
the [`united-utilities`](https://github.com/KRoperUK/united-utilities-py) client
library, Home Assistant core, or the United Utilities service should be reported
to their respective projects.
