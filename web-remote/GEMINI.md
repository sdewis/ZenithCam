# ZenithCam Web-Remote Guidelines

## Service Management
The remote server is installed as a systemd service: `zenith-web-remote.service`.

**MANDATE:** After making any changes to the source code (e.g., `server.js` or `public/index.html`), you **MUST** restart the service to apply the changes:
```bash
sudo systemctl restart zenith-web-remote.service
```

## Maintenance
- View logs: `journalctl -u zenith-web-remote.service -f`
- Check status: `systemctl status zenith-web-remote.service`
