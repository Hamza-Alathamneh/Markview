"""Cross-platform Markdown-aware spell checking and safe auto-correct."""
from bisect import bisect_left
from difflib import SequenceMatcher
from functools import lru_cache
import gzip
from pathlib import Path
import re

from PySide6.QtCore import QSettings

WORDLIST_PATH = Path(__file__).resolve().parent / 'markview-files' / 'en_words.txt.gz'
SYSTEM_WORDLISTS = (
    Path('/usr/share/dict/words'),
    Path('/usr/share/dict/american-english'),
)

COMMON_TYPOS = {
    'teh': 'the', 'hte': 'the', 'adn': 'and', 'nad': 'and', 'taht': 'that',
    'tath': 'that', 'wiht': 'with', 'wtih': 'with', 'thier': 'their',
    'waht': 'what', 'whta': 'what', 'wich': 'which', 'whcih': 'which',
    'becuase': 'because', 'beacuse': 'because', 'becasue': 'because',
    'recieve': 'receive', 'recieved': 'received', 'recieving': 'receiving',
    'writting': 'writing', 'writen': 'written', 'seperate': 'separate',
    'seperately': 'separately', 'definately': 'definitely', 'definitly': 'definitely',
    'occured': 'occurred', 'occurence': 'occurrence', 'ocurred': 'occurred',
    'langauge': 'language', 'freind': 'friend', 'untill': 'until',
    'compatable': 'compatible', 'compatble': 'compatible', 'exmaple': 'example',
    'docuemnt': 'document', 'documnt': 'document', 'fucntion': 'function',
    'funtion': 'function', 'varibale': 'variable', 'retrun': 'return',
    'improt': 'import', 'progam': 'program', 'progarm': 'program',
    'preveiw': 'preview', 'markdwon': 'markdown', 'sucess': 'success',
    'succesful': 'successful', 'adress': 'address', 'begining': 'beginning',
    'beleive': 'believe', 'calender': 'calendar', 'comming': 'coming',
    'completly': 'completely', 'concious': 'conscious', 'diffrent': 'different',
    'enviroment': 'environment', 'existance': 'existence', 'foriegn': 'foreign',
    'goverment': 'government', 'grammer': 'grammar', 'happend': 'happened',
    'immediatly': 'immediately', 'independant': 'independent', 'knowlege': 'knowledge',
    'libary': 'library', 'maintenence': 'maintenance', 'mispell': 'misspell',
    'neccessary': 'necessary', 'necesary': 'necessary', 'noticable': 'noticeable',
    'parrallel': 'parallel', 'persistant': 'persistent', 'posession': 'possession',
    'prefered': 'preferred', 'priviledge': 'privilege', 'publically': 'publicly',
    'realy': 'really', 'refered': 'referred', 'relavant': 'relevant',
    'rember': 'remember', 'repitition': 'repetition', 'rythm': 'rhythm',
    'schedual': 'schedule', 'similiar': 'similar', 'sincerly': 'sincerely',
    'speach': 'speech', 'suprise': 'surprise', 'temperture': 'temperature',
    'tommorow': 'tomorrow', 'tounge': 'tongue', 'truely': 'truly',
    'unfortunatly': 'unfortunately', 'usefull': 'useful', 'vaccum': 'vacuum',
    'wether': 'whether', 'alot': 'a lot', 'mesage': 'message', 'mesages': 'messages',
    'tpying': 'typing', 'wrod': 'word', 'thign': 'thing', 'windwo': 'window',
    'dont': "don't", 'doesnt': "doesn't", 'didnt': "didn't", 'cant': "can't",
    'wont': "won't", 'isnt': "isn't", 'arent': "aren't", 'wasnt': "wasn't",
    'werent': "weren't", 'hasnt': "hasn't", 'havent': "haven't", 'hadnt': "hadn't",
    'couldnt': "couldn't", 'wouldnt': "wouldn't", 'shouldnt': "shouldn't",
    'im': "I'm", 'ive': "I've", 'youre': "you're", 'theyre': "they're",
    'thats': "that's", 'whats': "what's", 'theres': "there's", 'heres': "here's",
    'lets': "let's", 'whos': "who's", 'iam': "I am",
    'abotu': 'about', 'accomodate': 'accommodate', 'acheive': 'achieve',
    'acress': 'across', 'agressive': 'aggressive', 'apparant': 'apparent',
    'arguement': 'argument', 'assasination': 'assassination', 'basicly': 'basically',
    'bussiness': 'business', 'catagory': 'category', 'cemetary': 'cemetery',
    'collegue': 'colleague', 'commitee': 'committee', 'concensus': 'consensus',
    'curiousity': 'curiosity', 'desparate': 'desperate', 'dilema': 'dilemma',
    'disapear': 'disappear', 'disapoint': 'disappoint', 'embarass': 'embarrass',
    'explaination': 'explanation', 'familar': 'familiar', 'finaly': 'finally',
    'flourescent': 'fluorescent', 'foward': 'forward', 'gaurd': 'guard',
    'glamourous': 'glamorous', 'greatful': 'grateful', 'guarentee': 'guarantee',
    'harrass': 'harass', 'humourous': 'humorous', 'ignorence': 'ignorance',
    'interupt': 'interrupt', 'irresistable': 'irresistible', 'jelousy': 'jealousy',
    'liason': 'liaison', 'lollypop': 'lollipop', 'millenium': 'millennium',
    'miniscule': 'minuscule', 'mischevious': 'mischievous', 'momento': 'memento',
    'naturaly': 'naturally', 'nieghbor': 'neighbor', 'ocassion': 'occasion',
    'oficial': 'official', 'oportunity': 'opportunity', 'orginal': 'original',
    'outragous': 'outrageous', 'particulary': 'particularly', 'passtime': 'pastime',
    'percieve': 'perceive', 'personel': 'personnel', 'pharoah': 'pharaoh',
    'peice': 'piece', 'playwrite': 'playwright', 'politican': 'politician',
    'potatos': 'potatoes', 'preceeding': 'preceding', 'presance': 'presence',
    'probaly': 'probably', 'profesional': 'professional', 'promiss': 'promise',
    'pronounciation': 'pronunciation', 'proove': 'prove', 'psycic': 'psychic',
    'que': 'queue', 'queston': 'question', 'reccomend': 'recommend',
    'rediculous': 'ridiculous', 'refering': 'referring', 'relevent': 'relevant',
    'religous': 'religious', 'reminise': 'reminisce', 'resistence': 'resistance',
    'sargent': 'sergeant', 'scedule': 'schedule', 'scissers': 'scissors',
    'sence': 'sense', 'sentance': 'sentence', 'shoud': 'should',
    'sieze': 'seize', 'sofware': 'software', 'somthing': 'something',
    'studing': 'studying', 'subconcious': 'subconscious', 'supercede': 'supersede',
    'surpress': 'suppress', 'tendancy': 'tendency', 'therefor': 'therefore',
    'threshhold': 'threshold', 'tomatos': 'tomatoes', 'transfered': 'transferred',
    'twelth': 'twelfth', 'tyrany': 'tyranny', 'underate': 'underrate',
    'unecessary': 'unnecessary', 'upholstry': 'upholstery',
    'usible': 'usable', 'visable': 'visible', 'warrantly': 'warranty',
    'wednesday': 'Wednesday', 'wierd': 'weird', 'whereever': 'wherever',
    'whitch': 'which', 'wihch': 'which', 'workng': 'working', 'yeild': 'yield',
}

