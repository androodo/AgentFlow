# AgentFlow video recording

The recording uses the actual local web application, its FastAPI worker, PostgreSQL, and the separate MCP service. It uses the seeded Northstar Shop records in rule-based mode. Optional providers, the LLM judge, and external tracing are disabled.

## Record on Windows

With Docker Desktop running Linux containers and Node.js available, run this command from the repository root.

```powershell
.\scripts\record_demo.ps1
```

The script prepares the Playwright Chromium browser and starts an isolated Compose project on unused loopback ports. It uses the example environment rather than the project's credential settings. It shuts down and removes only the temporary recording stack and its data volume when capture ends. No external account is required.

By default the outputs are written to `demo/video/`. Use `-OutputDirectory` to select another folder. Use `-WorkDirectory` to choose where to keep the raw capture, timing JSON, and verified Markdown export. By default, those intermediate files go under `web/test-results/`. Both default locations are excluded from Git.

With FFmpeg and ffprobe on PATH, the script adds the captions below the browser recording and encodes an H.264 MP4 with 1920 × 1080 resolution, 30 fps, and no audio track. It decodes the complete result and checks its stream metadata. If either executable is unavailable, it saves the Chromium WebM and separate SRT captions instead.

## Shot list

The video details file contains timestamps from the actual capture. The [optional narration](VIDEO_SCRIPT.md) follows the same sequence.

| Shot | Action and verification |
| --- | --- |
| Opening | Title card names LangGraph, MCP, synthetic data, and rule-based execution. |
| Investigation | Click **Try demo: Checkout Conversion Drop** and wait for the draft and conversion comparison. |
| Workflow | Open **Execution details**, inspect the three specialist branches, then open the metrics request and evidence provenance. |
| Evidence | Follow the checkout citation to a mobile traffic row. Open a release source record and return to the findings to see the uncertainty. |
| Review | Confirm export is gated. Open the saved checkpoint, enter a reviewer note, and approve through the UI. |
| Export | Open the approved report and download Markdown. Verify the file contains evidence and the approval. |
| Evaluation | Run the paired benchmark and wait for all 30 case runs. Show the measured results without an LLM judge. |
| Closing | Recap orchestration, tool access, auditing, review, and repeatable evaluation. |

When sharing, use the captioned MP4 and the real thumbnail from the captured app. Keep the generated video out of the Git repository.

## Recording verification

The Windows capture ran with Docker Engine 29.6.2, Compose 5.3.1, PostgreSQL 16.16, LangGraph 1.2.22, and MCP 1.30.0. Playwright 1.65.1 recorded Chromium 159.0.8154.6. FFmpeg 8.1.1 encoded the result.

The live browser flow completed the evidence audit, review, Markdown export, and both benchmark strategies. The capture checked the investigation events for the audit and for the absence of model execution. The MP4 ran 2:43 at 1920 × 1080 and 30 fps. FFmpeg decoded the complete stream, and Chromium played seeked frames at 2, 66, and 146 seconds. Frames from each chapter were inspected for legibility and caption placement. The isolated recording stack was removed after capture.
