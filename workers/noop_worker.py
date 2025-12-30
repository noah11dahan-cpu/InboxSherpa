
import time

def main() -> None:
    # no-op worker for Day 1 (keeps container alive, proves orchestration)
    while True:
        print("worker: alive")
        time.sleep(10)

if __name__ == "__main__":
    main()