TECH_WHITELIST = {
    'markview', 'crossnote', 'markdown', 'mermaid', 'graphviz', 'katex', 'mathjax',
    'wayland', 'hyprland', 'pyside', 'shiboken', 'fedora', 'ubuntu', 'debian', 'arch',
    'linux', 'macos', 'windows', 'github', 'gitlab', 'vscode', 'nodejs', 'npm', 'nvm',
    'fnm', 'volta', 'scoop', 'homebrew', 'venv', 'pip', 'pipx', 'setuptools', 'pyproject',
    'localhost', 'json', 'yaml', 'toml', 'html', 'css', 'svg', 'png', 'jpg', 'jpeg',
    'webp', 'gif', 'ico', 'avif', 'bmp', 'pdf', 'utf', 'ascii', 'bom', 'crlf', 'lf',
    'regex', 'symlink', 'symlinks', 'stylesheet', 'stylesheets', 'webview', 'webengine',
    'chromium', 'frontend', 'backend', 'codebase', 'filename', 'filenames', 'filepath',
    'tooltip', 'tooltips', 'checkbox', 'checkboxes', 'blockquote', 'blockquotes',
    'callout', 'callouts', 'admonition', 'admonitions', 'autocomplete', 'autocorrect',
    'spellcheck', 'spellchecker', 'reinstall', 'uninstall', 'powershell', 'dotfiles',
    'repo', 'repos', 'config', 'configs', 'cli', 'gui', 'async', 'todo', 'todos',
    'subfolder', 'subfolders', 'subdirectory', 'subdirectories', 'screenshot', 'screenshots',
    'previewer', 'distro', 'distros', 'dropdown', 'scrollbar', 'scrollbars', 'toolbar',
    'sidebar', 'metadata', 'frontmatter', 'url', 'urls', 'uri', 'uris', 'api', 'apis',
    'sdk', 'ide', 'dom', 'csp', 'wasm', 'tex', 'tikz', 'latex', 'pandoc', 'plantuml',
    'wavedrom', 'vega', 'qt', 'xdg', 'appdata', 'localappdata', 'stdin', 'stdout', 'stderr',
    'subprocess', 'subprocesses', 'runtime', 'unencoded', 'sandboxed', 'unsandboxed',
    'installable', 'jetbrains', 'pycharm', 'intellij', 'webstorm', 'offline', 'online',
    'darkmode', 'lightmode', 'clickable', 'resize', 'resized', 'resizing', 'rehighlight',
    'criticmarkup', 'flowchart', 'digraph', 'subgraph', 'rankdir', 'ok', 'vs', 'etc',
}

