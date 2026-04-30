# Audio Routing Notes

Animus Link uses dedicated Windows-routable virtual audio devices on the server PC:

- Client mic audio is written to `CABLE Input`.
- PersonaPlex reads from `CABLE Output`.
- PersonaPlex output is routed to `Speakers (Virtual Audio Driver by MTT)`.
- The bridge captures that render stream from `Speakers (Virtual Audio Driver by MTT) [Loopback]` and streams it back to the client.

The bridge uses SoundVolumeView to make `CABLE Output` the default capture device and the per-app capture device for `personaplex.exe`.
It also sets the MTT virtual speaker as the per-app render device for all three Windows audio roles so PersonaPlex does not fall back to the Windows default output.
