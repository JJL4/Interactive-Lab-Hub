import time
import threading
import subprocess
import sys
import re
import math

import board
from adafruit_seesaw import seesaw
from adafruit_seesaw import rotaryio
from adafruit_seesaw import digitalio


# ============================================================
# CONFIGURATION
# ============================================================

# Available study-session times.
# 1 minute is useful for quick testing/demo purposes.
STUDY_OPTIONS = [
    1,
    5,
    10,
    15,
    20,
    25,
    30,
    35,
    40,
    45,
    50,
    55,
    60
]

# Start on 30 minutes.
study_option_index = STUDY_OPTIONS.index(30)

# Break is always five real minutes.
BREAK_MINUTES = 5


# ============================================================
# STEMMA QT ROTARY ENCODER
# ============================================================

# Rotary encoder is connected through the Mini PiTFT's
# STEMMA QT connector and communicates over I2C.

i2c = board.I2C()

seesaw_device = seesaw.Seesaw(
    i2c,
    addr=0x36
)

encoder = rotaryio.IncrementalEncoder(
    seesaw_device
)

# Push button on the rotary encoder.
BUTTON_PIN = 24

seesaw_device.pin_mode(
    BUTTON_PIN,
    seesaw_device.INPUT_PULLUP
)

encoder_button = digitalio.DigitalIO(
    seesaw_device,
    BUTTON_PIN
)


# ============================================================
# PROGRAM STATE
# ============================================================

# Possible states:
#
# idle
# waiting_subject
# duration
# ready
# studying
# session_complete
# break

state = "idle"

subject = ""

end_options = [
    "5 minute break",
    "End session"
]

end_option_index = 0

timer_running = False

# Separate flag for stopping the break timer.
break_running = False

last_encoder_position = encoder.position
last_button_value = encoder_button.value

speech_lock = threading.Lock()

listener_process = None

last_transcript = ""


# ============================================================
# HELPER
# ============================================================

def get_study_minutes():
    """
    Return the currently selected study duration.
    """

    return STUDY_OPTIONS[study_option_index]


# ============================================================
# TEXT TO SPEECH
# ============================================================

def speak(text):
    """
    Print Focus Buddy's response and speak it
    through the Raspberry Pi speaker.
    """

    with speech_lock:

        print()
        print("======================================")
        print(f"Focus Buddy: {text}")
        print("======================================")
        print()

        subprocess.run([
            "espeak-ng",
            "-s",
            "155",
            text
        ])


# ============================================================
# TERMINAL DISPLAY
# ============================================================

def show_idle():

    print()
    print("======================================")
    print("            FOCUS BUDDY")
    print("======================================")
    print()
    print('Participant can say:')
    print('"Start a study session"')
    print()
    print("Wizard waits for transcription.")
    print()
    print("======================================")
    print()


def show_duration():

    minutes = get_study_minutes()

    print(
        f"\rSELECT STUDY TIME: {minutes:2d} MINUTE"
        f"{'' if minutes == 1 else 'S'}          ",
        end="",
        flush=True
    )


def show_confirmed_duration():

    minutes = get_study_minutes()

    print()
    print()
    print("======================================")
    print("          STUDY TIME SELECTED")
    print("======================================")
    print()
    print(
        f"              {minutes} MINUTE"
        f"{'' if minutes == 1 else 'S'}"
    )
    print()
    print(f"Subject: {subject}")
    print()
    print("Press the dial again to START.")
    print()
    print("======================================")
    print()


def show_end_option():

    option = end_options[end_option_index]

    print(
        f"\rSELECT OPTION: {option}                    ",
        end="",
        flush=True
    )


# ============================================================
# MICROPHONE / listen.py
# ============================================================

def microphone_listener():
    """
    Run the existing listen.py.

    The microphone transcribes what the participant says,
    while the hidden wizard decides which Focus Buddy
    response should happen.
    """

    global listener_process
    global last_transcript

    print()
    print("Starting microphone...")
    print()

    listener_process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "listen.py"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in listener_process.stdout:

        line = line.strip()

        if not line:
            continue

        # listen.py startup/status message
        if not line.startswith("["):

            print(
                f"[listen.py] {line}"
            )

            continue

        # Example:
        #
        # [1.9s speech, 0.98s to transcribe] Computer Architecture.
        #
        # Everything after the ] is the transcription.

        match = re.search(
            r"\]\s*(.+)$",
            line
        )

        if match:

            transcript = match.group(1).strip()

            last_transcript = transcript

            print()
            print("--------------------------------------")
            print("        PARTICIPANT TRANSCRIPT")
            print("--------------------------------------")
            print(transcript)
            print("--------------------------------------")
            print()

        else:

            print(
                f"[listen.py] {line}"
            )