MASK_PATTERNS = [
    re.compile(r'^\s*@import\s+.*$'),
    re.compile(r'(`+)(?:[^`]|`(?!\1))*?\1'),
    re.compile(r'(?<!\\)\$[^$\n]+(?<!\\)\$'),
    re.compile(r'</?[A-Za-z][^>\n]*>'),
    re.compile(r'(?:https?|file|mailto)://[^\s)>\]]+|mailto:[^\s)>\]]+|www\.[^\s)>\]]+', re.IGNORECASE),
    re.compile(r'(?<=\])\([^)\n]*\)'),
    re.compile(r'\[![A-Za-z]+\]|\[TOC\]|\[\^[^\]]+\]'),
    re.compile(r'\b\w*_\w*\b'),
    re.compile(r'\b\w*\d\w*\b'),
]

PLAIN_WORD_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]+(?:'[A-Za-z]+)?(?![A-Za-z0-9_])")
ALPHABET = 'abcdefghijklmnopqrstuvwxyz'


def _damerau_distance(a: str, b: str) -> int:
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return 3
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i] + [0] * lb
        ai = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ai == b[j - 1] else 1
            val = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ai == b[j - 2] and a[i - 2] == b[j - 1]:
                val = min(val, prev2[j - 2] + 1)
            curr[j] = val
        prev2, prev = prev, curr
    return prev[lb]


def _is_adjacent_transposition(a: str, b: str) -> bool:
    if len(a) != len(b) or a == b:
        return False
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    return len(diffs) == 2 and diffs[1] == diffs[0] + 1 and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]


def _match_case(original: str, replacement: str) -> str:
    if not original or not replacement:
        return replacement
    if replacement.startswith(("I'", "I ")) or replacement[0].isupper():
        return replacement.upper() if original.isupper() and len(original) > 1 else replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _edits1(word: str) -> set[str]:
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [a + b[1:] for a, b in splits if b]
    transposes = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1]
    replaces = [a + c + b[1:] for a, b in splits if b for c in ALPHABET]
    inserts = [a + c + b for a, b in splits for c in ALPHABET]
    return set(deletes + transposes + replaces + inserts)


def _load_wordlist() -> frozenset[str]:
    if WORDLIST_PATH.is_file():
        try:
            with gzip.open(WORDLIST_PATH, 'rt', encoding='ascii') as fh:
                return frozenset(line.strip() for line in fh if line.strip())
        except OSError:
            pass
    for path in SYSTEM_WORDLISTS:
        if path.is_file():
            try:
                raw = path.read_text(encoding='utf-8', errors='ignore').splitlines()
                return frozenset(w.lower() for w in raw if w.isascii() and w.isalpha())
            except OSError:
                pass
    return frozenset()


