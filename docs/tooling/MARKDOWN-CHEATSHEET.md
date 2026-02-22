# Markdown Cheatsheet

> Quick reference for writing documentation, agent configs, and structured
> content. Includes the history of Markdown, why it became the AI agent
> configuration format, and every syntax element you need.

---

## The Story of Markdown

### Who Created It and Why

**John Gruber** (Daring Fireball blog) and **Aaron Swartz** published Markdown
in December 2004 — a plain-text formatting syntax plus a Perl script to convert
it to HTML.

The motivation was frustration. Writing HTML for blog posts was painful:

```html
<p>This is <em>annoying</em> to write and <strong>impossible</strong> to read
in source form. Every <a href="https://example.com">link</a> becomes a wall
of angle brackets.</p>
```

Gruber's design goal was radical simplicity:

> "The overriding design goal for Markdown's formatting syntax is to make it as
> readable as possible. The idea is that a Markdown-formatted document should be
> publishable as-is, as plain text, without looking like it's been marked up
> with tags or formatting instructions."
>
> — John Gruber, Markdown philosophy

The name is a play on "markup" — it's the opposite direction. Where HTML *marks
up* text with complex tags, Markdown *marks it down* to the simplest possible
formatting.

### The Key Insight

Plain text IS the document. Rendering is optional, not required.

Unlike HTML where `<p>tags</p>` interrupt reading flow, a Markdown file reads
naturally even in a terminal with `cat`. The asterisks in `**bold**` look like
emphasis. The dashes in `- list item` look like bullet points. The `#` in
`# Heading` looks like a section marker.

This "readable without rendering" property is what makes Markdown unique among
structured text formats.

### How It Spread

| Year | Event |
|------|-------|
| 2004 | Gruber publishes original spec + Perl script |
| 2008 | GitHub launches, adopts Markdown for READMEs, issues, and PRs |
| 2009 | Stack Overflow uses Markdown for all user content |
| 2012 | GitHub Flavored Markdown (GFM) adds tables, task lists, fenced code blocks |
| 2014 | CommonMark project standardizes the ambiguous parts of Gruber's spec |
| 2017 | MDX combines Markdown with JSX for component-based documentation |
| 2020+ | Every major dev tool adopts Markdown: Notion, Obsidian, Slack, Discord |
| 2024+ | AI coding tools use Markdown for agent configuration files |

Today, Markdown is the lingua franca of developer documentation. If you write
software, you write Markdown.

### Why Markdown Became the AI Agent Format

Why `CLAUDE.md`, not `claude.json`? Why `.cursorrules` in Markdown, not YAML?

**1. Training data prevalence**

LLMs are trained on billions of Markdown files from GitHub, documentation sites,
wikis, and forums. Markdown is the format they "think" in. When an LLM reads
`## Rules`, it understands that as a section header because it has seen that
pattern millions of times.

**2. Human + machine readable**

Unlike JSON/YAML, humans can read and write Markdown without mentally parsing
brackets or indentation rules. Unlike plain text, it has structure that agents
can parse — headers create sections, bullets create lists, code blocks create
examples.

**3. Git-friendly**

Text diffs show exactly what changed. No merge conflicts from trailing commas
or bracket alignment. A one-line change in a Markdown file shows as a one-line
diff.

**4. Zero-tooling entry**

Any text editor works. No schema validation, no special IDE support needed
(though it helps). You can write a complete agent configuration in Notepad.

**5. Flexible structure**

Headers create a hierarchy. Bullets create lists. Code blocks create examples.
Tables create structured data. All without a rigid schema that breaks when you
need one more field.

### Markdown Across AI Tools

| Tool | Config File | Format | Purpose |
|------|------------|--------|---------|
| Claude Code | `CLAUDE.md` | Markdown | Project instructions, conventions, behavioral guidelines |
| Claude Code | `.claude/agents/*.md` | Markdown | Custom agent definitions |
| Cursor | `.cursorrules` | Markdown | Editor AI behavior rules |
| GitHub Copilot | `.github/copilot-instructions.md` | Markdown | Copilot context and instructions |
| Windsurf | `.windsurfrules` | Markdown | AI coding assistant rules |
| Aider | `.aider.conf.yml` | YAML | Exception — YAML config, but prompts are Markdown |

