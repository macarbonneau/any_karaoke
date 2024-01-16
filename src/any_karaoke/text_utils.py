import re


def split_into_sub_sentences(
    text, num_sub_sentences, split_markers=[",", ";", "!", "."]
):
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

    # if this fails, separate by words
    # Remove empty strings from the result
    sub_sentences = [segment.strip() for segment in sub_sentences if segment.strip()]
    if len(sub_sentences) != num_sub_sentences:
        print("OUPS!!")
        split_text = text.split(" ")
        split_text = [segment.strip() for segment in split_text if segment.strip()]
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

    return sub_sentences
