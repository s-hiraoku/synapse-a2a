import sys
import time
import signal

def handle_sigint(signum, frame):
    print("\n[DUMMY] Caught SIGINT! Resetting input...")
    sys.stdout.flush()

signal.signal(signal.SIGINT, handle_sigint)

print("Starting Dummy Agent...")
print("Type 'exit' to quit.")

while True:
    try:
        sys.stdout.write("> ")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:
            break
        
        line = line.strip()
        if line == 'exit':
            break
            
        print(f"[DUMMY] You said: {line}")
        # Simulate some work
        time.sleep(0.5)
        
    except KeyboardInterrupt:
        # Should be handled by signal handler, but just in case
        pass
