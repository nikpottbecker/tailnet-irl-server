# Security policy

## Supported versions

Security fixes are applied to the latest release on the `main` branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository. Do not open a public issue containing credentials, private Tailnet addresses, stream URLs or exploit details.

## Deployment boundary

Tailnet IRL Server is designed for trusted devices inside one Tailscale Tailnet. Do not expose its dashboard or media ports through router forwarding, public tunnels or public firewall rules. Connection URLs shown in the dashboard contain credentials and must be treated as secrets.
