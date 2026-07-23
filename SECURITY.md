# Security Policy

## Supported versions

ProxyManagerDeck2 is currently an early preview. Only the latest commit on the default branch receives security fixes.

## Reporting a vulnerability

Please do not disclose vulnerabilities in a public issue. Use GitHub's private vulnerability reporting feature in the repository's **Security** section. Include affected versions, reproduction steps, impact and any suggested mitigation.

Never include real passwords, API tokens, private keys, certificates, database files or complete configuration exports in a report.

## Operational security

- Keep the dashboard bound to loopback or behind a trusted HTTPS reverse proxy.
- Set a unique administrator password of at least 16 characters.
- Generate a unique `PROXYDECK_SECRET_KEY` and back it up separately.
- Never commit `.env`, SQLite databases, certificates or generated Nginx files.
- Never commit or share `proxydeck-login.txt`; it contains the initial administrator password.
- Restrict DNS API tokens to the required zones and DNS-edit permissions.
- Back up Docker volumes and test restoration regularly.
- Review provider compatibility before enabling unattended certificate renewal.

This preview has not received an independent security audit.
