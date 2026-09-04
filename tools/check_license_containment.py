#!/usr/bin/env python3
"""check_license_containment.py — has AGPL-3.0 material from the mmx4 decomp reached psxport?

  python3 tools/check_license_containment.py                     # scan the framework checkouts it finds
  python3 tools/check_license_containment.py --psxport <dir> ...  # scan these instead
  python3 tools/check_license_containment.py --selftest           # prove it fires AND stays silent

WHY THIS EXISTS. `external/mmx4` (github.com/sozud/mmx4) is AGPL-3.0. This game repo may use it
freely; `psxport` may not, because five ports share that framework and copyleft landing there pulls
Tomba! 2, Spyro, Spider-Man and Vagrant Story into AGPL with it. That rule is only real if it is
CHECKED, so this is the check.

WHAT IT CAN DETECT (independent classes, reported separately; A/B/C are HARD, A2/B2 are ADVISORY):
  A LICENCE/SOURCE — an AGPL/Affero licence NOTICE anywhere in psxport, or a CODE/BUILD file that
                 sources from the decomp (`external/mmx4`, `sozud/mmx4`, `mmx4/src|include|config`,
                 an `#include` of a decomp header).
  A2 NAME-MENTION (advisory) — the title or the decomp merely NAMED. psxport is deliberately the home
                 of `docs/workspace/*.md`, which must name this game in order to STATE this rule, so
                 a mention is not a leak; it is summarised per file and does not fail the run.
  B IDENTIFIER — an exact whole-word match on a DISTINCTIVE identifier from the decomp's own sources.
                 "Distinctive" is subtractive and measured, not guessed: >= MINLEN chars, taken only
                 from CODE files with comments and string literals STRIPPED (mining prose for
                 "identifiers" is what made the first version report 637 English words as leaks),
                 minus every identifier in the decomp's bundled Sony PSY-Q headers (those names are
                 Sony's SDK and appear in any PSX code), minus every identifier that also appears in a
                 BASELINE of unrelated port trees. Every subtraction prints its count. That baseline is
                 a TRACKED file (docs/info/containment-baseline.txt, regenerate with
                 --write-baseline), because it used to be read from sibling port trees OUTSIDE this
                 repo: a bare clone then subtracted nothing and 27 generic words read as leaks.
  B2 MAP-NAME (advisory) — a name found ONLY in the decomp's symbol map and never in its C sources.
                 That map mixes hand-named game symbols with Sony BIOS/SPU API names (`SysEnqIntRP`,
                 `SpuClearReverbWorkArea`) that psxport's BIOS HLE legitimately names, so these are
                 expected false positives. Summarised, not counted, unless --strict.
  C PHRASE     — an exact match on a >= PHRASELEN-char comment or string literal from the decomp,
                 whitespace-normalised. Catches copied prose even when identifiers were renamed.

WHAT IT CANNOT DETECT, and no run of it should be read as evidence about these:
  - PARAPHRASE or RE-TYPED LOGIC. Same algorithm, new names, no shared comment: invisible here.
  - IDEAS, struct layouts, field offsets, address maps carried over in a human's head.
  - anything inside psxport/vendor/ (excluded by default: third-party trees whose generic PSX
    vocabulary would drown class B; pass --include-vendor to scan them anyway).
  - binary artifacts and files git ignores (build/, scratch/).
  - a leak that landed in psxport's HISTORY and was later removed. This scans the WORKING TREE.
    History is `tools/go_public.py`'s job, not this one.

Every negative prints its denominator: which trees were scanned, how many files, how many signatures
of each class, and the blind-spot list above. A run that cannot see the decomp corpus, that derives
ZERO signatures, that finds no framework checkout, that SCANS ZERO FILES (an uninitialised submodule
directory used to read as `PASS — scanned 0 text files`), or that has no generic-vocabulary baseline
to make class B mean anything, REFUSES with exit 2 rather than reporting clean.

Exit: 0 nothing found · 1 at least one hit (human adjudication required) · 2 the tool could not look.
"""
import argparse
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MINLEN = 8       # identifier signatures must be at least this long
PHRASELEN = 40   # comment/string signatures must be at least this long, after normalisation

# Class A, HARD — a psxport file that SOURCES FROM the decomp or carries its licence notice.
# Split into "anywhere" and "code/build files only" because psxport is, by design, the home of the
# workspace docs (docs/workspace/{WORKSPACE,PROTOCOL}.md), which must be able to name this game and
# this decomp in order to STATE the containment rule. Flagging that prose was this tool's second
# false-positive wave: 23 hits, every one of them a doc explaining that AGPL must stay out of psxport.
A_HARD_ANY = [
    r"GNU Affero General Public License",
    r"under the terms of the GNU Affero",
    r"Affero General Public License",
]
A_HARD_CODE = [
    r"external/mmx4",
    r"sozud/mmx4",
    r"\bmmx4/(?:src|include|config|tools)\b",
    r'#\s*include\s*[<"][^">]*mmx4',
]
# Class A, ADVISORY — the title or the decomp NAMED, without sourcing from it. Legitimate in the
# workspace docs and in bootstrap scripts that enumerate the trees; suspicious in engine code.
A_SOFT = ["mmx4", "sozud", "SLUS_005.61", "SLUS_00561", "megamanx4", "Mega Man", "MegaMan", "AGPL"]

CODE_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inl", ".s", ".cmake", ".py",
            ".sh", ".ini", ".in", ".json", ".jsonl", ".yaml", ".yml"}


def is_code_or_build(path):
    return (os.path.splitext(path)[1].lower() in CODE_EXT
            or os.path.basename(path) == "CMakeLists.txt")

# Subtrees of the decomp that are NOT the decomp's own work and must not be mined for signatures.
CORPUS_EXCLUDE_DIRS = {
    os.path.join("include", "psy-q-4.0"),   # verbatim Sony SDK headers, (C) Sony Corporation
    os.path.join("tools", "maspsx"),        # third-party submodules
    os.path.join("tools", "psximager"),
    os.path.join("tools", "asm-differ"),
    ".git",
}
SDK_DIR = os.path.join("include", "psy-q-4.0")

