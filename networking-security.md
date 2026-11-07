# Networking and security decisions

I orchestrated access around different needs: applications talking to one another,
selected public access, private administration and one separately routed workload.
The details below come from Compose files and dated operational records.

| Decision | Purpose and evidence | Tradeoff or limit |
| --- | --- | --- |
| Shared Docker network for integrations | The gateway, dashboard and selected frontends can resolve container services without hard-coded host addresses. | Shared membership allows lateral connectivity; this is not comprehensive segmentation. |
| Stack-local database network | One application frontend joins both its default network and the shared network; its PostgreSQL service stays on the default network with no published database port. | This describes that stack, not a claim that every database is isolated identically. |
| Public tunnel for selected services | Tunnel configuration supplies a public access path without requiring a direct inbound router rule for that path. | Published host ports still exist elsewhere; tunnel use alone does not prove access control or a closed host firewall. |
| Private remote administration | The repository records Tailscale access and SSH forwarding for administration. | Saved access details and identities are excluded here. Current reachability and policy were not rechecked. |
| Dedicated VPN gateway | One workload shares a gateway container's namespace. A remote gateway forwards a narrow application port; the management UI stays off that remote public forwarding path. | The gateway needs networking privileges, and the dependent container's lifecycle must be coordinated with it. |
| Secrets outside Git | Configuration references environment variables or mounted secret files; examples and documentation stay separate from live values. | The real configuration is still required for recovery and needs protection in backups and offline storage. |
| Container restrictions where supported | Examples include `no-new-privileges`, a read-only application filesystem, temporary writable storage and reduced capabilities. | Restrictions vary by service. They are not uniformly applied. |
| Reviewed images and update checks | Some images are pinned; dated maintenance records describe staged checks and preserved data. | Other images use floating tags. Local security overlays require deliberate maintenance and do not provide permanent fixes. |

## A networking investigation, not just a VPN installation

The **2026-10-07** connectivity record distinguished internal reachability from
external reachability. The application listened and could be reached from another
container, but the reported incoming external connection failed. Router/upstream
forwarding remained the likely obstacle; the record did not claim that carrier NAT
had been proven.

The subsequent design used a remote WireGuard gateway and a local VPN container,
with only the intended workload routed through it. The record credits me with
creating the remote instance, installing its SSH public key and opening cloud
ingress rules. It also records user-supplied connection-test evidence.
AI-assisted implementation and validation are documented separately from those
human inputs.

Dated checks recorded a tunnel handshake, the workload's expected egress route,
external listener reachability and a deliberate tunnel interruption. Requests
failed during the interruption rather than falling back to the home connection.
This is evidence of the tested behavior at that time, not a permanent no-leak
guarantee. Reboot behavior and throughput were not measured in that exercise.

## Security maintenance includes functional checks

The **2026-10-23** maintenance record describes backups before changes, an isolated
application trial using copied database state, targeted runtime/trust updates and
checks of data preservation and application responses. It also records my feedback
that an application version was incompatible with an external integration, leading
to a rollback. That rollback later exposed the authentication issue described in
[the troubleshooting example](troubleshooting.md).

The same record explicitly leaves legacy dependencies and some vulnerabilities
unresolved. This showcase does not repeat dated advisory claims as current advice
or describe the system as fully patched or penetration-tested.

Administration tools with a Docker socket remain a consequential trust boundary:
a read-only socket mount does not by itself restrict Docker API operations.
No firewall rules, credentials or deployable VPN configuration are exported.
The [illustrative network pattern](examples/network-pattern.compose.txt) shows
relationships using example labels only.
