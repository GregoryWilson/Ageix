from __future__ import annotations

from models.public_exposure import ReverseProxyConfiguration, ReverseProxyProvider, ReverseProxyTemplate, TLSConfiguration


class ReverseProxyTemplateService:
    """Generates deterministic LAN reverse proxy templates for validation and deployment handoff."""

    def generate(self, *, proxy: ReverseProxyConfiguration, tls: TLSConfiguration) -> ReverseProxyTemplate:
        if proxy.provider == ReverseProxyProvider.NGINX:
            return self.nginx(proxy=proxy, tls=tls)
        if proxy.provider == ReverseProxyProvider.TRAEFIK:
            return self.traefik(proxy=proxy, tls=tls)
        raise ValueError("reverse_proxy_provider_required")

    def nginx(self, *, proxy: ReverseProxyConfiguration, tls: TLSConfiguration) -> ReverseProxyTemplate:
        cert = tls.certificate_secret_ref or "/etc/ageix/tls/ageix-self-signed.crt"
        key = tls.private_key_secret_ref or "/etc/ageix/tls/ageix-self-signed.key"
        content = f"""server {{
    listen 443 ssl;
    server_name {tls.hostname};

    ssl_certificate {cert};
    ssl_certificate_key {key};

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;

    location / {{
        proxy_pass http://{proxy.upstream_host}:{proxy.upstream_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Request-ID $request_id;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
"""
        return ReverseProxyTemplate(
            provider=ReverseProxyProvider.NGINX,
            hostname=tls.hostname,
            upstream_host=proxy.upstream_host,
            upstream_port=proxy.upstream_port,
            tls_certificate_path=cert,
            tls_private_key_path=key,
            content=content,
        )

    def traefik(self, *, proxy: ReverseProxyConfiguration, tls: TLSConfiguration) -> ReverseProxyTemplate:
        cert = tls.certificate_secret_ref or "/etc/ageix/tls/ageix-self-signed.crt"
        key = tls.private_key_secret_ref or "/etc/ageix/tls/ageix-self-signed.key"
        content = f"""http:
  routers:
    ageix:
      rule: Host(`{tls.hostname}`)
      entryPoints:
        - websecure
      service: ageix
      tls: {{}}
  services:
    ageix:
      loadBalancer:
        servers:
          - url: http://{proxy.upstream_host}:{proxy.upstream_port}
tls:
  certificates:
    - certFile: {cert}
      keyFile: {key}
"""
        return ReverseProxyTemplate(
            provider=ReverseProxyProvider.TRAEFIK,
            hostname=tls.hostname,
            upstream_host=proxy.upstream_host,
            upstream_port=proxy.upstream_port,
            tls_certificate_path=cert,
            tls_private_key_path=key,
            content=content,
        )