CORPUS_EXT = {".c", ".h", ".s", ".py", ".yaml", ".txt", ".inc"}
# Class B is mined ONLY from these: files where a token is an identifier rather than an English word.
# Everything else in the corpus still contributes class C phrases, which is the right class for prose.
IDENT_SOURCE_EXT = {".c", ".h", ".s", ".inc"}
SCAN_EXT = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inl", ".s", ".py", ".sh",
            ".cmake", ".txt", ".md", ".yaml", ".yml", ".json", ".ini", ".in", ".jsonl", ""}

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
WS_RE = re.compile(r"\s+")

# Reserved words and libc names are vocabulary, never evidence. Kept short on purpose: the real
# generic-word filter is the SDK subtraction plus the measured baseline, both of which report counts.
LANGUAGE_WORDS = {
    "unsigned", "continue", "register", "volatile", "restrict", "typedef", "sizeof", "default",
    "include", "defined", "ifndef", "endif", "return", "struct", "static", "extern", "inline",
    "memcpy", "memset", "strncpy", "strcmp", "sprintf", "printf", "malloc", "calloc", "realloc",
}


def die(msg):
    print("[containment] REFUSING: " + msg, file=sys.stderr)
    raise SystemExit(2)


def read_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None          # binary; class B/C cannot speak about it, so say nothing about it
    return raw.decode("utf-8", "replace")


# ---------------------------------------------------------------- corpus (the AGPL side)

def corpus_files(corpus):
    """(own_files, sdk_files) under the decomp checkout, or refuse if it is not there."""
    if not os.path.isdir(corpus):
        die(f"{corpus} does not exist — the mmx4 submodule is not checked out. This run compared "
            "NOTHING. `git submodule update --init external/mmx4`.")
    own, sdk = [], []
    for dirpath, dirs, files in os.walk(corpus):
        rel = os.path.relpath(dirpath, corpus)
        rel = "" if rel == "." else rel
        dirs[:] = [d for d in dirs
                   if os.path.join(rel, d) not in CORPUS_EXCLUDE_DIRS and d != ".git"]
        for f in files:
            p = os.path.join(dirpath, f)
            if os.path.splitext(f)[1].lower() in CORPUS_EXT or f.endswith(".H"):
                own.append(p)
    sdk_root = os.path.join(corpus, SDK_DIR)
    for dirpath, _dirs, files in os.walk(sdk_root):
        for f in files:
            sdk.append(os.path.join(dirpath, f))
    if not own:
        die(f"walked {corpus} and found ZERO source files to derive signatures from. A search with no "
            "signatures cannot find anything; that is not a pass.")
    return own, sdk


def strip_prose(text, hash_is_comment):
    """Remove comments and string/char literals — what is left is code, where a token is a name.

    `hash_is_comment` must be FALSE for C/C++ headers: stripping `#` lines there deletes every
    `#define`, which silently emptied the Sony-SDK subtraction set and made class B report
    `EvMdNOINTR` (a KERNEL.H macro) as a leak. In .s/.py/.sh, `#` really is a comment.
    """
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    if hash_is_comment:
        text = re.sub(r"^\s*#[^\n]*", " ", text, flags=re.M)
    text = re.sub(r'"(?:[^"\\\n]|\\.)*"', " ", text)
    text = re.sub(r"'(?:[^'\\\n]|\\.)*'", " ", text)
    return text


def hash_comments(path):
    return os.path.splitext(path)[1].lower() in {".s", ".py", ".sh", ".inc"}


def code_idents(path, text):
    return {w for w in IDENT_RE.findall(strip_prose(text, hash_comments(path))) if len(w) >= MINLEN}


def is_symbol_map(path):
    return os.path.basename(path).startswith("symbols")


def is_ident_source(path):
    """CODE files only. The symbol map is handled separately — see build_signatures."""
    return (os.path.splitext(path)[1].lower() in IDENT_SOURCE_EXT
            or os.path.basename(path).endswith(".H"))         # Sony-style uppercase headers


def phrases_from(text):
    """Comment bodies and string literals, whitespace-normalised, >= PHRASELEN chars."""
    out = set()
    for m in re.finditer(r"/\*(.*?)\*/", text, re.S):
        body = WS_RE.sub(" ", m.group(1)).strip(" *")
        if len(body) >= PHRASELEN:
            out.add(body)
    for line in text.splitlines():
        for marker in ("//", "#"):
            i = line.find(marker)
            if i >= 0:
                body = WS_RE.sub(" ", line[i + len(marker):]).strip()
                if len(body) >= PHRASELEN:
                    out.add(body)
                break
    for m in re.finditer(r'"((?:[^"\\\n]|\\.){%d,})"' % PHRASELEN, text):
        body = WS_RE.sub(" ", m.group(1)).strip()
        if len(body) >= PHRASELEN:
            out.add(body)
    return out


# ---------------------------------------------------------------- the generic-vocabulary baseline
#
# WHY THIS IS A TRACKED FILE AND NOT JUST `../<sibling>/game`. Class B's whole meaning is "DISTINCTIVE",
# and distinctiveness was defined by subtracting the vocabulary of unrelated port trees that live
# OUTSIDE this repository. A machine that clones megamanx4 alone has no siblings, so the subtraction
# silently did not happen and generic words became "signatures": MEASURED 2026-08-12 in a bare-clone
# simulation, the run printed `NO BASELINE APPLIED` and then `FAIL — 27 hit(s) in the HARD classes`,
# all 27 false positives (`checkpoint` x24, `func_8003F698` x3). A licence gate that cries wolf on
# every fresh clone gets ignored, so the exclusion set is now IN the repo, tracked and auditable.
#
# It stores the INTERSECTION (the signatures actually removed), not the siblings' whole word list:
# a few dozen reviewable names beat a megabyte of vocabulary nobody can read. Sibling trees, when
# present, are still subtracted ADDITIVELY on top — the file is a portable floor, not a ceiling.
#
# NOT INCLUDED, on purpose: psxport's own vocabulary. Subtracting the SCAN TARGET's words from the
# signature set would remove by construction whatever a leak would look like — the circular error the
# workspace already rejected once (WORKSPACE.md, `--sdk-filter K`).
BASELINE_FILE = os.path.join("docs", "info", "containment-baseline.txt")


