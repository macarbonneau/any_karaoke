#  Any Karaoke
```
conda create -n anykaraoke python=3.9
conda activate anykaraoke
conda install -c conda-forge ffmpeg
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install git+https://github.com/m-bain/whisperx.git
```
Then pip install this repo


