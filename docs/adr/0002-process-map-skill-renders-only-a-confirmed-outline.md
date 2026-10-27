# The process-map skill renders only a confirmed outline

`dia-transcript-to-process-map` used to chain meeting-note creation and then draw the process map from a silent extraction of the transcript. The team wants a readable intermediate artifact between the transcript and the visual, so the skill now writes a process-outline Markdown file, revises it under user feedback, and renders the diagram only after the user explicitly confirms that outline.

The skill no longer produces meeting notes. Keeping note-taking out of the skill gives it one outcome per run and leaves that work to `dia-transcript-to-meeting-notes`; users who want both artifacts run the two skills separately. The diagram is built from the confirmed outline rather than the raw extraction, so the user's approval gates exactly what appears in the visual, and outline files carry assumptions and open questions the user can resolve before any diagram exists.