def load_baseline_file(path):
    """-> (set_of_names, note) or (None, why) if the file is not there."""
    if not path or not os.path.isfile(path):
        return None, f"{path} not present"
    names, meta = set(), []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                meta.append(line)
                continue
            names.add(line.split()[0])
    return names, f"{len(names)} names from {path}"


def walk_vocab(dirs):
    """Every identifier >= MINLEN in these trees, with the file count. Prose included on purpose:
    a word that appears ANYWHERE in an unrelated port is not distinctive to this decomp."""
    vocab, nfiles = set(), 0
    for b in dirs:
        for dirpath, subs, files in os.walk(b):
            subs[:] = [d for d in subs if d not in (".git", "build", "scratch",
                                                    "external", "__pycache__")]
            for f in files:
                if os.path.splitext(f)[1].lower() in SCAN_EXT:
                    t = read_text(os.path.join(dirpath, f))
                    if t is not None:
                        nfiles += 1
                        vocab |= {w for w in IDENT_RE.findall(t) if len(w) >= MINLEN}
    return vocab, nfiles


def build_signatures(corpus, baselines, verbose=True, baseline_file=None,
                     require_baseline=False):
    own, sdk = corpus_files(corpus)
    idents, mapnames, phrases = set(), set(), set()
    ident_srcs, map_srcs = 0, 0
    for p in own:
        t = read_text(p)
        if t is None:
            continue
        if is_ident_source(p):
            ident_srcs += 1
            idents |= code_idents(p, t)
        elif is_symbol_map(p):
            map_srcs += 1
            for line in t.splitlines():
                m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                if m and len(m.group(1)) >= MINLEN:
                    mapnames.add(m.group(1))
        phrases |= phrases_from(t)
    raw_idents, raw_map = len(idents), len(mapnames)

    sdk_vocab = set()
    for p in sdk:
        t = read_text(p)
        if t is not None:
            # Stripped, same as the mining side: the SDK's own API names are declared in code, and a
            # wider subtraction taken from Sony's comment prose would blind class B without saying so.
            sdk_vocab |= code_idents(p, t)
    idents -= sdk_vocab
    idents -= LANGUAGE_WORDS
    mapnames -= sdk_vocab
    mapnames -= LANGUAGE_WORDS
    mapnames -= idents          # a name that also appears in the decomp's C code is class B, not B2
    after_sdk = len(idents)

    file_names, file_note = load_baseline_file(baseline_file)
    base_vocab, base_files = walk_vocab(baselines)
    if require_baseline and file_names is None and not baselines:
        die("class B has NO baseline: the tracked exclusion list is missing "
            f"({file_note}) and no unrelated port tree was found next to this repo. Without it "
            "\"distinctive\" is undefined — generic vocabulary reads as a leak (measured: 27 false "
            "HARD hits in a bare clone). Subtracted NOTHING, so this run compared signatures that are "
            "not evidence. Restore the file, or regenerate it with "
            "`--write-baseline` next to the sibling port trees, or pass --no-baseline to audit anyway.")
    excluded = (file_names or set()) | base_vocab
    idents -= excluded
    mapnames -= excluded
    if verbose:
        print(f"[containment] corpus: {len(own)} decomp source files under {corpus}")
        print(f"[containment]   identifiers >= {MINLEN} chars from {ident_srcs} CODE files "
              f"(comments and string literals stripped): {raw_idents}")
        print(f"[containment]   minus Sony PSY-Q SDK vocabulary ({len(sdk_vocab)} names from "
              f"{len(sdk)} files in {SDK_DIR}): {after_sdk}")
        if file_names is not None:
            print(f"[containment]   minus the TRACKED generic-vocabulary exclusion list "
                  f"({file_note}) — portable, works in a bare clone")
        else:
            print(f"[containment]   NO TRACKED EXCLUSION LIST ({file_note}) — "
                  + ("relying on the sibling port trees instead, which a bare clone will NOT have."
                     if baselines else
                     "and no sibling port tree either: class B subtracted NOTHING and its hits are "
                     "NOT evidence (--no-baseline was passed, or the file was deleted)."))
        if baselines:
            print(f"[containment]   minus sibling port-tree vocabulary ({len(base_vocab)} names from "
                  f"{base_files} files in {len(baselines)} unrelated tree(s))")
        print(f"[containment]   class B signatures after every subtraction: {len(idents)}")
        print(f"[containment]   symbol-map-ONLY names from {map_srcs} map file(s) (class B2,"
              f"ADVISORY — a decomp symbol map also lists Sony BIOS/SPU API names): "
              f"{len(mapnames)} of {raw_map}")
        print(f"[containment]   phrase signatures >= {PHRASELEN} chars: {len(phrases)}")
    if not idents and not phrases:
        die("derived ZERO identifier and ZERO phrase signatures from the corpus. Nothing could have "
            "matched; reporting a clean tree here would be a lie.")
    return idents, mapnames, phrases, {"corpus_files": len(own), "sdk_names": len(sdk_vocab),
                                       "idents": len(idents), "mapnames": len(mapnames),
                                       "phrases": len(phrases), "baseline_files": base_files,
                                       "baseline_note": file_note if file_names is not None
                                       else "NO tracked exclusion list: " + file_note,
                                       "baseline_dirs": len(baselines),
                                       "raw_idents": raw_idents,
                                       "after_sdk": after_sdk}


