"""
AUTONOMOUS SEARCH AND RESCUE DRONE SYSTEM
Educational Version - Extensive Comments for Learning

MAIN AUTHOR: [Your Name]
PROJECT: College Competition - Autonomous SAR Drone
DATE: [Current Date]

MODULE BREAKDOWN:
1. MAIN CONTROLLER - Program flow and state management
2. DRONE COMMUNICATION - Tello SDK commands and status
3. VISION PROCESSING - Camera and object detection
4. CONTROLLER INPUT - PS5 joystick and button handling
5. AUTONOMOUS LOGIC - Search patterns and tracking
6. MEDIA MANAGEMENT - Screenshot and recording system
7. PROFILE SYSTEM - Search mission configurations

LEARNING GOALS:
- Understand drone programming fundamentals
- Learn computer vision integration
- Master game controller input handling
- Implement state machines for autonomy
- Practice professional Python coding
"""

# =============================================================================
# MODULE 1: IMPORT AND INITIALIZATION
# =============================================================================
"""
WHY THESE IMPORTS?
- djitellopy: Official Tello drone SDK for Python
- ultralytics: YOLO (You Only Look Once) object detection
- OpenCV: Computer vision for video processing
- PyGame: Game controller input handling
- threading: Run multiple tasks simultaneously
- os/datetime: File management and timestamps
"""

from djitellopy import Tello
from ultralytics import YOLO
import cv2
import pygame
import time
import threading
import os
from datetime import datetime

# =============================================================================
# MODULE 2: GLOBAL CONSTANTS AND CONFIGURATION
# =============================================================================
"""
CONSTANTS EXPLANATION:
- Constants (UPPER_CASE) should never change during program execution
- This makes code more readable and maintainable
- Configuration in one place makes debugging easier
"""

# PS5 Controller Button Mapping
# Each number corresponds to a physical button on your PS5 controller
PS5_BUTTONS = {
    'X': 0,  # Bottom button - Usually for takeoff/action
    'CIRCLE': 1,  # Right button - Usually for cancel/land
    'SQUARE': 2,  # Left button - Usually for emergency stop
    'TRIANGLE': 3,  # Top button - Usually for profile change
    'L1': 4,  # Left bumper - Usually for recording
    'R1': 5,  # Right bumper - Usually for screenshots
    'L2': 6,  # Left trigger (button press)
    'R2': 7,  # Right trigger (button press)
    'SHARE': 8,  # Small left button - Toggle detection
    'OPTIONS': 9,  # Small right button - Not used
    'PS': 10,  # PlayStation button - Quit program
    'L3': 11,  # Left stick click
    'R3': 12,  # Right stick click
}

# Directory paths for organizing saved media
MEDIA_DIRECTORIES = {
    'photos': 'sar_photos',
    'videos': 'sar_videos',
    'profiles': 'profiles'
}

# =============================================================================
# MODULE 3: DRONE CONTROL CLASS
# =============================================================================
"""
DRONE CONTROL CONCEPTS:
- RC (Radio Control) commands: left_right, forward_back, up_down, yaw
- Yaw = rotation (left/right turning)
- Pitch = forward/backward movement
- Roll = left/right movement
- Throttle = up/down movement
"""


class SARDroneController:
    """
    MAIN DRONE CONTROLLER CLASS
    Purpose: Manage all drone operations and state
    Learning: Object-oriented programming, state management
    """

    def __init__(self):
        """
        INITIALIZATION - Setting up all components
        Why separate initialization? So we can restart components if they fail
        """
        print("🚀 Initializing SAR Drone System...")

        # Drone hardware components
        self.tello = Tello()
        self.model = YOLO('yolov8n.pt')  # Pre-trained object detection model

        # Controller state - Tracks what buttons are pressed
        self.controller_state = {
            # Movement controls (-100 to 100 values)
            'left_right': 0,  # Left/right movement
            'forward_back': 0,  # Forward/backward movement
            'up_down': 0,  # Up/down movement
            'yaw': 0,  # Rotation (turning)

            # Command flags (True when button pressed)
            'takeoff': False,
            'land': False,
            'emergency': False,
            'take_photo': False,
            'toggle_recording': False,
            'change_profile': False,

            # System states
            'detection_enabled': True
        }

        # Mission state - Tracks current operation
        self.mission_state = {
            'flying': False,
            'recording': False,
            'photo_count': 0,
            'mission_start_time': 0
        }

        # Initialize all subsystems
        self._initialize_pygame()
        self._create_directories()
        self._connect_drone()

    def _initialize_pygame(self):
        """
        PYGAME INITIALIZATION
        Purpose: Set up PS5 controller input
        Learning: Game controller API, event handling
        """
        print("🎮 Initializing controller...")
        pygame.init()
        pygame.joystick.init()

        # Check for connected controllers
        if pygame.joystick.get_count() == 0:
            raise Exception("❌ No controller found! Connect PS5 controller.")

        # Initialize first controller found
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        print(f"✅ Controller: {self.joystick.get_name()}")

    def _create_directories(self):
        """
        FILE SYSTEM SETUP
        Purpose: Create folders for organized file storage
        Learning: File path management, OS operations
        """
        for directory in MEDIA_DIRECTORIES.values():
            os.makedirs(directory, exist_ok=True)
        print("📁 Created media directories")

    def _connect_drone(self):
        """
        DRONE CONNECTION
        Purpose: Establish connection with Tello drone
        Learning: Network communication, hardware APIs
        """
        print("📡 Connecting to Tello drone...")
        self.tello.connect()

        battery = self.tello.get_battery()
        print(f"🔋 Battery: {battery}%")

        if battery < 20:
            print("⚠️ Warning: Low battery - please charge!")

        # Start video stream
        self.tello.streamon()
        time.sleep(2)  # Wait for stream to stabilize
        print("✅ Drone connected and ready!")