# ============================================================
# WIZARD CONVERSATION ACTIONS
# ============================================================

def wizard_start_session():
    """
    Wizard presses 1 after hearing the participant
    ask to start a study session.
    """

    global state

    if state != "idle":

        print()
        print(
            f"Cannot start right now. Current state: {state}"
        )

        return

    state = "waiting_subject"

    speak(
        "Sure. What subject are you studying?"
    )


def wizard_subject_received():
    """
    Wizard presses 2 after the participant says
    their subject.
    """

    global state
    global subject

    if state != "waiting_subject":

        print()
        print(
            "Focus Buddy is not currently waiting "
            "for a subject."
        )

        return

    print()

    print(
        f'Last microphone transcription: "{last_transcript}"'
    )

    typed_subject = input(
        "Wizard - enter subject "
        "(or press ENTER to use transcript): "
    ).strip()

    if typed_subject:

        subject = typed_subject

    elif last_transcript:

        subject = last_transcript.rstrip(".!?")

    else:

        subject = "your subject"

    state = "duration"

    speak(
        f"Got it. {subject}. "
        "Turn the dial to choose how long "
        "you want to study. "
        "Press the dial to confirm."
    )

    show_duration()


def repeat_prompt():
    """
    Wizard can repeat the appropriate prompt
    if the participant looks confused.
    """

    if state == "idle":

        speak(
            "When you are ready, say start a study session."
        )

    elif state == "waiting_subject":

        speak(
            "What subject are you studying?"
        )

    elif state == "duration":

        speak(
            "Turn the dial to choose how long "
            "you want to study. "
            "Press the dial to confirm."
        )

        show_duration()

    elif state == "ready":

        minutes = get_study_minutes()

        speak(
            f"You selected {minutes} minutes. "
            "Press the dial when you are ready to start."
        )

    elif state == "studying":

        print()
        print(
            "Study session is currently running."
        )

    elif state == "session_complete":

        speak(
            "Turn the dial to choose a five minute break "
            "or end the session. "
            "Press the dial to confirm."
        )

        show_end_option()

    elif state == "break":

        speak(
            "Your five minute break is currently running."
        )


# ============================================================
# ROTARY ENCODER ROTATION
# ============================================================

def rotate_clockwise():

    global study_option_index
    global end_option_index

    # Study time selection
    if state == "duration":

        study_option_index += 1

        if study_option_index >= len(STUDY_OPTIONS):
            study_option_index = len(STUDY_OPTIONS) - 1

        show_duration()


    # Break / End selection
    elif state == "session_complete":

        end_option_index += 1

        if end_option_index >= len(end_options):
            end_option_index = 0

        show_end_option()


def rotate_counterclockwise():

    global study_option_index
    global end_option_index

    # Study time selection
    if state == "duration":

        study_option_index -= 1

        if study_option_index < 0:
            study_option_index = 0

        show_duration()


    # Break / End selection
    elif state == "session_complete":

        end_option_index -= 1

        if end_option_index < 0:
            end_option_index = len(end_options) - 1

        show_end_option()


# ============================================================
# ROTARY ENCODER BUTTON
# ============================================================

def encoder_pressed():

    if state == "duration":

        confirm_duration()

    elif state == "ready":

        start_study_session()

    elif state == "session_complete":

        choose_end_option()

    else:

        print()
        print(
            f"[Encoder ignored. Current state: {state}]"
        )


def confirm_duration():

    global state

    state = "ready"

    minutes = get_study_minutes()

    show_confirmed_duration()

    speak(
        f"You selected {minutes} minute"
        f"{'' if minutes == 1 else 's'} "
        f"for {subject}. "
        "Press the dial again when you are ready to start."
    )

    show_confirmed_duration()


# ============================================================
# STUDY TIMER
# ============================================================