def write_baseline(corpus, baselines, path):
    """Regenerate the tracked exclusion list: the signatures that unrelated ports also use.

    Refuses if there is no sibling tree to learn from — writing an EMPTY exclusion list would look
    like a baseline and subtract nothing, which is the failure this file exists to prevent.
    """
    if not baselines:
        die("--write-baseline found no unrelated port tree to learn generic vocabulary FROM (looked "
            f"for {', '.join(SIBLING_TREES)} next to {os.path.abspath(os.path.join(ROOT, '..'))}). "
            "Writing an empty list would be a baseline in name only.")
    idents, mapnames, _phrases, _st = build_signatures(corpus, [], verbose=False)
    vocab, nfiles = walk_vocab(baselines)
    hit = sorted((idents | mapnames) & vocab)
    if not hit:
        die(f"the {len(idents | mapnames)} signatures and the {len(vocab)} names from "
            f"{nfiles} files in {len(baselines)} sibling tree(s) INTERSECT IN NOTHING. Either the "
            "sibling trees are empty or the mining changed shape; an empty list is not a baseline.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# containment-baseline.txt — generic vocabulary EXCLUDED from class B.\n"
                 "# Generated by `tools/check_license_containment.py --write-baseline`. Tracked on\n"
                 "# purpose: the subtraction used to come from sibling port trees OUTSIDE this repo,\n"
                 "# so a bare clone silently subtracted nothing and generic words read as leaks.\n"
                 "#\n"
                 "# Each line is a decomp signature (identifier >= %d chars, mined from the decomp's\n"
                 "# CODE with comments and strings stripped) that ALSO occurs in an unrelated port\n"
                 "# tree, i.e. it is vocabulary rather than evidence. A real leak of one of these\n"
                 "# names is INVISIBLE to class B — that is the price, and it is why the list is\n"
                 "# short enough to read.\n"
                 "#\n"
                 "# corpus:   %s\n"
                 "# learned from: %s (%d files)\n"
                 "# signatures before this subtraction: %d\n"
                 "# excluded by this file: %d\n"
                 % (MINLEN, os.path.relpath(corpus, ROOT),
                    ", ".join(os.path.relpath(b, os.path.join(ROOT, "..")) for b in baselines),
                    nfiles, len(idents | mapnames), len(hit)))
        for n in hit:
            fh.write(n + "\n")
    print(f"[containment] wrote {len(hit)} excluded name(s) to {path} "
          f"(from {len(idents | mapnames)} signatures against {len(vocab)} names in {nfiles} files)")
    return 0


# ---------------------------------------------------------------- scan target (the psxport side)

def scan_files(tree, include_vendor):
    """Files psxport would ship: tracked + untracked-not-ignored, or a plain walk if not a git tree."""
    files, how = [], "git ls-files -co --exclude-standard"
    try:
        out = subprocess.run(["git", "-C", tree, "ls-files", "-co", "--exclude-standard"],
                             capture_output=True, text=True, timeout=120)
        # `''.split('\n')` is `['']`, which is TRUTHY — so a git command that SUCCEEDS with empty
        # output (an empty repo, or a tree every file of which is git-ignored) used to take the
        # `if rels:` branch, enumerate nothing, and let run() report a clean pass over zero files.
        # Filtering the empty strings here is what makes "git listed nothing" fall through to the
        # walk; run()'s total_scanned==0 refusal is the second, independent half of that fix.
        rels = [r for r in out.stdout.split("\n") if r] if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        rels = []
    if rels:
        for rel in rels:
            if not rel:
                continue
            if not include_vendor and rel.startswith("vendor/"):
                continue
            if os.path.splitext(rel)[1].lower() in SCAN_EXT:
                files.append(os.path.join(tree, rel))
    else:
        how = ("filesystem walk (not a git checkout, or git listed NO files — an empty checkout, "
               "or one every file of which is git-ignored)")
        for dirpath, dirs, fs in os.walk(tree):
            dirs[:] = [d for d in dirs if d not in (".git", "scratch", "__pycache__")
                       and not d.startswith("build")
                       and (include_vendor or d != "vendor")]
            for f in fs:
                if os.path.splitext(f)[1].lower() in SCAN_EXT:
                    files.append(os.path.join(dirpath, f))
    return files, how


def _word_re(words):
    return re.compile(r"\b(" + "|".join(sorted(map(re.escape, words))) + r")\b") if words else None


def scan(tree, idents, mapnames, phrases, include_vendor, self_path):
    files, how = scan_files(tree, include_vendor)
    hits, scanned = [], 0
    ident_re, map_re = _word_re(idents), _word_re(mapnames)
    for p in files:
        if os.path.abspath(p) == self_path:
            continue                      # this tool quotes the markers it hunts for
        t = read_text(p)
        if t is None:
            continue
        scanned += 1
        lines = t.splitlines()
        code = is_code_or_build(p)
        for i, line in enumerate(lines, 1):
            for pat in A_HARD_ANY + (A_HARD_CODE if code else []):
                if re.search(pat, line, re.I):
                    hits.append(("A licence/source", p, i, pat, line.strip()[:160]))
            for mk in A_SOFT:
                if mk.lower() in line.lower():
                    hits.append(("A2 name-mention", p, i, mk, line.strip()[:160]))
            if ident_re:
                for m in ident_re.finditer(line):
                    hits.append(("B identifier", p, i, m.group(1), line.strip()[:160]))
            if map_re:
                for m in map_re.finditer(line):
                    hits.append(("B2 map-name", p, i, m.group(1), line.strip()[:160]))
        flat = WS_RE.sub(" ", t)
        for ph in phrases:
            if ph in flat:
                idx = flat.index(ph)
                hits.append(("C phrase", p, 1 + t[:idx].count("\n"), ph[:80], ""))
    return hits, scanned, how, len(files)