# =============================================================================
# MODULE 4: CONTROLLER INPUT HANDLING
# =============================================================================
"""
CONTROLLER INPUT CONCEPTS:
- Axes: Continuous values (joystick position)
- Buttons: Discrete on/off values
- Deadzone: Ignore small joystick movements to prevent drift
- Event loop: Check for new input every frame
"""


def read_controller_input(controller):
    """
    CONTROLLER READING THREAD
    Purpose: Continuously read controller input in background
    Learning: Multithreading, real-time input processing

    WHY USE A THREAD?
    - Prevents controller reading from blocking video processing
    - Ensures responsive controls even during heavy computation
    - Standard pattern for game input handling
    """
    print("🕹️ Starting controller input thread...")

    while True:
        try:
            # Process all controller events
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    _handle_button_press(event.button, controller)

            # Read analog sticks and triggers
            _read_analog_inputs(controller)

            # Small delay to prevent CPU overload
            time.sleep(0.01)

        except Exception as e:
            print(f"🎮 Controller error: {e}")


def _handle_button_press(button_number, controller):
    """
    BUTTON PRESS HANDLER
    Purpose: Convert button numbers to actions
    Learning: Event-driven programming, state machines
    """
    print(f"🔘 Button {button_number} pressed")

    # Map button numbers to actions
    if button_number == PS5_BUTTONS['X']:
        controller.controller_state['takeoff'] = True
        print("🛫 Takeoff command!")

    elif button_number == PS5_BUTTONS['CIRCLE']:
        controller.controller_state['land'] = True
        print("🛬 Land command!")

    elif button_number == PS5_BUTTONS['SQUARE']:
        controller.controller_state['emergency'] = True
        print("🆘 Emergency stop!")

    elif button_number == PS5_BUTTONS['R1']:
        controller.controller_state['take_photo'] = True
        print("📸 Screenshot requested!")

    elif button_number == PS5_BUTTONS['L1']:
        controller.controller_state['toggle_recording'] = True
        print("🎥 Recording toggle!")

    elif button_number == PS5_BUTTONS['SHARE']:
        # Toggle detection on/off
        controller.controller_state['detection_enabled'] = not controller.controller_state['detection_enabled']
        status = "ON" if controller.controller_state['detection_enabled'] else "OFF"
        print(f"🔍 Object detection: {status}")


def _read_analog_inputs(controller):
    """
    ANALOG INPUT PROCESSING
    Purpose: Read joystick positions and apply deadzone
    Learning: Analog input filtering, control systems

    DEADZONE EXPLANATION:
    - Prevents accidental movements from joystick drift
    - Only registers intentional user input
    - 0.1 means joystick must move 10% before registering
    """
    # Read joystick axes (values from -1.0 to 1.0)
    left_x = controller.joystick.get_axis(0)  # Left stick X
    left_y = controller.joystick.get_axis(1)  # Left stick Y
    right_x = controller.joystick.get_axis(2)  # Right stick X

    # Apply deadzone (ignore small movements)
    deadzone = 0.1
    if abs(left_x) > deadzone:
        controller.controller_state['left_right'] = int(left_x * 100)
    else:
        controller.controller_state['left_right'] = 0

    if abs(left_y) > deadzone:
        controller.controller_state['forward_back'] = int(-left_y * 100)  # Inverted!
    else:
        controller.controller_state['forward_back'] = 0

    if abs(right_x) > deadzone:
        controller.controller_state['yaw'] = int(right_x * 100)
    else:
        controller.controller_state['yaw'] = 0

    # Read triggers for up/down control
    _read_trigger_inputs(controller)


