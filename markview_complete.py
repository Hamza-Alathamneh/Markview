"""Context-aware JetBrains-style Markdown auto-completion for Markview."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QKeySequence, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QFrame, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
    QStyledItemDelegate, QStyle, QVBoxLayout,
)

from markview_theme import THEMES

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico', '.avif'}
DOC_EXTENSIONS = {'.md', '.markdown', '.mdown', '.mkd', '.txt'}
WORD_RE = re.compile(r'[A-Za-z0-9_\u00C0-\u024F\u0600-\u06FF][A-Za-z0-9_\-\u00C0-\u024F\u0600-\u06FF]*')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*#*$', re.MULTILINE)
FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+.-]*)')

FENCE_LANGUAGES = [
    ('python', 'Python code block'),
    ('javascript', 'JavaScript code block'),
    ('typescript', 'TypeScript code block'),
    ('bash', 'Bash shell script'),
    ('sh', 'Shell script'),
    ('json', 'JSON data'),
    ('yaml', 'YAML configuration'),
    ('toml', 'TOML configuration'),
    ('html', 'HTML markup'),
    ('css', 'CSS stylesheet'),
    ('sql', 'SQL query'),
    ('c', 'C source'),
    ('cpp', 'C++ source'),
    ('rust', 'Rust source'),
    ('go', 'Go source'),
    ('java', 'Java source'),
    ('markdown', 'Markdown snippet'),
    ('mermaid', 'Mermaid diagram'),
    ('dot', 'Graphviz diagram'),
    ('vega-lite', 'Vega-Lite chart'),
    ('vega', 'Vega chart'),
    ('wavedrom', 'WaveDrom timing diagram'),
    ('powershell', 'PowerShell script'),
    ('diff', 'Diff / patch'),
    ('xml', 'XML markup'),
    ('ini', 'INI config'),
    ('dockerfile', 'Dockerfile'),
    ('plaintext', 'Plain text'),
]

MERMAID_ITEMS = [
    ('flowchart LR', 'flowchart LR\n    A[Start] --> B[End]', 'Left-to-right flowchart', None),
    ('flowchart TD', 'flowchart TD\n    A[Start] --> B[End]', 'Top-down flowchart', None),
    ('sequenceDiagram', 'sequenceDiagram\n    Alice->>Bob: Hello', 'Sequence diagram', None),
    ('classDiagram', 'classDiagram\n    ClassA <|-- ClassB', 'Class diagram', None),
    ('stateDiagram-v2', 'stateDiagram-v2\n    [*] --> Active', 'State diagram', None),
    ('erDiagram', 'erDiagram\n    USER ||--o{ ORDER : places', 'Entity-relationship diagram', None),
    ('gantt', 'gantt\n    title Schedule\n    section Main\n    Task :a1, 2026-01-01, 3d', 'Gantt chart', None),
    ('pie', 'pie title Distribution\n    "A" : 60\n    "B" : 40', 'Pie chart', None),
    ('subgraph', 'subgraph Title\n    \nend', 'Mermaid subgraph', 9),
    ('participant', 'participant ', 'Sequence participant', None),
    ('actor', 'actor ', 'Sequence actor', None),
    ('note right of', 'note right of ', 'Sequence note', None),
    ('loop', 'loop Condition\n    \nend', 'Sequence loop', 5),
    ('alt', 'alt Condition\n    \nelse\n    \nend', 'Sequence branch', 4),
    ('end', 'end', 'Close block', None),
]

DOT_ITEMS = [
    ('digraph', 'digraph G {\n    rankdir=LR;\n    A -> B;\n}', 'Directed graph', 8),
    ('graph', 'graph G {\n    A -- B;\n}', 'Undirected graph', 6),
    ('subgraph', 'subgraph cluster_0 {\n    label="";\n    \n}', 'Cluster subgraph', 32),
    ('rankdir=LR;', 'rankdir=LR;', 'Left-to-right layout', None),
    ('rankdir=TB;', 'rankdir=TB;', 'Top-to-bottom layout', None),
    ('node [shape=box];', 'node [shape=box];', 'Default node style', None),
    ('edge [style=dashed];', 'edge [style=dashed];', 'Default edge style', None),
    ('label=""', 'label=""', 'Label attribute', 7),
]

CALLOUT_ITEMS = [
    ('NOTE', 'Informational callout'),
    ('TIP', 'Helpful tip callout'),
    ('IMPORTANT', 'Key information callout'),
    ('WARNING', 'Warning callout'),
    ('CAUTION', 'Caution callout'),
    ('INFO', 'Info callout'),
    ('TODO', 'Todo callout'),
    ('SUCCESS', 'Success callout'),
    ('QUESTION', 'Question callout'),
    ('BUG', 'Bug callout'),
    ('EXAMPLE', 'Example callout'),
    ('QUOTE', 'Quote callout'),
]

LATEX_ITEMS = [
    (r'\frac{}{}', r'\frac{}{}', 'Fraction', 6),
    (r'\sqrt{}', r'\sqrt{}', 'Square root', 6),
    (r'\sum_{i=1}^{n}', r'\sum_{i=1}^{n} ', 'Summation', None),
    (r'\int_{a}^{b}', r'\int_{a}^{b} ', 'Integral', None),
    (r'\lim_{x \to \infty}', r'\lim_{x \to \infty} ', 'Limit', None),
    (r'\prod_{i=1}^{n}', r'\prod_{i=1}^{n} ', 'Product', None),
    (r'\text{}', r'\text{}', 'Text in math', 6),
    (r'\mathbf{}', r'\mathbf{}', 'Bold math', 8),
    (r'\mathbb{}', r'\mathbb{}', 'Blackboard bold', 8),
    (r'\mathcal{}', r'\mathcal{}', 'Calligraphic', 9),
    (r'\left( \right)', r'\left(  \right)', 'Auto-sized parens', 7),
    (r'\begin{align}', '\\begin{align}\n    \n\\end{align}', 'Aligned equations', 18),
    (r'\begin{pmatrix}', '\\begin{pmatrix}\n    a & b \\\\\n    c & d\n\\end{pmatrix}', 'Matrix', 20),
    (r'\alpha', r'\alpha', 'Greek alpha', None),
    (r'\beta', r'\beta', 'Greek beta', None),
    (r'\gamma', r'\gamma', 'Greek gamma', None),
    (r'\delta', r'\delta', 'Greek delta', None),
    (r'\epsilon', r'\epsilon', 'Greek epsilon', None),
    (r'\theta', r'\theta', 'Greek theta', None),
    (r'\lambda', r'\lambda', 'Greek lambda', None),
    (r'\mu', r'\mu', 'Greek mu', None),
    (r'\pi', r'\pi', 'Greek pi', None),
    (r'\sigma', r'\sigma', 'Greek sigma', None),
    (r'\omega', r'\omega', 'Greek omega', None),
    (r'\Delta', r'\Delta', 'Greek Delta', None),
    (r'\Sigma', r'\Sigma', 'Greek Sigma', None),
    (r'\Omega', r'\Omega', 'Greek Omega', None),
    (r'\infty', r'\infty', 'Infinity', None),
    (r'\approx', r'\approx', 'Approximately equal', None),
    (r'\neq', r'\neq', 'Not equal', None),
    (r'\leq', r'\leq', 'Less or equal', None),
    (r'\geq', r'\geq', 'Greater or equal', None),
    (r'\pm', r'\pm', 'Plus-minus', None),
    (r'\times', r'\times', 'Multiplication', None),
    (r'\cdot', r'\cdot', 'Dot operator', None),
    (r'\rightarrow', r'\rightarrow', 'Right arrow', None),
    (r'\Rightarrow', r'\Rightarrow', 'Implies arrow', None),
    (r'\leftrightarrow', r'\leftrightarrow', 'Double arrow', None),
]

CODE_KEYWORDS = {
    'python': ['def', 'class', 'return', 'import', 'from', 'async', 'await', 'yield', 'lambda', 'try', 'except', 'finally', 'with', 'raise', 'elif', 'match', 'case', 'None', 'True', 'False'],
    'javascript': ['function', 'const', 'let', 'return', 'import', 'export', 'default', 'async', 'await', 'class', 'extends', 'try', 'catch', 'finally', 'throw', 'new', 'typeof', 'null', 'undefined'],
    'typescript': ['function', 'const', 'let', 'interface', 'type', 'enum', 'return', 'import', 'export', 'async', 'await', 'class', 'implements', 'extends', 'readonly', 'private', 'public'],
    'bash': ['if', 'then', 'elif', 'else', 'fi', 'for', 'in', 'do', 'done', 'while', 'case', 'esac', 'function', 'local', 'export', 'echo', 'return'],
    'sh': ['if', 'then', 'elif', 'else', 'fi', 'for', 'in', 'do', 'done', 'while', 'case', 'esac', 'export', 'echo', 'return'],
    'sql': ['SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'INNER JOIN', 'GROUP BY', 'ORDER BY', 'HAVING', 'INSERT INTO', 'UPDATE', 'DELETE FROM', 'CREATE TABLE', 'VALUES'],
    'rust': ['fn', 'let', 'mut', 'pub', 'struct', 'enum', 'impl', 'trait', 'match', 'return', 'use', 'mod', 'async', 'await', 'Option', 'Result'],
    'go': ['func', 'package', 'import', 'type', 'struct', 'interface', 'return', 'defer', 'go', 'chan', 'select', 'range', 'make', 'error'],
}

SLASH_SNIPPETS = [
    ('/h1', '# ', 'Heading 1', 2),
    ('/h2', '## ', 'Heading 2', 3),
    ('/h3', '### ', 'Heading 3', 4),
    ('/h4', '#### ', 'Heading 4', 5),
    ('/code', '```\n\n```', 'Fenced code block', 3),
    ('/mermaid', '```mermaid\nflowchart LR\n    A[Start] --> B[End]\n```', 'Mermaid flowchart', 28),
    ('/dot', '```dot\ndigraph G {\n    rankdir=LR;\n    A -> B;\n}\n```', 'Graphviz diagram', 38),
    ('/math', '$$\n\n$$', 'Display math block', 3),
    ('/table', '| Column 1 | Column 2 |\n| --- | --- |\n|  |  |', 'Markdown table', 2),
    ('/task', '- [ ] ', 'Task list item', 6),
    ('/image', '![]()', 'Insert image', 2),
    ('/link', '[]()', 'Insert link', 1),
    ('/note', '> [!NOTE]\n> ', 'Note callout', 12),
    ('/tip', '> [!TIP]\n> ', 'Tip callout', 11),
    ('/warning', '> [!WARNING]\n> ', 'Warning callout', 15),
    ('/toc', '[TOC]', 'Table of contents', None),
    ('/import', '@import ""', 'Import local file', 9),
    ('/footnote', '[^1]', 'Footnote reference', 3),
    ('/quote', '> ', 'Blockquote', 2),
    ('/hr', '---', 'Horizontal rule', None),
    ('/bold', '****', 'Bold text', 2),
    ('/highlight', '====', 'Highlighted text', 2),
]

BADGE_COLORS = {
    'dark': {
        'FIX': ('#59242b', '#ff8a94'),
        'NEXT': ('#1f4d46', '#8edbcc'),
        'HEAD': ('#3a3159', '#c9baf5'),
        'IMG': ('#4a3720', '#f1c784'),
        'FILE': ('#253c59', '#9fc4fa'),
        'LANG': ('#2c4238', '#9be2be'),
        'DIAG': ('#3e2f52', '#d2b4f8'),
        'MATH': ('#47303f', '#f2a8cf'),
        'CALL': ('#4a3922', '#f3cb88'),
        'CODE': ('#293c4d', '#9dd1f5'),
        'REF': ('#363e52', '#b8c8ee'),
        'SNIP': ('#2a4440', '#8edbcc'),
        'DICT': ('#283b4a', '#a8cbe8'),
        'WORD': ('#2d3746', '#b8c4d4'),
    },
    'light': {
        'FIX': ('#fce0e2', '#c5221f'),
        'NEXT': ('#d7f0eb', '#125e53'),
        'HEAD': ('#ece5fa', '#5c3c9c'),
        'IMG': ('#faecd6', '#8a5205'),
        'FILE': ('#dfecfc', '#145ab6'),
        'LANG': ('#dff2e6', '#18663d'),
        'DIAG': ('#efe3fa', '#693c9e'),
        'MATH': ('#fae3ef', '#8f2c5c'),
        'CALL': ('#faebd2', '#875206'),
        'CODE': ('#dff0fa', '#165a85'),
        'REF': ('#e6ebf5', '#3c527d'),
        'SNIP': ('#d9efea', '#176c60'),
        'DICT': ('#e0edf7', '#1c5a8a'),
        'WORD': ('#e7ecf2', '#445368'),
    },
}


@dataclass
class CompletionItem:
    label: str
    insert_text: str
    kind: str
    detail: str = ''
    cursor_offset: int | None = None
    score: float = 0.0
    action: str | None = None


def slugify_heading(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.strip().lower())
    return re.sub(r'\s+', '-', slug).strip('-')


def fuzzy_score(query: str, candidate: str) -> float | None:
    """JetBrains-style prefix, word-boundary/CamelHump, and subsequence matcher."""
    if not query:
        return 10.0
    q_low = query.lower()
    c_low = candidate.lower()
    if candidate.startswith(query):
        return 120.0 - min(len(candidate) - len(query), 30) * 0.4
    if c_low.startswith(q_low):
        return 105.0 - min(len(candidate) - len(query), 30) * 0.4

    # CamelCase / separator boundary initials match (e.g. "mp" -> "markview_preview")
    boundaries = [0]
    for i in range(1, len(candidate)):
        if candidate[i - 1] in '_-/. ' or (candidate[i].isupper() and candidate[i - 1].islower()):
            boundaries.append(i)
    initials = ''.join(candidate[i].lower() for i in boundaries)
    if initials.startswith(q_low):
        return 85.0 - min(len(candidate), 40) * 0.2

    pos = c_low.find(q_low)
    if pos != -1:
        boundary_bonus = 12.0 if pos in boundaries else 0.0
        return 62.0 + boundary_bonus - pos * 0.5 - min(len(candidate), 40) * 0.15

    # Ordered subsequence match
    qi = 0
    matched_boundaries = 0
    span_start = -1
    last_idx = -1
    boundary_set = set(boundaries)
    for ci, ch in enumerate(c_low):
        if ch == q_low[qi]:
            if span_start == -1:
                span_start = ci
            if ci in boundary_set:
                matched_boundaries += 1
            last_idx = ci
            qi += 1
            if qi == len(q_low):
                break
    if qi < len(q_low):
        return None
    spread = (last_idx - span_start + 1) - len(q_low)
    return 35.0 + matched_boundaries * 4.0 - spread * 0.8 - span_start * 0.3


def _fence_context(text: str, cursor_pos: int):
    """Return (in_fence, fence_lang, fence_body_start)."""
    in_fence = False
    fence_char = ''
    fence_len = 0
    fence_lang = ''
    fence_body_start = 0
    offset = 0
    before = text[:cursor_pos]
    lines = before.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        # Do not toggle fence on the active line itself
        if idx == len(lines) - 1 and not line.endswith('\n'):
            break
        match = FENCE_RE.match(line)
        if match:
            marker, lang = match.group(1), match.group(2).lower()
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
                fence_lang = lang
                fence_body_start = offset + len(line)
            elif marker[0] == fence_char and len(marker) >= fence_len and not lang:
                in_fence = False
                fence_lang = ''
        offset += len(line)
    return in_fence, fence_lang, fence_body_start


def _inside_math(text: str, cursor_pos: int) -> bool:
    before = text[:cursor_pos]
    # Check display math $$ blocks (ignoring escaped \$)
    display_count = len(re.findall(r'(?<!\\)\$\$', before))
    if display_count % 2 == 1:
        return True
    line_start = before.rfind('\n') + 1
    line_before = re.sub(r'(?<!\\)\$\$', '', before[line_start:])
    inline_count = len(re.findall(r'(?<!\\)\$', line_before))
    return inline_count % 2 == 1


class CompletionEngine:
    """Produces ranked, context-aware completion candidates for Markdown."""

    def __init__(self, spell=None):
        self.spell = spell
        self.suggestions_enabled = True
        self.markdown_suggestions = True
        self.word_suggestions = True
        self.spelling_mode = 'dropdown'  # 'dropdown' | 'right_click' | 'off'

    def configure(self, suggestions_enabled: bool = True, markdown_suggestions: bool = True,
                  word_suggestions: bool = True, spelling_mode: str = 'dropdown'):
        self.suggestions_enabled = suggestions_enabled
        self.markdown_suggestions = markdown_suggestions
        self.word_suggestions = word_suggestions
        self.spelling_mode = spelling_mode

    def quick_fix(self, text: str, cursor_pos: int) -> tuple[int, int, list[CompletionItem]]:
        """Return JetBrains Alt+Enter spelling fixes for a misspelled word at cursor_pos."""
        if self.spell is None or not self.spell.enabled or self.spelling_mode == 'off':
            return cursor_pos, cursor_pos, []
        in_fence, _, _ = _fence_context(text, cursor_pos)
        if in_fence or _inside_math(text, cursor_pos):
            return cursor_pos, cursor_pos, []
        line_start = text.rfind('\n', 0, cursor_pos) + 1
        line_end = text.find('\n', cursor_pos)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        hit = self.spell.word_at_position(line, cursor_pos - line_start)
        if hit is None:
            return cursor_pos, cursor_pos, []
        w_start, w_len, word = hit
        if self.spell.is_correct(word):
            return cursor_pos, cursor_pos, []
        items = [
            CompletionItem(sug, sug, 'FIX', 'spelling fix', score=100.0 - idx)
            for idx, sug in enumerate(self.spell.suggestions(word, limit=6))
        ]
        items.append(CompletionItem(f'Add "{word}" to dictionary', word, 'SNIP', 'save word', action='add_dict', score=-1.0))
        items.append(CompletionItem(f'Ignore "{word}"', word, 'SNIP', 'this session', action='ignore_word', score=-2.0))
        return line_start + w_start, line_start + w_start + w_len, items

    def suggest(self, text: str, cursor_pos: int, base_dir: Path | None = None,
                explicit: bool = False) -> tuple[int, int, list[CompletionItem]]:
        md_allowed = self.suggestions_enabled and self.markdown_suggestions
        words_allowed = self.suggestions_enabled and self.word_suggestions
        spell_dropdown = (
            self.spell is not None and self.spell.enabled and self.spelling_mode == 'dropdown'
        )
        if not md_allowed and not words_allowed and not spell_dropdown:
            return cursor_pos, cursor_pos, []

        line_start = text.rfind('\n', 0, cursor_pos) + 1
        line_before = text[line_start:cursor_pos]
        in_fence, fence_lang, fence_body_start = _fence_context(text, cursor_pos)

        # 1. Opening fence language line (e.g. ```py)
        if not in_fence:
            fence_match = re.match(r'^(\s*(?:`{3,}|~{3,}))([A-Za-z0-9_+.-]*)$', line_before)
            if fence_match:
                if not md_allowed:
                    return cursor_pos, cursor_pos, []
                prefix = fence_match.group(2)
                start = cursor_pos - len(prefix)
                return start, cursor_pos, self._fence_languages(text, prefix)

        # 2. Inside a fenced block
        if in_fence:
            if not md_allowed:
                return cursor_pos, cursor_pos, []
            if fence_lang == 'mermaid':
                return self._diagram_completions(text, cursor_pos, line_before, fence_body_start, MERMAID_ITEMS, explicit)
            if fence_lang in {'dot', 'graphviz'}:
                return self._diagram_completions(text, cursor_pos, line_before, fence_body_start, DOT_ITEMS, explicit)
            return self._code_completions(text, cursor_pos, line_before, fence_lang, fence_body_start, explicit)

        # 3. Callout after "> [" or "> [!"
        callout_match = re.match(r'^(\s*>\s*)\[(!?)([A-Za-z]*)$', line_before)
        if callout_match:
            if not md_allowed:
                return cursor_pos, cursor_pos, []
            prefix = callout_match.group(3)
            start = line_start + len(callout_match.group(1))
            return start, cursor_pos, self._callout_completions(prefix)

        # 4. @import "path..."
        import_match = re.search(r'@import\s+"([^"\n]*)$', line_before)
        if import_match:
            if not md_allowed:
                return cursor_pos, cursor_pos, []
            typed = import_match.group(1)
            start = cursor_pos - len(typed)
            return start, cursor_pos, self._path_completions(typed, base_dir, images_only=False, include_anchors=False, text=text)

        # 5. Image or link destination: ![alt](path... or [label](path...
        link_match = re.search(r'(!?)\[[^\]\n]*\]\(([^)\n]*)$', line_before)
        if link_match:
            if not md_allowed:
                return cursor_pos, cursor_pos, []
            is_image = link_match.group(1) == '!'
            typed = link_match.group(2)
            start = cursor_pos - len(typed)
            return start, cursor_pos, self._path_completions(
                typed, base_dir, images_only=is_image, include_anchors=not is_image, text=text,
            )

        # 6. Footnote reference: [^label
        fn_match = re.search(r'\[\^([^\s\]\n]*)$', line_before)
        if fn_match:
            if not md_allowed:
                return cursor_pos, cursor_pos, []
            typed = fn_match.group(1)
            start = cursor_pos - len(typed) - 2
            return start, cursor_pos, self._footnote_completions(text, cursor_pos, typed)

        # 7. LaTeX command inside $...$ or $$...$$ (or explicit \command)
        latex_match = re.search(r'(\\[A-Za-z]*)$', line_before)
        if latex_match and (_inside_math(text, cursor_pos) or explicit):
            if not md_allowed:
                return cursor_pos, cursor_pos, []
            typed = latex_match.group(1)
            if len(typed) >= 2 or explicit or _inside_math(text, cursor_pos):
                start = cursor_pos - len(typed)
                return start, cursor_pos, self._latex_completions(text, cursor_pos, typed)

        # 8. Slash command snippets (e.g. /table, /mermaid, /image)
        slash_match = re.match(r'^(\s*)(/[A-Za-z0-9_-]*)$', line_before)
        if slash_match:
            if not md_allowed:
                return cursor_pos, cursor_pos, []
            typed = slash_match.group(2)
            start = cursor_pos - len(typed)
            return start, cursor_pos, self._slash_completions(typed)

        # 9. Smart context-aware document + English word + spelling dropdown completion
        word_match = re.search(r'([A-Za-z0-9_\u00C0-\u024F\u0600-\u06FF][A-Za-z0-9_\-\u00C0-\u024F\u0600-\u06FF]*)$', line_before)
        prefix = word_match.group(1) if word_match else ''
        start = cursor_pos - len(prefix)
        if not explicit and len(prefix) < 2:
            if words_allowed and len(prefix) == 1:
                predicted = [
                    item for item in self._document_completions(
                        text, start, cursor_pos, prefix, line_before, False,
                        include_words=True, include_spelling=False, include_snippets=False,
                    )
                    if item.kind == 'NEXT'
                ]
                return start, cursor_pos, predicted
            return start, cursor_pos, []
        return start, cursor_pos, self._document_completions(
            text, start, cursor_pos, prefix, line_before, explicit,
            include_words=words_allowed, include_spelling=spell_dropdown, include_snippets=md_allowed,
        )

    def _fence_languages(self, text: str, prefix: str) -> list[CompletionItem]:
        used = Counter(m.group(2).lower() for m in FENCE_RE.finditer(text) if m.group(2))
        seen = set()
        items = []
        for lang, detail in FENCE_LANGUAGES:
            score = fuzzy_score(prefix, lang)
            if score is None:
                continue
            seen.add(lang)
            boost = 25.0 + min(used[lang] * 5.0, 20.0) if used[lang] else 0.0
            note = f'{detail} (used)' if used[lang] else detail
            items.append(CompletionItem(lang, lang, 'LANG', note, score=score + boost))
        for lang, count in used.items():
            if lang not in seen:
                score = fuzzy_score(prefix, lang)
                if score is not None:
                    items.append(CompletionItem(lang, lang, 'LANG', f'used {count}x in doc', score=score + 20.0))
        items.sort(key=lambda item: (-item.score, item.label))
        return items[:14]

    def _callout_completions(self, prefix: str) -> list[CompletionItem]:
        items = []
        for name, detail in CALLOUT_ITEMS:
            score = fuzzy_score(prefix, name)
            if score is not None:
                text = f'[!{name}]\n> '
                items.append(CompletionItem(f'[!{name}]', text, 'CALL', detail, cursor_offset=len(text), score=score))
        items.sort(key=lambda item: (-item.score, item.label))
        return items

    def _path_completions(self, typed: str, base_dir: Path | None, images_only: bool,
                          include_anchors: bool, text: str) -> list[CompletionItem]:
        items: list[CompletionItem] = []
        clean_typed = typed.lstrip('<')

        # Document heading anchors (#heading)
        if include_anchors and (clean_typed.startswith('#') or not clean_typed):
            anchor_query = clean_typed[1:] if clean_typed.startswith('#') else ''
            seen_slugs = set()
            for match in HEADING_RE.finditer(text):
                level = len(match.group(1))
                title = match.group(2).strip()
                slug = slugify_heading(title)
                if not slug or slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                score = fuzzy_score(anchor_query, slug)
                if score is not None:
                    boost = 20.0 if clean_typed.startswith('#') else 0.0
                    items.append(CompletionItem(f'#{slug}', f'#{slug}', 'HEAD', f'H{level}: {title}', score=score + boost))
            if clean_typed.startswith('#'):
                items.sort(key=lambda item: (-item.score, item.label))
                return items[:14]

        # Filesystem scan (supports relative, absolute, and ~/ paths)
        rel_dir = ''
        name_query = clean_typed
        if '/' in clean_typed or '\\' in clean_typed:
            sep_idx = max(clean_typed.rfind('/'), clean_typed.rfind('\\'))
            rel_dir = clean_typed[:sep_idx + 1]
            name_query = clean_typed[sep_idx + 1:]

        scan_dir = None
        if rel_dir:
            expanded_dir = Path(rel_dir).expanduser()
            if expanded_dir.is_absolute():
                scan_dir = expanded_dir.resolve()
            elif base_dir and base_dir.is_dir():
                scan_dir = (base_dir / rel_dir).resolve()
        elif base_dir and base_dir.is_dir():
            scan_dir = base_dir

        if scan_dir and scan_dir.is_dir():
            folder_hint = (scan_dir.name + '/') if scan_dir.name else str(scan_dir)
            try:
                entries = sorted(scan_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError:
                entries = []
            for entry in entries:
                if entry.name.startswith('.') and not name_query.startswith('.'):
                    continue
                is_dir = entry.is_dir()
                ext = entry.suffix.lower()
                if images_only and not is_dir and ext not in IMAGE_EXTENSIONS:
                    continue
                score = fuzzy_score(name_query, entry.name)
                if score is None:
                    continue
                label = entry.name + ('/' if is_dir else '')
                rel_path = rel_dir + label
                if is_dir:
                    insert = f'<{rel_path}' if typed.startswith('<') else rel_path
                    kind, tag, boost = 'FILE', 'folder', 8.0
                else:
                    insert = f'<{rel_path}>' if (' ' in rel_path or typed.startswith('<')) else rel_path
                    if ext == '.gif':
                        kind, tag, boost = 'IMG', 'GIF', 30.0 if images_only else 8.0
                    elif ext in IMAGE_EXTENSIONS:
                        kind, tag, boost = 'IMG', 'image', 28.0 if images_only else 6.0
                    elif ext in DOC_EXTENSIONS:
                        kind, tag, boost = 'FILE', 'Markdown', 20.0
                    else:
                        kind, tag, boost = 'FILE', 'file', 2.0
                detail = f'{folder_hint} · {tag}' if rel_dir else tag
                items.append(CompletionItem(label, insert, kind, detail, score=score + boost))

        items.sort(key=lambda item: (-item.score, item.label))
        return items[:14]

    def _footnote_completions(self, text: str, cursor_pos: int, typed: str) -> list[CompletionItem]:
        masked = text[:max(0, cursor_pos - len(typed) - 2)] + ' ' + text[cursor_pos:]
        defs = set(re.findall(r'^\[\^([^\s\]]+)\]:', masked, re.MULTILINE))
        refs = set(re.findall(r'\[\^([^\s\]]+)\]', masked))
        labels = sorted(defs | refs)
        items = []
        for label in labels:
            score = fuzzy_score(typed, label)
            if score is not None:
                detail = 'defined footnote' if label in defs else 'referenced footnote'
                boost = 15.0 if label in defs else 5.0
                items.append(CompletionItem(f'[^{label}]', f'[^{label}]', 'REF', detail, score=score + boost))
        if not items and not typed:
            items.append(CompletionItem('[^note]', '[^note]', 'REF', 'new footnote', cursor_offset=6, score=10.0))
        items.sort(key=lambda item: (-item.score, item.label))
        return items[:12]

    def _latex_completions(self, text: str, cursor_pos: int, typed: str) -> list[CompletionItem]:
        query = typed[1:]
        masked = text[:cursor_pos - len(typed)] + ' ' + text[cursor_pos:]
        doc_cmds = Counter(re.findall(r'\\([A-Za-z]{2,})', masked))
        seen = set()
        items = []
        for label, insert, detail, offset in LATEX_ITEMS:
            cmd_name = re.match(r'\\([A-Za-z]+)', label).group(1)
            seen.add(cmd_name)
            score = fuzzy_score(query, cmd_name)
            if score is not None:
                boost = 18.0 if doc_cmds[cmd_name] else 0.0
                items.append(CompletionItem(label, insert, 'MATH', detail, cursor_offset=offset, score=score + boost))
        for cmd_name, count in doc_cmds.items():
            if cmd_name not in seen:
                score = fuzzy_score(query, cmd_name)
                if score is not None:
                    items.append(CompletionItem(f'\\{cmd_name}', f'\\{cmd_name}', 'MATH', f'used {count}x in doc', score=score + 12.0))
        items.sort(key=lambda item: (-item.score, item.label))
        return items[:14]

    def _slash_completions(self, typed: str) -> list[CompletionItem]:
        query = typed[1:]
        items = []
        for cmd, insert, detail, offset in SLASH_SNIPPETS:
            score = fuzzy_score(query, cmd[1:])
            if score is None:
                score = fuzzy_score(query, detail)
                if score is not None:
                    score -= 15.0
            if score is not None:
                items.append(CompletionItem(cmd, insert, 'SNIP', detail, cursor_offset=offset, score=score))
        items.sort(key=lambda item: (-item.score, item.label))
        return items[:14]

    def _diagram_completions(self, text: str, cursor_pos: int, line_before: str,
                             fence_body_start: int, templates: list, explicit: bool):
        word_match = re.search(r'([A-Za-z0-9_=-]*)$', line_before)
        prefix = word_match.group(1) if word_match else ''
        start = cursor_pos - len(prefix)
        if not explicit and len(prefix) < 2:
            return start, cursor_pos, []

        items = []
        seen = set()
        for label, insert, detail, offset in templates:
            score = fuzzy_score(prefix, label)
            if score is not None:
                seen.add(label.lower())
                items.append(CompletionItem(label, insert, 'DIAG', detail, cursor_offset=offset, score=score + 15.0))

        # Extract node / participant identifiers already written inside this diagram block
        block_end = text.find('\n```', cursor_pos)
        if block_end == -1:
            block_end = len(text)
        block_text = text[fence_body_start:start] + ' ' + text[cursor_pos:block_end]
        for ident, count in Counter(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', block_text)).items():
            if ident.lower() in seen or len(ident) < 1:
                continue
            score = fuzzy_score(prefix, ident)
            if score is not None:
                seen.add(ident.lower())
                items.append(CompletionItem(ident, ident, 'CODE', f'diagram node ({count}x)', score=score + 20.0 + min(count * 3.0, 15.0)))

        items.sort(key=lambda item: (-item.score, item.label))
        return start, cursor_pos, items[:14]

    def _code_completions(self, text: str, cursor_pos: int, line_before: str,
                          fence_lang: str, fence_body_start: int, explicit: bool):
        word_match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)$', line_before)
        prefix = word_match.group(1) if word_match else ''
        start = cursor_pos - len(prefix)
        if not explicit and len(prefix) < 2:
            return start, cursor_pos, []

        block_end = text.find('\n```', cursor_pos)
        if block_end == -1:
            block_end = len(text)
        block_text = text[fence_body_start:start] + ' ' + text[cursor_pos:block_end]
        counts = Counter(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]{1,}\b', block_text))
        items = []
        seen = set()
        for ident, count in counts.items():
            if ident == prefix:
                continue
            score = fuzzy_score(prefix, ident)
            if score is not None:
                seen.add(ident)
                items.append(CompletionItem(ident, ident, 'CODE', f'in block ({count}x)', score=score + 25.0 + min(count * 4.0, 20.0)))
        for kw in CODE_KEYWORDS.get(fence_lang, ()):
            if kw in seen:
                continue
            score = fuzzy_score(prefix, kw)
            if score is not None:
                seen.add(kw)
                items.append(CompletionItem(kw, kw, 'LANG', f'{fence_lang} keyword', score=score + 10.0))
        items.sort(key=lambda item: (-item.score, item.label))
        return start, cursor_pos, items[:14]

    def _document_completions(self, text: str, start: int, cursor_pos: int, prefix: str,
                              line_before: str, explicit: bool,
                              include_words: bool = True, include_spelling: bool = True,
                              include_snippets: bool = True) -> list[CompletionItem]:
        items: list[CompletionItem] = []

        if include_words:
            # Identify previous word for bigram next-word prediction
            before_prefix = text[:start]
            prev_match = re.search(r'([A-Za-z0-9_\u00C0-\u024F\u0600-\u06FF][A-Za-z0-9_\-\u00C0-\u024F\u0600-\u06FF]*)\s+$', before_prefix)
            prev_word = prev_match.group(1) if prev_match else ''
            prev_low = prev_word.lower()

            # Mask the currently edited token span so half-typed text isn't suggested to itself
            masked = text[:start] + ' ' * (cursor_pos - start) + text[cursor_pos:]

            heading_words = set()
            for m in HEADING_RE.finditer(masked):
                for w in WORD_RE.findall(m.group(2)):
                    heading_words.add(w.lower())

            code_words = set()
            for m in re.finditer(r'`([^`\n]+)`', masked):
                for w in WORD_RE.findall(m.group(1)):
                    code_words.add(w.lower())

            bold_words = set()
            for m in re.finditer(r'\*\*([^*\n]+)\*\*|__([^_\n]+)__', masked):
                for w in WORD_RE.findall(m.group(1) or m.group(2) or ''):
                    bold_words.add(w.lower())

            # Scan all tokens for frequencies, proximity to cursor, and bigrams
            counts: Counter[str] = Counter()
            best_case: dict[str, str] = {}
            closest_dist: dict[str, int] = {}
            bigrams: dict[str, Counter[str]] = defaultdict(Counter)
            prev_tok = ''
            prev_end = -10
            doc_len = max(len(masked), 1)

            for match in WORD_RE.finditer(masked):
                tok = match.group(0)
                if len(tok) < 2:
                    prev_tok = tok.lower()
                    prev_end = match.end()
                    continue
                low = tok.lower()
                counts[low] += 1
                dist = abs(match.start() - start)
                if low not in closest_dist or dist < closest_dist[low]:
                    closest_dist[low] = dist
                    best_case[low] = tok
                # Only form bigrams when separated by whitespace (not punctuation/newlines across paragraphs)
                gap = masked[prev_end:match.start()]
                if prev_tok and gap and gap.isspace() and '\n\n' not in gap:
                    bigrams[prev_tok][low] += 1
                prev_tok = low
                prev_end = match.end()

            predicted = bigrams.get(prev_low, Counter()) if prev_low else Counter()

            for low, count in counts.items():
                word = best_case[low]
                if word == prefix:
                    continue
                match_score = fuzzy_score(prefix, word)
                if match_score is None:
                    continue
                proximity_bonus = 28.0 * (1.0 - min(closest_dist[low], doc_len) / doc_len)
                freq_bonus = min(count * 3.5, 22.0)

                if predicted[low]:
                    kind = 'NEXT'
                    detail = f'after "{prev_word}"'
                    context_bonus = 75.0 + min(predicted[low] * 12.0, 36.0)
                elif low in heading_words:
                    kind = 'HEAD'
                    detail = 'in heading'
                    context_bonus = 30.0
                elif low in code_words:
                    kind = 'CODE'
                    detail = 'inline code'
                    context_bonus = 24.0
                elif low in bold_words:
                    kind = 'WORD'
                    detail = 'emphasized'
                    context_bonus = 16.0
                else:
                    kind = 'WORD'
                    detail = f'{count}x in doc' if count > 1 else 'in doc'
                    context_bonus = 0.0

                items.append(CompletionItem(
                    label=word,
                    insert_text=word,
                    kind=kind,
                    detail=detail,
                    score=match_score + proximity_bonus + freq_bonus + context_bonus,
                ))

            # Add English dictionary prefix completions below document/context words
            if self.spell is not None and (len(prefix) >= 3 or (explicit and len(prefix) >= 2)):
                existing = {item.label.lower() for item in items}
                for idx, cand in enumerate(self.spell.complete_prefix(prefix, limit=6)):
                    if cand.lower() not in existing and cand != prefix:
                        existing.add(cand.lower())
                        items.append(CompletionItem(cand, cand, 'DICT', 'English word', score=42.0 - idx * 2.0))

        # Include spelling fixes in the dropdown only when spelling dropdown mode is active
        if (include_spelling and self.spell is not None and self.spell.enabled
                and len(prefix) >= 3 and prefix.isalpha() and not self.spell.is_correct(prefix)):
            existing_labels = {item.label.lower() for item in items}
            for idx, sug in enumerate(self.spell.suggestions(prefix, limit=4)):
                if sug.lower() not in existing_labels:
                    existing_labels.add(sug.lower())
                    items.append(CompletionItem(sug, sug, 'FIX', 'spelling fix', score=170.0 - idx * 6.0))

        # On explicit Ctrl+Space at start of line, also surface helpful Markdown snippets
        if explicit and include_snippets and not line_before.strip():
            for cmd, insert, detail, offset in SLASH_SNIPPETS[:12]:
                items.append(CompletionItem(cmd, insert, 'SNIP', detail, cursor_offset=offset, score=20.0))

        items.sort(key=lambda item: (-item.score, item.label.lower()))
        return items[:14]


class CompletionDelegate(QStyledItemDelegate):
    """Renders JetBrains-style rows with kind badge, label, and right-aligned detail."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = 'dark'

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 28)

    def paint(self, painter: QPainter, option, index):
        item: CompletionItem = index.data(Qt.ItemDataRole.UserRole)
        if item is None:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = THEMES[self.theme]
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect

        if selected:
            painter.fillRect(rect, QColor(c['selection']))
        else:
            painter.fillRect(rect, QColor(c['base']))

        # Kind badge
        badges = BADGE_COLORS[self.theme]
        bg_hex, fg_hex = badges.get(item.kind, badges['WORD'])
        badge_rect = QRect(rect.left() + 8, rect.top() + 5, 42, rect.height() - 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg_hex))
        painter.drawRoundedRect(badge_rect, 4, 4)

        badge_font = QFont(option.font)
        badge_font.setPointSize(max(badge_font.pointSize() - 2, 8))
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(QColor(fg_hex))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, item.kind)

        # Detail text (right-aligned)
        detail_font = QFont(option.font)
        detail_font.setPointSize(max(detail_font.pointSize() - 1, 9))
        detail_fm = QFontMetrics(detail_font)
        detail_width = min(detail_fm.horizontalAdvance(item.detail) + 12, rect.width() // 2) if item.detail else 0
        detail_rect = QRect(rect.right() - detail_width - 8, rect.top(), detail_width, rect.height())
        if item.detail:
            painter.setFont(detail_font)
            painter.setPen(QColor('#e8f1f0' if selected else c['muted']))
            elided_detail = detail_fm.elidedText(item.detail, Qt.TextElideMode.ElideRight, detail_rect.width())
            painter.drawText(detail_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, elided_detail)

        # Main label
        label_font = QFont(option.font)
        label_font.setBold(selected or item.kind == 'NEXT')
        label_fm = QFontMetrics(label_font)
        label_left = badge_rect.right() + 10
        label_right = (detail_rect.left() - 8) if item.detail else (rect.right() - 8)
        label_rect = QRect(label_left, rect.top(), max(label_right - label_left, 40), rect.height())
        painter.setFont(label_font)
        painter.setPen(QColor('#ffffff' if selected else c['text']))
        elided_label = label_fm.elidedText(item.label, Qt.TextElideMode.ElideRight, label_rect.width())
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_label)
        painter.restore()


