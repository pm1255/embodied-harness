# Security and execution boundaries

This alpha is intended for simulation development. It is not validated for unattended physical robots. Hardware plugins need independent physical limits, watchdogs and emergency-stop integration.

- Model output is data, validated against registered tool schemas. It is never evaluated as Python or shell.
- Factories are trusted operator configuration, not model-controlled arguments.
- Plans are bounded; a failure prevents later steps from executing.
- The trace viewer is read-only, binds loopback, and has no execution endpoint.
- API keys stay in environment variables and are not written to traces. Camera images and task text are written to traces and sent to the configured GPT endpoint when using `run`.
- Cooperative cancellation cannot interrupt a blocking simulator/native call. A hardware or network driver must implement its own bounded calls and stop semantics.

Do not publish live credentials or sensitive recordings in issues. For a security bug, use GitHub private vulnerability reporting if enabled, or contact the repository owner privately before sharing exploit details.
