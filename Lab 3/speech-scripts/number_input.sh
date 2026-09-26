#!/bin/bash

echo "Asking user for ZIP code..."

espeak "Jerry, what is your five digit zip code?"

sleep 1

echo "Recording answer..."

arecord -d 5 -f cd -c 1 -r 16000 number_answer.wav

echo "Recording complete."
echo "Transcribing answer..."

python transcribe.py number_answer.wav --model base.en
