import sys
import time
import signal

sigint_count = 0

def handle_sigint(signum, frame):
    global sigint_count
    sigint_count += 1
    if sigint_count >= 2:
        print("\n[DUMMY] Exiting...")
        sys.exit(0)
    print("\n[DUMMY] Press Ctrl+C again to exit...")
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

        # Skip empty lines (e.g., from @Agent command interception)
        if not line:
            continue

        print(f"[DUMMY] You said: {line}")
        # Simulate some work
        time.sleep(0.5)
        
    except KeyboardInterrupt:
        # Should be handled by signal handler, but just in case
        pass
