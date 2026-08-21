"""Filling the reference lyrics with timings taken from the aligner output.

Two sequences of the same song: the reference lyrics have the right words but no
timings, the aligner output has timings but the words the ASR thought it heard. On the
sample track that means "Baby that's a fact" against "Maybe that's a fact", and
"ten-dollar" against "ten dollar".

They run in the same order, so it is a sequence alignment. difflib finds the runs that do
match, those anchor the timeline, and whatever falls between anchors is interpolated.
"""

import copy
import re
from difflib import SequenceMatcher

# Hyphens and slashes join words in written lyrics that the ASR emits separately
SPLIT_INSIDE_WORD = re.compile(r"[-‐-―/]+")
KEEP_IN_KEY = re.compile(r"[^\w']+", re.UNICODE)


def normalize_word(word):
    """Comparison key. Case and punctuation do not survive the trip between sources."""
    return KEEP_IN_KEY.sub("", (word or "").lower()).strip("'")


def comparison_tokens(words):
    """Split words into comparable pieces, remembering which word each piece came from.

    "ten-dollar" becomes two pieces both owned by the one reference word, so it lines up
    with the aligner's separate "ten" and "dollar".
    """
    keys, owners = [], []
    for index, word in enumerate(words):
        for piece in SPLIT_INSIDE_WORD.split(word or ""):
            key = normalize_word(piece)
            if key:
                keys.append(key)
                owners.append(index)
    return keys, owners


def timed_words(align_result):
    """Flatten the aligner segments into words that actually carry a start and an end."""
    if not align_result:
        return []

    flat = []
    for segment in align_result.get("segments", []):
        for word in segment.get("words", []):
            if word.get("start") is not None and word.get("end") is not None:
                flat.append({"word": word.get("word", ""), "start": word["start"], "end": word["end"]})
    return flat


# ================================================
# Matching
# ================================================
def _assign_direct(reference_words, reference, hypothesis, timed):
    """Copy timings across wherever the two sequences line up. Returns slots per word."""
    slots = [[] for _ in reference_words]

    reference_keys, reference_owners = reference
    hypothesis_keys, hypothesis_owners = hypothesis

    matcher = SequenceMatcher(None, reference_keys, hypothesis_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            continue  # the aligner heard something the lyrics do not have

        if tag == "delete":
            continue  # handled later by interpolation

        reference_span, hypothesis_span = i2 - i1, j2 - j1

        if tag == "equal" or reference_span == hypothesis_span:
            # Same length, so pair them off. A "replace" of equal length is a
            # misheard word rather than a structural difference.
            for offset in range(reference_span):
                word = timed[hypothesis_owners[j1 + offset]]
                slots[reference_owners[i1 + offset]].append((word["start"], word["end"], tag == "equal"))
            continue

        # Different lengths: spread the block's span evenly over the reference pieces
        block_start = timed[hypothesis_owners[j1]]["start"]
        block_end = timed[hypothesis_owners[j2 - 1]]["end"]
        step = (block_end - block_start) / reference_span if reference_span else 0
        for offset in range(reference_span):
            start = block_start + step * offset
            slots[reference_owners[i1 + offset]].append((start, start + step, False))

    return slots


def _interpolate_gaps(words):
    """Give a time to words that matched nothing, from the anchors around them."""
    interpolated = 0
    index = 0

    while index < len(words):
        if words[index]["start"] is not None:
            index += 1
            continue

        run_start = index
        while index < len(words) and words[index]["start"] is None:
            index += 1
        run_end = index  # exclusive

        before = words[run_start - 1]["end"] if run_start > 0 else None
        after = words[run_end]["start"] if run_end < len(words) else None

        if before is None and after is None:
            continue  # nothing anywhere to anchor against

        # An unmatched run at either end borrows its neighbour's edge
        span_start = before if before is not None else after
        span_end = after if after is not None else before

        # Share the gap out by word length, so long words get more of it
        weights = [max(1, len(words[i]["word"])) for i in range(run_start, run_end)]
        total = sum(weights)
        position = span_start

        for offset, i in enumerate(range(run_start, run_end)):
            share = (span_end - span_start) * weights[offset] / total
            words[i]["start"] = position
            words[i]["end"] = position + share
            words[i]["timing"] = "interpolated"
            position += share
            interpolated += 1

    return interpolated


def fill_lyrics_timings(scaffold, align_result):
    """Fill a lyrics scaffold's blank timings from the aligner's timed words.

    Returns a new scaffold. Each word gains a `timing` of "matched", "approximate" or
    "interpolated" saying how its time was arrived at, and the result carries a `timing`
    summary so a bad match is visible rather than silent.
    """
    filled = copy.deepcopy(scaffold or {})
    lines = filled.get("lines", [])

    flat_words = [word for line in lines for word in line.get("words", [])]
    timed = timed_words(align_result)

    if not flat_words or not timed:
        filled["timing"] = {"matched": 0, "approximate": 0, "interpolated": 0, "unmatched": len(flat_words)}
        filled["timing"]["coverage"] = 0.0
        return filled

    reference = comparison_tokens([word["word"] for word in flat_words])
    hypothesis = comparison_tokens([word["word"] for word in timed])
    slots = _assign_direct(flat_words, reference, hypothesis, timed)

    matched = approximate = 0
    for word, candidates in zip(flat_words, slots):
        if not candidates:
            continue
        # A word split into pieces spans from its first piece to its last
        word["start"] = min(start for start, _, _ in candidates)
        word["end"] = max(end for _, end, _ in candidates)
        if all(exact for _, _, exact in candidates):
            word["timing"] = "matched"
            matched += 1
        else:
            word["timing"] = "approximate"
            approximate += 1

    _enforce_forward_order(flat_words)
    interpolated = _interpolate_gaps(flat_words)

    for line in lines:
        _set_line_span(line)

    unmatched = sum(1 for word in flat_words if word["start"] is None)
    filled["timing"] = {
        "matched": matched,
        "approximate": approximate,
        "interpolated": interpolated,
        "unmatched": unmatched,
        "coverage": round((len(flat_words) - unmatched) / len(flat_words), 4),
    }
    return filled


def _enforce_forward_order(words):
    """Keep the timeline monotonic; a stray match must not send it backwards."""
    previous_end = None
    for word in words:
        if word["start"] is None:
            continue
        if previous_end is not None and word["start"] < previous_end:
            word["start"] = previous_end
        if word["end"] < word["start"]:
            word["end"] = word["start"]
        previous_end = word["end"]


def _set_line_span(line):
    starts = [word["start"] for word in line.get("words", []) if word["start"] is not None]
    ends = [word["end"] for word in line.get("words", []) if word["end"] is not None]
    line["start"] = min(starts) if starts else None
    line["end"] = max(ends) if ends else None