def start_study_session():

    global state

    if state != "ready":
        return

    state = "studying"

    minutes = get_study_minutes()

    print()
    print("======================================")
    print("         STUDY SESSION STARTED")
    print("======================================")
    print()
    print(f"Subject: {subject}")
    print(
        f"Selected time: {minutes} minute"
        f"{'' if minutes == 1 else 's'}"
    )
    print()
    print("======================================")
    print()

    speak(
        f"Starting your {minutes} minute"
        f"{'' if minutes == 1 else 's'} "
        f"{subject} study session now. "
        "Good luck!"
    )

    timer_thread = threading.Thread(
        target=study_timer,
        daemon=True
    )

    timer_thread.start()


def study_timer():
    """
    Count down the actual amount of selected time.
    """

    global timer_running

    timer_running = True

    minutes = get_study_minutes()

    total_seconds = minutes * 60

    end_time = (
        time.monotonic()
        + total_seconds
    )

    while timer_running:

        remaining = (
            end_time
            - time.monotonic()
        )

        if remaining <= 0:
            break

        seconds_remaining = math.ceil(
            remaining
        )

        minutes_left = (
            seconds_remaining // 60
        )

        seconds_left = (
            seconds_remaining % 60
        )

        print(
            f"\rTIME REMAINING: "
            f"{minutes_left:02d}:"
            f"{seconds_left:02d}       ",
            end="",
            flush=True
        )

        time.sleep(0.2)

    print()

    if timer_running:

        study_session_finished()


def study_session_finished():

    global state
    global timer_running
    global end_option_index

    timer_running = False

    state = "session_complete"

    end_option_index = 0

    print()
    print("======================================")
    print("          SESSION COMPLETE")
    print("======================================")
    print()

    speak(
        "Your study session is complete. "
        "Turn the dial to choose a five minute break "
        "or end the session. "
        "Press the dial to confirm."
    )

    show_end_option()


# ============================================================
# FORCE STUDY TIMER TO FINISH
# ============================================================

def force_finish():
    """
    Hidden wizard shortcut for skipping the remaining
    study-session timer.
    """

    global timer_running

    if state != "studying":

        print()
        print(
            "There is no active study session."
        )

        return

    timer_running = False

    print()
    print()
    print("[WIZARD SKIPPED REMAINING STUDY TIME]")

    study_session_finished()


# ============================================================
# BREAK / END SESSION
# ============================================================

def choose_end_option():

    selected = end_options[
        end_option_index
    ]

    print()
    print()
    print(
        f"SELECTED: {selected}"
    )
    print()

    if selected == "5 minute break":

        start_break()

    else:

        end_session()


def start_break():
    """
    Start the real five-minute break timer.
    """

    global state
    global break_running

    state = "break"
    break_running = True

    print()
    print("======================================")
    print("          BREAK STARTED")
    print("======================================")
    print()
    print(
        f"Break time: {BREAK_MINUTES} minutes"
    )
    print()
    print(
        "Wizard can press B to skip the break."
    )
    print()
    print("======================================")
    print()

    speak(
        "Okay. Starting your five minute break. "
        "I will let you know when it is over."
    )

    break_thread = threading.Thread(
        target=break_timer,
        daemon=True
    )

    break_thread.start()


def break_timer():
    """
    Count down the real five-minute break.

    break_running can be set to False by the wizard
    to stop the timer early.
    """

    global break_running

    total_seconds = (
        BREAK_MINUTES * 60
    )

    end_time = (
        time.monotonic()
        + total_seconds
    )

    while break_running:

        remaining = (
            end_time
            - time.monotonic()
        )

        if remaining <= 0:
            break

        seconds_remaining = math.ceil(
            remaining
        )

        minutes_left = (
            seconds_remaining // 60
        )

        seconds_left = (
            seconds_remaining % 60
        )

        print(
            f"\rBREAK REMAINING: "
            f"{minutes_left:02d}:"
            f"{seconds_left:02d}       ",
            end="",
            flush=True
        )

        time.sleep(0.2)

    print()

    # If the timer reached zero normally,
    # finish the break here.
    #
    # If the wizard skipped it, skip_break()
    # handles break_finished() instead.

    if break_running:

        break_running = False

        break_finished()


def skip_break():
    """
    Hidden Wizard-of-Oz shortcut.

    Immediately stop the current five-minute break
    and continue as though the break finished normally.
    """

    global break_running

    if state != "break":

        print()
        print(
            "There is no active break to skip."
        )

        return

    break_running = False

    print()
    print()
    print("======================================")
    print("         WIZARD SKIPPED BREAK")
    print("======================================")
    print()

    break_finished()