### Why Markdown Won Over Alternatives

| Format | Human Readable | Machine Parseable | Git Diffs | AI Fluency | Structured |
|--------|---------------|-------------------|-----------|------------|------------|
| **Markdown** | Excellent | Good | Excellent | Excellent | Medium |
| JSON | Poor | Excellent | Poor | Good | Excellent |
| YAML | Good | Good | Good | Good | Good |
| TOML | Good | Good | Good | Fair | Good |
| reStructuredText | Fair | Good | Good | Fair | Good |
| AsciiDoc | Fair | Good | Good | Fair | Excellent |
| Plain text | Excellent | Poor | Excellent | Good | None |

Markdown wins because it optimizes for the intersection of ALL columns — no
other format scores above "Good" in every category.

---

## Quick Start (5 Rules)

Before writing any Markdown, know these 5 rules. They cover 90% of formatting
errors.

### Rule 1: Headers create hierarchy (`#` through `######`)

```markdown
# Document Title (H1)
## Major Section (H2)
### Subsection (H3)
#### Detail (H4)
```

One `#` per level. Always put a space after the `#`. One H1 per document.

### Rule 2: Blank lines separate blocks

```markdown
This is paragraph one.

This is paragraph two.

- This is a list that needs a blank line before it
```

Without a blank line between elements, Markdown may merge them into one block
or fail to recognize a list. When in doubt, add a blank line.

### Rule 3: Indentation matters in lists (2 or 4 spaces)

```markdown
- Top-level item
  - Nested item (2 spaces)
    - Deeper item (4 spaces from top)
```

Inconsistent indentation breaks nested lists. Pick 2 or 4 spaces and stick
with it.

### Rule 4: Backticks for code (`` ` `` inline, ` ``` ` blocks)

````markdown
Use `variable_name` in a sentence for inline code.

```python
def hello():
    print("Hello, world!")
```
````

Single backticks for inline, triple backticks for blocks. Add the language
name after opening backticks for syntax highlighting.

### Rule 5: One blank line before and after code blocks and lists

````markdown
Some paragraph text.

```python
code_here()
```

More paragraph text.

- List item one
- List item two

Back to paragraph text.
````

Forgetting the blank line before a code block or list is the most common
Markdown rendering bug.

---

## 1. Headers

**When to use:** Document structure, navigation, table of contents generation.

### ATX-style headers (standard)

```markdown
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
##### Heading 5
###### Heading 6
```

### Setext-style headers (alternative for H1 and H2 only)

```markdown
Heading 1
=========

Heading 2
---------
```

Setext style only supports two levels and is rarely used in modern Markdown.
Prefer ATX-style (`#`) for consistency.

### Key rules

- Always put a space after `#` — `#Heading` may not render correctly
- One H1 (`#`) per document — it's the document title
- Don't skip levels — go from `##` to `###`, not from `##` to `####`
- Headers generate anchor links automatically: `## My Section` →
  `#my-section`

---

## 2. Text Formatting

**When to use:** Emphasis, highlighting code, marking revisions.

### Inline formatting

```markdown
**bold text**
*italic text*
***bold and italic***
~~strikethrough~~
`inline code`
```

Result:

- **bold text**
- *italic text*
- ***bold and italic***
- ~~strikethrough~~
- `inline code`

### Alternative syntax

```markdown
__bold with underscores__
_italic with underscores_
```

Both `*` and `_` work for bold and italic. Convention: use `*` (asterisks)
because underscores can conflict with `snake_case` variable names in technical
writing.

### Subscript and superscript (HTML)

```markdown
H<sub>2</sub>O is water.

E = mc<sup>2</sup>
```

Native Markdown has no subscript/superscript syntax. Use HTML tags — they work
in GitHub and most renderers.

### Keyboard keys (HTML)

```markdown
Press <kbd>Ctrl</kbd> + <kbd>C</kbd> to copy.
```

Renders with a keyboard key visual style on GitHub.

### Highlight (GFM — limited support)

```markdown
==highlighted text==
```

Not widely supported. Works in some renderers (Obsidian, some GitHub
contexts), but not universally.

