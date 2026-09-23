#!/bin/bash

python3 -m piper -m en_US-lessac-medium -f greeting.wav -- "Hello Jerry! Welcome back!"

aplay greeting.wav
