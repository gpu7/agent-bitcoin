# Public HTTPS L402 endpoint

The lab paid route is public at `https://agent-bitcoin.net/paid/hello`.

| Item | Value |
|---|---|
| Hostname | `agent-bitcoin.net` |
| Public URL | `https://agent-bitcoin.net/paid/hello` |
| DNS | Route 53 `agent-bitcoin.net` points at Elastic IP `3.90.159.146` |
| TLS | Caddy on the EC2 instance listens on **443** and reverse-proxies to `127.0.0.1:8081` |
| Aperture | Unchanged. Still plain HTTP on **8081** |
| Security group | **443** is open. **8081** stays restricted to the operator |
| 402index | https://402index.io/service/65d85944-d292-4cf5-8196-4eb30a9f51e0 |
| Domain verification | `/.well-known/402index-verify.txt`, served by Caddy |

Callers outside the box use the hostname on port 443. Health checks and operator scripts on the instance keep using `http://127.0.0.1:8081`. Lightning peering stays on `3.90.159.146:9735`. That address is not this HTTP endpoint.

Operator ports: [aws-operator.md](./aws-operator.md). Aperture runbook: [l402-aperture.md](./l402-aperture.md).

## Caddy

`/etc/caddy/Caddyfile` on the instance:

```
agent-bitcoin.net {
    handle /.well-known/402index-verify.txt {
        root * /var/www/agent-bitcoin
        file_server
    }
    reverse_proxy 127.0.0.1:8081
}
```

There is no custom `tls` directive. Caddy obtains and renews the Let's Encrypt certificate automatically.

The 402index verification file is on disk at `/var/www/agent-bitcoin/.well-known/402index-verify.txt`. Caddy serves it at `https://agent-bitcoin.net/.well-known/402index-verify.txt`. The token is not stored in this repo.

Every other path, including `/health` and `/paid/…`, is reverse-proxied to Aperture.
