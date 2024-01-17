import whisperx
import gc
import json

device = "cuda"
audio_file = r"D:\demucs_processed_files\karaoke\favorite things\vocals.wav"
batch_size = 16  # reduce if low on GPU mem
compute_type = "float16"  # change to "int8" if low on GPU mem (may reduce accuracy)

# 1. Transcribe with original whisper (batched)
model = whisperx.load_model("large", device, compute_type=compute_type)

# save model to local path (optional)
# model_dir = "/path/"
# model = whisperx.load_model("large-v2", device, compute_type=compute_type, download_root=model_dir)

audio = whisperx.load_audio(audio_file)
result = model.transcribe(audio, batch_size=batch_size)
for i in result["segments"]:
    print(i["text"])  # before alignment

with open("whisperx.json", "w") as f:
    f.write(json.dumps(result, ensure_ascii=True, indent=4))
# delete model if low on GPU resources
# import gc; gc.collect(); torch.cuda.empty_cache(); del model

# 2. Align whisper output
model_a, metadata = whisperx.load_align_model(
    language_code=result["language"], device=device
)
result = whisperx.align(
    result["segments"], model_a, metadata, audio, device, return_char_alignments=False
)

for i in result["segments"]:
    print("\n", i)  # before alignment
# print(result["segments"])  # after alignment
