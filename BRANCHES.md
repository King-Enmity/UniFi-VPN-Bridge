# Release channels

UniFi VPN Bridge uses three long-lived branches.

| Branch | Release channel | Requirements |
|---|---|---|
| `main` | Stable / safe to use | Only functionality tested to a release-quality standard. At present this means **read-only diagnostics only**. No VPN forwarding or leak protection is offered. |
| `coming-soon` | Preview / beta | Features that work in limited testing but lack complete real-hardware and failure-mode validation. **Not safe to rely on for privacy.** |
| `development` | Active development | Experiments, new features, unfinished work, and breaking changes. **Never deploy on a production gateway.** |

## Development flow

1. Build and unit-test new work in `development`.
2. Open a pull request from `development` into `coming-soon` after basic checks pass.
3. Validate on supported UniFi devices, including Teleport, WireGuard Server, OpenVPN Server, outbound VPNs, DNS, IPv6, disconnects, reboots and firewall reloads.
4. Only merge `coming-soon` into `main` when the applicable release checklist is complete.
5. Use review, automated tests and branch rules to protect `main`.

## Stability is feature-scoped

The v0.2 discovery CLI is designed to only *read* information: it never changes firewall rules or starts routing. This does **not** mean the planned VPN bridge is ready. It is not.

Do not label the project "production-ready" or claim "no leaks" until packet-level tests cover failure states on real supported hardware. No workflow should auto-deploy to a UniFi gateway.

## Recommended GitHub rules

Configure in GitHub Settings → Rules → Rulesets (or Branch protection):
- `main`: require pull request reviews and passing `test` status; block force pushes and deletions.
- `coming-soon`: require passing tests and pull requests; block force pushes.
- `development`: require passing tests for merges, permit work-in-progress commits.
- Consider signed commits and CODEOWNERS after contributors join.

These rules are **recommendations** until configured in GitHub; creating the branches alone does not enforce them.