class SpellChecker:
    """Markdown-aware spell checker with Hunspell/PySpellChecker/offline-wordlist backends."""

    def __init__(self, settings: QSettings | None = None, use_default_settings: bool = True):
        if settings is not None:
            self.settings = settings
        elif use_default_settings:
            self.settings = QSettings('Markview', 'Markview')
        else:
            self.settings = None

        self._enchant = None
        self._pyspell = None
        self._words: frozenset[str] = frozenset()
        self._sorted_words: tuple[str, ...] | None = None
        self._init_backend()

        self.enabled: bool = True
        self.custom_words: set[str] = set()
        self.ignored_words: set[str] = set()
        self.auto_correct_enabled: bool = True
        self._load_preferences()
        self._check_cache: dict[str, bool] = {}

    def _init_backend(self):
        try:
            import enchant  # type: ignore
            for lang in ('en_US', 'en_GB', 'en'):
                if enchant.dict_exists(lang):
                    self._enchant = enchant.Dict(lang)
                    return
        except Exception:
            pass
        try:
            from spellchecker import SpellChecker as PySpellChecker  # type: ignore
            self._pyspell = PySpellChecker()
            return
        except Exception:
            pass
        self._words = _load_wordlist()

    @property
    def backend_name(self) -> str:
        if self._enchant is not None:
            return 'enchant'
        if self._pyspell is not None:
            return 'pyspellchecker'
        if self._words:
            return 'wordlist'
        return 'none'

    def _load_preferences(self):
        if self.settings is None:
            return
        saved = self.settings.value('spelling/custom_words', [])
        if isinstance(saved, str):
            saved = [saved] if saved else []
        elif not isinstance(saved, (list, tuple)):
            saved = []
        self.custom_words = {str(w).lower() for w in saved if w}
        raw_ac = self.settings.value('spelling/auto_correct', True)
        if isinstance(raw_ac, str):
            self.auto_correct_enabled = raw_ac.lower() not in {'false', '0', 'no'}
        else:
            self.auto_correct_enabled = bool(raw_ac)

    def set_auto_correct(self, enabled: bool):
        self.auto_correct_enabled = bool(enabled)
        if self.settings is not None:
            self.settings.setValue('spelling/auto_correct', self.auto_correct_enabled)
            self.settings.sync()

    def add_word(self, word: str):
        low = word.strip().lower()
        if not low:
            return
        self.custom_words.add(low)
        self._check_cache.clear()
        if self.settings is not None:
            self.settings.setValue('spelling/custom_words', sorted(self.custom_words))
            self.settings.sync()

    def ignore_word(self, word: str):
        low = word.strip().lower()
        if low:
            self.ignored_words.add(low)
            self._check_cache.clear()

    def should_skip(self, word: str) -> bool:
        if len(word) < 2 or not word.isascii():
            return True
        if any(ch.isdigit() for ch in word):
            return True
        # Skip ALL-CAPS acronyms (HTML, JSON, API) and camelCase / PascalCase identifiers
        if word.isupper() and len(word) >= 2:
            return True
        if any(ch.isupper() for ch in word[1:]):
            return True
        low = word.lower()
        if low in TECH_WHITELIST or low in self.custom_words or low in self.ignored_words:
            return True
        return False

    def _backend_check(self, word: str) -> bool:
        low = word.lower()
        if self._enchant is not None:
            return bool(self._enchant.check(word) or (low != word and self._enchant.check(low)))
        if self._pyspell is not None:
            return low in self._pyspell
        if self._words:
            return low in self._words
        return True

    def is_correct(self, word: str) -> bool:
        if self.should_skip(word):
            return True
        cached = self._check_cache.get(word)
        if cached is not None:
            return cached
        low = word.lower()
        # Explicitly flag high-confidence typos (e.g., "dont", "cant", "teh", "wich")
        if low in COMMON_TYPOS and COMMON_TYPOS[low].lower() != low:
            self._check_cache[word] = False
            return False
        ok = self._backend_check(word)
        if not ok and low.endswith("'s") and len(low) > 3:
            stem = word[:-2]
            ok = self.should_skip(stem) or self._backend_check(stem)
        self._check_cache[word] = ok
        return ok

    @lru_cache(maxsize=512)
    def _raw_suggestions(self, word: str) -> tuple[str, ...]:
        low = word.lower()
        results: list[str] = []
        seen: set[str] = set()

        def push(cand: str):
            c = cand.strip()
            if c and c.lower() not in seen and c.lower() != low:
                seen.add(c.lower())
                results.append(c)

        if low in COMMON_TYPOS:
            push(COMMON_TYPOS[low])

        if self._enchant is not None:
            for cand in self._enchant.suggest(word)[:10]:
                push(cand)
        elif self._pyspell is not None:
            top = self._pyspell.correction(low)
            if top:
                push(top)
            for cand in sorted(self._pyspell.candidates(low) or (), key=lambda w: _damerau_distance(low, w)):
                push(cand)
        elif self._words:
            e1 = _edits1(low)
            collapsed_low = re.sub(r'(.)\1+', r'\1', low)
            hits1 = [w for w in e1 if w in self._words]
            hits1.sort(key=lambda w: (
                not _is_adjacent_transposition(low, w),
                re.sub(r'(.)\1+', r'\1', w) != collapsed_low,
                w[0] != low[0],
                -SequenceMatcher(None, low, w).ratio(),
                abs(len(w) - len(low)),
                w,
            ))
            for cand in hits1[:8]:
                push(cand)
            if len(results) < 4 and len(low) <= 11:
                hits2 = set()
                for mid in e1:
                    for w in _edits1(mid):
                        if w in self._words and w not in seen:
                            hits2.add(w)
                ranked2 = sorted(hits2, key=lambda w: (
                    w[0] != low[0],
                    abs(len(w) - len(low)),
                    -SequenceMatcher(None, low, w).ratio(),
                    w,
                ))
                for cand in ranked2[:6]:
                    push(cand)

        return tuple(results[:10])

    def suggestions(self, word: str, limit: int = 6) -> list[str]:
        return [_match_case(word, cand) for cand in self._raw_suggestions(word)[:limit]]

    def auto_correct(self, word: str) -> str | None:
        """Return a safe automatic correction, or None when uncertain."""
        if not self.enabled or not self.auto_correct_enabled or self.is_correct(word):
            return None
        low = word.lower()
        if low in COMMON_TYPOS:
            target = COMMON_TYPOS[low]
            return _match_case(word, target) if target.lower() != low else None

        # Only auto-correct unambiguous lowercase typos (avoid mutating proper names)
        if not (word.islower() and word.isalpha() and len(word) >= 4):
            return None

        cands = [c for c in self._raw_suggestions(word) if c.isalpha() and c.islower()]
        if not cands:
            return None

        transpositions = [c for c in cands if _is_adjacent_transposition(low, c)]
        if len(transpositions) == 1:
            return transpositions[0]

        dist1_same_start = [c for c in cands if _damerau_distance(low, c) == 1 and c[0] == low[0]]
        if len(dist1_same_start) == 1:
            return dist1_same_start[0]
        return None

    @staticmethod
    def mask_markdown_line(line: str) -> str:
        masked = line
        for pattern in MASK_PATTERNS:
            masked = pattern.sub(lambda m: ' ' * (m.end() - m.start()), masked)
        return masked

    def find_misspelled(self, line: str) -> list[tuple[int, int, str]]:
        """Return (start, length, word) spans for misspelled words in a Markdown line."""
        if not self.enabled or self.backend_name == 'none':
            return []
        masked = self.mask_markdown_line(line)
        errors = []
        for match in PLAIN_WORD_RE.finditer(masked):
            word = match.group(0)
            if not self.is_correct(word):
                errors.append((match.start(), match.end() - match.start(), word))
        return errors

    def complete_prefix(self, prefix: str, limit: int = 8) -> list[str]:
        """Fast O(log N) English dictionary prefix suggestions for the word dropdown."""
        if not prefix or not prefix.isascii() or not prefix.isalpha() or len(prefix) < 2:
            return []
        if self._sorted_words is None:
            words = self._words or _load_wordlist()
            self._sorted_words = tuple(sorted(w for w in words if w.isalpha()))
        if not self._sorted_words:
            return []
        low = prefix.lower()
        idx = bisect_left(self._sorted_words, low)
        matches = []
        upper = min(len(self._sorted_words), idx + 200)
        for i in range(idx, upper):
            cand = self._sorted_words[i]
            if not cand.startswith(low):
                break
            if cand != low and len(cand) <= len(low) + 12:
                matches.append(cand)
        # Prefer concise, natural English words over long obscure derivatives
        matches.sort(key=lambda w: (len(w), w))
        return [_match_case(prefix, w) for w in matches[:limit]]

    def word_at_position(self, line: str, col: int) -> tuple[int, int, str] | None:
        """Return (start, length, word) if col lies on a spell-checkable word in line."""
        masked = self.mask_markdown_line(line)
        for match in PLAIN_WORD_RE.finditer(masked):
            if match.start() <= col <= match.end():
                return match.start(), match.end() - match.start(), match.group(0)
        return None
