# Literature capability contract

A literature integration should ideally support:

1. Search by topic/author/title/DOI.
2. Retrieve bibliographic metadata.
3. Fetch or open the full text when legally accessible.
4. Preserve source identifiers.
5. Return enough information to cite exact source locations.
6. Optionally inspect citation context.

Preferred workflow:

```text
broad search
→ anchor sources
→ source verification
→ citation snowballing
→ claim matrix
```

A literature tool does not replace reading important sources.
