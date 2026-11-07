# Optional recording: a three-minute system tour

1. **Purpose and ownership — 20 seconds.** Explain that this is a personal system
   you orchestrated using AI assistance: applications, supporting data services,
   access paths and recovery, with documented decisions and checks.
2. **Connections — 50 seconds.** Open the service map. Trace dashboard → application
   API → database, then the internal search/rendering dependency. Explain the
   public tunnel, private administration path and separately routed workload.
3. **One investigation — 35 seconds.** Explain why running containers did not
   prove the dashboard integration worked. Describe version-specific settings
   and verification through the original failing API route.
4. **Backup design — 40 seconds.** Show why the renderer's database and authored
   files belong to one backup generation. Explain logical dumps, deliberate
   exclusions and the difference between backup success and application recovery.
5. **Safe evidence — 25 seconds.** Run one of the local example test commands from
   `examples/README.md` in a temporary copy. Identify it as synthetic or stubbed,
   and distinguish it from the dated recovery evidence.
6. **AI contribution — 10 seconds.** Explain that you set direction and give
   feedback; AI helps investigate and implement; outputs need concrete checks.

Use only this export, a neutral working directory and a terminal prompt without
account or host names. Close unrelated tabs and disable notifications. Do not show
live dashboards, credentials, shell history, application records or private logs.
The diagram is sufficient to demonstrate connections without a live system tour.
Nothing in this plan requires contacting production or publishing a recording.