---

## 3. Lists

**When to use:** Steps, requirements, options, structured information.

### Unordered lists

```markdown
- Item one
- Item two
- Item three
```

All three markers work: `-`, `*`, `+`. Convention: use `-` consistently.

### Ordered lists

```markdown
1. First item
2. Second item
3. Third item
```

Lazy numbering — you can use `1.` for every item and Markdown auto-numbers:

```markdown
1. First item
1. Second item
1. Third item
```

This renders as 1, 2, 3. Useful for avoiding renumbering when you insert items.

### Nested lists

```markdown
- Top level
  - Second level (2 spaces)
    - Third level (4 spaces)
  - Back to second level
- Back to top level
```

```markdown
1. First
   1. Nested ordered (3 spaces to align with text above)
   2. Another nested item
2. Second
```

### Task lists (GFM)

```markdown
- [x] Completed task
- [ ] Incomplete task
- [ ] Another todo
```

Renders as checkboxes on GitHub. Interactive in issues and PRs.

### Definition lists (limited support)

```markdown
Term
: Definition of the term

Another term
: Its definition
```

Supported by PHP Markdown Extra, Pandoc, and some static site generators.
Not supported by GitHub.

### Multi-line list items

```markdown
- First item with a long description that continues
  on the next line (indent continuation by 2 spaces).

- Second item.

  A full paragraph inside a list item (blank line +
  indent by 2 spaces).

- Third item.
```

### Key rules

- Consistent marker: pick `-` or `*`, don't mix
- Blank line between list items creates "loose" list (paragraphs)
- No blank line creates "tight" list (compact)
- Nested items: 2 spaces for unordered, 3 spaces for ordered (to align
  with text after `1. `)

---

## 4. Links and Images

**When to use:** Navigation, references, visual content.

### Inline links

```markdown
[Link text](https://example.com)
[Link with title](https://example.com "Hover title")
```

### Reference links

```markdown
[Link text][ref-id]

[ref-id]: https://example.com "Optional title"
```

Reference links keep paragraphs clean when you have many URLs. Put reference
definitions at the bottom of the file.

### Autolinks

```markdown
<https://example.com>
<user@example.com>
```

GFM also auto-links bare URLs: `https://example.com` (without angle brackets).

### Images

```markdown
![Alt text](image-url.png)
![Alt text](image-url.png "Optional title")
```

### Linked images (image that is also a link)

```markdown
[![Alt text](image-url.png)](https://example.com)
```

### Relative paths

```markdown
[See the architecture doc](../ARCHITECTURE.md)
![Diagram](./images/diagram.png)
```

Use relative paths in documentation repos so links work regardless of where
the repo is cloned.

### Key rules

- Always include alt text for images (accessibility)
- Prefer reference links when a paragraph has 3+ links
- Use relative paths within the same repo
- URL encoding: spaces in paths become `%20`

---

## 5. Code

**When to use:** Code examples, commands, configuration, file paths.

### Inline code

```markdown
Run `npm install` to install dependencies.
The `src/main.py` file is the entry point.
```

### Fenced code blocks

````markdown
```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```
````

The language identifier after the opening backticks enables syntax
highlighting.

### Common language identifiers

| Identifier | Language |
|-----------|---------|
| `python` or `py` | Python |
| `javascript` or `js` | JavaScript |
| `typescript` or `ts` | TypeScript |
| `bash` or `sh` | Shell/Bash |
| `json` | JSON |
| `yaml` or `yml` | YAML |
| `sql` | SQL |
| `html` | HTML |
| `css` | CSS |
| `markdown` or `md` | Markdown |
| `diff` | Diff output |
| `text` or `plaintext` | No highlighting |

### Diff syntax highlighting

````markdown
```diff
- const old_value = "before";
+ const new_value = "after";
  const unchanged = "same";
```
````

Lines starting with `-` show as red (removed), `+` as green (added).

### Indented code blocks (alternative)

```markdown
Regular paragraph.

    This is a code block
    created by 4 spaces of indentation.
    No language highlighting.

Regular paragraph.
```