def break_finished():
    """
    Called when the break either finishes normally
    or is skipped by the hidden wizard.
    """

    global state
    global break_running

    break_running = False

    print()
    print("======================================")
    print("            BREAK OVER")
    print("======================================")
    print()

    speak(
        "Your break is over. "
        "When you are ready, "
        "say start a study session."
    )

    state = "idle"

    show_idle()


def end_session():

    global state
    global timer_running
    global break_running

    timer_running = False
    break_running = False

    state = "idle"

    print()
    print("======================================")
    print("          SESSION ENDED")
    print("======================================")
    print()

    speak(
        "Study session complete. "
        "Nice work. Focus Buddy out!"
    )

    show_idle()


# ============================================================
# ROTARY ENCODER MONITOR
# ============================================================

def monitor_encoder():

    global last_encoder_position
    global last_button_value

    while True:

        # Rotation
        current_position = (
            encoder.position
        )

        if (
            current_position
            != last_encoder_position
        ):

            difference = (
                current_position
                - last_encoder_position
            )

            if difference > 0:

                rotate_clockwise()

            else:

                rotate_counterclockwise()

            last_encoder_position = (
                current_position
            )


        # Push button
        current_button_value = (
            encoder_button.value
        )

        # True = not pressed
        # False = pressed

        if (
            last_button_value
            and not current_button_value
        ):

            encoder_pressed()

        last_button_value = (
            current_button_value
        )

        time.sleep(0.01)


# ============================================================
# WIZARD CONTROLLER
# ============================================================

def show_wizard_menu():

    print()
    print("--------------------------------------")
    print("      HIDDEN WIZARD CONTROLLER")
    print("--------------------------------------")
    print("[1] User asked to start study session")
    print("[2] User answered with their subject")
    print("[R] Repeat current Focus Buddy prompt")
    print("[F] Skip remaining STUDY timer")
    print("[B] Skip current 5-minute BREAK")
    print("[S] Show current system state")
    print("[L] Show last microphone transcript")
    print("[Q] Quit")
    print("--------------------------------------")


def show_state():

    print()
    print("--------------------------------------")
    print("            SYSTEM STATE")
    print("--------------------------------------")
    print(f"State: {state}")
    print(f"Subject: {subject}")
    print(
        f"Selected study time: "
        f"{get_study_minutes()} minutes"
    )
    print(
        f"End option: "
        f"{end_options[end_option_index]}"
    )
    print(
        f"Study timer running: {timer_running}"
    )
    print(
        f"Break timer running: {break_running}"
    )
    print("--------------------------------------")


# ============================================================
# MAIN
# ============================================================

def main():

    global listener_process

    print()
    print("======================================")
    print("        FOCUS BUDDY STARTING")
    print("======================================")
    print()

    # Start encoder monitoring.
    encoder_thread = threading.Thread(
        target=monitor_encoder,
        daemon=True
    )

    encoder_thread.start()


    # Start microphone transcription.
    microphone_thread = threading.Thread(
        target=microphone_listener,
        daemon=True
    )

    microphone_thread.start()


    show_idle()


    try:

        while True:

            show_wizard_menu()

            command = input(
                "\nWizard command: "
            ).strip().lower()


            # Participant asked to start
            if command == "1":

                wizard_start_session()


            # Participant gave subject
            elif command == "2":

                wizard_subject_received()


            # Repeat current prompt
            elif command == "r":

                repeat_prompt()


            # Skip study timer
            elif command == "f":

                force_finish()


            # Skip break timer
            elif command == "b":

                skip_break()


            # Show state
            elif command == "s":

                show_state()


            # Show last transcription
            elif command == "l":

                print()
                print(
                    f'Last transcript: "{last_transcript}"'
                )


            # Quit
            elif command == "q":

                print()
                print("Stopping Focus Buddy...")

                timer_running = False
                break_running = False

                if listener_process is not None:

                    listener_process.terminate()

                print("Goodbye.")

                break


            else:

                print()
                print(
                    "Unknown wizard command."
                )


    except KeyboardInterrupt:

        print()
        print()
        print("Stopping Focus Buddy...")

        if listener_process is not None:

            listener_process.terminate()

        print("Goodbye.")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