def _read_trigger_inputs(controller):
    """
    TRIGGER INPUT PROCESSING
    Purpose: Convert trigger positions to up/down movement
    Learning: Analog to digital conversion, control mapping
    """
    # Triggers are also axes but work differently
    l2_axis = controller.joystick.get_axis(4)  # L2 trigger
    r2_axis = controller.joystick.get_axis(5)  # R2 trigger

    # Convert from (-1 to 1) to (0 to 100)
    l2_value = max(0, int((l2_axis + 1) * 50))
    r2_value = max(0, int((r2_axis + 1) * 50))

    # Map to up/down control
    if r2_value > 10 and l2_value <= 10:  # R2 pressed
        controller.controller_state['up_down'] = r2_value
    elif l2_value > 10 and r2_value <= 10:  # L2 pressed
        controller.controller_state['up_down'] = -l2_value
    else:  # Neither pressed significantly
        controller.controller_state['up_down'] = 0


# =============================================================================
# MODULE 5: VISION AND OBJECT DETECTION
# =============================================================================
"""
COMPUTER VISION CONCEPTS:
- Frames: Individual images from video stream
- BGR vs RGB: Different color channel orders
- YOLO: Real-time object detection neural network
- Bounding boxes: Rectangles around detected objects
"""


def process_camera_frame(drone_controller):
    """
    CAMERA FRAME PROCESSING PIPELINE
    Purpose: Get frame from drone and run object detection
    Learning: Real-time video processing, AI inference

    PROCESSING STEPS:
    1. Get raw frame from drone (BGR format)
    2. Convert to RGB for display and YOLO
    3. Run object detection if enabled
    4. Return annotated frame and detection info
    """
    # Get raw frame from drone camera
    raw_frame = drone_controller.tello.get_frame_read().frame

    if raw_frame is None:
        return None, "No frame"

    # Convert from BGR to RGB color space
    # WHY? OpenCV uses BGR, but displays and YOLO use RGB
    display_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB)

    # Object detection
    detections_info = "None"
    if drone_controller.controller_state['detection_enabled']:
        display_frame, detections_info = _run_object_detection(
            display_frame,
            drone_controller.model
        )

    return display_frame, detections_info


def _run_object_detection(frame, model):
    """
    YOLO OBJECT DETECTION
    Purpose: Identify objects in the frame using AI
    Learning: Neural network inference, computer vision

    YOLO PARAMETERS:
    - verbose=False: Don't print detection logs (keeps console clean)
    - Confidence threshold: Built into the model
    - Returns: Bounding boxes, class names, confidence scores
    """
    # Run YOLO inference on the frame
    results = model(frame, verbose=False)

    # Check if we got any results
    if len(results) == 0 or results[0] is None:
        return frame, "No detections"

    # Annotate the frame with detection boxes
    annotated_frame = results[0].plot()

    # Count and categorize detections
    detections_info = _count_detections(results[0])

    return annotated_frame, detections_info


def _count_detections(results):
    """
    DETECTION ANALYSIS
    Purpose: Count and categorize detected objects
    Learning: Data analysis, dictionary operations
    """
    if results.boxes is None:
        return "None"

    detection_counts = {}

    # Count each detected object type
    for box in results.boxes:
        class_id = int(box.cls[0])
        class_name = model.names[class_id]
        confidence = float(box.conf[0])

        # Only count confident detections
        if confidence > 0.5:
            if class_name not in detection_counts:
                detection_counts[class_name] = 0
            detection_counts[class_name] += 1

    # Format for display
    if detection_counts:
        return ", ".join([f"{k}:{v}" for k, v in detection_counts.items()])
    else:
        return "None"


# =============================================================================
# MODULE 6: MEDIA MANAGEMENT
# =============================================================================
"""
MEDIA HANDLING CONCEPTS:
- File I/O: Reading/writing files to disk
- Timestamps: Organizing files by time
- Video encoding: Compressing video data
"""


def take_screenshot(frame, drone_controller):
    """
    SCREENSHOT CAPTURE
    Purpose: Save current frame as image file
    Learning: File operations, image processing
    """
    try:
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{MEDIA_DIRECTORIES['photos']}/photo_{timestamp}.jpg"

        # Convert back to BGR for OpenCV saving
        save_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Save image file
        success = cv2.imwrite(filename, save_frame)

        if success:
            drone_controller.mission_state['photo_count'] += 1
            print(f"✅ Screenshot: {filename}")
        else:
            print("❌ Failed to save screenshot")

        return success

    except Exception as e:
        print(f"❌ Screenshot error: {e}")
        return False


