# Security policy

PresenceSync handles authentication tokens for your Microsoft and Slack accounts, so
security is taken seriously despite the small size of the project.

## Reporting a vulnerability

Please report vulnerabilities **privately**, not as a public issue.

Use GitHub's private reporting:
[**Report a vulnerability**](https://github.com/jermainewalkes/presencesync/security/advisories/new).
You will get an acknowledgement, and a fix or mitigation will be worked out with you
before any public disclosure.

Please do not open a public issue, pull request or discussion for a security problem until
it has been resolved.

## Supported versions

Fixes are made against the latest release and `main`. Please confirm an issue reproduces
on the current version before reporting.

## How PresenceSync protects your data

- **No hosted service.** PresenceSync talks directly to Microsoft Graph and the Slack API
  using your own app registrations. Your tokens never leave your machine and there is no
  server in the middle.
- **Secrets live in the OS keychain.** Slack OAuth tokens and the Slack client secret are
  stored in the macOS Keychain / Windows Credential Locker. The Microsoft token cache is
  encrypted at rest (Keychain on macOS, DPAPI on Windows). Nothing sensitive is written to
  the app's settings file.
- **Browser-based OAuth with CSRF protection.** Sign-in happens in your browser. The Slack
  flow captures the redirect on a loopback address (`127.0.0.1:53682`) and verifies the
  `state` parameter to guard against cross-site request forgery.
- **Least privilege.** The app requests only the scopes it needs: Microsoft
  `Presence.Read` and `Presence.ReadWrite`; Slack `users.profile:read`,
  `users.profile:write` and `users:read`.

## A note on org-config.json

The optional `org-config.json` seed file used for organisational rollout contains your
Slack **client secret**. It is listed in `.gitignore` so it cannot be committed by
accident, and it must only ever be distributed internally. Never commit it or attach it to
a public issue.