def default_psxport_trees():
    # A SET-but-wrong $PSXPORT_DIR is a refusal, not a silent fallback: filtering it out by isdir()
    # made a typo scan a DIFFERENT checkout than the operator named, in the one tool where scanning
    # the wrong framework tree matters most. Matches code_scan.py / discdump.py, which both exit 2.
    env = os.environ.get("PSXPORT_DIR")
    if env is not None and env != "" and not os.path.isdir(env):
        die(f"$PSXPORT_DIR={env} is not a directory — refusing to silently scan a different "
            "checkout. Unset it to fall back to external/psxport, or fix the path.")
    cands = [env,
             os.path.join(ROOT, "external", "psxport"),
             os.path.abspath(os.path.join(ROOT, "..", "psxport"))]
    seen, out = set(), []
    for c in cands:
        if c and os.path.isdir(c):
            r = os.path.realpath(c)
            if r not in seen:
                seen.add(r)
                out.append(c)
    return out


SIBLING_TREES = ("Tomba2Engine", "spyro", "spider1", "vagrant")


def default_baselines():
    ws = os.path.abspath(os.path.join(ROOT, ".."))
    out = []
    for name in SIBLING_TREES:
        g = os.path.join(ws, name, "game")
        if os.path.isdir(g):
            out.append(g)
    return out


def run(corpus, trees, baselines, include_vendor, strict=False, show_advisory=False,
        baseline_file=None, require_baseline=True):
    self_path = os.path.abspath(__file__)
    if not trees:
        die("found no psxport checkout to scan (looked at $PSXPORT_DIR, "
            f"{os.path.join(ROOT, 'external/psxport')}, and ../psxport). Scanned NOTHING.")
    idents, mapnames, phrases, stats = build_signatures(corpus, baselines,
                                                        baseline_file=baseline_file,
                                                        require_baseline=require_baseline)
    total_hits, total_scanned, total_listed = [], 0, 0
    for t in trees:
        hits, scanned, how, listed = scan(t, idents, mapnames, phrases, include_vendor, self_path)
        print(f"[containment] scanned {scanned} text files ({listed} listed via {how}) in {t}"
              f"{'' if include_vendor else ' — vendor/ EXCLUDED'}")
        total_hits += hits
        total_scanned += scanned
        total_listed += listed
    # THE SECOND HALF OF THE GREEN-OVER-NOTHING FIX. The detector was never the weak part: the
    # ENUMERATOR could return nothing (an uninitialised submodule directory, a tree whose every file
    # git ignores) and the summary below would print "0 hard matches" over it. MEASURED 2026-08-12: a
    # verbatim 1163-line AGPL decomp file planted in such a tree read as `PASS — scanned 0 text files`,
    # exit 0, while the identical file in a plain directory produced 540 HARD hits, exit 1.
    if total_scanned == 0:
        die(f"scanned ZERO text files across {len(trees)} checkout(s) "
            f"({', '.join(trees)}) — {total_listed} file(s) were even enumerated. The framework "
            "checkout(s) are empty, absent or entirely git-ignored, so NOTHING was compared. This is "
            "NOT a clean tree; a leak sitting in there would have looked exactly like this. "
            "`git submodule update --init external/psxport`, or point --psxport / $PSXPORT_DIR at a "
            "populated checkout.")
    print()
    hard = [h for h in total_hits if h[0][:2] not in ("A2", "B2")]
    advisory = [h for h in total_hits if h[0][:2] in ("A2", "B2")]
    if hard:
        print(f"[containment] FAIL — {len(hard)} hit(s) in the HARD classes (A licence/source, "
              "B code identifier, C copied phrase). Each needs a human decision: remove it from "
              "psxport, or move it into this game repo.")
        for cls, p, ln, what, ctx in hard[:200]:
            print(f"  {cls:16} {p}:{ln}  <{what}>  {ctx}")
        if len(hard) > 200:
            print(f"  ... and {len(hard) - 200} more")
    if advisory:
        per = {}
        for cls, p, _ln, _w, _c in advisory:
            per[(cls, p)] = per.get((cls, p), 0) + 1
        print(f"[containment] ADVISORY — {len(advisory)} hit(s) in {len(per)} file(s), EXPECTED to be "
              "false positives, summarised not listed"
              + (" (counted toward the exit code: --strict)" if strict
                 else " (not counted toward the exit code; --strict counts them, --show-advisory "
                      "lists them)") + ":")
        print("  A2 name-mention = the title/decomp NAMED without sourcing from it. psxport is the "
              "home of docs/workspace/*.md, which must name this game to STATE the containment rule.")
        print("  B2 map-name     = a name found ONLY in the decomp's symbol map, never in its C "
              "sources. That map also lists Sony BIOS/SPU/GPU API names psxport legitimately uses.")
        for (cls, p), n in sorted(per.items(), key=lambda kv: -kv[1]):
            print(f"  {cls:16} {n:4}x  {p}")
        if show_advisory:
            for cls, p, ln, what, ctx in advisory:
                print(f"    {cls:16} {p}:{ln}  <{what}>  {ctx}")
    if hard or (strict and advisory):
        return 1
    print(f"[containment] PASS — scanned {total_scanned} text files across {len(trees)} framework "
          f"checkout(s) against {len(A_HARD_ANY) + len(A_HARD_CODE)} hard licence/source patterns, "
          f"{stats['idents']} distinctive code identifiers and {stats['phrases']} phrases from "
          f"{stats['corpus_files']} decomp source files (plus {len(A_SOFT)} advisory name markers and "
          f"{stats['mapnames']} advisory symbol-map names): 0 hard matches, "
          f"{len(advisory)} advisory.")
    print(f"[containment] class B baseline: {stats['baseline_note']}"
          f" + {stats['baseline_dirs']} sibling port tree(s)")
    print("[containment] CANNOT SEE, and this result says nothing about any of it: paraphrased or "
          "re-typed logic, renamed identifiers, struct layouts / field offsets / address maps carried "
          "in a human's head, "
          + ("" if include_vendor else "anything under vendor/, ")
          + "binary and git-ignored files, and psxport's git HISTORY (working tree only).")
    return 0