Fenced blocks (` ``` `) are preferred because they support language hints
and don't conflict with list indentation.

### Nested code blocks (quad backticks)

`````markdown
````markdown
```python
print("You can nest code blocks")
```
````
`````

Use 4 backticks to wrap a block that itself contains 3 backticks.

### Key rules

- Always add a language identifier for syntax highlighting
- Use `text` or `plaintext` when no highlighting is desired
- One blank line before and after fenced blocks
- Use inline code for file paths, variable names, and short commands

---

## 6. Blockquotes and Callouts

**When to use:** Quoting sources, notes, warnings, tips.

### Basic blockquotes

```markdown
> This is a blockquote.
> It can span multiple lines.
```

### Nested blockquotes

```markdown
> Outer quote
>
> > Nested quote
> > with multiple lines
>
> Back to outer quote
```

### Multi-paragraph blockquotes

```markdown
> First paragraph of the quote.
>
> Second paragraph, still inside the quote.
```

The blank `>` line keeps both paragraphs inside the blockquote.

### GitHub alert syntax (GFM)

```markdown
> [!NOTE]
> Useful information that users should know, even when skimming.

> [!TIP]
> Helpful advice for doing things better or more easily.

> [!IMPORTANT]
> Key information users need to know to achieve their goal.

> [!WARNING]
> Urgent info that needs immediate user attention to avoid problems.

> [!CAUTION]
> Advises about risks or negative outcomes of certain actions.
```

These render as colored callout boxes on GitHub with icons.

### Content inside blockquotes

```markdown
> **Note:** You can use any Markdown inside blockquotes:
>
> - Lists work
> - `code` works
>
> ```python
> # Even code blocks work
> print("inside a quote")
> ```
```

### Key rules

- `>` at the start of every line (including blank lines within the quote)
- Blank line before and after the blockquote
- GitHub alerts: `[!NOTE]` must be the first line after `>`
- Five alert types: `NOTE`, `TIP`, `IMPORTANT`, `WARNING`, `CAUTION`

---

## 7. Tables

**When to use:** Structured comparisons, reference data, configuration options.

### Basic table

```markdown
| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |
```

### Column alignment

```markdown
| Left-aligned | Center-aligned | Right-aligned |
|:-------------|:--------------:|--------------:|
| Left         | Center         | Right         |
| text         | text           | 123           |
```

- `:---` left-align (default)
- `:---:` center-align
- `---:` right-align

### Formatting in cells

```markdown
| Feature | Status | Notes |
|---------|--------|-------|
| **Auth** | `done` | Uses JWT |
| *Search* | `WIP` | [PR #42](https://example.com) |
| ~~Cache~~ | `cut` | Deferred to V2 |
```

You can use bold, italic, code, links, and strikethrough inside cells.

### Compact syntax

```markdown
Header 1 | Header 2
--- | ---
Cell 1 | Cell 2
```

The outer pipes are optional. Leading/trailing whitespace is ignored.

### Key rules

- The header separator row (`|---|---|`) is required
- At least 3 dashes per column in the separator
- Outer pipes (`|`) are optional but improve readability
- No merged cells — each row has the same number of columns
- No multi-line cells — use `<br>` for line breaks within cells
- Keep columns aligned in source for readability (not required, but helpful)

### Limitations

Tables in Markdown are intentionally simple. You cannot:

- Merge cells (rowspan/colspan)
- Add multi-line content (without `<br>`)
- Nest tables
- Add captions

For complex tables, use HTML `<table>` directly.

---

## 8. Horizontal Rules

**When to use:** Section breaks, visual separation between major topics.

```markdown
---

***

___
```

All three produce a horizontal rule. Use `---` by convention. Requires a blank
line before and after. At least 3 characters.

---

## 9. HTML in Markdown

**When to use:** Features Markdown doesn't support natively.

### Collapsible sections

```markdown
<details>
<summary>Click to expand</summary>

Hidden content here. You can use **Markdown** inside.

- List items work
- Code blocks work

</details>
```

### Forced line breaks

```markdown
Line one<br>
Line two (no paragraph gap)
```

Alternative: two trailing spaces at end of line (hard to see in source).

### Superscript and subscript

```markdown
x<sup>2</sup> + y<sup>2</sup> = z<sup>2</sup>
H<sub>2</sub>O
```

### Keyboard keys

```markdown
<kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>P</kbd>
```

### Centering content

```markdown
<div align="center">

![Logo](logo.png)

**Project Name**

</div>
```

Note the blank lines inside the `<div>` — required for Markdown rendering
inside HTML blocks.

### When to use HTML vs Markdown

| Need | Use |
|------|-----|
| Bold, italic, lists, links | Markdown (always) |
| Collapsible sections | HTML `<details>` |
| Keyboard keys | HTML `<kbd>` |
| Subscript/superscript | HTML `<sub>` / `<sup>` |
| Complex tables | HTML `<table>` |
| Centering | HTML `<div align="center">` |
| Line breaks without paragraphs | HTML `<br>` |
| Anything else | Markdown first, HTML as fallback |

### Key rules

- Blank line before and after HTML blocks
- Markdown inside HTML blocks: add a blank line after the opening tag
- Not all renderers support all HTML — GitHub strips `<style>`, `<script>`,
  and some attributes
- Prefer Markdown syntax when it exists; HTML is the escape hatch

---

## 10. Footnotes

**When to use:** Citations, clarifications, tangential notes.

### Inline footnotes

```markdown
This claim needs a source[^1].

Another point to note[^2].

[^1]: Source: Gruber, J. (2004). "Markdown." Daring Fireball.
[^2]: This is a longer footnote that can contain **formatting**
    and even multiple paragraphs if indented.
```

### Named footnotes

```markdown
Markdown was created in 2004[^gruber].

[^gruber]: By John Gruber and Aaron Swartz.
```

### Key rules

- Footnote markers: `[^identifier]` (numbers or names)
- Definitions can go anywhere in the document (convention: bottom)
- Supported by GFM, Pandoc, and most modern renderers
- Footnotes auto-number in rendered output regardless of identifier

---

## 11. Escaping Special Characters

**When to use:** Displaying Markdown syntax literally instead of rendering it.

### Backslash escapes

```markdown
\*This is not italic\*
\# This is not a heading
\- This is not a list item
\[This is not a link\](url)
```

### Characters that need escaping

| Character | Name | When to escape |
|-----------|------|---------------|
| `\` | Backslash | When literal backslash is needed |
| `` ` `` | Backtick | When showing literal backticks |
| `*` | Asterisk | When not used for emphasis |
| `_` | Underscore | When not used for emphasis |
| `{ }` | Braces | In some extended syntaxes |
| `[ ]` | Brackets | When not creating links |
| `( )` | Parentheses | When not part of link URL |
| `#` | Hash | At start of line when not a heading |
| `+` | Plus | At start of line when not a list |
| `-` | Dash | At start of line when not a list or rule |
| `.` | Period | After a number at line start (e.g., `1\.`) |
| `!` | Exclamation | Before brackets when not an image |
| `|` | Pipe | When not in a table |

### Alternative: use code backticks

Instead of escaping, wrap in backticks to show characters literally:

```markdown
The `**` operator means exponentiation in Python.
Use `#` for comments in YAML.
```

This is often cleaner than backslash escapes.

---

## 12. CommonMark vs GFM vs MDX

**When to use:** Understanding which features work where.

### CommonMark — the standard

CommonMark (2014–present) is the unambiguous specification for Markdown.
It standardized the many edge cases in Gruber's original spec. When people
say "Markdown" in 2026, they usually mean CommonMark.

Core features: headers, paragraphs, bold/italic, links, images, code blocks,
blockquotes, lists, horizontal rules.

### GitHub Flavored Markdown (GFM)

GFM is CommonMark plus GitHub's extensions. It's the most widely used Markdown
dialect because GitHub is where most developers encounter Markdown.

Extensions over CommonMark:

| Feature | Syntax | CommonMark | GFM |
|---------|--------|-----------|-----|
| Tables | `\| a \| b \|` | No | Yes |
| Task lists | `- [x] done` | No | Yes |
| Strikethrough | `~~text~~` | No | Yes |
| Autolinks | `https://example.com` | No | Yes |
| Fenced code | ` ``` ` | Yes | Yes |
| Footnotes | `[^1]` | No | Yes |
| Alerts | `> [!NOTE]` | No | Yes |

### MDX — Markdown + JSX

MDX (2017–present) embeds React components inside Markdown. Used by
documentation frameworks like Docusaurus, Nextra, and Astro.

```markdown
# Welcome

<CustomAlert type="warning">
  This is a React component inside Markdown.
</CustomAlert>

Regular **Markdown** works alongside JSX.
```

MDX is not compatible with standard Markdown renderers — it requires a
build step.

### What to use when

| Context | Dialect |
|---------|---------|
| GitHub READMEs, issues, PRs | GFM |
| Static site generators | CommonMark or MDX |
| AI agent configs (CLAUDE.md) | GFM (GitHub renders it) |
| Pandoc document conversion | CommonMark + extensions |
| Obsidian / note-taking | CommonMark + app extensions |

---

## 13. Markdown for AI Agent Configuration

**When to use:** Writing CLAUDE.md, .cursorrules, copilot-instructions.md, or
any AI tool configuration.

### Why structure matters for agents

AI agents parse Markdown structurally. They treat:

- **Headers** as named sections they can reference ("see the Testing section")
- **Bullet lists** as enumerated rules they follow sequentially
- **Code blocks** as examples they can copy and adapt
- **Tables** as structured data they can look up
- **Bold text** as emphasis — higher-weight instructions

This means how you format your agent config directly affects how well the
agent follows it.

### Structural patterns that help agents

**Headers create addressable sections:**

```markdown
## Code Style

- Use ruff for Python formatting
- Use ESLint + Prettier for TypeScript

## Testing Conventions

- Mock all external APIs in tests
- Run pytest before committing
```

The agent can now reference "the Code Style section" or "the Testing
Conventions section" because headers create named boundaries.

**Tables create lookup data:**

```markdown
| Wrong | Right |
|-------|-------|
| `from anthropic import ...` | `from claude_agent_sdk import ...` |
| `pip install` | `uv install` |
| Class components | Functional + hooks |
```

Tables are better than prose for rule sets because each row is a discrete,
unambiguous rule.

**Code blocks create copy-ready examples:**

````markdown
Run the backend:

```bash
cd backend && uv run uvicorn src.main:app --reload
```
````

Agents can extract and execute code blocks directly. A command in a code
block is clearer than a command buried in a paragraph.

**Bullet lists create sequential rules:**

```markdown
## Git Workflow

- Main branch: `main`
- Feature branches: `feature/<name>`
- Run tests before committing
- Never push directly to main
```

Agents process bullet lists item-by-item. Each bullet is a discrete
instruction.

### Anti-patterns for agent configs

| Anti-pattern | Problem | Fix |
|-------------|---------|-----|
| Wall of prose | Agent loses instructions in long paragraphs | Break into bullets |
| No headers | Agent can't navigate to relevant section | Add `##` headers for each topic |
| Ambiguous instructions | "Write good code" means nothing | Be specific: "Use early returns over nested conditionals" |
| Inconsistent formatting | Mixing bullets, numbering, prose | Pick one format per section |
| Too many rules | Agent can't prioritize | Keep to essential rules, remove obvious ones |
| Deeply nested bullets | Hard to parse priority | Max 2 levels of nesting |

### CLAUDE.md template pattern

```markdown
# Project Name

## Tech Stack
- **Backend:** FastAPI + Python 3.12
- **Frontend:** React 19 + TypeScript
- **Database:** PostgreSQL 16

## Architecture Rules
- [High-level design decisions]
- [Key constraints]

## Common Mistakes to Avoid
| Wrong | Right |
|-------|-------|
| mistake | correction |

## Testing Conventions
- [How to run tests]
- [What to mock]

## Code Style
- [Formatting tools]
- [Naming conventions]
```

### Cross-tool patterns

The same structural principles apply across AI tools:

```markdown
# .cursorrules / .windsurfrules / copilot-instructions.md

## General
- [Language and framework]
- [Core conventions]

## Do
- [Positive instructions]

## Don't
- [Things to avoid]

## Examples
```

The "Do / Don't" pattern with bullet lists works well across all AI coding
assistants because it creates unambiguous positive/negative examples.

---

## 14. Markdown Tooling

### Neovim / LazyVim

**render-markdown.nvim** — Renders Markdown inline in the buffer. Headers get
background colors, bullets get icons, code blocks get highlights, checkboxes
render as visual checkmarks.

```lua
-- lazy.nvim spec
{
  "MeanderingProgrammer/render-markdown.nvim",
  ft = { "markdown" },
  dependencies = {
    "nvim-treesitter/nvim-treesitter",
    "nvim-tree/nvim-web-devicons",
  },
}
```

**markdown-preview.nvim** — Opens a live browser preview that updates as you
type. Useful for checking rendered output.

```lua
{
  "iamcco/markdown-preview.nvim",
  cmd = { "MarkdownPreviewToggle", "MarkdownPreview" },
  build = "cd app && npx --yes yarn install",
  ft = { "markdown" },
}
```

**vim-markdown** (preservim) — Adds folding, concealing, and table of
contents generation.

```lua
{
  "preservim/vim-markdown",
  ft = { "markdown" },
  config = function()
    vim.g.vim_markdown_folding_disabled = 0
    vim.g.vim_markdown_conceal = 2
    vim.g.vim_markdown_conceal_code_blocks = 0
  end,
}
```

**Treesitter** — Ensure the Markdown parsers are installed for proper syntax
highlighting:

```lua
-- In your treesitter config
ensure_installed = { "markdown", "markdown_inline" }
```

**Useful built-in commands:**

| Command | Action |
|---------|--------|
| `gx` | Open URL under cursor in browser |
| `gf` | Open file path under cursor |
| `zc` / `zo` | Fold/unfold section (with vim-markdown) |
| `:Toc` | Table of contents sidebar (vim-markdown) |

### VS Code

| Extension | Purpose |
|-----------|---------|
| Markdown All in One | Shortcuts, TOC generation, auto-preview |
| Markdown Preview Enhanced | Advanced preview with diagrams, math |
| markdownlint | Real-time linting |
| Prettier | Consistent formatting on save |

### Linting

**markdownlint** / **markdownlint-cli2** — Catches common errors:

```bash
# Install
npm install -g markdownlint-cli2

# Lint a file
markdownlint-cli2 "docs/**/*.md"

# Fix auto-fixable issues
markdownlint-cli2 --fix "docs/**/*.md"
```

Common rules worth enabling:

| Rule | What it catches |
|------|----------------|
| MD001 | Heading level increment (no skipping H2 → H4) |
| MD009 | Trailing spaces |
| MD012 | Multiple consecutive blank lines |
| MD013 | Line length (configurable) |
| MD022 | Headings should be surrounded by blank lines |
| MD031 | Fenced code blocks should be surrounded by blank lines |
| MD032 | Lists should be surrounded by blank lines |
| MD033 | Inline HTML (can disable for `<details>`, `<kbd>`, etc.) |

### Formatting

**Prettier** — Auto-formats Markdown with consistent spacing:

```bash
# Install
npm install -g prettier

# Format a file
prettier --write "docs/**/*.md"
```

### Document conversion

**Pandoc** — Converts Markdown to and from almost any format:

```bash
# Markdown to PDF (requires LaTeX)
pandoc README.md -o README.pdf

# Markdown to HTML
pandoc README.md -o README.html

# Markdown to DOCX
pandoc README.md -o README.docx

# HTML to Markdown
pandoc page.html -t markdown -o page.md
```

---

## Appendix: Emoji in Markdown

### Shortcodes (GitHub)

```markdown
:rocket: :white_check_mark: :warning: :x: :bulb:
```

Renders as: :rocket: :white_check_mark: :warning: :x: :bulb:

Shortcode syntax works on GitHub, Slack, Discord, and many other platforms.

### Unicode emoji (universal)

```markdown
🚀 ✅ ⚠️ ❌ 💡
```

Unicode emoji work everywhere — in any editor, any renderer, any terminal.
Prefer Unicode when portability matters.

### Common emoji for documentation

| Emoji | Shortcode | Common usage |
|-------|-----------|-------------|
| ✅ | `:white_check_mark:` | Done, supported, correct |
| ❌ | `:x:` | Not done, unsupported, wrong |
| ⚠️ | `:warning:` | Caution, deprecation |
| 🚀 | `:rocket:` | Releases, deployments |
| 💡 | `:bulb:` | Tips, ideas |
| 🐛 | `:bug:` | Bug reports, fixes |
| 📝 | `:memo:` | Documentation |
| 🔧 | `:wrench:` | Configuration, tooling |
| 🏗️ | `:building_construction:` | Work in progress |
| 📦 | `:package:` | Packages, dependencies |

---

## Appendix: Line Breaks

Markdown has two kinds of line breaks, and confusing them is common.

### Paragraph break (blank line)

```markdown
Paragraph one.

Paragraph two.
```

A blank line creates a new `<p>` tag — full visual separation.

### Hard line break (two trailing spaces or `<br>`)

```markdown
Line one
Line two (note: two spaces at end of "Line one")

Line one<br>
Line two (explicit — prefer this over trailing spaces)
```

A hard line break creates a `<br>` — new line, same paragraph. Two trailing
spaces are invisible in source, so `<br>` is preferred.

### Soft line break (single newline)

```markdown
These two lines
become one paragraph.
```

A single newline in source renders as a space. The lines join into one
paragraph.

---

## Quick Reference Card

| Element | Syntax | Notes |
|---------|--------|-------|
| **Heading 1** | `# Text` | One per document |
| **Heading 2–6** | `## Text` through `###### Text` | Don't skip levels |
| **Bold** | `**text**` | |
| **Italic** | `*text*` | |
| **Bold + italic** | `***text***` | |
| **Strikethrough** | `~~text~~` | GFM |
| **Inline code** | `` `code` `` | |
| **Code block** | ```` ``` lang ```` | Add language for highlighting |
| **Unordered list** | `- item` | Also `*` or `+` |
| **Ordered list** | `1. item` | Auto-numbers |
| **Task list** | `- [x] done` | GFM |
| **Blockquote** | `> text` | |
| **Alert** | `> [!NOTE]` | GFM: NOTE, TIP, IMPORTANT, WARNING, CAUTION |
| **Link** | `[text](url)` | |
| **Reference link** | `[text][ref]` | Define `[ref]: url` below |
| **Image** | `![alt](url)` | |
| **Table** | `\| H \| H \|` | Separator row required |
| **Horizontal rule** | `---` | Also `***` or `___` |
| **Footnote** | `[^1]` | Define `[^1]: text` below |
| **Escape** | `\*` | Backslash before special chars |
| **HTML** | `<details>`, `<kbd>`, etc. | Escape hatch for missing features |
| **Line break** | `<br>` or two trailing spaces | Prefer `<br>` — visible in source |
| **Collapsible** | `<details><summary>` | HTML in Markdown |
| **Emoji** | `:rocket:` or 🚀 | Shortcode (GitHub) or Unicode |

---

## Common Mistakes

Real errors that break Markdown rendering:

| Mistake | Fix |
|---------|-----|
| `#Heading` (no space) | `# Heading` (space after `#`) |
| No blank line before list | Add blank line before first `- item` |
| No blank line before code block | Add blank line before ` ``` ` |
| Inconsistent list indent | Pick 2 or 4 spaces, use consistently |
| `1)` for ordered lists | `1.` (period, not parenthesis) |
| Tab characters for nesting | Use spaces (2 or 4), not tabs |
| Mixing `*` and `-` in one list | Pick one marker for the whole list |
| Missing table header separator | Always include `\|---\|---\|` row |
| Forgetting blank line after HTML | Markdown won't render inside HTML without it |
| Trailing spaces (invisible) | Use `<br>` for line breaks instead |
| `![](image.png)` (empty alt) | `![Description of image](image.png)` |
| Bare URL without angle brackets | `<https://example.com>` or `[text](url)` |
| Deeply nested lists (4+ levels) | Restructure — use headers or flatten |
| Single newline expecting line break | Use `<br>` or blank line for new paragraph |
| Forgetting to escape `\|` in tables | `\|` inside a table cell |
| Code block inside list (wrong indent) | Indent code block by list depth + 4 spaces |
