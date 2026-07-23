# GitHub release checklist

## Before the first push

- Choose the final repository name and description.
- Review the copyright holder in `LICENSE`.
- Enable GitHub private vulnerability reporting.
- Enable branch protection and require the CI workflow.
- Disable force pushes and branch deletion on the default branch.
- Confirm that `.env`, databases, certificates and API credentials are absent.

## Before a tagged release

- Run `docker compose build` on a Linux Docker host.
- Test `install.sh` on every advertised distribution family.
- Test first login with a fresh volume.
- Test IPv4 and IPv6 upstreams.
- Validate Nginx reload behavior with both valid and invalid configurations.
- Test HTTP-01 against the ACME staging service.
- Test every advertised DNS provider against a non-production zone.
- Test certificate renewal and restoration from backup.
- Review dependencies and known vulnerabilities.
- Update the README and release notes with limitations.

## Suggested GitHub description

> Self-hosted dual-stack reverse proxy manager with multi-upstream IPv4/IPv6 routing, Nginx, ACME DNS plugins, healthchecks, streams and role-based administration.

Suggested topics: `nginx`, `reverse-proxy`, `docker`, `ipv6`, `acme`, `letsencrypt`, `self-hosted`, `sqlite`.