# ---------------------------------------------------------------- selftest

CLEAN_C = '''// Generic PSX port code: SDK names and ordinary prose only, nothing from the decomp.
#include <cstdint>
void frame(uint32_t* fb) {
  DrawSync(0); VSync(0); LoadImage(&rect, fb);
  // The framebuffer upload path waits on the GPU before presenting the finished frame.
  for (int i = 0; i < 16; i++) fb[i] = 0;
}
'''

DIRTY_C = '''#include "common.h"
// This file is a planted leak for the selftest.
void character_select_state_0(struct EngineObj* arg0) {
  background_objects[0].unk3 = 0;
  need_palette_load |= 1;
}
'''


# CORRECTION, 2026-08-12. An earlier version of this comment said "a fixture inside a gitignored
# directory cannot test a git-aware scanner", and moved the fixtures out to make 6 failing checks pass.
# That was fixing the fixture and leaving the LIE: the failures were the enumerator returning nothing
# (`''.split('\n') == ['']` is truthy, so the filesystem-walk fallback never ran) and run() reporting
# `PASS — scanned 0 text files`, exit 0, over it. Both halves are fixed — scan_files() falls through to
# the walk when git lists nothing, and run() refuses on total_scanned == 0 — and there is now a check
# that plants a leak in a tree whose every file git ignores and asserts it FIRES. Fixture location is
# no longer load-bearing. Keep it under the repository's gitignored scratch tree: `/tmp` is a small
# shared RAM-backed filesystem in this workspace and is forbidden even for selftest fixtures.
def _tmpdir(prefix):
    scratch = os.path.join(ROOT, "scratch", "raw")
    os.makedirs(scratch, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=scratch)


