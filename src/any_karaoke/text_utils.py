import re

DEFAULT_SPLIT_MARKERS = [",", ";", "!", "."]


def split_into_sub_sentences(text, num_sub_sentences, split_markers=DEFAULT_SPLIT_MARKERS):
    """Split text into roughly equal chunks, preferring punctuation breaks over word breaks."""
    if not text:
        return []
    if num_sub_sentences < 2:
        return [text.strip()]

    # Use regular expression to split at specified punctuation marks
    split_text = re.split(f"[{re.escape(''.join(split_markers))}]", text)

    # Remove empty strings from the result
    split_text = [segment.strip() for segment in split_text if segment.strip()]

    # Calculate the target length for each sub-sentence
    target_length = len(text) // num_sub_sentences

    # Initialize variables
    current_sub_sentence = ""
    sub_sentences = []

    # Iterate through the split_text and group into sub-sentences
    for segment in split_text:
        if len(current_sub_sentence) + len(segment) < target_length:
            current_sub_sentence += " " + segment
        else:
            sub_sentences.append(current_sub_sentence.strip())
            current_sub_sentence = segment

    # Add the last sub-sentence
    sub_sentences.append(current_sub_sentence.strip())

    # Remove empty strings from the result
    sub_sentences = [segment.strip() for segment in sub_sentences if segment.strip()]

    # if punctuation did not give us the requested number of chunks, separate by words
    if len(sub_sentences) != num_sub_sentences:
        split_text = [segment.strip() for segment in text.split(" ") if segment.strip()]
        target_length = len(text) / num_sub_sentences

        sub_sentences = []
        current_sub_sentence = ""

        for segment in split_text:
            if len(sub_sentences) == num_sub_sentences - 1:
                current_sub_sentence += " " + segment
            elif len(current_sub_sentence) + len(segment) <= target_length:
                current_sub_sentence += " " + segment
            else:
                sub_sentences.append(current_sub_sentence.strip())
                current_sub_sentence = segment
        sub_sentences.append(current_sub_sentence.strip())
        sub_sentences = [segment.strip() for segment in sub_sentences if segment.strip()]

    return sub_sentences


def wrap_to_width(text, measure_width, max_width):
    """Greedy word wrap guaranteed to terminate.

    measure_width is a callable returning the rendered width of a string. Words that are
    wider than max_width on their own are broken character by character.
    """
    if not text:
        return []
    if max_width <= 0:
        return [text.strip()]

    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or measure_width(candidate) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word

    if current:
        lines.append(current)

    # Break any single word still too wide to fit
    wrapped = []
    for line in lines:
        if measure_width(line) <= max_width:
            wrapped.append(line)
            continue
        wrapped.extend(_break_by_character(line, measure_width, max_width))

    return [line for line in wrapped if line]


def _break_by_character(line, measure_width, max_width):
    pieces = []
    current = ""
    for character in line:
        candidate = current + character
        if current and measure_width(candidate) > max_width:
            pieces.append(current)
            current = character
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces
