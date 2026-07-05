class PredictionView:

    @staticmethod
    def show(prediction, last):

        print()
        print("=" * 60)
        print("LIVE PREDICTION")
        print("=" * 60)

        print(f"Time       : {last['time']}")
        print(f"Price      : {last['close']:.2f}")

        print()

        print(f"Signal     : {prediction['signal']}")
        print(f"Confidence : {prediction['confidence']:.2%}")

        print()

        print("Probability")
        print("-" * 60)

        for signal, value in prediction["probability"].items():
            print(f"{signal:<5}: {value:.2%}")