class CompletionPopup(QFrame):
    """In-editor overlay popup (Wayland/Hyprland, X11, and Windows safe)."""

    def __init__(self, editor: 'MarkdownEditor'):
        super().__init__(editor)
        self.editor = editor
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName('completionPopup')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.list = QListWidget(self)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setUniformItemSizes(True)
        self.delegate = CompletionDelegate(self.list)
        self.list.setItemDelegate(self.delegate)
        self.list.itemClicked.connect(lambda _: self.editor.accept_completion())
        layout.addWidget(self.list)

        self.footer = QLabel('Tab / Enter: accept  ·  Esc: close  ·  Alt+Enter: quick-fix', self)
        self.footer.setObjectName('completionFooter')
        self.footer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.footer)
        self.hide()

    def apply_theme(self, theme: str):
        c = THEMES[theme]
        self.delegate.theme = theme
        self.setStyleSheet(f"""
            QFrame#completionPopup {{
                background: {c['base']};
                border: 1px solid {c['accent']};
                border-radius: 8px;
            }}
            QListWidget {{
                background: {c['base']};
                border: none;
                outline: none;
            }}
            QLabel#completionFooter {{
                background: {c['window']};
                color: {c['muted']};
                font-size: 10px;
                padding: 4px 8px;
                border-top: 1px solid {c['border']};
                border-bottom-left-radius: 7px;
                border-bottom-right-radius: 7px;
            }}
        """)
        self.list.viewport().update()

    def populate(self, items: list[CompletionItem]):
        self.list.clear()
        for item in items:
            entry = QListWidgetItem(item.label)
            entry.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(entry)
        if items:
            self.list.setCurrentRow(0)

    def current_item(self) -> CompletionItem | None:
        entry = self.list.currentItem()
        return entry.data(Qt.ItemDataRole.UserRole) if entry else None

    def move_selection(self, delta: int):
        count = self.list.count()
        if count:
            self.list.setCurrentRow((self.list.currentRow() + delta) % count)


