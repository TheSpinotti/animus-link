# Audio Routing Notes

Animus Link uses VB-CABLE on the server PC:

- Client mic audio is written to `CABLE Input`.
- PersonaPlex reads from `CABLE Output`.
- PersonaPlex output is captured from the default Windows output loopback and streamed back to the client.

The bridge uses SoundVolumeView to make `CABLE Output` the default capture device and the per-app capture device for `personaplex.exe`.
