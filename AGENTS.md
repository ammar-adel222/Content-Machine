# Project working conventions

- Keep implementation minimal, readable, and efficient. Add dependencies only when useful.
- Prioritize vertical 9:16 videos: design framing, units, labels, animation, and captions for phone screens first. Keep landscape as a supported secondary format.
- Keep research, writing, battle direction, and production independently runnable through saved contracts.
- Use LangGraph for the planned pipeline orchestration and cross-agent review loops; keep each agent independently callable.
- Unit-test every implemented behavior, including error paths; keep unit tests offline and independent of API keys.
- Run the tests after changes. Live API checks are separate from unit tests and should use bounded budgets.
- Never print, copy into reports, or commit API credentials. The existing external `.env` can be supplied at runtime.
- After completing each component, create or update a Markdown report under `docs/` explaining its purpose,
  architecture, inputs/outputs, usage, verification results, and limitations. Link it in the completion message.
