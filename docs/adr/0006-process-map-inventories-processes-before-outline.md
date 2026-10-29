# Process maps inventory processes before outlining

`dia-transcript-to-process-map` used to infer the process to analyze and write a full outline immediately. In conversations that mention both a request-discovery workflow and the operational process the request targets, that inference could pick the wrong subject and blend two baselines.

The skill now presents a short numbered inventory of plausible processes in chat before any outline is written. Each entry has an ID, PascalCase label, actors, trigger, end point, evidence strength, likely role, and one-sentence rationale. The user confirms one, several, or all processes. The skill then produces the full outline, ROI baseline, and diagram separately for each confirmed process.

This keeps the inventory lightweight and avoids creating another artifact before the user has chosen what to analyze. It also preserves explicit confirmation as the gate between a plausible process and a full outline.
