# WhatsApp Web channel

The current channel uses Playwright and a persistent browser profile. The profile is runtime-private and **must never be committed**. Browser automation is isolated behind `src/cancheria/channels/whatsapp_web/` facades while the mature implementation remains compatibility-backed by the legacy core.

WhatsApp Web is an external UI and can change without notice; maintain selector-health and recovery tests separately from domain tests.
