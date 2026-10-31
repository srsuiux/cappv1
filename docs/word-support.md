# Word documents (.docx)

**Word documents (`.docx`)** are handled the same way for pictures and tables: the description goes into the picture's or table's alt-text field (the one Word's **Edit Alt Text** pane uses), and the AI sees the nearest heading and the paragraphs around the item as context. Tiny pictures are marked decorative. Embedded objects (such as a Visio drawing) get a description too. Charts, SmartArt, and headers, footers or footnotes are not handled in Word yet, and the accessibility check (`/audit`) reads decks only.

The rules this tool follows for Word files, including what is deliberately not supported, are in [scope.md](scope.md#word-documents-docx).
