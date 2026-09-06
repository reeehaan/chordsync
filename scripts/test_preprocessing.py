from pathlib import Path

from analysis.preprocessing.audio_preprocessor import (
    get_audio_metadata,
    preprocess_audio,
)


input_path = Path("storage/uploads/518fdf79-508d-4030-a24c-f3b4869fa8bf.mp3")
output_path = Path("storage/processed/abc123.wav")


print("Original:")
print(get_audio_metadata(input_path))

preprocess_audio(
    input_path=input_path,
    output_path=output_path,
)

print("\nProcessed:")
print(get_audio_metadata(output_path))