# =============================================================================
# MODULE 7: MAIN PROGRAM FLOW
# =============================================================================
"""
PROGRAM FLOW CONCEPTS:
- Main loop: Continuous execution until exit
- State management: Tracking program mode
- Event handling: Responding to user input
- Resource cleanup: Properly closing connections
"""


def main():
    """
    MAIN PROGRAM ENTRY POINT
    Purpose: Coordinate all system components
    Learning: Program architecture, system integration
    """
    print("=" * 50)
    print("🤖 AUTONOMOUS SAR DRONE SYSTEM")
    print("=" * 50)

    # Initialize drone controller
    drone = SARDroneController()

    # Start controller input thread
    controller_thread = threading.Thread(
        target=read_controller_input,
        args=(drone,),
        daemon=True  # Thread will close when main program ends
    )
    controller_thread.start()

    print("\n🎮 CONTROLS:")
    print("X: Takeoff | Circle: Land | Square: Emergency")
    print("R1: Screenshot | L1: Record | Share: Toggle Detection")
    print("Left Stick: Move | Right Stick: Turn | Triggers: Up/Down")
    print("=" * 50)

    try:
        # MAIN PROGRAM LOOP
        while True:
            # Process camera frame and detection
            display_frame, detections_info = process_camera_frame(drone)

            if display_frame is not None:
                # Handle user commands
                _handle_commands(drone, display_frame, detections_info)

                # Display video feed
                cv2.imshow("SAR Drone - Live Feed", display_frame)

            # Check for exit conditions
            if _should_exit(drone):
                break

            # Small delay to control loop speed
            time.sleep(0.03)

    except Exception as e:
        print(f"❌ Program error: {e}")

    finally:
        # CLEANUP - Always run, even if error occurs
        _cleanup_resources(drone)


def _handle_commands(drone, frame, detections_info):
    """
    COMMAND PROCESSING
    Purpose: Execute user commands from controller
    Learning: State machines, command pattern
    """
    # Takeoff command
    if drone.controller_state['takeoff'] and not drone.mission_state['flying']:
        drone.tello.takeoff()
        drone.mission_state['flying'] = True
        drone.mission_state['mission_start_time'] = time.time()
        drone.controller_state['takeoff'] = False
        print("🛫 Drone airborne!")

    # Land command
    elif drone.controller_state['land'] and drone.mission_state['flying']:
        drone.tello.land()
        drone.mission_state['flying'] = False
        drone.controller_state['land'] = False
        print("🛬 Drone landed!")

    # Emergency stop
    elif drone.controller_state['emergency']:
        drone.tello.emergency()
        drone.mission_state['flying'] = False
        drone.controller_state['emergency'] = False
        print("🆘 EMERGENCY STOP!")

    # Screenshot command
    elif drone.controller_state['take_photo']:
        take_screenshot(frame, drone)
        drone.controller_state['take_photo'] = False

    # Movement control
    if drone.mission_state['flying']:
        drone.tello.send_rc_control(
            drone.controller_state['left_right'],
            drone.controller_state['forward_back'],
            drone.controller_state['up_down'],
            drone.controller_state['yaw']
        )


def _should_exit(drone):
    """
    EXIT CONDITION CHECKING
    Purpose: Determine when to end the program
    Learning: Program flow control, user interface
    """
    # PS button pressed
    if drone.joystick.get_button(PS5_BUTTONS['PS']):
        print("⏹️ PS button pressed - Exiting...")
        return True

    # 'q' key pressed (keyboard alternative)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("⌨️ Q key pressed - Exiting...")
        return True

    return False


def _cleanup_resources(drone):
    """
    RESOURCE CLEANUP
    Purpose: Properly close all connections and files
    Learning: Resource management, graceful shutdown

    WHY CLEANUP?
    - Prevents memory leaks
    - Ensures files are properly saved
    - Leaves system in good state
    """
    print("\n🧹 Cleaning up resources...")

    # Land drone if still flying
    if drone.mission_state['flying']:
        drone.tello.land()
        print("✅ Drone landed safely")

    # Stop video stream
    drone.tello.streamoff()
    print("✅ Video stream stopped")

    # Close display window
    cv2.destroyAllWindows()
    print("✅ Display windows closed")

    # Quit PyGame
    pygame.quit()
    print("✅ Controller system shut down")

    print(f"📊 Mission summary: {drone.mission_state['photo_count']} photos taken")
    print("🎯 Program completed successfully!")


# =============================================================================
# PROGRAM START
# =============================================================================
"""
PROGRAM EXECUTION:
- This block only runs if the file is executed directly
- Allows the file to be imported as a module if needed
- Standard Python practice for reusable code
"""

if __name__ == "__main__":
    main()