class MarkdownEditor(QPlainTextEdit):
    """QPlainTextEdit with JetBrains-style completion, spellcheck fixes, and safe auto-correct."""

    BOUNDARY_CHARS = frozenset(' \t\r\n.,;:!?)')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spell = None
        self.rehighlight_callback = None
        self.engine = CompletionEngine()
        self.popup = CompletionPopup(self)
        self.base_dir_provider = lambda: Path.cwd()
        self._replace_range = (0, 0)
        self._last_autocorrect: tuple[int, str, str] | None = None

    def set_spell_checker(self, spell, rehighlight_callback=None):
        self.spell = spell
        self.engine.spell = spell
        self.rehighlight_callback = rehighlight_callback

    def apply_preferences(self, prefs):
        self.engine.configure(
            suggestions_enabled=prefs.suggestions_enabled,
            markdown_suggestions=prefs.markdown_suggestions,
            word_suggestions=prefs.word_suggestions,
            spelling_mode=prefs.spelling_mode,
        )
        if not prefs.suggestions_enabled and prefs.spelling_mode != 'dropdown':
            self.popup.hide()

    def apply_theme(self, theme: str):
        self.popup.apply_theme(theme)

    def hide_completions(self):
        self.popup.hide()

    def completions_visible(self) -> bool:
        return self.popup.isVisible()

    def trigger_completions(self, explicit: bool = False):
        cursor = self.textCursor()
        if cursor.hasSelection():
            self.popup.hide()
            return
        base_dir = self.base_dir_provider() if self.base_dir_provider else None
        start, end, items = self.engine.suggest(self.toPlainText(), cursor.position(), base_dir, explicit=explicit)
        if not items:
            self.popup.hide()
            return
        self._show_popup_items(start, end, items)

    def trigger_quick_fix(self) -> bool:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        if cursor.block().userState() in (1, 2, 3):
            return False
        start, end, items = self.engine.quick_fix(self.toPlainText(), cursor.position())
        if not items:
            self.popup.hide()
            return False
        self._show_popup_items(start, end, items)
        return True

    def _show_popup_items(self, start: int, end: int, items: list[CompletionItem]):
        self._replace_range = (start, end)
        self.popup.populate(items)
        self._position_popup(len(items))
        self.popup.show()
        self.popup.raise_()

    def _position_popup(self, count: int):
        row_height = 28
        visible_rows = min(count, 8)
        footer_height = 24
        popup_h = visible_rows * row_height + footer_height + 4
        popup_w = min(max(360, self.viewport().width() // 2), max(self.viewport().width() - 16, 220))
        self.popup.resize(popup_w, popup_h)

        caret = self.cursorRect()
        vp_offset = self.viewport().pos()
        x = vp_offset.x() + caret.left()
        y_below = vp_offset.y() + caret.bottom() + 4
        y_above = vp_offset.y() + caret.top() - popup_h - 4

        max_x = max(8, self.width() - popup_w - 8)
        x = max(8, min(x, max_x))
        if y_below + popup_h <= self.height() - 8:
            y = y_below
        elif y_above >= 8:
            y = y_above
        else:
            y = max(8, self.height() - popup_h - 8)
        self.popup.move(x, y)

    def _replace_span(self, start: int, end: int, text: str, cursor_offset: int | None = None):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        if cursor_offset is not None:
            cursor.setPosition(start + cursor_offset)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def accept_completion(self) -> bool:
        item = self.popup.current_item()
        if item is None:
            self.popup.hide()
            return False
        if item.action == 'add_dict' and self.spell is not None:
            self.spell.add_word(item.insert_text)
            if self.rehighlight_callback:
                self.rehighlight_callback()
            self.popup.hide()
            return True
        if item.action == 'ignore_word' and self.spell is not None:
            self.spell.ignore_word(item.insert_text)
            if self.rehighlight_callback:
                self.rehighlight_callback()
            self.popup.hide()
            return True

        start, end = self._replace_range
        self._replace_span(start, end, item.insert_text, item.cursor_offset)
        self.popup.hide()
        if item.kind == 'FILE' and item.insert_text.endswith('/'):
            self.trigger_completions(explicit=True)
        return True

    def _try_autocorrect(self, boundary_char: str):
        if self.spell is None or not self.spell.auto_correct_enabled:
            return
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        if boundary_char in ('\r', '\n'):
            block = cursor.block().previous()
            if not block.isValid() or block.userState() in (1, 2, 3):
                return
            line = block.text()
            col = len(line)
        else:
            block = cursor.block()
            if not block.isValid() or block.userState() in (1, 2, 3):
                return
            line = block.text()
            col = cursor.positionInBlock() - len(boundary_char)
        if col <= 0:
            return
        stripped = line.lstrip()
        if stripped.startswith(('```', '~~~', '$$', '---')):
            return
        hit = self.spell.word_at_position(line, col)
        if hit is None:
            return
        w_start, w_len, word = hit
        if w_start + w_len != col:
            return
        replacement = self.spell.auto_correct(word)
        if not replacement or replacement == word:
            return
        abs_start = block.position() + w_start
        abs_end = abs_start + w_len
        prev_pos = cursor.position()
        delta = len(replacement) - w_len
        edit = self.textCursor()
        edit.beginEditBlock()
        edit.setPosition(abs_start)
        edit.setPosition(abs_end, QTextCursor.MoveMode.KeepAnchor)
        edit.insertText(replacement)
        edit.endEditBlock()
        new_cursor = self.textCursor()
        new_cursor.setPosition(prev_pos + delta)
        self.setTextCursor(new_cursor)
        self._last_autocorrect = (abs_start, word, replacement)

    def _misspelled_word_at(self, cursor: QTextCursor):
        if self.spell is None or not self.spell.enabled:
            return None
        block = cursor.block()
        if not block.isValid() or block.userState() in (1, 2, 3):
            return None
        line = block.text()
        hit = self.spell.word_at_position(line, cursor.positionInBlock())
        if hit is None:
            return None
        w_start, w_len, word = hit
        if self.spell.is_correct(word):
            return None
        return block.position() + w_start, block.position() + w_start + w_len, word

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        if self.spell is not None and self.spell.enabled:
            hit = self._misspelled_word_at(self.cursorForPosition(event.pos()))
            if hit is not None:
                start, end, word = hit
                first_action = menu.actions()[0] if menu.actions() else None
                suggestions = self.spell.suggestions(word, limit=5)
                if suggestions:
                    bold_font = QFont(menu.font())
                    bold_font.setBold(True)
                    for sug in suggestions:
                        action = QAction(sug, menu)
                        action.setFont(bold_font)
                        action.triggered.connect(
                            lambda checked=False, s=start, e=end, r=sug: self._replace_span(s, e, r)
                        )
                        menu.insertAction(first_action, action)
                else:
                    empty = QAction('No spelling suggestions', menu)
                    empty.setEnabled(False)
                    menu.insertAction(first_action, empty)
                menu.insertSeparator(first_action)
                add_action = QAction(f'Add "{word}" to dictionary', menu)
                add_action.triggered.connect(lambda checked=False, w=word: self._add_to_dictionary(w))
                menu.insertAction(first_action, add_action)
                ignore_action = QAction(f'Ignore "{word}"', menu)
                ignore_action.triggered.connect(lambda checked=False, w=word: self._ignore_word(w))
                menu.insertAction(first_action, ignore_action)
                menu.insertSeparator(first_action)

            menu.addSeparator()
            toggle_ac = QAction('Auto-correct typos', menu)
            toggle_ac.setCheckable(True)
            toggle_ac.setChecked(self.spell.auto_correct_enabled)
            toggle_ac.toggled.connect(self.spell.set_auto_correct)
            menu.addAction(toggle_ac)

        menu.exec(event.globalPos())

    def _add_to_dictionary(self, word: str):
        if self.spell is not None:
            self.spell.add_word(word)
            if self.rehighlight_callback:
                self.rehighlight_callback()

    def _ignore_word(self, word: str):
        if self.spell is not None:
            self.spell.ignore_word(word)
            if self.rehighlight_callback:
                self.rehighlight_callback()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        # Immediate Ctrl+Z after auto-correct reverts it and ignores that word for the session
        is_undo = event.matches(QKeySequence.StandardKey.Undo) or (
            key == Qt.Key.Key_Z and mods == Qt.KeyboardModifier.ControlModifier
        )
        if is_undo and self._last_autocorrect is not None:
            pos, original, replacement = self._last_autocorrect
            self._last_autocorrect = None
            super().keyPressEvent(event)
            if self.spell is not None and self.toPlainText()[pos:pos + len(original)] == original:
                self.spell.ignore_word(original)
                if self.rehighlight_callback:
                    self.rehighlight_callback()
            self.popup.hide()
            return

        # Ctrl+Space manually triggers completion popup
        if key == Qt.Key.Key_Space and (mods & Qt.KeyboardModifier.ControlModifier):
            self.trigger_completions(explicit=True)
            event.accept()
            return

        # Alt+Enter triggers JetBrains-style spelling quick-fix
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (mods & Qt.KeyboardModifier.AltModifier):
            if self.trigger_quick_fix():
                event.accept()
                return

        if self.popup.isVisible():
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept_completion()
                event.accept()
                return
            if key == Qt.Key.Key_Escape:
                self.popup.hide()
                event.accept()
                return
            if key == Qt.Key.Key_Down:
                self.popup.move_selection(1)
                event.accept()
                return
            if key == Qt.Key.Key_Up:
                self.popup.move_selection(-1)
                event.accept()
                return
            if key == Qt.Key.Key_PageDown:
                self.popup.move_selection(5)
                event.accept()
                return
            if key == Qt.Key.Key_PageUp:
                self.popup.move_selection(-5)
                event.accept()
                return
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
                self.popup.hide()

        if key not in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            self._last_autocorrect = None
        super().keyPressEvent(event)

        # Do not pop up on Ctrl/Alt/Meta shortcuts (e.g. Ctrl+E, Ctrl+S, Ctrl+Z)
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
            self.popup.hide()
            return

        text = event.text()
        if key == Qt.Key.Key_Backspace:
            if self.popup.isVisible():
                self.trigger_completions(explicit=False)
            return
        if not text:
            return
        if text in self.BOUNDARY_CHARS:
            self.popup.hide()
            self._try_autocorrect(text)
            return
        if text.isalnum() or text in '_-/`~[!(\\#@."\'<>:':
            self.trigger_completions(explicit=False)
        else:
            self.popup.hide()

    def mousePressEvent(self, event):
        self.popup.hide()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        self.popup.hide()
        super().focusOutEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.popup.isVisible():
            self._position_popup(self.popup.list.count())