def selftest(corpus_real=None, baseline_file=None):
    corpus_real = corpus_real or os.path.join(ROOT, "external", "mmx4")
    baseline_file = baseline_file or os.path.join(ROOT, BASELINE_FILE)
    fails, checks = [], []

    with _tmpdir("containment-selftest-") as td:
        # A synthetic decomp corpus, laid out like mmx4: own sources + a Sony SDK subtree that must
        # be subtracted, and one phrase long enough to be a signature.
        corpus = os.path.join(td, "corpus")
        os.makedirs(os.path.join(corpus, "src", "main"))
        os.makedirs(os.path.join(corpus, SDK_DIR))
        with open(os.path.join(corpus, "src", "main", "character_select.c"), "w") as fh:
            fh.write('''#include "common.h"
/* The decomp's own comment, long enough to be a phrase signature in its own right. */
void character_select_state_0(struct EngineObj* arg0) {
  background_objects[0].unk3 = 0;
  need_palette_load |= 1;
  func_8001D134();
  /* The decomp USES the SDK macro, exactly as src/main/323C.c does. Without this line the
     "SDK MACRO names are subtracted" check below would pass vacuously: a name absent from the
     mining side can never become a signature, whatever the subtraction does. */
  D_80139670 = OpenEvent(SwCARD, EvSpIOE, EvMdNOINTR, NULL);
}
''')
        with open(os.path.join(corpus, SDK_DIR, "LIBGPU.H"), "w") as fh:
            fh.write("/* (C) Copyright 1993-1995 Sony Corporation. */\n"
                     "void DrawSyncCallback(void); void LoadImage(RECT*, u_long*);\n"
                     "#define EvMdNOINTR 0x2000\n"       # a MACRO: the `#`-stripping bug lost these
                     "struct DRAWENV { RECT clip; };\n")
        # A symbol map like the real one: hand-named game symbols mixed with Sony BIOS API names.
        os.makedirs(os.path.join(corpus, "config"))
        with open(os.path.join(corpus, "config", "symbols.us.txt"), "w") as fh:
            fh.write("find_free_weapon_obj = 0x8002AC0C;\nSysEnqIntRP = 0x800EE35C;\n"
                     "SpuClearReverbWorkArea = 0x800DAF48;\n")

        neg = os.path.join(td, "psxport-clean")
        os.makedirs(os.path.join(neg, "runtime"))
        with open(os.path.join(neg, "runtime", "gpu.cpp"), "w") as fh:
            fh.write(CLEAN_C)

        pos = os.path.join(td, "psxport-leaked")
        os.makedirs(os.path.join(pos, "runtime"))
        with open(os.path.join(pos, "runtime", "gpu.cpp"), "w") as fh:
            fh.write(CLEAN_C)
        with open(os.path.join(pos, "runtime", "leaked.cpp"), "w") as fh:
            fh.write('''// Taken from external/mmx4 — a class A source reference in a CODE file.
// Licensed under the terms of the GNU Affero General Public License version 3.
/* The decomp's own comment, long enough to be a phrase signature in its own right. */
void character_select_state_0(struct EngineObj* arg0) {
  background_objects[0].unk3 = 0;
  need_palette_load |= 1;
}
''')

        # A second negative tree: legitimate psxport BIOS-HLE code, which names Sony kernel APIs, plus
        # the workspace doc that STATES this containment rule and therefore has to name the decomp.
        # These are the two false-positive waves earlier versions of this tool produced (637 English
        # words, then 23 docs explaining the rule). Both must stay out of the HARD classes.
        hle = os.path.join(td, "psxport-bios-hle")
        os.makedirs(os.path.join(hle, "runtime"))
        os.makedirs(os.path.join(hle, "docs", "workspace"))
        with open(os.path.join(hle, "runtime", "hle.cpp"), "w") as fh:
            fh.write("// BIOS HLE: an event opened EvMdNOINTR (0x2000) is POLLED, not delivered.\n"
                     "void hle_sys(uint32_t fn) { /* SysEnqIntRP chain walk */ }\n"
                     "void spu_reset(void) { SpuClearReverbWorkArea(); }\n")
        with open(os.path.join(hle, "docs", "workspace", "PROTOCOL.md"), "w") as fh:
            fh.write("| `megamanx4/external/mmx4` | Mega Man X4 decomp | AGPL-3.0 | repo-local; "
                     "never lift into psxport |\n")

        idents, mapnames, phrases, _ = build_signatures(corpus, [], verbose=False)
        self_path = os.path.abspath(__file__)

        # NEGATIVE: a clean tree must produce zero hits, or the tool cries wolf and gets ignored.
        h, n, _, _ = scan(neg, idents, mapnames, phrases, False, self_path)
        checks.append(("negative: clean framework tree gives 0 hits",
                       len(h) == 0, f"{len(h)} hit(s) over {n} file(s): {h[:3]}"))

        # NEGATIVE: Sony API names, and the doc that states the rule, must produce 0 HARD hits.
        h, n, _, _ = scan(hle, idents, mapnames, phrases, False, self_path)
        hard = [x for x in h if x[0][:2] not in ("A2", "B2")]
        checks.append(("negative: BIOS-HLE code naming Sony APIs + the workspace doc that STATES this "
                       "rule give 0 HARD hits (EvMdNOINTR is a KERNEL.H macro, SysEnqIntRP is "
                       "symbol-map-only, and naming the decomp in a .md is not sourcing from it)",
                       len(hard) == 0, f"{len(hard)} hard hit(s): {hard[:3]}"))
        checks.append(("negative: that same tree DOES raise advisory hits (silence there would mean "
                       "the advisory tier is dead code)",
                       any(x[0][:2] in ("A2", "B2") for x in h),
                       f"classes seen: {sorted({x[0] for x in h})}"))

        # POSITIVE: a planted leak must fire, and every hard class must be reachable.
        h, n, _, _ = scan(pos, idents, mapnames, phrases, False, self_path)
        classes = {c for c, *_ in h}
        checks.append(("positive: planted leak fires at all", len(h) > 0,
                       f"{len(h)} hit(s) over {n} file(s)"))
        for cls, label in (("A licence/source", "AGPL notice + external/mmx4 in a .cpp"),
                           ("B identifier", "distinctive code identifier"),
                           ("C phrase", "copied comment")):
            checks.append((f"positive: class {cls} ({label}) fires", cls in classes,
                           f"classes seen: {sorted(classes)}"))

        # The SDK subtraction must actually remove Sony names, or class B would flag any PSX code.
        checks.append(("SDK vocabulary is subtracted (DrawSyncCallback is not a signature)",
                       "DrawSyncCallback" not in idents, "it IS in the signature set"))
        checks.append(("SDK MACRO names are subtracted too (EvMdNOINTR is not a signature)",
                       "EvMdNOINTR" not in idents and "EvMdNOINTR" not in mapnames,
                       "it IS in the signature set — the `#`-stripping bug is back"))
        checks.append(("a hand-named game symbol from the map is a signature "
                       "(find_free_weapon_obj)", "find_free_weapon_obj" in mapnames,
                       f"mapnames={sorted(mapnames)}"))

        # REFUSAL: a missing corpus must exit 2, never a clean pass over nothing.
        try:
            build_signatures(os.path.join(td, "no-such-corpus"), [], verbose=False)
            checks.append(("refusal: missing corpus exits 2", False, "it returned instead"))
        except SystemExit as e:
            checks.append(("refusal: missing corpus exits 2", e.code == 2, f"exit {e.code}"))

        # REFUSAL: no framework checkout to scan must exit 2 as well.
        try:
            run(corpus, [], [], False, False, False, require_baseline=False)
            checks.append(("refusal: no framework checkout exits 2", False, "it returned instead"))
        except SystemExit as e:
            checks.append(("refusal: no framework checkout exits 2", e.code == 2, f"exit {e.code}"))

        # REFUSAL: a framework checkout that EXISTS but holds nothing to scan. This is the
        # fresh-clone default — `external/psxport` present as an uninitialised submodule directory —
        # and it used to print "PASS — scanned 0 text files ... 0 hard matches", exit 0.
        empty = os.path.join(td, "psxport-empty")
        os.makedirs(empty)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                rc = run(corpus, [empty], [], False, False, False, require_baseline=False)
            checks.append(("refusal: an EMPTY framework checkout exits 2 (scanned zero files is not "
                           "a clean tree)", False, f"it returned {rc}: {out.getvalue()[-200:]}"))
        except SystemExit as e:
            checks.append(("refusal: an EMPTY framework checkout exits 2 (scanned zero files is not "
                           "a clean tree)", e.code == 2, f"exit {e.code}"))

        # POSITIVE: a leak in a tree where `git ls-files` lists NOTHING (every file git-ignored) must
        # still be found. MEASURED 2026-08-12: it reported PASS over zero files, because
        # `''.split('\n') == ['']` is truthy and the filesystem-walk fallback never ran.
        ign = os.path.join(td, "psxport-ignored")
        os.makedirs(os.path.join(ign, "runtime"))
        with open(os.path.join(ign, ".gitignore"), "w") as fh:
            fh.write("*\n")
        with open(os.path.join(ign, "runtime", "leaked.cpp"), "w") as fh:
            fh.write('''// Taken from external/mmx4 — a class A source reference in a CODE file.
void character_select_state_0(void) { need_palette_load |= 1; }
''')
        subprocess.run(["git", "init", "-q", ign], capture_output=True)
        listed, how = scan_files(ign, False)
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                rc = run(corpus, [ign], [], False, False, False, require_baseline=False)
        except SystemExit as e:
            rc = e.code
        checks.append(("positive: a leak in a tree whose every file git IGNORES is still found "
                       "(never a clean pass over zero files)", rc == 1,
                       f"exit {rc}; enumerated {len(listed)} file(s) via {how[:40]}"))

    # With the REAL corpus present, prove the real signature set is non-degenerate and still fires.
    # THE BASELINE HERE IS THE TRACKED FILE ALONE, with NO sibling port trees: that is the bare-clone
    # configuration, and it is the one the earlier version never exercised. It reported 15/15 while a
    # baseline-less bare clone FAILED with 27 false HARD hits.
    if os.path.isdir(corpus_real):
        ridents, rmap, rphrases, _ = build_signatures(corpus_real, [], verbose=False,
                                                      baseline_file=baseline_file)
        checks.append((f"real corpus at {corpus_real} yields >= 100 identifier signatures",
                       len(ridents) >= 100,
                       f"{len(ridents)} identifiers, {len(rmap)} map names, {len(rphrases)} phrases"))
        with _tmpdir("containment-real-") as td2:
            os.makedirs(os.path.join(td2, "runtime"))
            with open(os.path.join(td2, "runtime", "leak.cpp"), "w") as fh:
                fh.write(DIRTY_C)
            h, _, _, _ = scan(td2, ridents, rmap, rphrases, False, os.path.abspath(__file__))
            checks.append(("real corpus: a verbatim decomp function body fires",
                           any(c == "B identifier" for c, *_ in h), f"hits: {h[:3]}"))
            with open(os.path.join(td2, "runtime", "leak.cpp"), "w") as fh:
                fh.write(CLEAN_C)
            h, _, _, _ = scan(td2, ridents, rmap, rphrases, False, os.path.abspath(__file__))
            checks.append(("real corpus: generic SDK code stays silent", len(h) == 0, f"hits: {h}"))

        # THE BARE-CLONE NEGATIVE, and the one that fails without the tracked exclusion list: the real
        # signature set, the tracked baseline only, against a REAL psxport checkout must give 0 HARD
        # hits. Without the file this reads FAIL — 27 hits (checkpoint x24, func_8003F698 x3).
        real_trees = default_psxport_trees()
        if real_trees:
            hard = []
            for t in real_trees:
                h, _, _, _ = scan(t, ridents, rmap, rphrases, False, os.path.abspath(__file__))
                hard += [x for x in h if x[0][:2] not in ("A2", "B2")]
            checks.append(("BARE CLONE: real corpus + the TRACKED exclusion list ONLY (no sibling port "
                           f"trees) gives 0 HARD hits against {len(real_trees)} real psxport "
                           "checkout(s)", len(hard) == 0,
                           f"{len(hard)} hard hit(s): {[(x[0], x[3]) for x in hard[:6]]}"))
        else:
            checks.append(("BARE CLONE: real corpus + the tracked exclusion list against a real "
                           "psxport checkout", None,
                           "NO psxport checkout found ($PSXPORT_DIR / external/psxport / ../psxport) "
                           "— the bare-clone false-positive case was NOT exercised"))

        # REFUSAL: no baseline at all (file deleted AND no sibling tree) must refuse, because a
        # class-B result with nothing subtracted is provably not evidence.
        try:
            build_signatures(corpus_real, [], verbose=False,
                             baseline_file=os.path.join(ROOT, "docs", "info", "no-such-baseline.txt"),
                             require_baseline=True)
            checks.append(("refusal: NO baseline (no tracked list, no sibling tree) exits 2", False,
                           "it returned a signature set instead"))
        except SystemExit as e:
            checks.append(("refusal: NO baseline (no tracked list, no sibling tree) exits 2",
                           e.code == 2, f"exit {e.code}"))
    else:
        checks.append((f"real corpus at {corpus_real} present", None,
                       "NOT CHECKED OUT — the synthetic cases passed, but the real signature set was "
                       "never exercised. This selftest is weaker than it looks."))

    print("[selftest] both classes are gated; a pass means the tool can say YES and NO.")
    for name, ok, detail in checks:
        tag = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
        print(f"  [{tag}] {name}" + (f" — {detail}" if (ok is not True) else ""))
        if ok is False:
            fails.append(name)
    print(f"[selftest] {len(checks)} checks, {len(fails)} failed")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=os.path.join(ROOT, "external", "mmx4"),
                    help="the AGPL decomp checkout (default: external/mmx4)")
    ap.add_argument("--psxport", action="append", default=[],
                    help="framework checkout to scan; repeatable. Default: $PSXPORT_DIR, "
                         "external/psxport, ../psxport (whichever exist)")
    ap.add_argument("--baseline", action="append", default=None,
                    help="unrelated port tree whose vocabulary is subtracted from class B; "
                         "repeatable. Default: the sibling game trees' game/ dirs")
    ap.add_argument("--baseline-file", default=os.path.join(ROOT, BASELINE_FILE),
                    help=f"tracked list of generic names excluded from class B (default: "
                         f"{BASELINE_FILE}). This is what makes the check work in a bare clone")
    ap.add_argument("--no-baseline", action="store_true",
                    help="audit with NO generic-vocabulary subtraction at all. Over-reports by "
                         "construction (measured: 27 false HARD hits); use to see what the "
                         "exclusion list is hiding, never as a gate")
    ap.add_argument("--write-baseline", action="store_true",
                    help=f"regenerate {BASELINE_FILE} from the sibling port trees, then exit")
    ap.add_argument("--include-vendor", action="store_true",
                    help="also scan psxport/vendor/ (noisy: third-party PSX code)")
    ap.add_argument("--strict", action="store_true",
                    help="count the ADVISORY classes (A2 name-mention, B2 symbol-map name) toward "
                         "the exit code")
    ap.add_argument("--show-advisory", action="store_true",
                    help="list every advisory hit instead of summarising per file")
    ap.add_argument("--selftest", action="store_true", help="gate a positive AND a negative case")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest(a.corpus, a.baseline_file))
    baselines = a.baseline if a.baseline is not None else default_baselines()
    if a.write_baseline:
        raise SystemExit(write_baseline(a.corpus, baselines, a.baseline_file))
    trees = a.psxport or default_psxport_trees()
    if a.no_baseline:
        baselines, a.baseline_file = [], None
    raise SystemExit(run(a.corpus, trees, baselines, a.include_vendor, a.strict,
                         a.show_advisory, baseline_file=a.baseline_file,
                         require_baseline=not a.no_baseline))


if __name__ == "__main__":
    main()
