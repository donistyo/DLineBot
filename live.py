from app.live.live_runner import LiveRunner


def main():

    runner = LiveRunner(
        interval=10
    )

    runner.start()


if __name__ == "__main__":
    main()